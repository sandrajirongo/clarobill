/**
 * Pricing tier resolution — server-side trust boundary.
 *
 * The frontend never tells the engine which tier to charge — `getPriceTier`
 * is invoked server-side against the engine's verified `total_potential_savings`.
 * A bug here would charge the wrong amount, which is the worst kind of
 * silent regression: the customer sees the price on the paywall page, then
 * sees a different amount on the Stripe receipt.
 */

import { describe, expect, it } from 'vitest';
import { PRICING_TIERS, getPriceTier } from '@/lib/pricing';

describe('getPriceTier', () => {
  describe('clean bill tier ($0–$20)', () => {
    it('returns Clean Bill for $0 savings', () => {
      const tier = getPriceTier(0);
      expect(tier.label).toBe('Clean Bill');
      expect(tier.priceCents).toBe(0);
    });

    it('returns Clean Bill for boundary $20', () => {
      expect(getPriceTier(20).label).toBe('Clean Bill');
    });

    it('returns Clean Bill for fractional cents under $20', () => {
      expect(getPriceTier(19.99).label).toBe('Clean Bill');
    });
  });

  describe('boundary cuts — exact thresholds must not slip a tier', () => {
    it('$21 is Small Win, not Clean Bill', () => {
      // Off-by-one regression net: a >= vs > flip would push $20 into Small Win
      // and silently charge $14.99 to clean-bill users.
      expect(getPriceTier(21).label).toBe('Small Win');
    });

    it('$100 is the upper edge of Small Win', () => {
      expect(getPriceTier(100).label).toBe('Small Win');
    });

    it('$101 jumps to Standard Fix', () => {
      expect(getPriceTier(101).label).toBe('Standard Fix');
    });

    it('$500 is Standard Fix', () => {
      expect(getPriceTier(500).label).toBe('Standard Fix');
    });

    it('$501 jumps to Major Fix', () => {
      expect(getPriceTier(501).label).toBe('Major Fix');
    });

    it('$1500 is Major Fix', () => {
      expect(getPriceTier(1500).label).toBe('Major Fix');
    });

    it('$1501 jumps to Heavy Hitter', () => {
      expect(getPriceTier(1501).label).toBe('Heavy Hitter');
    });
  });

  describe('Heavy Hitter has no upper bound', () => {
    it('$10,000 stays in Heavy Hitter', () => {
      expect(getPriceTier(10_000).label).toBe('Heavy Hitter');
      expect(getPriceTier(10_000).priceCents).toBe(19999);
    });

    it('Number.MAX_SAFE_INTEGER stays in Heavy Hitter', () => {
      expect(getPriceTier(Number.MAX_SAFE_INTEGER).label).toBe('Heavy Hitter');
    });
  });

  describe('defensive fallback', () => {
    it('negative savings (impossible from engine, defensive only) falls back to Clean Bill', () => {
      // The engine never emits negative savings, but a malformed BillingError
      // carrying a negative estimatedOvercharge could feed in a negative sum.
      // Default to the free tier — never charge — rather than pricing wrap.
      const tier = getPriceTier(-50);
      expect(tier.priceCents).toBe(0);
      expect(tier.label).toBe('Clean Bill');
    });
  });

  describe('PRICING_TIERS contract', () => {
    it('has 5 tiers', () => {
      expect(PRICING_TIERS).toHaveLength(5);
    });

    it('every tier has matching priceDisplay derived from priceCents', () => {
      const lookup: Record<number, string> = {
        0: 'Free',
        1499: '$14.99',
        7999: '$79.99',
        12999: '$129.99',
        19999: '$199.99',
      };
      for (const tier of PRICING_TIERS) {
        expect(tier.priceDisplay).toBe(lookup[tier.priceCents]);
      }
    });

    it('tiers are non-overlapping and cover [0, ∞)', () => {
      // Sort by minSavings, then verify each tier's max+1 == next tier's min.
      const sorted = [...PRICING_TIERS].sort((a, b) => a.minSavings - b.minSavings);
      expect(sorted[0]!.minSavings).toBe(0);
      for (let i = 0; i < sorted.length - 1; i += 1) {
        expect(sorted[i + 1]!.minSavings).toBe(sorted[i]!.maxSavings + 1);
      }
      expect(sorted[sorted.length - 1]!.maxSavings).toBe(Infinity);
    });
  });
});
