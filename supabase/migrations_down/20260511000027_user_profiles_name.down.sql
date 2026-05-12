alter table public.user_profiles
  drop column if exists first_name,
  drop column if exists last_name;
