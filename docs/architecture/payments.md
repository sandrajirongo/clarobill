# Payments Architecture

**Provider:** Stripe  
**API version:** 2024-06-20  
**Mode:** Checkout Sessions (`mode: 'payment'`) — one-time payments only, no subscriptions

---

## Pricing Model

Pricing is performance-based. Users pay only when errors worth disputing are found. The fee is a function of the total potential savings discovered:

| Tier | Savings found | Price |
|---|---|---|
| Clean Bill | $0 – $20 | Free |
| Small Win | $21 – $100 | $14.99 |
| Standard Fix | $101 – $500 | $79.99 |
| Major Fix | $501 – $1,500 | $129.99 |
| Heavy Hitter | $1,500+ | $199.99 |

The tier is calculated server-side from `analysis_results.total_potential_savings` via `lib/pricing.ts::getPriceTier()`. The client sends only a `billId` — it never proposes a price.

---

## Checkout Flow

```
Frontend (bill results page)
  → POST /api/stripe/checkout { billId }
    → server reads analysis_results.total_potential_savings
    → calls getPriceTier() to determine amount_cents
    → checks for pending referral discount (-$5, capped at tier price)
    → calls stripe.checkout.sessions.create()
    → inserts payments row { status: 'pending', stripe_session_id: cs_... }
    → returns { checkoutUrl }
  → browser redirects to Stripe-hosted checkout page

User completes payment on Stripe
  → Stripe sends checkout.session.completed to POST /api/stripe/webhook
    → signature verified via stripe.webhooks.constructEvent()
    → payments row updated to { status: 'complete' }
    → POST ENGINE_URL/api/v1/bills/{billId}/report (generate PDF + email)
    → Loops transactional email sent (receipt)
    → Loops event 'payment_completed' sent (triggers follow-up workflows)
    → referral settled if applicable
  → browser lands on /dashboard/bills/{billId}?payment=success
```

---

## Idempotency Guards

**Double-charge prevention:**  
The checkout route checks for an existing `payments` row with `status IN ('pending', 'complete')` AND `stripe_session_id LIKE 'cs_%'` before creating a new session. If one exists, the user is redirected to the success URL without a new Stripe session.

The `cs_%` filter is deliberate: it excludes synthetic beta-era sessions (`beta_*`, `free_*`) so users who had beta records still see the real Stripe checkout after GA.

**Webhook idempotency:**  
The webhook handler checks `existing?.status === 'complete'` before processing. If the session was already completed (Stripe occasionally delivers events more than once), the handler returns early.

**Free tier:**  
When `finalAmountCents === 0` (savings ≤ $20 or referral discount covers full price), the checkout route inserts a synthetic `payments` row with `stripe_session_id: 'free_${billId}'` and redirects directly to the success URL — no Stripe session is created.

---

## Referral Discounts

The referral discount ($5) is applied at checkout time:

1. Checkout route queries `referrals` for a `pending` row with `referred_user_id = auth.uid()`.
2. If found, `discountCents = min(500, tier.priceCents)` is subtracted from the session amount.
3. `referral_id` and `referrer_user_id` are stored in `session.metadata`.
4. On `checkout.session.completed`, `settleReferral()` is called:
   - Marks `referrals.status = 'converted'` (idempotent — skips if already converted)
   - Calls `increment_referral_credits` RPC (+500 cents to `referral_codes.credits`)
   - Sends referral credit email via SendGrid to the referrer

**Referrer reward:** $5 credit for every referred user who purchases. Credits auto-apply on the next purchase (enforced in the checkout route's discount calculation by checking `referral_codes.credits` balance).

---

## Database Records

| Table | Written by | When |
|---|---|---|
| `payments` INSERT (`pending`) | Checkout route | Stripe session created |
| `payments` UPDATE (`complete`) | Webhook handler | `checkout.session.completed` |
| `referrals` UPDATE (`converted`) | Webhook `settleReferral()` | Payment confirmed |
| `referral_codes` credits increment | Webhook `settleReferral()` | Referral settled |

The `payments.stripe_session_id` column has a UNIQUE constraint — two inserts with the same session ID will fail. This enforces at-most-one payment record per Stripe session.

---

## Stripe Configuration

| Setting | Value |
|---|---|
| Payment methods | `card`, `link` (Stripe Link for one-tap) |
| Customer email | Passed as `customer_email` so Stripe pre-fills it |
| Success URL | `/dashboard/bills/{billId}?payment=success` |
| Cancel URL | `/dashboard/bills/{billId}?payment=cancelled` |
| Metadata | `bill_id`, `user_id`, `referral_id`, `referrer_user_id` |

**Webhook endpoint:** Register `https://clarobill.com/api/stripe/webhook` in the Stripe dashboard. Only `checkout.session.completed` is handled; all other event types return 200 immediately to prevent Stripe retries.

---

## Environment Variables

| Variable | Where used |
|---|---|
| `STRIPE_SECRET_KEY` | `lib/stripe.ts` — Stripe SDK client |
| `STRIPE_WEBHOOK_SECRET` | Webhook route signature verification |

---

*Last reviewed: 2026-05-25*
