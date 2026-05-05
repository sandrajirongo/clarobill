-- Reverse Phase 1.4 — rewrite camelCase BillingError keys back to snake_case.
--
-- Use only if you need to roll the engine code back past commit a0fd6b3
-- (Pydantic alias_generator addition). The frontend Zod schema accepts both
-- shapes during the migration window, so reverting just this migration is
-- safe even with the new frontend in place.

create or replace function public._unwrite_billing_error_keys(err jsonb)
  returns jsonb
  language sql
  immutable
as $$
  select
    case
      when err ? 'affected_line_item_ids' or err is null then err
      else jsonb_strip_nulls(jsonb_build_object(
        'code',                    err -> 'code',
        'severity',                err -> 'severity',
        'description',             err -> 'description',
        'affected_line_item_ids',  coalesce(err -> 'affected_line_item_ids',  err -> 'affectedLineItemIds'),
        'estimated_overcharge',    coalesce(err -> 'estimated_overcharge',    err -> 'estimatedOvercharge'),
        'medicare_benchmark_rate', coalesce(err -> 'medicare_benchmark_rate', err -> 'medicareBenchmarkRate')
      ))
    end;
$$;

update public.analysis_results
   set errors = (
     select jsonb_agg(public._unwrite_billing_error_keys(elem))
       from jsonb_array_elements(errors) as elem
   )
 where errors::text like '%affectedLineItemIds%'
    or errors::text like '%estimatedOvercharge%'
    or errors::text like '%medicareBenchmarkRate%';

drop function public._unwrite_billing_error_keys(jsonb);
