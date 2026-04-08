import { headers } from 'next/headers';
import { NextResponse } from 'next/server';
import type Stripe from 'stripe';
import { stripe } from '@/lib/stripe';
import { createSupabaseServerClient, createSupabaseServiceClient } from '@/lib/supabase/server';

// Stripe requires the raw body for signature verification — don't parse as JSON first
export const runtime = 'nodejs';

// POST /api/stripe/webhook
// Receives Stripe events and updates payment/report access accordingly.
// Signature verification is mandatory — any unverified payload is rejected.
export async function POST(request: Request): Promise<NextResponse> {
  const body = await request.text();
  const headersList = await headers();
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

  const supabase = await createSupabaseServerClient();

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
  const engineUrl = process.env.ENGINE_URL ?? 'http://localhost:8000';
  const reportResponse = await fetch(`${engineUrl}/api/v1/bills/${billId}/report`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_email: session.customer_email, user_id: userId }),
  });

  if (!reportResponse.ok) {
    // Log but don't throw — payment is confirmed, report generation can be retried
    console.error('[webhook] Report generation failed for bill %s, status %d', billId, reportResponse.status);
  } else {
    console.info('[webhook] Report generated and emailed for bill %s', billId);
  }

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

  // Mark the referral as converted
  await service
    .from('referrals')
    .update({ status: 'converted' })
    .eq('id', referralId)
    .eq('status', 'pending'); // idempotent — only update if still pending

  // Add $5 credit to the referrer's balance
  await service.rpc('increment_referral_credits', {
    p_user_id: referrerUserId,
    p_amount: REFERRAL_REWARD_CENTS,
  });
}
