-- ZIP-to-ambulance-locality mapping for rural/urban indicator resolution.
--
-- Source: CMS AFS ZIP5 fixed-width files (ZIP5_<period>_FINAL.txt)
-- Download: same AFS page as the PUF files
--
-- The ambulance fee schedule uses ZIP codes (not county names) to determine
-- the carrier/locality assignment and the rural designation for each address:
--   rural_indicator = ''  → urban
--   rural_indicator = 'R' → rural (based on 2013 OMB delineations + 2010 RUCA)
--   rural_indicator = 'B' → super rural (lowest quartile rural)
--
-- This table is used by _resolve_ambulance_rural_indicator() to determine which
-- rate column (urban_rate, rural_rate, or super_rural_rate) to use when comparing
-- a billed ambulance charge against the cms_ambulance_rates benchmark.
--
-- Unique constraint is (zip5, effective_from) — one active entry per ZIP per period.
-- The file is published annually with a Dec effective date; we load as Jan 1 of
-- the following year (e.g. ZIP5_DEC2024_FINAL.txt → effective_from = 2025-01-01).

create table if not exists public.cms_ambulance_zip_locality (
  id               uuid  primary key default gen_random_uuid(),
  effective_from   date  not null,
  state            text  not null,            -- 2-char state abbreviation
  zip5             text  not null,            -- 5-digit ZIP code
  carrier          text  not null,            -- 5-char MAC contractor code
  pricing_locality text  not null,            -- 2-char locality number
  rural_indicator  text  not null default '', -- '' = urban, 'R' = rural, 'B' = super rural
  unique (zip5, effective_from)
);

create index if not exists cms_ambulance_zip_locality_lookup_idx
  on public.cms_ambulance_zip_locality (zip5, effective_from desc);

-- Reference data — read via service role on the engine side (no RLS policies needed).
alter table public.cms_ambulance_zip_locality enable row level security;
