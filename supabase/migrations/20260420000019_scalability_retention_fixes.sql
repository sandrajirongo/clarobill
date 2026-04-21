-- Migration: 20260420000019_scalability_retention_fixes
--
-- Three categories of change:
--
-- 1. HIPAA / data promise compliance
--    The 60-day retention policy (migration 20260408000001) promised to purge
--    uploaded bill files after 60 days but left two gaps:
--      a. The cron job was commented out — retention never ran.
--      b. Even if it ran, it deleted the bills row and cascaded to
--         analysis_results, destroying users' reports — contrary to the stated
--         intent of "analysis results are kept indefinitely".
--      c. Storage objects in the 'bills' bucket were never deleted — only DB
--         rows. The actual uploaded PHI document remained in storage forever.
--    Fix: null out file_path after 60 days instead of deleting the bill row,
--    queue the storage path for deletion, and schedule the job.
--
-- 2. Missing indexes
--    Two indexes were absent that become important at scale:
--      a. No index on payments(bill_id) — the analysis route and Reports page
--         both query payments by bill_id; at millions of payment records this
--         is a full table scan.
--      b. No index on bills(created_at) — the nightly retention scan queries
--         WHERE created_at < now() - interval '60 days' across all bills.
--
-- 3. Index consolidation on bills
--    bills_user_id_idx (single column) is made redundant by the new composite
--    index (user_id, created_at DESC), which satisfies both the equality
--    predicate the old index served and the ORDER BY created_at DESC the
--    dashboard query adds. The low-cardinality bills_status_idx (5 values)
--    is dropped — Postgres rarely uses it and it adds write overhead.


-- ─── 1a. Allow file_path to be null once the uploaded file has been purged ────
-- Analysis results, line items, and the bill row itself are kept indefinitely.
-- Only the raw uploaded document is subject to the 60-day purge.
-- PostgreSQL treats each NULL as distinct for unique constraints, so multiple
-- purged rows with file_path = NULL do not violate the existing unique index.
alter table public.bills
  alter column file_path drop not null;


-- ─── 1b. Storage deletion queue ───────────────────────────────────────────────
-- Holds file paths of uploaded bill documents that have been logically purged
-- (file_path set to NULL) but not yet deleted from Supabase Storage.
-- The Edge Function process-deleted-bill-files reads this table, calls
-- storage.remove(), then deletes the processed rows.
create table public.deleted_bill_files (
  id         uuid primary key default gen_random_uuid(),
  file_path  text not null,
  queued_at  timestamptz not null default now(),
  unique (file_path)
);

-- No RLS policies = deny for all non-service-role requests.
-- Only the Edge Function (service role) reads and clears this table.
alter table public.deleted_bill_files enable row level security;


-- ─── 1c. Retention function ───────────────────────────────────────────────────
-- Called by the pg_cron job. In a single transaction:
--   1. Queues storage paths of expired bill files for deletion.
--   2. Nulls out file_path on the bill rows (marks file as purged in DB).
--
-- The bill row, line items, analysis results, and generated PDFs are NOT
-- deleted — users retain access to their reports indefinitely.
create or replace function public.expire_bill_files()
returns void language plpgsql security definer
set search_path = public
as $$
begin
  insert into public.deleted_bill_files (file_path)
  select file_path
  from public.bills
  where created_at < now() - interval '60 days'
    and file_path is not null
  on conflict (file_path) do nothing;

  update public.bills
  set file_path = null
  where created_at < now() - interval '60 days'
    and file_path is not null;
end;
$$;


-- ─── 1d. Schedule nightly retention ──────────────────────────────────────────
-- Requires the pg_cron extension enabled in the Supabase dashboard:
--   Dashboard → Database → Extensions → pg_cron  (Pro plan and above)
--
-- Runs at 02:00 UTC daily. Nulls out expired file_paths and queues them.
-- Storage objects are deleted separately by the Edge Function (see 1b above),
-- which should be scheduled at 02:15 UTC via:
--   Dashboard → Edge Functions → process-deleted-bill-files → Cron schedule
select cron.schedule(
  'expire-bill-files',
  '0 2 * * *',
  'select public.expire_bill_files()'
);


-- ─── 2. Index on payments(bill_id) ───────────────────────────────────────────
-- The analysis route (/api/bills/[billId]/analysis) and the Reports page both
-- query payments by bill_id. After migration 20260408000001 made bill_id
-- nullable, no index was added. At millions of payment records this is a seq
-- scan on every bill detail page load.
create index payments_bill_id_idx on public.payments (bill_id);


-- ─── 3a. Drop low-cardinality status index ───────────────────────────────────
-- 5 possible values ('uploading', 'ocr_processing', 'analyzing', 'complete',
-- 'failed'). At millions of rows the vast majority have status='complete',
-- making the index selectivity near zero for the common case. Postgres skips
-- it and does a seq scan anyway. The write overhead is not worth it.
drop index if exists public.bills_status_idx;


-- ─── 3b. Replace single-column user_id index with composite ──────────────────
-- The dashboard query is effectively:
--   SELECT ... FROM bills WHERE user_id = ? ORDER BY created_at DESC
-- The composite index satisfies the equality predicate AND eliminates the sort,
-- making it a strict superset of the old single-column index.
-- bills_created_at_idx is added separately for the retention scan.
drop index if exists public.bills_user_id_idx;

create index bills_user_id_created_at_idx
  on public.bills (user_id, created_at desc);

create index bills_created_at_idx
  on public.bills (created_at);
