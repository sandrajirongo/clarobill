alter table public.bills
    drop column if exists hospital_city,
    drop column if exists hospital_state,
    drop column if exists hospital_zip;
