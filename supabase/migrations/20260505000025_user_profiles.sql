-- user_profiles: one row per authenticated user, created on signup.
--
-- Supabase Auth owns the canonical email in auth.users. This table
-- provides a public-schema home for account-level profile data so
-- application queries don't need to join auth.users (which requires
-- service-role access). Email is denormalised here and kept in sync
-- by the triggers below.
--
-- Separate from profile_members: profile_members represents insured
-- household members (the patient on a bill, including dependents).
-- user_profiles represents the account holder — the person who created
-- the Supabase Auth account.

create table public.user_profiles (
  id         uuid primary key references auth.users(id) on delete cascade,
  email      text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index user_profiles_email_idx on public.user_profiles (email);

alter table public.user_profiles enable row level security;

create policy "user_profiles: user isolation"
  on public.user_profiles for all
  using (auth.uid() = id);

-- ─── Sync triggers ────────────────────────────────────────────────────────────

-- Create a profile row when a new auth user is confirmed.
create or replace function public.handle_new_user()
  returns trigger
  language plpgsql
  security definer
  set search_path = public
as $$
begin
  insert into public.user_profiles (id, email)
  values (new.id, new.email)
  on conflict (id) do nothing;
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- Keep email in sync if the user changes it in Supabase Auth.
create or replace function public.handle_user_email_updated()
  returns trigger
  language plpgsql
  security definer
  set search_path = public
as $$
begin
  update public.user_profiles
  set email = new.email, updated_at = now()
  where id = new.id;
  return new;
end;
$$;

create trigger on_auth_user_email_updated
  after update of email on auth.users
  for each row
  when (old.email is distinct from new.email)
  execute function public.handle_user_email_updated();

-- ─── Backfill existing users ──────────────────────────────────────────────────
-- Users who signed up before this migration have no profile row yet.
-- Insert for all existing auth users; conflict clause makes this idempotent.
insert into public.user_profiles (id, email)
select id, email
from auth.users
where email is not null
on conflict (id) do nothing;

-- updated_at trigger (reuses the set_updated_at() function from initial schema)
create trigger user_profiles_updated_at
  before update on public.user_profiles
  for each row execute function public.set_updated_at();
