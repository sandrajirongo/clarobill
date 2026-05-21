import { NextResponse } from 'next/server';
import { getAuthenticatedUser, createSupabaseServerClient, createSupabaseServiceClient } from '@/lib/supabase/server';
import { stripe, getPriceTier } from '@/lib/stripe';
import type { ApiErrorResponse } from '@clarobill/shared';
import { captureServerEvent } from '@/lib/analytics-server';

const REFERRAL_DISCOUNT_CENTS = 500; // $5.00 — applies to any paid tier

// POST /api/stripe/checkout
// Creates a Stripe Checkout Session for purchasing a bill report.
// Tier is determined server-side from the bill's analysis savings total.
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

  // Determine pricing tier from total savings found in analysis.
  // Server-calculated — never trust the client for price.
  const { data: analysisResult } = await supabase
    .from('analysis_results')
    .select('total_potential_savings')
    .eq('bill_id', billId)
    .single();

  const savingsDollars = Number(analysisResult?.total_potential_savings ?? 0);
  const tier = getPriceTier(savingsDollars);

  // Referral discount — one-time use per referred user, capped at the tier price
  const service = createSupabaseServiceClient();
  const { data: pendingReferral } = await service
    .from('referrals')
    .select('id, referrer_user_id')
    .eq('referred_user_id', user.id)
    .eq('status', 'pending')
    .maybeSingle();

  const discountCents = pendingReferral
    ? Math.min(REFERRAL_DISCOUNT_CENTS, tier.priceCents)
    : 0;
  const finalAmountCents = Math.max(0, tier.priceCents - discountCents);

  const origin = request.headers.get('origin') ?? 'http://localhost:3000';

  // Free tier: savings ≤ $20 — paywall should not show in this case, but guard here
  // to prevent a $0 Stripe session from being created.
  if (finalAmountCents === 0) {
    await supabase.from('payments').upsert(
      {
        user_id: user.id,
        bill_id: billId,
        stripe_session_id: `free_${billId}`,
        amount_cents: 0,
        currency: 'usd',
        status: 'complete',
      },
      { onConflict: 'stripe_session_id' }
    );
    return NextResponse.json({ checkoutUrl: `${origin}/dashboard/bills/${billId}?payment=success` });
  }

  // Guard against double-charging: only match real Stripe sessions (cs_*).
  // Beta-era synthetic sessions (beta_*, free_*) are intentionally excluded
  // so users with beta records get routed through real Stripe checkout.
  const { data: existingPayment } = await service
    .from('payments')
    .select('id')
    .eq('bill_id', billId)
    .eq('user_id', user.id)
    .in('status', ['pending', 'complete'])
    .like('stripe_session_id', 'cs_%')
    .maybeSingle();
  if (existingPayment) {
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
            name: `ClaroBill Report: ${tier.label}`,
            description: `${tier.range} in potential savings found on: ${bill.file_name}${discountLabel}`,
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

  void captureServerEvent(user.id, 'checkout_session_created', {
    bill_id: billId,
    amount_cents: finalAmountCents,
    tier_label: tier.label,
    has_referral_discount: discountCents > 0,
  });

  return NextResponse.json({ checkoutUrl: session.url });
}
