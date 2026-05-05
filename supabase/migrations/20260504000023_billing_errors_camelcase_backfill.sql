-- Rewrite legacy snake_case keys in analysis_results.errors to camelCase.
--
-- Before commit a0fd6b3 (2026-05-04), the engine wrote BillingError.model_dump()
-- with the default Pydantic field names (snake_case). The frontend reads the
-- column as BillingError[] (camelCase). The mismatch was masked by an unsafe
-- `as` cast at apps/web/src/app/dashboard/bills/[billId]/page.tsx:148, but
-- meant error.estimatedOvercharge would have been undefined for any real
-- finding the rules engine emitted.
--
-- The engine now emits camelCase (alias_generator=to_camel + by_alias=True);
-- the frontend now parses with Zod; this migration rewrites the existing
-- JSONB rows so the snake-coalesce path in the Zod schema can be retired in
-- Phase 6.
--
-- IDEMPOTENT: the UPDATE is gated on a substring match against the legacy
-- snake key. Re-running on already-camel rows is a no-op.
--
-- BEFORE RUNNING: capture row counts so the impact is auditable.
--   SELECT COUNT(*) FROM public.analysis_results
--    WHERE errors::text LIKE '%affected_line_item_ids%';
--   SELECT COUNT(*) FROM public.analysis_results
--    WHERE jsonb_typeof(errors) = 'array' AND jsonb_array_length(errors) > 0;
--
-- AFTER RUNNING: confirm zero remaining snake rows.
--   SELECT COUNT(*) FROM public.analysis_results
--    WHERE errors::text LIKE '%affected_line_item_ids%';  -- expect 0
--
-- Per CLAUDE.md Rule 16: Supabase Pro database compute is included; bandwidth
-- is metered but this UPDATE never leaves the database. Beta volume is small
-- (<100 rows expected). No external service calls.

-- ─── Helper: rewrite one error object's keys ────────────────────────────────

create or replace function public._rewrite_billing_error_keys(err jsonb)
  returns jsonb
  language sql
  immutable
as $$
  select
    case
      -- Already camelCase or empty — return unchanged
      when err ? 'affectedLineItemIds' or err is null then err
      else jsonb_strip_nulls(jsonb_build_object(
        'code',                  err -> 'code',
        'severity',              err -> 'severity',
        'description',           err -> 'description',
        'affectedLineItemIds',   coalesce(err -> 'affectedLineItemIds',   err -> 'affected_line_item_ids'),
        'estimatedOvercharge',   coalesce(err -> 'estimatedOvercharge',   err -> 'estimated_overcharge'),
        'medicareBenchmarkRate', coalesce(err -> 'medicareBenchmarkRate', err -> 'medicare_benchmark_rate')
      ))
    end;
$$;

-- ─── Backfill ───────────────────────────────────────────────────────────────

-- Only touch rows that actually carry the legacy key, so re-running the
-- migration on a clean DB writes zero rows. The check is on the JSON text
-- representation — cheap, no GIN index needed for a one-time migration on
-- a beta-sized table.
update public.analysis_results
   set errors = (
     select jsonb_agg(public._rewrite_billing_error_keys(elem))
       from jsonb_array_elements(errors) as elem
   )
 where errors::text like '%affected_line_item_ids%'
    or errors::text like '%estimated_overcharge%'
    or errors::text like '%medicare_benchmark_rate%';

-- ─── Cleanup ────────────────────────────────────────────────────────────────

drop function public._rewrite_billing_error_keys(jsonb);

-- ─── Postcondition ──────────────────────────────────────────────────────────

-- Sanity check: no rows should retain any of the legacy snake keys.
do $$
declare
  remaining int;
begin
  select count(*) into remaining
    from public.analysis_results
   where errors::text like '%affected_line_item_ids%'
      or errors::text like '%estimated_overcharge%'
      or errors::text like '%medicare_benchmark_rate%';
  if remaining > 0 then
    raise exception 'billing_errors backfill incomplete: % rows still hold legacy keys', remaining;
  end if;
end
$$;
