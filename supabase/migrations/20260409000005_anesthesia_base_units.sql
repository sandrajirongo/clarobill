-- CMS anesthesia base units per CPT code.
--
-- Base units represent the inherent complexity of each anesthesia procedure.
-- Medicare payment formula: (base_units + time_units) × locality_CF
--
-- CMS has published two tables: CY 2018 (valid 2018-2021) and CY 2022 (valid 2022+).
-- The effective_year column lets the engine select the correct vintage for any bill.
-- Lookup: WHERE cpt_code = ? AND effective_year <= bill_year ORDER BY effective_year DESC.
--
-- Loaded via: scripts/load_anesthesia_base_units.py

create table if not exists public.cms_anesthesia_base_units (
  id             uuid    primary key default gen_random_uuid(),
  cpt_code       text    not null,
  base_units     integer not null,
  effective_year integer not null,
  unique (cpt_code, effective_year)
);

create index if not exists cms_anesthesia_base_units_lookup
  on public.cms_anesthesia_base_units (cpt_code, effective_year desc);

alter table public.cms_anesthesia_base_units enable row level security;

create policy "cms_anesthesia_base_units: public read"
  on public.cms_anesthesia_base_units for select using (true);
