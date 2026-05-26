-- Migration: bill_analytics
-- Fact table for performance monitoring: one row per analyzed bill.
-- Populated automatically by triggers on analysis_results and payments.
-- No user-level RLS — this table is internal only, queried via service role.

CREATE TABLE public.bill_analytics (
  id                      uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  bill_id                 uuid        NOT NULL UNIQUE REFERENCES public.bills(id) ON DELETE CASCADE,
  user_id                 uuid        NOT NULL,

  -- Hospital identity (from engine NPI resolution)
  hospital_npi            text,
  hospital_name           text,
  hospital_state          text,
  hospital_city           text,
  hospital_zip            text,

  -- Payer / plan identity (from bills row, set before analysis)
  payer_name              text,
  plan_name               text,
  plan_type               text        CHECK (plan_type IN ('commercial','medicare','medicaid','tricare','self_pay')),

  -- Financial outcomes
  original_bill_total     numeric(12,2),
  total_potential_savings numeric(12,2),
  savings_pct             numeric(6,2),        -- savings / original_bill_total * 100, NULL when total is 0

  -- Service date context (MIN service_date across all line items for this bill)
  service_date_earliest   date,
  pricing_effective_year  integer,             -- EXTRACT(YEAR FROM service_date_earliest)

  -- Error breakdown
  total_error_count       integer     NOT NULL DEFAULT 0,
  critical_error_count    integer     NOT NULL DEFAULT 0,
  warning_error_count     integer     NOT NULL DEFAULT 0,
  info_error_count        integer     NOT NULL DEFAULT 0,
  error_codes             text[],              -- distinct BillingErrorCode values fired

  -- Benchmark coverage flags (which data sources enriched this analysis)
  had_negotiated_rate     boolean     NOT NULL DEFAULT false,  -- NEGOTIATED_RATE_EXCEEDED fired
  had_hospital_charge     boolean     NOT NULL DEFAULT false,  -- HOSPITAL_CHARGE_OUTLIER fired
  had_benchmark_gap       boolean     NOT NULL DEFAULT false,  -- BENCHMARK_UNAVAILABLE fired

  -- Conversion tracking
  report_purchased        boolean     NOT NULL DEFAULT false,

  analyzed_at             timestamptz NOT NULL DEFAULT now(),
  created_at              timestamptz NOT NULL DEFAULT now()
);

-- ── Indices ───────────────────────────────────────────────────────────────────

-- Dashboard filters: location, payer, plan type, year
CREATE INDEX bill_analytics_hospital_state_idx  ON public.bill_analytics (hospital_state);
CREATE INDEX bill_analytics_hospital_npi_idx    ON public.bill_analytics (hospital_npi)   WHERE hospital_npi IS NOT NULL;
CREATE INDEX bill_analytics_plan_type_idx       ON public.bill_analytics (plan_type)      WHERE plan_type IS NOT NULL;
CREATE INDEX bill_analytics_payer_name_idx      ON public.bill_analytics (payer_name)     WHERE payer_name IS NOT NULL;
CREATE INDEX bill_analytics_effective_year_idx  ON public.bill_analytics (pricing_effective_year);
CREATE INDEX bill_analytics_analyzed_at_idx     ON public.bill_analytics (analyzed_at DESC);

-- User retention queries
CREATE INDEX bill_analytics_user_id_idx         ON public.bill_analytics (user_id);

-- ── RLS ───────────────────────────────────────────────────────────────────────
-- Internal table only. Enable RLS so anon/authenticated roles cannot read rows.
-- The service role bypasses RLS and is the only consumer.

ALTER TABLE public.bill_analytics ENABLE ROW LEVEL SECURITY;

-- No permissive policies — authenticated users cannot access this table directly.


-- ── Trigger: sync from analysis_results ──────────────────────────────────────
-- Fires after every INSERT or UPDATE on analysis_results.
-- Derives all fields that come from the analysis pipeline output.

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
  -- Fetch denormalised bill fields we need for the fact row
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

  -- Earliest service date across all line items for this bill
  SELECT MIN(li.service_date)
  INTO v_service_date_min
  FROM public.line_items li
  WHERE li.bill_id = NEW.bill_id;

  v_effective_year := EXTRACT(YEAR FROM v_service_date_min)::integer;

  -- Aggregate error counts and codes from the JSONB errors array
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

  -- Benchmark coverage flags
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

  -- savings_pct: NULL-safe; avoid divide-by-zero
  IF NEW.total_bill_charges IS NOT NULL AND NEW.total_bill_charges > 0 THEN
    v_savings_pct := ROUND(
      (NEW.total_potential_savings / NEW.total_bill_charges) * 100,
      2
    );
  ELSE
    v_savings_pct := NULL;
  END IF;

  -- Hospital location: prefer the profile_member address attached to this bill,
  -- fall back to NULL (engine may not always resolve a full address)
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
    NEW.total_bill_charges,
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

CREATE TRIGGER trg_bill_analytics_from_analysis
  AFTER INSERT OR UPDATE ON public.analysis_results
  FOR EACH ROW
  EXECUTE FUNCTION public.sync_bill_analytics_from_analysis();


-- ── Trigger: sync from payments ───────────────────────────────────────────────
-- Fires after every INSERT or UPDATE on payments.
-- Only job: flip report_purchased = true when a payment completes.

CREATE OR REPLACE FUNCTION public.sync_bill_analytics_from_payment()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF NEW.status = 'complete' THEN
    UPDATE public.bill_analytics
    SET report_purchased = true
    WHERE bill_id = NEW.bill_id;
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_bill_analytics_from_payment
  AFTER INSERT OR UPDATE ON public.payments
  FOR EACH ROW
  EXECUTE FUNCTION public.sync_bill_analytics_from_payment();
