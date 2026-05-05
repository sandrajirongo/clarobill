# ClaroBill Pricing Model

## Overview

ClaroBill uses **performance-based pricing**. Every bill analysis is free to run. Users only pay when the AI finds real errors worth disputing. The fee tier is assigned automatically based on the total dollar value of savings found — users always keep significantly more than they pay.

---

## Pricing Tiers

| Tier | Savings Found | Fee | User Keeps |
|---|---|---|---|
| Clean Bill | $0 – $20 | Free | Everything |
| Small Win | $21 – $100 | $14.99 | ≥ $6 |
| Standard Fix | $101 – $500 | $79.99 | ≥ $21 |
| Major Fix | $501 – $1,500 | $129.99 | ≥ $371 |
| Heavy Hitter | $1,500+ | $199.99 | ≥ $1,300 |

**Key principle:** No errors found = no charge. Guaranteed.

The 5-tier structure (introduced 2026-04-29) replaces the original 4-tier model — adds the **Major Fix** tier for the $501–$1,500 band, where the previous Standard Fix tier had become too cheap for the value delivered. Tier rebranding also drops the "The" prefix for cleaner display.

---

## How Tier Assignment Works

1. User uploads bill (free, no payment required)
2. Engine benchmarks every line item against Medicare fee schedules, NCCI billing rules, and (when available) hospital MRF data
3. `total_potential_savings` is calculated and stored in `analysis_results`
4. When user clicks "Get Full Report", the checkout API reads `total_potential_savings` from the DB, calls `getPriceTier()`, and uses that price
5. The tier is **server-calculated** — the client is never trusted for price

### Code location

- Tier logic: `apps/web/src/lib/pricing.ts` — `PRICING_TIERS` array + `getPriceTier(savingsDollars)` function
- Checkout: `apps/web/src/app/api/stripe/checkout/route.ts` — queries analysis, calls `getPriceTier`
- Paywall UI: `apps/web/src/components/bill-results-view.tsx` — imports `getPriceTier`, shows tier label + price dynamically
- Marketing page: `apps/web/src/app/pricing/page.tsx` — static display, hardcoded tier descriptions
- Beta gate: `apps/web/src/lib/beta.ts` — `isBetaMode()` reads `NEXT_PUBLIC_BETA_MODE`

---

## Referral Discount

Users who signed up via a referral link receive a **$5 discount** on their first paid tier fee. The discount is:

- Applied server-side by checking `referrals` table for a `pending` referral linked to the user
- Capped at the tier price (cannot make the final price negative)
- One-time use — marked as `converted` after the referral settles

Formula: `final_price = max(0, tier_price - $5)`

---

## Beta Timeline

ClaroBill is in beta. Pricing is locked in (above) but charges are bypassed until General Availability (GA). The timeline:

### Phase 1 — Closed Beta (now → May 31, 2026)

- **Audience:** Invite-only, ~50–100 users
- **Goal:** Case studies and engine validation against real bills
- **Charging:** $0 across all tiers (`BETA_MODE = true`)
- **Marketing:** None — direct outreach only

### Phase 2 — Open Beta (June 1, 2026 → June 30 OR 200 bills, whichever comes first)

- **Audience:** Public, free signup
- **Goal:** Soft launch — collect more diverse audit data, refine UX, validate pricing tiers against real savings distribution
- **Charging:** $0 across all tiers (`BETA_MODE = true`)
- **Marketing:** Soft launch push (organic + targeted social)
- **Exit trigger:** Whichever happens first:
  - Calendar date June 30, 2026, OR
  - 200 bills processed across all users

When the 200-bill threshold hits before June 30, Sandra will explicitly trigger the GA flip — the threshold is monitored manually for now (no auto-flip; we want a human in the loop for launch readiness checks).

### Phase 3 — GA (July 2, 2026 onward)

- **`BETA_MODE` flipped to `false`** in Vercel (`NEXT_PUBLIC_BETA_MODE=false`)
- **Pricing goes live** — Stripe processes real charges per tier
- **Launch email** to the full beta list announcing GA + a small "thank you" credit for early users

### Beta-mode mechanism

`apps/web/src/lib/beta.ts` exports `isBetaMode()` which reads `NEXT_PUBLIC_BETA_MODE`. When `true`:

- `apps/web/src/app/api/stripe/checkout/route.ts` writes a payment record with `amount_cents: 0`
- Report generation is triggered immediately (no Stripe webhook needed)
- User is redirected to `?payment=success` without going through Stripe Checkout

**To activate live payments at GA:** in Vercel project settings, set `NEXT_PUBLIC_BETA_MODE=false` (or remove the env var — code defaults to beta-mode-on for safety, see comment in `beta.ts`). Confirm Stripe live keys are populated: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY`.

---

## What Users Get in a Paid Tier

Every paid tier (Small Win and above) unlocks:

1. Full itemized error report (all findings, not just the teaser)
2. Specific billing codes violated with plain-English explanations
3. Ready-to-send dispute letter tailored to their bill
4. PDF download of both documents
5. Email delivery with PDFs attached

Every tier produces the same artifacts. Higher tiers cost more because the *value* delivered (savings recovered) is higher — fee scales with outcome, not effort.

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
| ClaroBill | $0–$199.99 flat | Minutes | Included |
| Medical billing advocate | 25–35% of savings | Days to weeks | Yes |
| DIY | Free | Hours | Write your own |
| Do nothing | Full bill | — | None |

**Worked examples:**
- $100 error: advocate charges $25–$35; ClaroBill charges $14.99
- $500 error: advocate charges $125–$175; ClaroBill charges $79.99
- $1,000 error: advocate charges $250–$350; ClaroBill charges $129.99
- $2,000 error: advocate charges $500–$700; ClaroBill charges $199.99

ClaroBill is materially cheaper than a billing advocate at every savings level, especially as recovery amounts grow. The 5-tier structure means our fee scales sub-linearly with savings while advocate fees scale linearly — the bigger the error, the better our value.

---

*Last updated: 2026-04-29*
