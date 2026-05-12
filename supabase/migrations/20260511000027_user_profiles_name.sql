-- Add first_name and last_name to user_profiles.
-- Nullable: existing rows have no name yet. No default is more honest than a placeholder.
alter table public.user_profiles
  add column if not exists first_name text,
  add column if not exists last_name  text;
