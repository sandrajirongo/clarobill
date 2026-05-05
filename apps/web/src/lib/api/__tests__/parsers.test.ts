import { describe, expect, it } from 'vitest';
import { parseBillingErrors, safeCountErrors } from '../parsers';

describe('parseBillingErrors', () => {
  it('parses camelCase array (current contract)', () => {
    const errors = parseBillingErrors([
      {
        code: 'PRICE_OUTLIER',
        severity: 'critical',
        affectedLineItemIds: ['li-1'],
        description: 'd',
        estimatedOvercharge: 100,
        medicareBenchmarkRate: null,
      },
    ]);
    expect(errors).toHaveLength(1);
    expect(errors[0]?.estimatedOvercharge).toBe(100);
  });

  it('parses legacy snake_case array (pre-backfill rows)', () => {
    const errors = parseBillingErrors([
      {
        code: 'PRICE_OUTLIER',
        severity: 'critical',
        affected_line_item_ids: ['li-1'],
        description: 'd',
        estimated_overcharge: 100,
        medicare_benchmark_rate: null,
      },
    ]);
    expect(errors[0]?.affectedLineItemIds).toEqual(['li-1']);
    expect(errors[0]?.estimatedOvercharge).toBe(100);
  });

  it('throws on garbage shape', () => {
    expect(() => parseBillingErrors([{ random: 'junk' }])).toThrow();
  });

  it('throws on non-array input', () => {
    expect(() => parseBillingErrors('not an array')).toThrow();
    expect(() => parseBillingErrors(null)).toThrow();
  });

  it('returns [] for empty array', () => {
    expect(parseBillingErrors([])).toEqual([]);
  });
});

describe('safeCountErrors', () => {
  it('counts arrays', () => {
    expect(safeCountErrors([])).toBe(0);
    expect(safeCountErrors([1, 2, 3])).toBe(3);
  });

  it('returns 0 for non-arrays without throwing', () => {
    expect(safeCountErrors(null)).toBe(0);
    expect(safeCountErrors(undefined)).toBe(0);
    expect(safeCountErrors('not array')).toBe(0);
    expect(safeCountErrors({})).toBe(0);
  });
});
