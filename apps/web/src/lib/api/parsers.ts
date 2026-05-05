// Boundary parsers for Supabase JSONB columns and engine HTTP responses.
//
// M12 (2026-05-04): also exports small Zod schemas + `parseJsonResponse`
// helper for the common HTTP shapes in the codebase. Replaces unsafe
// `await res.json() as { ... }` casts in components and API routes —
// see ad-hoc shapes in StatusResponseSchema / CheckoutResponseSchema /
// ErrorResponseSchema below.
//
// Use these wherever the frontend reads JSON the engine produced. They call
// the shared Zod schemas, so:
//
//   - legacy snake_case rows (persisted before the engine alias_generator)
//     transparently coalesce to camelCase
//   - shape drift (missing fields, wrong types, unknown enum values) throws
//     loudly instead of silently rendering `$undefined.toFixed(2)`
//
// Replaces every `as BillingError[]` / `as BillAnalysisResponse` style cast
// in the codebase per Phase 1 of the bug-fix campaign.

import { z } from 'zod';
import {
  AnalysisResultSchema,
  BillingErrorSchema,
  BillSchema,
  LineItemSchema,
} from '@clarobill/shared';
import type { BillingError, AnalysisResult, Bill, LineItem } from '@clarobill/shared';

// ─── Common HTTP response shapes (M12) ────────────────────────────────────────

export const StatusResponseSchema = z.object({
  status: z.string(),
});

export const CheckoutResponseSchema = z.object({
  checkoutUrl: z.string().url(),
});

export const ErrorResponseSchema = z.object({
  error: z.object({
    detail: z.string(),
  }),
});

export const MemberCreatedResponseSchema = z.object({
  member: z.object({ id: z.string() }),
});

export const PlanCreatedResponseSchema = z.object({
  plan: z.object({ id: z.string() }),
});

// Used by bill-results-view's analysis poll: only the report/dispute URLs
// are read off the wider response, so accept partial shapes.
export const AnalysisUrlsResponseSchema = z.object({
  analysis: z
    .object({
      reportUrl: z.string().nullable().optional(),
      disputeLetterUrl: z.string().nullable().optional(),
    })
    .optional(),
});

// Wrappers that validate only the outer envelope. The inner element shape
// is locally typed in the consumer (e.g. ProfileMember in bill-verification.tsx
// is snake_case to match the API; converting it to camelCase is M10 territory).
// `.unknown()` makes the cast at the call site explicit but bounded — we've
// already proven the wire shape is `{members: array}`, just not what's in it.
export const MembersListResponseSchema = z.object({
  members: z.array(z.unknown()),
});

// Mirrors the InsuranceCardExtraction interface in apps/web/src/app/api/
// insurance-card/extract/route.ts. Validated at the consumer boundary so
// engine-side schema drift fails loudly.
export const InsuranceCardExtractionSchema = z.object({
  payerName: z.string().nullable(),
  planName: z.string().nullable(),
  memberId: z.string().nullable(),
  groupId: z.string().nullable(),
  planType: z.string().nullable(),
  rxBin: z.string().nullable(),
  rxPcn: z.string().nullable(),
  rxGroup: z.string().nullable(),
  confident: z.boolean(),
  note: z.string().nullable(),
});

/**
 * Parse a fetch Response's JSON body through a Zod schema. Returns the
 * narrowed type on success; throws ZodError on shape mismatch. Use
 * everywhere a previous version of the code did
 * `await res.json() as { ... }` — that cast lied to TypeScript and let
 * shape drift slip through to runtime.
 */
export async function parseJsonResponse<T>(
  res: Response,
  schema: z.ZodSchema<T>,
): Promise<T> {
  const raw = await res.json();
  return schema.parse(raw);
}

export function parseBillingErrors(value: unknown): BillingError[] {
  return BillingErrorSchema.array().parse(value);
}

export function parseAnalysisResult(value: unknown): AnalysisResult {
  return AnalysisResultSchema.parse(value);
}

export function parseBill(value: unknown): Bill {
  return BillSchema.parse(value);
}

export function parseLineItems(value: unknown): LineItem[] {
  return LineItemSchema.array().parse(value);
}

// Lighter-weight: counts errors without strictly validating each one. Used by
// the dashboard summary, where shape drift on a single row should not break
// the whole list. Still validates that the value is array-shaped.
export function safeCountErrors(value: unknown): number {
  return Array.isArray(value) ? value.length : 0;
}
