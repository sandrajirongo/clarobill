alter table public.bills
    drop column if exists hospital_npi,
    drop column if exists hospital_name;
