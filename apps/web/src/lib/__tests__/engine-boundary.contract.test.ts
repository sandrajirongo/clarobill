// Engine→web boundary contract test (web side).
//
// Reads the fixture written by
// apps/engine/tests/services/test_billing_error_fixture_export.py and parses
// it with the shared Zod schema. If the engine's BillingError shape drifts
// from what Zod expects, EITHER:
//   - the engine pytest fails (fixture regenerated, didn't match disk), OR
//   - this vitest fails (fixture regenerated, parse rejects new shape).
//
// Both halves move together — the fixture file is the single source of
// truth for the wire shape. CI runs both sides; either side catching drift
// is enough to block a deployment.

import { describe, expect, it } from 'vitest';
import {
  BillingErrorCodeSchema,
  BillingErrorSchema,
} from '@clarobill/shared';
import fixture from './fixtures/engine-billing-error.json';

describe('engine→web BillingError boundary contract', () => {
  it('every fixture entry parses with the shared Zod schema', () => {
    expect(() => BillingErrorSchema.array().parse(fixture)).not.toThrow();
  });

  it('fixture covers every BillingErrorCode the engine knows about', () => {
    const fixtureCodes = new Set((fixture as Array<{ code: string }>).map((f) => f.code));
    const schemaCodes = new Set(BillingErrorCodeSchema.options);
    expect(fixtureCodes).toEqual(schemaCodes);
  });

  it('parsed output is camelCase end-to-end (no snake leakage)', () => {
    const parsed = BillingErrorSchema.array().parse(fixture);
    for (const error of parsed) {
      expect(error).toHaveProperty('affectedLineItemIds');
      expect(error).toHaveProperty('estimatedOvercharge');
      expect(error).toHaveProperty('medicareBenchmarkRate');
      expect(error).not.toHaveProperty('affected_line_item_ids');
      expect(error).not.toHaveProperty('estimated_overcharge');
      expect(error).not.toHaveProperty('medicare_benchmark_rate');
    }
  });
});
