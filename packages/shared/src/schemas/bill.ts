// Runtime-validated schemas for the engine→web boundary.
//
// These are the single source of truth for the wire shape of bill / line item /
// analysis / billing-error data. The TypeScript interfaces in `../types/bill.ts`
// remain for now and will be migrated to `z.infer<>` aliases in Phase 6.
//
// Each schema accepts BOTH camelCase (current contract) AND snake_case
// (legacy rows persisted before the engine switched to camelCase output).
// The `.preprocess()` step coalesces the two key sets so consumers always
// see camelCase regardless of which shape Supabase returned.

import { z } from 'zod';

// ─── Enums ────────────────────────────────────────────────────────────────────

export const BillStatusSchema = z.enum([
  'uploading',
  'ocr_processing',
  'analyzing',
  'complete',
  'failed',
]);

export const ErrorSeveritySchema = z.enum(['critical', 'warning', 'info']);

export const BillingErrorCodeSchema = z.enum([
  'DUPLICATE_CHARGE',
  'PRICE_OUTLIER',
  'NCCI_UNBUNDLING',
  'INVALID_CPT_CODE',
  'UPCODING',
  'MISSING_MODIFIER',
  'DATE_INCONSISTENCY',
  'NON_PAYABLE_CODE',
  'TERMINATED_CODE_BILLED',
  'ANESTHESIA_OUTLIER',
  'FACILITY_CHARGE_OUTLIER',
  'AMBULANCE_CHARGE_OUTLIER',
  'HOSPITAL_CHARGE_OUTLIER',
  'NEGOTIATED_RATE_EXCEEDED',
  'NEGOTIATED_CEILING_EXCEEDED',
  'MUE_EXCEEDED',
  'REDUNDANT_CLINICAL_PAIR',
]);

export const PlanTypeSchema = z.enum([
  'commercial',
  'medicare',
  'medicaid',
  'tricare',
  'self_pay',
]);

export const MimeTypeSchema = z.enum([
  'application/pdf',
  'image/jpeg',
  'image/png',
]);

// ─── Snake/camel coalescing ───────────────────────────────────────────────────

// Picks the camelCase value if present, falls back to the snake_case value.
// Used inside z.preprocess to migrate legacy JSONB rows transparently.
function coalesce<T extends Record<string, unknown>>(
  raw: unknown,
  pairs: Array<[camelKey: string, snakeKey: string]>,
): T {
  if (typeof raw !== 'object' || raw === null) return raw as T;
  const r = raw as Record<string, unknown>;
  const out: Record<string, unknown> = { ...r };
  for (const [camel, snake] of pairs) {
    if (out[camel] === undefined && r[snake] !== undefined) {
      out[camel] = r[snake];
    }
  }
  return out as T;
}

// ─── BillingError ─────────────────────────────────────────────────────────────

const BillingErrorBase = z.object({
  code: BillingErrorCodeSchema,
  severity: ErrorSeveritySchema,
  affectedLineItemIds: z.array(z.string()),
  description: z.string(),
  estimatedOvercharge: z.number().nonnegative(),
  medicareBenchmarkRate: z.number().nonnegative().nullable(),
});

export const BillingErrorSchema = z.preprocess(
  (raw) =>
    coalesce(raw, [
      ['affectedLineItemIds', 'affected_line_item_ids'],
      ['estimatedOvercharge', 'estimated_overcharge'],
      ['medicareBenchmarkRate', 'medicare_benchmark_rate'],
    ]),
  BillingErrorBase,
);

// Type alias intentionally NOT exported here — `BillingError` is still exported
// from `../types/bill.ts`. Phase 6 retires the interface and re-exports
// `z.infer<typeof BillingErrorSchema>` from this file.

// ─── LineItem ─────────────────────────────────────────────────────────────────

const LineItemBase = z.object({
  id: z.string(),
  billId: z.string(),
  cptCode: z.string(),
  description: z.string(),
  serviceDate: z.string(),
  quantity: z.number().int().min(1),
  unitCharge: z.number().nonnegative(),
  totalCharge: z.number().nonnegative(),
  modifier: z.string().nullable(),
  diagnosisPointers: z.array(z.string()),
});

export const LineItemSchema = z.preprocess(
  (raw) =>
    coalesce(raw, [
      ['billId', 'bill_id'],
      ['cptCode', 'cpt_code'],
      ['serviceDate', 'service_date'],
      ['unitCharge', 'unit_charge'],
      ['totalCharge', 'total_charge'],
      ['diagnosisPointers', 'diagnosis_pointers'],
    ]),
  LineItemBase,
);

// Type alias intentionally NOT exported — see note on BillingError above.

// ─── Bill ─────────────────────────────────────────────────────────────────────

const BillBase = z.object({
  id: z.string(),
  userId: z.string(),
  displayName: z.string().nullable(),
  fileName: z.string(),
  filePath: z.string(),
  fileSize: z.number().int().nonnegative(),
  mimeType: MimeTypeSchema,
  status: BillStatusSchema,
  hospitalNpi: z.string().nullable(),
  hospitalName: z.string().nullable(),
  hospitalCity: z.string().nullable(),
  hospitalState: z.string().nullable(),
  hospitalZip: z.string().nullable(),
  profileMemberId: z.string().nullable(),
  payerName: z.string().nullable(),
  planName: z.string().nullable(),
  planType: PlanTypeSchema.nullable(),
  confirmedAt: z.string().nullable(),
  createdAt: z.string(),
  updatedAt: z.string(),
});

export const BillSchema = z.preprocess(
  (raw) =>
    coalesce(raw, [
      ['userId', 'user_id'],
      ['displayName', 'display_name'],
      ['fileName', 'file_name'],
      ['filePath', 'file_path'],
      ['fileSize', 'file_size'],
      ['mimeType', 'mime_type'],
      ['hospitalNpi', 'hospital_npi'],
      ['hospitalName', 'hospital_name'],
      ['hospitalCity', 'hospital_city'],
      ['hospitalState', 'hospital_state'],
      ['hospitalZip', 'hospital_zip'],
      ['profileMemberId', 'profile_member_id'],
      ['payerName', 'payer_name'],
      ['planName', 'plan_name'],
      ['planType', 'plan_type'],
      ['confirmedAt', 'confirmed_at'],
      ['createdAt', 'created_at'],
      ['updatedAt', 'updated_at'],
    ]),
  BillBase,
);

// Type alias intentionally NOT exported — see note on BillingError above.

// ─── AnalysisResult ───────────────────────────────────────────────────────────

const AnalysisResultBase = z.object({
  id: z.string(),
  billId: z.string(),
  errors: z.array(BillingErrorSchema),
  totalCharges: z.number().nonnegative(),
  estimatedFairValue: z.number().nonnegative(),
  totalPotentialSavings: z.number().nonnegative(),
  aiSummary: z.string(),
  disputeLetterUrl: z.string().nullable(),
  reportUrl: z.string().nullable(),
  createdAt: z.string(),
});

export const AnalysisResultSchema = z.preprocess(
  (raw) =>
    coalesce(raw, [
      ['billId', 'bill_id'],
      ['totalCharges', 'total_charges'],
      ['estimatedFairValue', 'estimated_fair_value'],
      ['totalPotentialSavings', 'total_potential_savings'],
      ['aiSummary', 'ai_summary'],
      ['disputeLetterUrl', 'dispute_letter_url'],
      ['reportUrl', 'report_url'],
      ['createdAt', 'created_at'],
    ]),
  AnalysisResultBase,
);

// Type alias intentionally NOT exported — see note on BillingError above.

// ─── ProfileMember + InsurancePlan (M10) ──────────────────────────────────────

const InsurancePlanBase = z.object({
  id: z.string(),
  profileMemberId: z.string(),
  payerName: z.string(),
  planName: z.string(),
  memberId: z.string().nullable(),
  planType: PlanTypeSchema,
  isPrimaryPlan: z.boolean(),
  createdAt: z.string(),
});

export const InsurancePlanSchema = z.preprocess(
  (raw) =>
    coalesce(raw, [
      ['profileMemberId', 'profile_member_id'],
      ['payerName', 'payer_name'],
      ['planName', 'plan_name'],
      ['memberId', 'member_id'],
      ['planType', 'plan_type'],
      ['isPrimaryPlan', 'is_primary_plan'],
      ['createdAt', 'created_at'],
    ]),
  InsurancePlanBase,
);

const ProfileMemberBase = z.object({
  id: z.string(),
  fullName: z.string(),
  dateOfBirth: z.string(),
  state: z.string().nullable(),
  county: z.string().nullable(),
  zipCode: z.string().nullable(),
  isPrimary: z.boolean(),
  createdAt: z.string(),
});

export const ProfileMemberSchema = z.preprocess(
  (raw) =>
    coalesce(raw, [
      ['fullName', 'full_name'],
      ['dateOfBirth', 'date_of_birth'],
      ['zipCode', 'zip_code'],
      ['isPrimary', 'is_primary'],
      ['createdAt', 'created_at'],
    ]),
  ProfileMemberBase,
);

// The /api/profile/members endpoint returns a member joined with all of
// its insurance plans nested under `insurance_plans`. Define the joined
// shape explicitly so the mapper / consumers can rely on the `insurancePlans`
// camelCase form even though the join from PostgREST returns snake-cased keys.
const ProfileMemberWithPlansBase = ProfileMemberBase.extend({
  insurancePlans: z.array(InsurancePlanSchema),
});

export const ProfileMemberWithPlansSchema = z.preprocess(
  (raw) =>
    coalesce(raw, [
      ['fullName', 'full_name'],
      ['dateOfBirth', 'date_of_birth'],
      ['zipCode', 'zip_code'],
      ['isPrimary', 'is_primary'],
      ['createdAt', 'created_at'],
      ['insurancePlans', 'insurance_plans'],
    ]),
  ProfileMemberWithPlansBase,
);
