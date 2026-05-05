// Centralised mappers from Supabase row shape (snake_case columns) to the
// camelCase API/UI shape declared in @clarobill/shared.
//
// Pre-M11, the same hand-rolled mapping was duplicated character-for-character
// across `app/api/bills/[billId]/analysis/route.ts` and `app/dashboard/bills/[billId]/page.tsx`.
// Any time we added a column to the bills/line_items/analysis_results tables,
// we had to remember to update both. The duplication was a Phase 6 audit
// finding (M11). Single source of truth here.
//
// IMPORTANT: do NOT use these mappers as a substitute for parsing engine
// output. The mappers translate Supabase column names → camelCase only;
// they do NOT validate the BillingError JSONB shape (which has its own
// snake/camel migration window — see `parseBillingErrors` in `parsers.ts`).
// Callers that consume the `errors` field still go through `parseBillingErrors`.

import type { Bill, LineItem, AnalysisResult, BillStatus, PlanType } from '@clarobill/shared';

// MimeType is declared as an inline literal on Bill in @clarobill/shared
// rather than a named export. Re-derive the same shape here so the cast
// stays narrow.
type _MimeType = Bill['mimeType'];

// Loose row type for what Supabase hands back. We don't use `any`; instead the
// caller has already gone through Supabase's `.select()` typing, so each
// individual field has the type the schema declares.
type BillRow = {
  id: string;
  user_id: string;
  file_name: string;
  display_name: string | null;
  file_path: string;
  file_size: number;
  mime_type: string;
  status: string;
  hospital_npi: string | null;
  hospital_name: string | null;
  profile_member_id: string | null;
  payer_name: string | null;
  plan_name: string | null;
  plan_type?: string | null;
  confirmed_at: string | null;
  created_at: string;
  updated_at: string;
};

type LineItemRow = {
  id: string;
  bill_id: string;
  cpt_code: string;
  description: string;
  service_date: string;
  quantity: number;
  unit_charge: number | string;
  total_charge: number | string;
  modifier: string | null;
  diagnosis_pointers: string[];
};

type AnalysisRow = {
  id: string;
  bill_id: string;
  errors: unknown; // BillingError[] in JSONB; parsed separately by parseBillingErrors
  total_charges: number | string;
  estimated_fair_value: number | string;
  total_potential_savings: number | string;
  ai_summary: string;
  dispute_letter_url: string | null;
  report_url: string | null;
  created_at: string;
};

export function mapBillRow(row: BillRow): Bill {
  return {
    id: row.id,
    userId: row.user_id,
    displayName: row.display_name ?? null,
    fileName: row.file_name,
    filePath: row.file_path,
    fileSize: row.file_size,
    mimeType: row.mime_type as _MimeType,
    status: row.status as BillStatus,
    hospitalNpi: row.hospital_npi ?? null,
    hospitalName: row.hospital_name ?? null,
    profileMemberId: row.profile_member_id ?? null,
    payerName: row.payer_name ?? null,
    planName: row.plan_name ?? null,
    planType: (row.plan_type ?? null) as PlanType | null,
    confirmedAt: row.confirmed_at ?? null,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

export function mapLineItemRow(row: LineItemRow): LineItem {
  return {
    id: row.id,
    billId: row.bill_id,
    cptCode: row.cpt_code,
    description: row.description,
    serviceDate: row.service_date,
    quantity: row.quantity,
    unitCharge: Number(row.unit_charge),
    totalCharge: Number(row.total_charge),
    modifier: row.modifier,
    diagnosisPointers: row.diagnosis_pointers,
  };
}

export function mapAnalysisRow(row: AnalysisRow): Omit<AnalysisResult, 'errors'> & { errors: unknown } {
  // The `errors` field is left as `unknown` so callers can decide how to
  // parse — typically via `parseBillingErrors` which handles the snake/camel
  // migration window. Returning a stricter shape would force callers to
  // double-validate or hit a Zod failure on legacy rows.
  return {
    id: row.id,
    billId: row.bill_id,
    errors: row.errors,
    totalCharges: Number(row.total_charges),
    estimatedFairValue: Number(row.estimated_fair_value),
    totalPotentialSavings: Number(row.total_potential_savings),
    aiSummary: row.ai_summary,
    disputeLetterUrl: row.dispute_letter_url,
    reportUrl: row.report_url,
    createdAt: row.created_at,
  };
}
