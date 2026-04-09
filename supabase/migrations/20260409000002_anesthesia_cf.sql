-- ─── CMS Locality-Adjusted Anesthesia Conversion Factors ────────────────────
--
-- Loaded from: scripts/load_anesthesia_cf.py
-- Source file: "Anesthesia CY 2026 locality adjusted CF with update factor" from CMS
--
-- Medicare pays anesthesia as: (base_units + time_units) × locality_CF
-- where time_units = anesthesia_minutes / 15
--
-- Two CF tracks exist per locality:
--   qualifying_cf     — for providers in a Qualifying APM (~$20.60 nationally)
--   non_qualifying_cf — for all other providers (~$20.50 nationally)
--
-- The non_qualifying_cf is used by default since most providers are not in
-- a qualifying APM. Locality lookup is via contractor + locality_number.

create table public.cms_anesthesia_cf (
  id                uuid primary key default gen_random_uuid(),
  year              integer not null,
  contractor        text,
  locality_number   text not null,   -- 2-digit locality within the MAC (e.g. '00', '01')
  locality_name     text not null,
  qualifying_cf     numeric(8, 4) not null,
  non_qualifying_cf numeric(8, 4) not null,
  unique (year, contractor, locality_number)
);

create index cms_anesthesia_cf_locality_idx on public.cms_anesthesia_cf (year, contractor, locality_number);

alter table public.cms_anesthesia_cf enable row level security;

create policy "cms_anesthesia_cf: public read"
  on public.cms_anesthesia_cf for select using (true);
