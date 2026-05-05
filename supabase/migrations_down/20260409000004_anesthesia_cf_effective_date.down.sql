alter table public.cms_anesthesia_cf
  drop constraint if exists cms_anesthesia_cf_unique;

drop index if exists cms_anesthesia_cf_locality_idx;

alter table public.cms_anesthesia_cf
  add constraint cms_anesthesia_cf_year_contractor_locality_number_key
  unique (year, contractor, locality_number);

create index cms_anesthesia_cf_locality_idx
  on public.cms_anesthesia_cf (year, contractor, locality_number);

alter table public.cms_anesthesia_cf
  drop column if exists effective_from;
