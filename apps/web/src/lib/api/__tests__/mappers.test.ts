import { describe, expect, it } from 'vitest';
import { mapBillRow, mapLineItemRow, mapAnalysisRow } from '../mappers';

describe('mapBillRow', () => {
  const baseRow = {
    id: 'b-1',
    user_id: 'u-1',
    file_name: 'bill.pdf',
    display_name: null,
    file_path: 'u-1/b-1/bill.pdf',
    file_size: 12345,
    mime_type: 'application/pdf',
    status: 'complete',
    hospital_npi: null,
    hospital_name: null,
    profile_member_id: null,
    payer_name: null,
    plan_name: null,
    confirmed_at: null,
    created_at: '2026-05-04T00:00:00Z',
    updated_at: '2026-05-04T00:00:00Z',
  };

  it('translates snake_case columns to camelCase fields', () => {
    const out = mapBillRow(baseRow);
    expect(out.userId).toBe('u-1');
    expect(out.fileName).toBe('bill.pdf');
    expect(out.filePath).toBe('u-1/b-1/bill.pdf');
    expect(out.mimeType).toBe('application/pdf');
    expect(out.hospitalNpi).toBeNull();
    expect(out.profileMemberId).toBeNull();
    expect(out.createdAt).toBe('2026-05-04T00:00:00Z');
  });

  it('handles plan_type when present', () => {
    const out = mapBillRow({ ...baseRow, plan_type: 'commercial' });
    expect(out.planType).toBe('commercial');
  });

  it('defaults plan_type to null when omitted', () => {
    expect(mapBillRow(baseRow).planType).toBeNull();
  });
});

describe('mapLineItemRow', () => {
  it('coerces numeric strings from JSONB to numbers', () => {
    const out = mapLineItemRow({
      id: 'li-1',
      bill_id: 'b-1',
      cpt_code: '99214',
      description: 'Office visit',
      service_date: '2026-01-15',
      quantity: 1,
      unit_charge: '350.00', // Supabase numeric returns as string
      total_charge: '350.00',
      modifier: null,
      diagnosis_pointers: ['A'],
    });
    expect(out.unitCharge).toBe(350);
    expect(out.totalCharge).toBe(350);
    expect(typeof out.unitCharge).toBe('number');
  });

  it('preserves diagnosis_pointers array shape', () => {
    const out = mapLineItemRow({
      id: 'li-1',
      bill_id: 'b-1',
      cpt_code: '99214',
      description: '',
      service_date: '2026-01-15',
      quantity: 1,
      unit_charge: 0,
      total_charge: 0,
      modifier: null,
      diagnosis_pointers: ['A', 'B', 'C'],
    });
    expect(out.diagnosisPointers).toEqual(['A', 'B', 'C']);
  });
});

describe('mapAnalysisRow', () => {
  it('translates fields and leaves errors un-parsed for the boundary parser', () => {
    const errors = [{ legacy: 'shape' }];
    const out = mapAnalysisRow({
      id: 'a-1',
      bill_id: 'b-1',
      errors,
      total_charges: '1000',
      estimated_fair_value: '800',
      total_potential_savings: '200',
      ai_summary: 'summary',
      dispute_letter_url: null,
      report_url: null,
      created_at: '2026-05-04T00:00:00Z',
    });
    expect(out.billId).toBe('b-1');
    expect(out.totalCharges).toBe(1000);
    expect(out.estimatedFairValue).toBe(800);
    // errors is intentionally left as `unknown` so the caller routes through
    // parseBillingErrors (snake/camel migration tolerance).
    expect(out.errors).toBe(errors);
  });
});
