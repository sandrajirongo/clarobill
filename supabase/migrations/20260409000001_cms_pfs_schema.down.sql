drop table if exists public.cms_pfs_indicators;
drop table if exists public.cms_localities;

-- Restore original flat-rate table
create table public.medicare_fee_schedule (
  id                uuid primary key default gen_random_uuid(),
  cpt_code          text not null,
  locality_code     text not null,
  facility_rate     numeric(10, 2) not null,
  non_facility_rate numeric(10, 2) not null,
  year              integer not null,
  unique (cpt_code, locality_code, year)
);

create index medicare_fee_schedule_cpt_idx on public.medicare_fee_schedule (cpt_code);

alter table public.medicare_fee_schedule enable row level security;
create policy "medicare_fee_schedule: public read"
  on public.medicare_fee_schedule for select using (true);
