-- Down migration: 20260420000017_ncci_insurance_mue

drop table if exists public.ncci_mue_limits cascade;

alter table public.bills drop column if exists plan_type;

alter table public.ncci_edit_pairs drop constraint if exists ncci_edit_pairs_unique;
alter table public.ncci_edit_pairs drop column if exists payer_type;
alter table public.ncci_edit_pairs drop column if exists service_type;
alter table public.ncci_edit_pairs
  add constraint ncci_edit_pairs_column_one_code_column_two_code_key
    unique (column_one_code, column_two_code);
