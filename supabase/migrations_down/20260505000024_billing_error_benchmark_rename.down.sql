-- Reverse T10 backfill: undo the benchmarkRate + benchmarkSource rename
-- back to medicareBenchmarkRate. This is a best-effort reversal — it
-- preserves the value but loses the source distinction (a
-- HOSPITAL_CHARGE_OUTLIER finding's hospital_gross_charge becomes
-- "medicareBenchmarkRate" again, perpetuating the original lie). Use only
-- if a deploy needs to be rolled back.

create or replace function public._rename_source_back_to_legacy(err jsonb)
  returns jsonb
  language sql
  immutable
as $$
  select
    case
      when err ? 'medicareBenchmarkRate' or err is null then err
      when not (err ? 'benchmarkRate') then err
      else
        (err - 'benchmarkRate' - 'benchmarkSource')
        || jsonb_build_object('medicareBenchmarkRate', err -> 'benchmarkRate');
    end;
$$;

update public.analysis_results
set errors = (
  select jsonb_agg(public._rename_source_back_to_legacy(e))
  from jsonb_array_elements(errors) e
)
where errors::text like '%benchmarkRate%';

drop function if exists public._rename_source_back_to_legacy(jsonb);
drop function if exists public._rename_benchmark_to_source(jsonb);
