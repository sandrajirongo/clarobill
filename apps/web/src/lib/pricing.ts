// Pricing tier logic — client-safe (no Stripe dependency).
// Thresholds match the /pricing page exactly.
//
// Tier model (5 tiers as of 2026-04-29):
//
//   Clean Bill     | $0–$20         | Free
//   Small Win      | $21–$100       | $14.99
//   Standard Fix   | $101–$500      | $79.99
//   Major Fix      | $501–$1,500    | $129.99
//   Heavy Hitter   | $1,500+        | $199.99
//
// Pricing is performance-based: users pay only when the audit engine finds
// real savings worth disputing. Tier fee is server-calculated from the
// engine's `total_potential_savings` value — never trusted from the client.
//
// Beta mode (until July 2, 2026 GA): every tier is gated through
// `lib/beta.isBetaMode()` which currently bypasses Stripe and unlocks every
// report at $0. See `docs/pricing.md` "Beta Timeline" for the launch plan.

export interface PricingTier {
  label: string;
  range: string;
  minSavings: number;   // dollars, inclusive
  maxSavings: number;   // dollars, inclusive (Infinity for the top tier)
  priceCents: number;
  priceDisplay: string;
}

export const PRICING_TIERS: PricingTier[] = [
  {
    label: 'Clean Bill',
    range: '$0 – $20',
    minSavings: 0,
    maxSavings: 20,
    priceCents: 0,
    priceDisplay: 'Free',
  },
  {
    label: 'Small Win',
    range: '$21 – $100',
    minSavings: 21,
    maxSavings: 100,
    priceCents: 1499,
    priceDisplay: '$14.99',
  },
  {
    label: 'Standard Fix',
    range: '$101 – $500',
    minSavings: 101,
    maxSavings: 500,
    priceCents: 7999,
    priceDisplay: '$79.99',
  },
  {
    label: 'Major Fix',
    range: '$501 – $1,500',
    minSavings: 501,
    maxSavings: 1500,
    priceCents: 12999,
    priceDisplay: '$129.99',
  },
  {
    label: 'Heavy Hitter',
    range: '$1,500+',
    minSavings: 1501,
    maxSavings: Infinity,
    priceCents: 19999,
    priceDisplay: '$199.99',
  },
];

export function getPriceTier(savingsDollars: number): PricingTier {
  const match = PRICING_TIERS.find(
    (t) => savingsDollars >= t.minSavings && savingsDollars <= t.maxSavings
  );
  return match ?? PRICING_TIERS[0]!;
}
