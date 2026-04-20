# ClaroBill Pricing Model

## Overview

ClaroBill uses **performance-based pricing**. Every bill analysis is free to run. Users only pay when the AI finds real errors worth disputing. The fee tier is assigned automatically based on the total dollar value of savings found — users always keep significantly more than they pay.

---

## Pricing Tiers

| Tier | Savings Found | Fee | User Keeps |
|---|---|---|---|
| Clean Bill | $0 – $20 | Free | Everything |
| Small Win | $21 – $100 | $9.99 | ≥ $11 |
| The Standard Fix | $101 – $1,000 | $49.99 | ≥ $51 |
| The Heavy Hitter | $1,000+ | $99.99 | ≥ $900 |

**Key principle:** No errors found = no charge. Guaranteed.

---

## How Tier Assignment Works

1. User uploads bill (free, no payment required)
2. Engine benchmarks every line item against Medicare fee schedules and NCCI billing rules
3. `total_potential_savings` is calculated and stored in `analysis_results`
4. When user clicks "Get Full Report", the checkout API reads `total_potential_savings` from the DB, calls `getPriceTier()`, and uses that price
5. The tier is **server-calculated** — the client is never trusted for price

### Code location

- Tier logic: `apps/web/src/lib/pricing.ts` — `PRICING_TIERS` array + `getPriceTier(savingsDollars)` function
- Checkout: `apps/web/src/app/api/stripe/checkout/route.ts` — queries analysis, calls `getPriceTier`
- Paywall UI: `apps/web/src/components/bill-results-view.tsx` — imports `getPriceTier`, shows tier label + price dynamically
- Marketing page: `apps/web/src/app/pricing/page.tsx` — static display, hardcoded tier descriptions

---

## Referral Discount

Users who signed up via a referral link receive a **$5 discount** on their first paid tier fee. The discount is:

- Applied server-side by checking `referrals` table for a `pending` referral linked to the user
- Capped at the tier price (cannot make the final price negative)
- One-time use — marked as `converted` after the referral settles

Formula: `final_price = max(0, tier_price - $5)`

---

## Beta Mode

During beta testing, `BETA_MODE = true` in `checkout/route.ts` bypasses Stripe entirely:

- Payment record is written with `amount_cents: 0`
- Report generation is triggered immediately (no webhook needed)
- User is redirected to `?payment=success` without going through Stripe

**To activate live payments:** Set `BETA_MODE = false` and ensure Stripe live keys are set in the production environment (`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY`).

---

## What Users Get in a Paid Tier

Every paid tier (including Small Win) unlocks:

1. Full itemized error report (all findings, not just the teaser)
2. Specific billing codes violated with plain-English explanations
3. Ready-to-send dispute letter tailored to their bill
4. PDF download of both documents
5. Email delivery with PDFs attached

---

## Stripe Configuration

| Environment | Variable | Notes |
|---|---|---|
| Both | `STRIPE_SECRET_KEY` | Server-only |
| Both | `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` | Client-safe |
| Both | `STRIPE_WEBHOOK_SECRET` | Webhook signature verification |

Stripe product/price are created dynamically per session (`price_data` inline, not pre-created Stripe prices). This allows the tier amount to vary per checkout without pre-configuring prices in the Stripe dashboard.

Webhook endpoint: `POST /api/stripe/webhook` — must be registered in Stripe Dashboard pointing to the production domain.

---

## Competitive Positioning

| Option | Cost | Speed | Dispute letter |
|---|---|---|---|
| ClaroBill | $0–$99.99 flat | Minutes | Included |
| Medical billing advocate | 25–35% of savings | Days to weeks | Yes |
| DIY | Free | Hours | Write your own |
| Do nothing | Full bill | — | None |

A $500 error with a billing advocate would cost $125–$175 in fees. ClaroBill charges $49.99.
