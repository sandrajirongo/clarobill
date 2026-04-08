-- Migration: 60-day retention policy for uploaded bill files
-- The raw bill file is purged after 60 days; analysis results are kept indefinitely.
--
-- Note: delete_after is NOT stored in the database — it is always computed in the
-- application as (created_at + 60 days). PostgreSQL generated columns require
-- IMMUTABLE expressions, but timestamptz arithmetic is only STABLE (timezone-dependent).

-- 1. Fix payments.amount_cents constraint to allow $0 (beta / free reports)
alter table public.payments
  drop constraint if exists payments_amount_cents_check;
alter table public.payments
  add constraint payments_amount_cents_check check (amount_cents >= 0);

-- 2. Change payments.bill_id FK to ON DELETE SET NULL so bills can be
--    deleted cleanly when retention expires. Payment history is preserved
--    via user_id; bill_id becomes nullable.
alter table public.payments
  drop constraint if exists payments_bill_id_fkey;
alter table public.payments
  alter column bill_id drop not null;
alter table public.payments
  add constraint payments_bill_id_fkey
    foreign key (bill_id) references public.bills(id) on delete set null;

-- 3. Scheduled nightly cleanup via pg_cron (requires pg_cron extension).
--    Enable in Supabase: Dashboard → Database → Extensions → pg_cron
--    Deletes bills older than 60 days. Line items and analysis_results cascade.
--    Storage files in the 'bills' bucket need separate cleanup via an Edge Function.
--
-- Uncomment once pg_cron is enabled:
-- select cron.schedule(
--   'delete-expired-bills',
--   '0 2 * * *',
--   $$
--     delete from public.bills
--     where created_at < now() - interval '60 days';
--   $$
-- );
