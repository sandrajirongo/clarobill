-- Down migration for 20260526000031_bill_analytics.sql

DROP TRIGGER IF EXISTS trg_bill_analytics_from_payment  ON public.payments;
DROP TRIGGER IF EXISTS trg_bill_analytics_from_analysis ON public.analysis_results;

DROP FUNCTION IF EXISTS public.sync_bill_analytics_from_payment();
DROP FUNCTION IF EXISTS public.sync_bill_analytics_from_analysis();

DROP TABLE IF EXISTS public.bill_analytics;
