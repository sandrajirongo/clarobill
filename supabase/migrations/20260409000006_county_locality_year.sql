-- Add year column to cms_county_locality to support historical locality assignments.
--
-- CMS occasionally reassigns counties between MAC localities (e.g. when MAC
-- jurisdictions are restructured). Storing year allows the engine to use the
-- correct locality for a bill's actual service date year.
--
-- Lookup: WHERE state = ? AND county_name = ? AND year <= bill_year
--         ORDER BY year DESC LIMIT 1

alter table public.cms_county_locality
  add column year integer;

-- Backfill existing rows (loaded from 26LOCCO.csv) with 2026.
update public.cms_county_locality
  set year = 2026;

alter table public.cms_county_locality
  alter column year set not null;

-- Index for year-aware lookups
create index if not exists cms_county_locality_year_state_county
  on public.cms_county_locality (year, state, county_name);

create index if not exists cms_county_locality_year_state_flags
  on public.cms_county_locality (year, state, is_rest_of_state, is_statewide);
