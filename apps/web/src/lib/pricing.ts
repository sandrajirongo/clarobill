// Pricing tier logic — client-safe (no Stripe dependency).
// Thresholds match the /pricing page exactly.

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
    priceCents: 999,
    priceDisplay: '$9.99',
  },
  {
    label: 'The Standard Fix',
    range: '$101 – $1,000',
    minSavings: 101,
    maxSavings: 1000,
    priceCents: 4999,
    priceDisplay: '$49.99',
  },
  {
    label: 'The Heavy Hitter',
    range: '$1,000+',
    minSavings: 1001,
    maxSavings: Infinity,
    priceCents: 9999,
    priceDisplay: '$99.99',
  },
];

export function getPriceTier(savingsDollars: number): PricingTier {
  const match = PRICING_TIERS.find(
    (t) => savingsDollars >= t.minSavings && savingsDollars <= t.maxSavings
  );
  return match ?? PRICING_TIERS[0]!;
}
