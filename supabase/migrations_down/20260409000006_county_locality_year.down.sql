drop index if exists cms_county_locality_year_state_county;
drop index if exists cms_county_locality_year_state_flags;

alter table public.cms_county_locality
  drop column if exists year;
