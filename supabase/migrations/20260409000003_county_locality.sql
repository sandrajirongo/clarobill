-- Maps US counties to their CMS MAC locality code for geography-adjusted PFS rates.
-- Source: CMS "Counties Included in CY 2026 Localities" (26LOCCO.csv)
--
-- Each row is either:
--   - An exact county match (county_name IS NOT NULL, is_statewide = false, is_rest_of_state = false)
--   - A statewide catch-all (county_name IS NULL, is_statewide = true)
--   - A rest-of-state fallback (county_name IS NULL, is_rest_of_state = true)
--
-- Lookup order: exact county → rest-of-state → statewide → national default (0000000).

create table if not exists public.cms_county_locality (
  id               uuid    primary key default gen_random_uuid(),
  state            text    not null,               -- uppercase state name, e.g. 'CALIFORNIA'
  locality_code    text    not null,               -- 7-char code: contractor (5) || locality_number (2)
  locality_name    text    not null,               -- CMS fee schedule area name
  county_name      text,                           -- normalised county name; null for statewide / rest-of-state
  is_statewide     boolean not null default false, -- true when row represents ALL COUNTIES
  is_rest_of_state boolean not null default false  -- true when row represents ALL OTHER COUNTIES
);

-- Exact county lookup (most common path)
create index if not exists cms_county_locality_state_county
  on public.cms_county_locality (state, county_name);

-- Fallback lookups
create index if not exists cms_county_locality_state_flags
  on public.cms_county_locality (state, is_rest_of_state, is_statewide);
