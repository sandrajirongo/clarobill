import { NextResponse } from 'next/server';
import { getAuthenticatedUser, createSupabaseServerClient, createSupabaseServiceClient } from '@/lib/supabase/server';
import { stripe, REPORT_PRICE_CENTS } from '@/lib/stripe';
import type { ApiErrorResponse } from '@clarobill/shared';

const REFERRAL_DISCOUNT_CENTS = 500; // $5.00

// POST /api/stripe/checkout
// Creates a Stripe Checkout Session for purchasing a bill report.
// Applies a $5 referral discount if the user signed up via a referral link.
export async function POST(
  request: Request
): Promise<NextResponse<{ checkoutUrl: string } | ApiErrorResponse>> {
  const user = await getAuthenticatedUser();
  if (!user) {
    return NextResponse.json(
      { error: { code: 'UNAUTHORIZED', detail: 'Authentication required.' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 401 }
    );
  }

  const { billId } = await request.json() as { billId: string };

  const supabase = await createSupabaseServerClient();
  const { data: bill } = await supabase
    .from('bills')
    .select('id, status, file_name')
    .eq('id', billId)
    .single();

  if (!bill || bill.status !== 'complete') {
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Bill not ready for purchase.', step: 'checkout' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 400 }
    );
  }

  // Check for a pending referral discount — one-time use per referred user
  const service = createSupabaseServiceClient();
  const { data: pendingReferral } = await service
    .from('referrals')
    .select('id, referrer_user_id')
    .eq('referred_user_id', user.id)
    .eq('status', 'pending')
    .maybeSingle();

  const discountCents = pendingReferral ? REFERRAL_DISCOUNT_CENTS : 0;
  const finalAmountCents = Math.max(0, REPORT_PRICE_CENTS - discountCents);

  const origin = request.headers.get('origin') ?? 'http://localhost:3000';

  // Beta mode: skip Stripe, grant free access, and trigger report generation.
  if (process.env.BETA_MODE === 'true') {
    await supabase.from('payments').upsert(
      {
        user_id: user.id,
        bill_id: billId,
        stripe_session_id: `beta_${billId}`,
        amount_cents: 0,
        currency: 'usd',
        status: 'complete',
      },
      { onConflict: 'stripe_session_id' }
    );

    const engineUrl = process.env.ENGINE_URL ?? 'http://localhost:8000';
    const reportRes = await fetch(`${engineUrl}/api/v1/bills/${billId}/report`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_email: user.email, user_id: user.id }),
    });
    if (!reportRes.ok) {
      console.error('[beta-checkout] Report generation failed for bill %s, status %d', billId, reportRes.status);
    }

    return NextResponse.json({ checkoutUrl: `${origin}/dashboard/bills/${billId}?payment=success` });
  }

  const discountLabel = discountCents > 0
    ? ` (includes $${(discountCents / 100).toFixed(2)} referral discount)`
    : '';

  const session = await stripe.checkout.sessions.create({
    mode: 'payment',
    line_items: [
      {
        price_data: {
          currency: 'usd',
          unit_amount: finalAmountCents,
          product_data: {
            name: 'Clarobill Full Report',
            description: `Detailed analysis and dispute letter for: ${bill.file_name}${discountLabel}`,
          },
        },
        quantity: 1,
      },
    ],
    metadata: {
      bill_id: billId,
      user_id: user.id,
      referral_id: pendingReferral?.id ?? '',
      referrer_user_id: pendingReferral?.referrer_user_id ?? '',
    },
    customer_email: user.email,
    success_url: `${origin}/dashboard/bills/${billId}?payment=success`,
    cancel_url: `${origin}/dashboard/bills/${billId}?payment=cancelled`,
  });

  if (!session.url) {
    return NextResponse.json(
      { error: { code: 'PAYMENT_FAILED', detail: 'Failed to create checkout session.', stripeError: 'no_url' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 500 }
    );
  }

  await supabase.from('payments').insert({
    user_id: user.id,
    bill_id: billId,
    stripe_session_id: session.id,
    amount_cents: finalAmountCents,
    currency: 'usd',
    status: 'pending',
  });

  return NextResponse.json({ checkoutUrl: session.url });
}
