-- Migration: 60-day retention policy for uploaded bill files
-- The raw bill file is purged after 60 days; analysis results are kept indefinitely.

-- 1. Add delete_after as a stored generated column (created_at + 60 days)
alter table public.bills
  add column delete_after timestamptz
    generated always as (created_at + interval '60 days') stored;

-- 2. Fix payments.amount_cents constraint to allow $0 (beta / free reports)
alter table public.payments
  drop constraint if exists payments_amount_cents_check;
alter table public.payments
  add constraint payments_amount_cents_check check (amount_cents >= 0);

-- 3. Change payments.bill_id FK to ON DELETE CASCADE so bills can be
--    deleted cleanly when retention expires (payments history is preserved
--    via user_id; bill_id becomes nullable below)
alter table public.payments
  drop constraint if exists payments_bill_id_fkey;
alter table public.payments
  alter column bill_id drop not null;
alter table public.payments
  add constraint payments_bill_id_fkey
    foreign key (bill_id) references public.bills(id) on delete set null;

-- 4. Scheduled nightly cleanup via pg_cron (requires pg_cron extension).
--    Enable in Supabase: Dashboard → Database → Extensions → pg_cron
--    This job runs at 02:00 UTC every night and deletes bills whose
--    60-day window has passed. Line items and analysis results cascade.
--    Storage files in the 'bills' bucket must be cleaned separately via
--    a Supabase Edge Function triggered by the same schedule.
--
-- Uncomment once pg_cron is enabled:
-- select cron.schedule(
--   'delete-expired-bills',
--   '0 2 * * *',
--   $$
--     delete from public.bills
--     where delete_after < now();
--   $$
-- );
