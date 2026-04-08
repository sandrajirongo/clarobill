-- Referral program: each user gets a unique shareable code.
-- When a referred user makes their first purchase, both get $5 off.

-- 1. Referral codes — one per user, auto-created on signup via trigger below
create table public.referral_codes (
  user_id       uuid primary key references auth.users(id) on delete cascade,
  code          text not null unique,
  credits_cents integer not null default 0, -- accumulated credits (future: multi-referral rewards)
  created_at    timestamptz not null default now()
);

-- 2. Referral relationships — one row per referred user (unique on referred_user_id)
create table public.referrals (
  id               uuid primary key default gen_random_uuid(),
  referrer_user_id uuid not null references auth.users(id) on delete cascade,
  referred_user_id uuid unique references auth.users(id) on delete set null,
  status           text not null default 'pending'
                     check (status in ('pending', 'converted')),
  created_at       timestamptz not null default now()
);

create index referrals_referrer_idx on public.referrals (referrer_user_id);
create index referrals_referred_idx on public.referrals (referred_user_id);

-- 3. RLS
alter table public.referral_codes enable row level security;
alter table public.referrals enable row level security;

create policy "referral_codes: own row only"
  on public.referral_codes for all
  using (user_id = auth.uid());

create policy "referrals: referrer sees their rows"
  on public.referrals for select
  using (referrer_user_id = auth.uid() or referred_user_id = auth.uid());

-- 4. Trigger: auto-create a referral code when a new user signs up
create or replace function public.create_user_referral_code()
returns trigger language plpgsql security definer
set search_path = public
as $$
begin
  insert into public.referral_codes (user_id, code)
  values (
    new.id,
    upper(substr(encode(gen_random_bytes(5), 'hex'), 1, 8))
  )
  on conflict (user_id) do nothing;
  return new;
end;
$$;

create trigger on_auth_user_created_referral_code
  after insert on auth.users
  for each row execute function public.create_user_referral_code();

-- 5. RPC function to safely increment referral credits (called by webhook)
create or replace function public.increment_referral_credits(p_user_id uuid, p_amount integer)
returns void language plpgsql security definer
set search_path = public
as $$
begin
  update public.referral_codes
  set credits_cents = credits_cents + p_amount
  where user_id = p_user_id;
end;
$$;

-- 6. Backfill existing users who predate the trigger
insert into public.referral_codes (user_id, code)
select
  id,
  upper(substr(encode(gen_random_bytes(5), 'hex'), 1, 8))
from auth.users
where id not in (select user_id from public.referral_codes)
on conflict (user_id) do nothing;
