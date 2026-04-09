-- Add effective_from to cms_anesthesia_cf to support mid-year CF updates.
--
-- CMS issued a mid-year correction for 2024 (effective 2024-03-09), creating two
-- distinct CF values for the same year. Without this column we cannot store both
-- periods without a unique constraint violation.
--
-- Lookup uses: year <= bill_year ORDER BY year DESC, effective_from DESC
-- so the latest active period for the closest available year is always used.

alter table public.cms_anesthesia_cf
  add column effective_from date;

-- Backfill existing 2026 rows: the 2026 file covers the full calendar year.
update public.cms_anesthesia_cf
  set effective_from = make_date(year, 1, 1);

alter table public.cms_anesthesia_cf
  alter column effective_from set not null;

-- Replace the unique constraint to include effective_from.
alter table public.cms_anesthesia_cf
  drop constraint cms_anesthesia_cf_year_contractor_locality_number_key;

alter table public.cms_anesthesia_cf
  add constraint cms_anesthesia_cf_unique
  unique (year, contractor, locality_number, effective_from);

-- Replace the lookup index with one that orders by effective_from descending
-- so the latest period is found first in ORDER BY year DESC, effective_from DESC queries.
drop index if exists cms_anesthesia_cf_locality_idx;

create index cms_anesthesia_cf_locality_idx
  on public.cms_anesthesia_cf (year, contractor, locality_number, effective_from desc);
