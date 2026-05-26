-- Fix sync_bill_analytics_from_analysis: column is total_charges, not total_bill_charges.
-- The previous version raised a column-does-not-exist error on every analysis_results
-- INSERT/UPDATE, which broke the analysis pipeline.

CREATE OR REPLACE FUNCTION public.sync_bill_analytics_from_analysis()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_bill              record;
  v_service_date_min  date;
  v_effective_year    integer;
  v_total_errors      integer;
  v_critical          integer;
  v_warning           integer;
  v_info              integer;
  v_codes             text[];
  v_had_negotiated    boolean;
  v_had_hospital      boolean;
  v_had_gap           boolean;
  v_savings_pct       numeric(6,2);
BEGIN
  SELECT
    b.user_id,
    b.hospital_npi,
    b.hospital_name,
    b.payer_name,
    b.plan_name,
    b.plan_type
  INTO v_bill
  FROM public.bills b
  WHERE b.id = NEW.bill_id;

  SELECT MIN(li.service_date)
  INTO v_service_date_min
  FROM public.line_items li
  WHERE li.bill_id = NEW.bill_id;

  v_effective_year := EXTRACT(YEAR FROM v_service_date_min)::integer;

  SELECT
    COUNT(*)::integer,
    COUNT(*) FILTER (WHERE (err->>'severity') = 'critical')::integer,
    COUNT(*) FILTER (WHERE (err->>'severity') = 'warning')::integer,
    COUNT(*) FILTER (WHERE (err->>'severity') = 'info')::integer,
    ARRAY(
      SELECT DISTINCT err->>'code'
      FROM jsonb_array_elements(NEW.errors) AS err
      WHERE err->>'code' IS NOT NULL
      ORDER BY 1
    )
  INTO v_total_errors, v_critical, v_warning, v_info, v_codes
  FROM jsonb_array_elements(NEW.errors) AS err;

  v_had_negotiated := EXISTS (
    SELECT 1 FROM jsonb_array_elements(NEW.errors) AS err
    WHERE err->>'code' IN ('NEGOTIATED_RATE_EXCEEDED', 'NEGOTIATED_CEILING_EXCEEDED')
  );

  v_had_hospital := EXISTS (
    SELECT 1 FROM jsonb_array_elements(NEW.errors) AS err
    WHERE err->>'code' = 'HOSPITAL_CHARGE_OUTLIER'
  );

  v_had_gap := EXISTS (
    SELECT 1 FROM jsonb_array_elements(NEW.errors) AS err
    WHERE err->>'code' = 'BENCHMARK_UNAVAILABLE'
  );

  -- FIX: column is total_charges (was incorrectly total_bill_charges)
  IF NEW.total_charges IS NOT NULL AND NEW.total_charges > 0 THEN
    v_savings_pct := ROUND(
      (NEW.total_potential_savings / NEW.total_charges) * 100,
      2
    );
  ELSE
    v_savings_pct := NULL;
  END IF;

  INSERT INTO public.bill_analytics (
    bill_id,
    user_id,
    hospital_npi,
    hospital_name,
    hospital_state,
    hospital_city,
    hospital_zip,
    payer_name,
    plan_name,
    plan_type,
    original_bill_total,
    total_potential_savings,
    savings_pct,
    service_date_earliest,
    pricing_effective_year,
    total_error_count,
    critical_error_count,
    warning_error_count,
    info_error_count,
    error_codes,
    had_negotiated_rate,
    had_hospital_charge,
    had_benchmark_gap,
    analyzed_at
  )
  SELECT
    NEW.bill_id,
    v_bill.user_id,
    v_bill.hospital_npi,
    v_bill.hospital_name,
    pm.state,
    pm.city,
    pm.zip_code,
    v_bill.payer_name,
    v_bill.plan_name,
    v_bill.plan_type,
    NEW.total_charges,
    NEW.total_potential_savings,
    v_savings_pct,
    v_service_date_min,
    v_effective_year,
    COALESCE(v_total_errors, 0),
    COALESCE(v_critical, 0),
    COALESCE(v_warning, 0),
    COALESCE(v_info, 0),
    v_codes,
    v_had_negotiated,
    v_had_hospital,
    v_had_gap,
    now()
  FROM public.bills b
  LEFT JOIN public.profile_members pm ON pm.id = b.profile_member_id
  WHERE b.id = NEW.bill_id
  ON CONFLICT (bill_id) DO UPDATE SET
    hospital_npi            = EXCLUDED.hospital_npi,
    hospital_name           = EXCLUDED.hospital_name,
    hospital_state          = EXCLUDED.hospital_state,
    hospital_city           = EXCLUDED.hospital_city,
    hospital_zip            = EXCLUDED.hospital_zip,
    payer_name              = EXCLUDED.payer_name,
    plan_name               = EXCLUDED.plan_name,
    plan_type               = EXCLUDED.plan_type,
    original_bill_total     = EXCLUDED.original_bill_total,
    total_potential_savings = EXCLUDED.total_potential_savings,
    savings_pct             = EXCLUDED.savings_pct,
    service_date_earliest   = EXCLUDED.service_date_earliest,
    pricing_effective_year  = EXCLUDED.pricing_effective_year,
    total_error_count       = EXCLUDED.total_error_count,
    critical_error_count    = EXCLUDED.critical_error_count,
    warning_error_count     = EXCLUDED.warning_error_count,
    info_error_count        = EXCLUDED.info_error_count,
    error_codes             = EXCLUDED.error_codes,
    had_negotiated_rate     = EXCLUDED.had_negotiated_rate,
    had_hospital_charge     = EXCLUDED.had_hospital_charge,
    had_benchmark_gap       = EXCLUDED.had_benchmark_gap,
    analyzed_at             = EXCLUDED.analyzed_at;

  RETURN NEW;
END;
$$;
