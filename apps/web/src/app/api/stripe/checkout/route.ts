import { NextResponse } from 'next/server';
import { getAuthenticatedUser, createSupabaseServerClient } from '@/lib/supabase/server';
import { stripe, REPORT_PRICE_CENTS } from '@/lib/stripe';
import type { ApiErrorResponse } from '@clarobill/shared';

// POST /api/stripe/checkout
// Creates a Stripe Checkout Session for purchasing a bill report.
// Returns the session URL which the client redirects to.
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

  // Confirm the bill exists, belongs to this user, and analysis is complete
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

  const origin = request.headers.get('origin') ?? 'http://localhost:3000';

  // Beta mode: skip Stripe and grant free access by inserting a completed payment record.
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
    return NextResponse.json({ checkoutUrl: `${origin}/dashboard/bills/${billId}?payment=success` });
  }

  const session = await stripe.checkout.sessions.create({
    mode: 'payment',
    line_items: [
      {
        price_data: {
          currency: 'usd',
          unit_amount: REPORT_PRICE_CENTS,
          product_data: {
            name: 'Clarobill Full Report',
            description: `Detailed analysis and dispute letter for: ${bill.file_name}`,
          },
        },
        quantity: 1,
      },
    ],
    metadata: {
      bill_id: billId,
      user_id: user.id,
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

  // Record the pending payment
  await supabase.from('payments').insert({
    user_id: user.id,
    bill_id: billId,
    stripe_session_id: session.id,
    amount_cents: REPORT_PRICE_CENTS,
    currency: 'usd',
    status: 'pending',
  });

  return NextResponse.json({ checkoutUrl: session.url });
}
