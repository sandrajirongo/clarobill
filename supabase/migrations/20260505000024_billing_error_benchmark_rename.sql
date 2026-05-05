-- T10 (Phase 8.1) JSONB backfill: rename `medicareBenchmarkRate` to
-- `benchmarkRate` and add `benchmarkSource` per rule code on every existing
-- analysis_results.errors[] element.
--
-- Pre-T10 the field was overloaded — set to hospital_gross for
-- HOSPITAL_CHARGE_OUTLIER, negotiated_rate for NEGOTIATED_RATE_EXCEEDED,
-- ceiling_rate for NEGOTIATED_CEILING_EXCEEDED, opps_cap for
-- FACILITY_CHARGE_OUTLIER, ambulance_fee_schedule for
-- AMBULANCE_CHARGE_OUTLIER — but the field NAME claimed it was the Medicare
-- rate. The dispute letter copy printed "Medicare benchmark: $X" wrongly
-- for those 5 rule codes.
--
-- This migration:
--   1. Adds `benchmarkRate` (renamed from medicareBenchmarkRate)
--   2. Adds `benchmarkSource` derived from the rule code (the value was
--      always implicit pre-T10 — a hospital_gross_charge stored under the
--      medicareBenchmarkRate key was always actually source='hospital_gross').
--   3. Drops the old `medicareBenchmarkRate` key.
--
-- IDEMPOTENT: the UPDATE is gated on whether the legacy key still exists;
-- re-running on already-renamed rows is a no-op.
--
-- BEFORE RUNNING: count affected rows.
--   SELECT COUNT(*) FROM public.analysis_results
--    WHERE errors::text LIKE '%medicareBenchmarkRate%';
--
-- AFTER RUNNING: verify zero remaining legacy rows + benchmarkSource set.
--   SELECT COUNT(*) FROM public.analysis_results
--    WHERE errors::text LIKE '%medicareBenchmarkRate%';  -- expect 0
--   SELECT COUNT(*) FROM public.analysis_results, jsonb_array_elements(errors) e
--    WHERE NOT (e ? 'benchmarkSource');  -- expect 0
--
-- Per CLAUDE.md Rule 16: Supabase Pro database compute is included; the
-- UPDATE never leaves the database. Beta-era volume is small (<100 rows).

-- ─── Helper: rename + derive source from code ────────────────────────────────

create or replace function public._rename_benchmark_to_source(err jsonb)
  returns jsonb
  language sql
  immutable
as $$
  select
    case
      -- Already migrated — return unchanged
      when err ? 'benchmarkSource' or err is null then err
      else
        -- Strip the legacy key, add the renamed pair
        (err - 'medicareBenchmarkRate')
        || jsonb_build_object(
          'benchmarkRate', err -> 'medicareBenchmarkRate',
          'benchmarkSource',
            case
              -- Map each rule code to the benchmark source the engine
              -- was actually using, even though the field name lied.
              when err ->> 'code' = 'PRICE_OUTLIER'                then to_jsonb('medicare'::text)
              when err ->> 'code' = 'INVALID_CPT_CODE'             then to_jsonb('medicare'::text)
              when err ->> 'code' = 'DUPLICATE_CHARGE'             then to_jsonb('medicare'::text)
              when err ->> 'code' = 'REDUNDANT_CLINICAL_PAIR'      then to_jsonb('medicare'::text)
              when err ->> 'code' = 'HOSPITAL_CHARGE_OUTLIER'      then to_jsonb('hospital_gross'::text)
              when err ->> 'code' = 'NEGOTIATED_RATE_EXCEEDED'     then to_jsonb('negotiated_rate'::text)
              when err ->> 'code' = 'NEGOTIATED_CEILING_EXCEEDED'  then to_jsonb('negotiated_ceiling'::text)
              when err ->> 'code' = 'FACILITY_CHARGE_OUTLIER'      then to_jsonb('opps_cap'::text)
              when err ->> 'code' = 'AMBULANCE_CHARGE_OUTLIER'     then to_jsonb('ambulance_fee_schedule'::text)
              when err ->> 'code' = 'ANESTHESIA_OUTLIER'           then to_jsonb('anesthesia'::text)
              -- Codes that don't carry a benchmark (MUE_EXCEEDED,
              -- TERMINATED_CODE_BILLED, NCCI_UNBUNDLING, etc.) get null.
              else 'null'::jsonb
            end
        )
    end
$$;

-- ─── Apply the rewrite to every analysis_results.errors[] element ────────────

update public.analysis_results
set errors = (
  select jsonb_agg(public._rename_benchmark_to_source(e))
  from jsonb_array_elements(errors) e
)
where errors::text like '%medicareBenchmarkRate%';

-- ─── Postcondition: assert zero legacy rows remain ──────────────────────────

do $$
declare
  legacy_count integer;
  missing_source_count integer;
begin
  select count(*) into legacy_count
    from public.analysis_results
    where errors::text like '%medicareBenchmarkRate%';
  if legacy_count > 0 then
    raise exception 'T10 backfill incomplete: % rows still have medicareBenchmarkRate', legacy_count;
  end if;

  select count(*) into missing_source_count
    from public.analysis_results
    cross join lateral jsonb_array_elements(errors) e
    where not (e ? 'benchmarkSource');
  if missing_source_count > 0 then
    raise notice 'T10 backfill: % error elements lack benchmarkSource (acceptable for empty-errors rows or rows that never had a benchmark)', missing_source_count;
  end if;
end $$;

-- Helper kept available for forensics; callers should not depend on it.
-- A follow-up migration in 1-2 releases can `drop function _rename_benchmark_to_source(jsonb)`.
