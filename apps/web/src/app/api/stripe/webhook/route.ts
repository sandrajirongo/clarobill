import { headers } from 'next/headers';
import { NextResponse } from 'next/server';
import type Stripe from 'stripe';
import { stripe } from '@/lib/stripe';
import { createSupabaseServiceClient } from '@/lib/supabase/server';
import { getCloudRunIdToken } from '@/lib/gcp-auth';
import { sendLoopsEvent, sendLoopsTransactional } from '@/lib/loops';
import { captureServerEvent } from '@/lib/analytics-server';

// Stripe requires the raw body for signature verification — don't parse as JSON first
export const runtime = 'nodejs';

// POST /api/stripe/webhook
// Receives Stripe events and updates payment/report access accordingly.
// Signature verification is mandatory — any unverified payload is rejected.
export async function POST(request: Request): Promise<NextResponse> {
  const body = await request.text();
  const headersList = headers();
  const stripeSignature = headersList.get('stripe-signature');

  if (!stripeSignature) {
    return NextResponse.json({ error: 'Missing stripe-signature header' }, { status: 400 });
  }

  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(
      body,
      stripeSignature,
      process.env.STRIPE_WEBHOOK_SECRET!
    );
  } catch (err) {
    // Signature mismatch — reject with 400, not 500, so Stripe doesn't retry
    const message = err instanceof Error ? err.message : 'Unknown error';
    console.error('[webhook] Signature verification failed:', message);
    return NextResponse.json({ error: 'Invalid signature' }, { status: 400 });
  }

  if (event.type === 'checkout.session.completed') {
    await handleCheckoutCompleted(event.data.object as Stripe.Checkout.Session);
  }

  // Return 200 for all other events so Stripe doesn't retry them
  return NextResponse.json({ received: true });
}

async function handleCheckoutCompleted(session: Stripe.Checkout.Session): Promise<void> {
  const billId = session.metadata?.['bill_id'];
  const userId = session.metadata?.['user_id'];

  if (!billId || !userId) {
    console.error('[webhook] checkout.session.completed missing metadata', { sessionId: session.id });
    return;
  }

  // Stripe calls this endpoint directly — no user session exists, so we must use
  // the service client. The anon client would have auth.uid() = null and all
  // payments queries would be silently blocked by RLS.
  const supabase = createSupabaseServiceClient();

  // Idempotency check — don't process the same session twice
  const { data: existing } = await supabase
    .from('payments')
    .select('id, status')
    .eq('stripe_session_id', session.id)
    .single();

  if (existing?.status === 'complete') {
    return;
  }

  await supabase
    .from('payments')
    .update({
      status: 'complete',
      stripe_payment_intent: session.payment_intent as string | null,
    })
    .eq('stripe_session_id', session.id);

  // Trigger PDF report generation and email delivery via the engine
  void captureServerEvent(userId, 'report_generation_requested', { bill_id: billId });
  const engineUrl = process.env.ENGINE_URL ?? 'http://localhost:8000';
  const idToken = await getCloudRunIdToken(engineUrl);
  const reportResponse = await fetch(`${engineUrl}/api/v1/bills/${billId}/report`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(idToken ? { 'Authorization': `Bearer ${idToken}` } : {}),
      ...(process.env.ENGINE_API_KEY ? { 'X-Engine-Api-Key': process.env.ENGINE_API_KEY } : {}),
    },
    body: JSON.stringify({ user_email: session.customer_email, user_id: userId }),
  });

  if (!reportResponse.ok) {
    console.error('[webhook] Report generation failed for bill %s, status %d', billId, reportResponse.status);
  } else {
    console.info('[webhook] Report generated and emailed for bill %s', billId);
    void captureServerEvent(userId, 'report_generated', { bill_id: billId });
  }

  // Fetch user email (needed for Loops transactional email)
  const { data: profile } = await supabase
    .from('user_profiles')
    .select('email')
    .eq('id', userId)
    .single();

  const userEmail = profile?.email ?? session.customer_email ?? null;

  // Track payment in PostHog and send Loops payment-confirmed email in parallel.
  // sendLoopsTransactional is a no-op when LOOPS_PAYMENT_EMAIL_ID is not configured.
  await Promise.all([
    captureServerEvent(userId, 'payment_completed', {
      bill_id: billId,
      amount_cents: session.amount_total ?? 0,
      stripe_session_id: session.id,
    }),
    userEmail
      ? Promise.all([
          // Immediate receipt — transactional email with amount/currency data variables
          sendLoopsTransactional(
            process.env.LOOPS_PAYMENT_EMAIL_ID ?? '',
            userEmail,
            {
              amount_dollars: ((session.amount_total ?? 0) / 100).toFixed(2),
              currency: (session.currency ?? 'usd').toUpperCase(),
            }
          ),
          // payment_completed event triggers the 1-day and 30-day follow-up workflows
          sendLoopsEvent(userEmail, 'payment_completed', {
            bill_id: billId,
            stripe_session_id: session.id,
          }),
        ])
      : Promise.resolve(),
  ]);

  // Convert referral discount and credit the referrer
  const referralId = session.metadata?.['referral_id'];
  const referrerUserId = session.metadata?.['referrer_user_id'];
  if (referralId && referrerUserId) {
    await settleReferral(referralId, referrerUserId);
  }
}

const REFERRAL_REWARD_CENTS = 500; // $5 credit for the referrer

async function settleReferral(referralId: string, referrerUserId: string): Promise<void> {
  const service = createSupabaseServiceClient();

  // Mark the referral as converted — idempotent, only updates if still pending
  const { data: updated } = await service
    .from('referrals')
    .update({ status: 'converted' })
    .eq('id', referralId)
    .eq('status', 'pending')
    .select('id')
    .maybeSingle();

  // Already settled — don't double-credit or double-email
  if (!updated) return;

  // Add $5 credit to the referrer's balance
  await service.rpc('increment_referral_credits', {
    p_user_id: referrerUserId,
    p_amount: REFERRAL_REWARD_CENTS,
  });

  // Look up the referrer's email and notify them of their new credit
  const { data: { user: referrer } } = await service.auth.admin.getUserById(referrerUserId);
  if (referrer?.email) {
    // Count total converted referrals to personalise the message
    const { count } = await service
      .from('referrals')
      .select('id', { count: 'exact', head: true })
      .eq('referrer_user_id', referrerUserId)
      .eq('status', 'converted');

    await sendReferralCreditEmail(referrer.email, REFERRAL_REWARD_CENTS, count ?? 1);
  }
}

async function sendReferralCreditEmail(
  toEmail: string,
  creditsCents: number,
  totalConverted: number,
): Promise<void> {
  const apiKey = process.env.SENDGRID_API_KEY;
  const fromEmail = process.env.SENDGRID_FROM_EMAIL ?? 'noreply@clarobill.com';

  if (!apiKey) {
    console.warn('[webhook] SENDGRID_API_KEY not set — referral credit email not sent');
    return;
  }

  const dollars = (creditsCents / 100).toFixed(0);
  const totalEarned = (totalConverted * creditsCents / 100).toFixed(0);

  const response = await fetch('https://api.sendgrid.com/v3/mail/send', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      personalizations: [{ to: [{ email: toEmail }] }],
      from: { email: fromEmail, name: 'ClaroBill' },
      subject: `You earned $${dollars}. Someone just used your referral link`,
      content: [{ type: 'text/html', value: referralCreditEmailHtml(dollars, totalConverted, totalEarned) }],
    }),
  });

  if (!response.ok) {
    console.error('[webhook] Referral credit email failed, status=%d', response.status);
  } else {
    console.info('[webhook] Referral credit email sent to referrer');
  }
}

function referralCreditEmailHtml(dollars: string, totalConverted: number, totalEarned: string): string {
  const friendWord = totalConverted === 1 ? 'friend' : 'friends';
  return `
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#1a2e18">
      <div style="background:#2D4A2A;padding:24px 32px;margin-bottom:32px;border-radius:0 0 8px 8px">
        <h1 style="color:#C8F060;font-size:20px;margin:0;font-style:italic">ClaroBill</h1>
      </div>
      <div style="padding:0 32px 32px">
        <h2 style="font-size:24px;margin:0 0 12px">You earned $${dollars}! 🎉</h2>
        <p style="color:#4a6048;line-height:1.6">
          Someone just purchased their first ClaroBill report using your referral link.
          We've added <strong>$${dollars} in credit</strong> to your account.
        </p>
        <div style="background:#F7F5EF;border-radius:12px;padding:20px 24px;margin:24px 0;border:1px solid #e8e4da">
          <p style="margin:0 0 4px;font-size:13px;color:#6b7c6a;text-transform:uppercase;letter-spacing:.05em">Total earned</p>
          <p style="margin:0;font-size:28px;font-weight:700;color:#2D4A2A">$${totalEarned}</p>
          <p style="margin:4px 0 0;font-size:13px;color:#6b7c6a">${totalConverted} ${friendWord} referred</p>
        </div>
        <p style="color:#4a6048;line-height:1.6">
          Your credit will be automatically applied the next time you purchase a report.
          Keep sharing your link to earn more!
        </p>
        <a href="https://clarobill.com/dashboard"
           style="display:inline-block;background:#2D4A2A;color:#C8F060;padding:14px 28px;border-radius:99px;text-decoration:none;font-weight:700;margin-top:8px">
          View my dashboard →
        </a>
      </div>
      <div style="padding:0 32px 24px;border-top:1px solid #eee;margin-top:16px">
        <p style="font-size:11px;color:#999;line-height:1.6">
          ClaroBill · Credits have no cash value and apply to ClaroBill report purchases only.
        </p>
      </div>
    </div>`;
}
