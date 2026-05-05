import { describe, expect, it } from 'vitest';
import {
  AnalysisUrlsResponseSchema,
  CheckoutResponseSchema,
  ErrorResponseSchema,
  InsuranceCardExtractionSchema,
  MemberCreatedResponseSchema,
  MembersListResponseSchema,
  PlanCreatedResponseSchema,
  StatusResponseSchema,
  parseBillingErrors,
  parseJsonResponse,
  safeCountErrors,
} from '../parsers';

describe('parseBillingErrors', () => {
  it('parses camelCase array (current contract)', () => {
    const errors = parseBillingErrors([
      {
        code: 'PRICE_OUTLIER',
        severity: 'critical',
        affectedLineItemIds: ['li-1'],
        description: 'd',
        estimatedOvercharge: 100,
        benchmarkRate: null,
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
        benchmark_rate: null,
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

describe('M12 response schemas', () => {
  it('StatusResponseSchema accepts any status string', () => {
    expect(StatusResponseSchema.parse({ status: 'complete' })).toEqual({ status: 'complete' });
  });

  it('StatusResponseSchema rejects missing status', () => {
    expect(() => StatusResponseSchema.parse({})).toThrow();
  });

  it('CheckoutResponseSchema requires a URL', () => {
    expect(() => CheckoutResponseSchema.parse({ checkoutUrl: 'not-a-url' })).toThrow();
    expect(() => CheckoutResponseSchema.parse({ checkoutUrl: 'https://stripe.com/x' })).not.toThrow();
  });

  it('ErrorResponseSchema requires a detail message', () => {
    expect(() => ErrorResponseSchema.parse({ error: {} })).toThrow();
    expect(ErrorResponseSchema.parse({ error: { detail: 'why' } })).toEqual({
      error: { detail: 'why' },
    });
  });

  it('MemberCreatedResponseSchema picks out id', () => {
    expect(MemberCreatedResponseSchema.parse({ member: { id: 'abc' } })).toEqual({
      member: { id: 'abc' },
    });
  });

  it('PlanCreatedResponseSchema picks out id', () => {
    expect(PlanCreatedResponseSchema.parse({ plan: { id: 'xyz' } })).toEqual({
      plan: { id: 'xyz' },
    });
  });

  it('AnalysisUrlsResponseSchema accepts partial analysis', () => {
    expect(AnalysisUrlsResponseSchema.parse({ analysis: { reportUrl: '/x' } }).analysis?.reportUrl).toBe('/x');
    expect(AnalysisUrlsResponseSchema.parse({}).analysis).toBeUndefined();
  });

  it('MembersListResponseSchema validates wrapper but not inner element shape', () => {
    expect(
      MembersListResponseSchema.parse({ members: [{ anything: 'goes' }] }).members,
    ).toHaveLength(1);
    expect(() => MembersListResponseSchema.parse({})).toThrow();
  });

  it('InsuranceCardExtractionSchema requires every field', () => {
    expect(() => InsuranceCardExtractionSchema.parse({ payerName: 'Aetna' })).toThrow();
    const valid = {
      payerName: 'Aetna', planName: 'PPO', memberId: 'M1', groupId: 'G1', planType: 'commercial',
      rxBin: null, rxPcn: null, rxGroup: null, confident: true, note: null,
    };
    expect(InsuranceCardExtractionSchema.parse(valid)).toEqual(valid);
  });
});

describe('parseJsonResponse', () => {
  it('parses a JSON body through a schema', async () => {
    const fakeRes = { json: async () => ({ status: 'ok' }) } as Response;
    expect(await parseJsonResponse(fakeRes, StatusResponseSchema)).toEqual({ status: 'ok' });
  });

  it('throws on shape mismatch', async () => {
    const fakeRes = { json: async () => ({ wrong: 'field' }) } as Response;
    await expect(parseJsonResponse(fakeRes, StatusResponseSchema)).rejects.toThrow();
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
