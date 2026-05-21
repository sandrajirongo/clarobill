-- Denormalize error_count and total_potential_savings onto bills so per-bill
-- summaries are readable without joining analysis_results. The engine writes
-- these at the same time it flips status = 'complete'.
alter table public.bills
  add column if not exists error_count            integer,
  add column if not exists total_potential_savings numeric(10, 2);
