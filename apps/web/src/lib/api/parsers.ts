// Boundary parsers for Supabase JSONB columns and engine HTTP responses.
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

import {
  AnalysisResultSchema,
  BillingErrorSchema,
  BillSchema,
  LineItemSchema,
} from '@clarobill/shared';
import type { BillingError, AnalysisResult, Bill, LineItem } from '@clarobill/shared';

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
