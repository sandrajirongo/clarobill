-- CMS Outpatient Prospective Payment System (OPPS) cap rates per locality.
--
-- Source: CMS OPPSCAP quarterly files (OPPSCAP_Apr.csv, etc.)
-- Download: https://www.cms.gov/medicare/payment/prospective-payment-systems/hospital-outpatient
--
-- Each row is the Medicare payment cap for a HCPC code in a specific MAC locality.
-- Unlike cms_pfs_indicators (RVU components), these are pre-computed dollar amounts —
-- no GPCI multiplication is needed.
--
-- locality_code = CARRIER (5 chars) || LOCALITY (2 chars, already zero-padded in source)
-- This matches the locality_code format in cms_county_locality and cms_localities,
-- so _resolve_locality() works without modification.
--
-- proc_stat values seen in source data:
--   A = active (APC-priced, primary benchmark for facility overcharge detection)
--   C = capped (OPPS payment is capped at this amount)

create table if not exists public.cms_opps_cap (
  id                 uuid    primary key default gen_random_uuid(),
  year               integer not null,
  hcpc               text    not null,
  modifier           text    not null default '',
  proc_stat          text,
  locality_code      text    not null,
  facility_price     numeric(12, 2),
  non_facility_price numeric(12, 2),
  unique (year, hcpc, modifier, locality_code)
);

create index if not exists cms_opps_cap_lookup_idx
  on public.cms_opps_cap (year, hcpc, modifier, locality_code);

-- Reference data — any authenticated or anonymous read is fine.
alter table public.cms_opps_cap enable row level security;

create policy "cms_opps_cap: public read"
  on public.cms_opps_cap for select using (true);
