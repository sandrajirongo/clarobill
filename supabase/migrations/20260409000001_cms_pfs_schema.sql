-- ─── Replace flat medicare_fee_schedule with CMS PFS source tables ──────────
--
-- The old medicare_fee_schedule stored a single pre-computed dollar rate per code.
-- The CMS PFS data is structured differently: the indicators file provides RVU
-- components (work, PE, malpractice) and a conversion factor. The localities file
-- provides GPCI multipliers per MAC locality that adjust for geography.
--
-- The actual payment formula is:
--   rate = (rvu_work * gpci_work + pe_rvu * gpci_pe + rvu_mp * gpci_mp) * conv_fact
--
-- Storing the components lets us compute locality-adjusted rates at query time
-- instead of having to pre-compute and store one row per code × locality.
-- For the national rate, all GPCIs are 1.0 (locality 0000000).

drop table if exists public.medicare_fee_schedule;

-- ─── CMS PFS Indicators ───────────────────────────────────────────────────────
-- One row per HCPC code (+ modifier) per year.
-- Source: CMS Physician Fee Schedule indicators file.
create table public.cms_pfs_indicators (
  id             uuid primary key default gen_random_uuid(),
  year           integer not null,
  hcpc           text not null,
  modifier       text not null default '',
  sdesc          text,
  -- A = active, I = inactive/non-priced, J = anesthesia, B = bundled, etc.
  proc_stat      text,
  -- RVU components — used to compute locality-adjusted rates
  rvu_work       numeric(10, 4) not null default 0,
  nfac_pe_rvu    numeric(10, 4) not null default 0,   -- full non-facility PE RVU
  fac_pe_rvu     numeric(10, 4) not null default 0,   -- full facility PE RVU
  rvu_mp         numeric(10, 4) not null default 0,
  -- Pre-summed national totals (GPCIs = 1.0 for national locality)
  nfac_total_rvu numeric(10, 4) not null default 0,   -- = rvu_work + nfac_pe_rvu + rvu_mp
  fac_total_rvu  numeric(10, 4) not null default 0,
  -- National conversion factor for this code
  conv_fact      numeric(10, 4) not null default 0,
  -- Metadata flags
  pctc           text,   -- professional/technical component indicator
  global_days    text,   -- global surgery days
  unique (year, hcpc, modifier)
);

create index cms_pfs_indicators_hcpc_idx on public.cms_pfs_indicators (hcpc);
create index cms_pfs_indicators_year_hcpc_idx on public.cms_pfs_indicators (year, hcpc);

-- ─── CMS Localities ───────────────────────────────────────────────────────────
-- GPCI (Geographic Practice Cost Index) values per MAC locality per year.
-- National locality code is '0000000' with all GPCIs = 1.0.
create table public.cms_localities (
  id                   uuid primary key default gen_random_uuid(),
  year                 integer not null,
  locality_code        text not null,
  locality_description text not null,
  mac                  text,
  mac_description      text,
  gpci_work            numeric(8, 4) not null,
  gpci_pe              numeric(8, 4) not null,
  gpci_mp              numeric(8, 4) not null,
  unique (year, locality_code)
);

create index cms_localities_code_idx on public.cms_localities (locality_code);

-- ─── RLS ──────────────────────────────────────────────────────────────────────
-- Reference data — any authenticated or anonymous read is fine.
alter table public.cms_pfs_indicators enable row level security;
alter table public.cms_localities enable row level security;

create policy "cms_pfs_indicators: public read"
  on public.cms_pfs_indicators for select using (true);

create policy "cms_localities: public read"
  on public.cms_localities for select using (true);
