/**
 * Tests for the insurance constants/lookup helpers shared across the
 * verification flow and the profile members panel.
 */

import { describe, expect, it } from 'vitest';
import {
  MEDICAID_MCOS_BY_STATE,
  MEDICAID_MCOS_NATIONAL,
  MEDICAID_PLAN_TYPES,
  MEDICAID_STATE_BRANDS,
  MEDICARE_PLAN_TYPES,
  TRICARE_PLAN_TYPES,
  getMedicaidBrandName,
} from '@/lib/utils/insurance-constants';

describe('getMedicaidBrandName', () => {
  it('returns generic "Medicaid" when state is null', () => {
    expect(getMedicaidBrandName(null)).toBe('Medicaid');
  });

  it('returns generic "Medicaid" when state is undefined', () => {
    expect(getMedicaidBrandName(undefined)).toBe('Medicaid');
  });

  it('returns generic "Medicaid" when state is empty string', () => {
    expect(getMedicaidBrandName('')).toBe('Medicaid');
  });

  it('returns the branded name for California (Medi-Cal)', () => {
    expect(getMedicaidBrandName('California')).toBe('Medi-Cal');
  });

  it('returns the branded name for Tennessee (TennCare)', () => {
    expect(getMedicaidBrandName('Tennessee')).toBe('TennCare');
  });

  it('returns the branded name for Massachusetts (MassHealth)', () => {
    expect(getMedicaidBrandName('Massachusetts')).toBe('MassHealth');
  });

  it('falls back to "[State] Medicaid" for unbranded states', () => {
    // Iowa has no entry in MEDICAID_STATE_BRANDS.
    expect(getMedicaidBrandName('Iowa')).toBe('Iowa Medicaid');
  });

  it('is case-sensitive — "california" is not a branded match', () => {
    // The state names in the lookup table are properly capitalized; lowercase
    // input falls through. Documents the case-sensitivity behavior.
    expect(getMedicaidBrandName('california')).toBe('california Medicaid');
  });
});

describe('plan-type lookups', () => {
  it('MEDICAID_PLAN_TYPES has the four canonical CMS programme categories', () => {
    const values = MEDICAID_PLAN_TYPES.map((t) => t.value);
    expect(values).toContain('Fee-for-Service Medicaid');
    expect(values).toContain('Medicaid Managed Care');
    expect(values).toContain('CHIP');
    expect(values).toContain('Dual Eligible (Medicare + Medicaid)');
  });

  it('every plan-type entry has both value and label', () => {
    for (const list of [MEDICAID_PLAN_TYPES, MEDICARE_PLAN_TYPES, TRICARE_PLAN_TYPES]) {
      for (const entry of list) {
        expect(entry.value.length).toBeGreaterThan(0);
        expect(entry.label.length).toBeGreaterThan(0);
      }
    }
  });

  it('values are unique within each list', () => {
    for (const list of [MEDICAID_PLAN_TYPES, MEDICARE_PLAN_TYPES, TRICARE_PLAN_TYPES]) {
      const values = list.map((t) => t.value);
      expect(new Set(values).size).toBe(values.length);
    }
  });
});

describe('MCO lookups', () => {
  it('MEDICAID_MCOS_NATIONAL is non-empty (used as fallback)', () => {
    expect(MEDICAID_MCOS_NATIONAL.length).toBeGreaterThan(0);
  });

  it('major Medicaid Managed Care states have populated MCO arrays', () => {
    // Each of these states has multi-million-enrollee Medicaid programs;
    // the autocomplete must offer something for them.
    for (const state of ['California', 'Texas', 'New York', 'Florida']) {
      expect(MEDICAID_MCOS_BY_STATE[state]).toBeDefined();
      expect(MEDICAID_MCOS_BY_STATE[state]!.length).toBeGreaterThan(0);
    }
  });

  it('every MCO entry is a non-empty string', () => {
    for (const list of Object.values(MEDICAID_MCOS_BY_STATE)) {
      for (const mco of list) {
        expect(typeof mco).toBe('string');
        expect(mco.length).toBeGreaterThan(0);
      }
    }
    for (const mco of MEDICAID_MCOS_NATIONAL) {
      expect(mco.length).toBeGreaterThan(0);
    }
  });
});

describe('MEDICAID_STATE_BRANDS contract', () => {
  it('California maps to "Medi-Cal" (the official Department of Health Care Services brand)', () => {
    // Hard-coded sanity check — if somebody renames this to "California Medicaid",
    // every California UI surface starts using the wrong brand name.
    expect(MEDICAID_STATE_BRANDS['California']).toBe('Medi-Cal');
  });
});
