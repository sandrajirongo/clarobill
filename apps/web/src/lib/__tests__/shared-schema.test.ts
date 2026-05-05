import { describe, expect, it } from 'vitest';
import {
  AnalysisResultSchema,
  BillingErrorSchema,
  BillSchema,
  LineItemSchema,
} from '@clarobill/shared';

describe('BillingErrorSchema', () => {
  const validCamel = {
    code: 'PRICE_OUTLIER',
    severity: 'critical',
    affectedLineItemIds: ['li-1', 'li-2'],
    description: 'CPT 99214 billed at 3x Medicare rate',
    estimatedOvercharge: 250.5,
    medicareBenchmarkRate: 50.25,
  };

  it('parses canonical camelCase input unchanged', () => {
    expect(BillingErrorSchema.parse(validCamel)).toEqual(validCamel);
  });

  it('parses legacy snake_case input by coalescing into camelCase', () => {
    const snake = {
      code: 'PRICE_OUTLIER',
      severity: 'critical',
      affected_line_item_ids: ['li-1', 'li-2'],
      description: 'CPT 99214 billed at 3x Medicare rate',
      estimated_overcharge: 250.5,
      medicare_benchmark_rate: 50.25,
    };
    expect(BillingErrorSchema.parse(snake)).toEqual(validCamel);
  });

  it('parses mixed camel + snake (camel wins on collision)', () => {
    const mixed = {
      code: 'PRICE_OUTLIER',
      severity: 'critical',
      affectedLineItemIds: ['camel'],
      affected_line_item_ids: ['snake'],
      description: 'd',
      estimatedOvercharge: 1,
      medicareBenchmarkRate: null,
    };
    expect(BillingErrorSchema.parse(mixed).affectedLineItemIds).toEqual(['camel']);
  });

  it('throws on garbage shape (missing required fields)', () => {
    expect(() => BillingErrorSchema.parse({ code: 'PRICE_OUTLIER' })).toThrow();
  });

  it('throws on unknown BillingErrorCode', () => {
    expect(() => BillingErrorSchema.parse({ ...validCamel, code: 'NOT_A_CODE' })).toThrow();
  });

  it('rejects negative estimatedOvercharge', () => {
    expect(() => BillingErrorSchema.parse({ ...validCamel, estimatedOvercharge: -1 })).toThrow();
  });

  it('accepts null medicareBenchmarkRate', () => {
    const out = BillingErrorSchema.parse({ ...validCamel, medicareBenchmarkRate: null });
    expect(out.medicareBenchmarkRate).toBeNull();
  });
});

describe('LineItemSchema', () => {
  const validCamel = {
    id: 'li-1',
    billId: 'bill-1',
    cptCode: '99214',
    description: 'Office visit',
    serviceDate: '2026-01-15',
    quantity: 1,
    unitCharge: 350,
    totalCharge: 350,
    modifier: null,
    diagnosisPointers: ['A', 'B'],
  };

  it('parses camelCase unchanged', () => {
    expect(LineItemSchema.parse(validCamel)).toEqual(validCamel);
  });

  it('coalesces snake_case keys', () => {
    const snake = {
      id: 'li-1',
      bill_id: 'bill-1',
      cpt_code: '99214',
      description: 'Office visit',
      service_date: '2026-01-15',
      quantity: 1,
      unit_charge: 350,
      total_charge: 350,
      modifier: null,
      diagnosis_pointers: ['A', 'B'],
    };
    expect(LineItemSchema.parse(snake)).toEqual(validCamel);
  });

  it('rejects quantity less than 1', () => {
    expect(() => LineItemSchema.parse({ ...validCamel, quantity: 0 })).toThrow();
  });
});

describe('BillSchema', () => {
  const validCamel = {
    id: 'b-1',
    userId: 'u-1',
    displayName: null,
    fileName: 'bill.pdf',
    filePath: 'u-1/b-1/bill.pdf',
    fileSize: 12345,
    mimeType: 'application/pdf',
    status: 'complete',
    hospitalNpi: null,
    hospitalName: null,
    hospitalCity: null,
    hospitalState: null,
    hospitalZip: null,
    profileMemberId: null,
    payerName: null,
    planName: null,
    planType: null,
    confirmedAt: null,
    createdAt: '2026-05-04T00:00:00Z',
    updatedAt: '2026-05-04T00:00:00Z',
  };

  it('parses camelCase unchanged', () => {
    expect(BillSchema.parse(validCamel)).toEqual(validCamel);
  });

  it('rejects unknown PlanType', () => {
    expect(() => BillSchema.parse({ ...validCamel, planType: 'platinum' })).toThrow();
  });
});

describe('AnalysisResultSchema', () => {
  it('parses snake_case end-to-end including nested errors', () => {
    const snake = {
      id: 'a-1',
      bill_id: 'b-1',
      errors: [
        {
          code: 'NCCI_UNBUNDLING',
          severity: 'critical',
          affected_line_item_ids: ['li-1'],
          description: 'd',
          estimated_overcharge: 100,
          medicare_benchmark_rate: null,
        },
      ],
      total_charges: 1000,
      estimated_fair_value: 800,
      total_potential_savings: 200,
      ai_summary: 'summary',
      dispute_letter_url: null,
      report_url: null,
      created_at: '2026-05-04T00:00:00Z',
    };
    const parsed = AnalysisResultSchema.parse(snake);
    expect(parsed.billId).toBe('b-1');
    expect(parsed.errors[0]?.affectedLineItemIds).toEqual(['li-1']);
    expect(parsed.errors[0]?.estimatedOvercharge).toBe(100);
    expect(parsed.totalCharges).toBe(1000);
  });
});
