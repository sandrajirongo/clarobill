-- CMS Ambulance Fee Schedule (AFS) payment rates per MAC carrier/locality.
--
-- Source: CMS Ambulance Fee Schedule Public Use Files (AFS PUF)
-- Download: https://www.cms.gov/medicare/payment/ambulance-services/ambulance-fee-schedule
--
-- The AFS publishes pre-computed locality-adjusted rates for each ambulance HCPCS
-- code (A0425–A0436). Three rate tiers exist based on geographic designation:
--   urban       = standard locality rate
--   rural       = slightly elevated (~5-50% above urban depending on code)
--   super_rural = elevated rate for lowest-quartile rural areas (~1.5x urban)
--
-- Mileage codes (A0425 = ground, A0435 = fixed-wing air, A0436 = rotary air):
--   urban_rate and rural_rate are the per-statute-mile amounts.
--   For A0425 in super-rural, super_rural_rate is the "Rural Ground Miles 1-17"
--   column (the elevated per-mile rate for the first 17 ground miles).
--   Air mileage codes have no super_rural_rate (n/a in source data).
--
-- locality_key = carrier (5 chars) || locality (2 chars) — this is NOT the same
-- as the 7-char locality_code in cms_county_locality. The engine splits
-- locality_code[:5] and locality_code[5:] to match against carrier and locality here.
--
-- The script is re-runnable — it upserts on (effective_from, carrier, locality, hcpc).

create table if not exists public.cms_ambulance_rates (
  id               uuid        primary key default gen_random_uuid(),
  effective_from   date        not null,
  carrier          text        not null,  -- 5-char MAC contractor code (e.g. '01112')
  locality         text        not null,  -- 2-char locality number (e.g. '05')
  hcpc             text        not null,  -- A0425–A0436
  rvu              numeric(8, 4),
  gpci             numeric(8, 4),
  base_rate        numeric(12, 2),        -- national base rate (pre-GPCI adjustment)
  urban_rate       numeric(12, 2),        -- locality-adjusted urban rate / urban mileage
  rural_rate       numeric(12, 2),        -- locality-adjusted rural rate / rural mileage
  super_rural_rate numeric(12, 2),        -- super-rural rate; null for air mileage codes
  unique (effective_from, carrier, locality, hcpc)
);

create index if not exists cms_ambulance_rates_lookup_idx
  on public.cms_ambulance_rates (effective_from desc, carrier, locality, hcpc);

-- Reference data — read via service role on the engine side (no RLS policies needed).
alter table public.cms_ambulance_rates enable row level security;
