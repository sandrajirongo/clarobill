-- Migration: 20260416000013_profile_members_insurance
-- Adds profile_members and insurance_plans tables for multi-member accounts
-- and per-bill payer/plan confirmation. Also adds fields to bills table used
-- by the NEGOTIATED_RATE_EXCEEDED rule.

-- ─── Profile Members ──────────────────────────────────────────────────────────
-- One account can hold bills for multiple insured members (holder + dependents).
-- Each member has their own location (for GPCI) and insurance plans.
create table public.profile_members (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references auth.users(id) on delete cascade,
  full_name     text not null,
  date_of_birth date not null,
  -- Location fields used for Medicare GPCI locality adjustment and ambulance rates.
  -- These mirror the state/county/zip_code fields on AnalyzeRequest.
  state         text,  -- CMS uppercase state name, e.g. "CALIFORNIA"
  county        text,  -- County name without "County" suffix, e.g. "LOS ANGELES"
  zip_code      text,  -- 5-digit ZIP for ambulance rural indicator lookup
  -- Whether this is the account holder's own record (used to pre-select on upload)
  is_primary    boolean not null default false,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

create index profile_members_user_id_idx on public.profile_members (user_id);

-- Only one primary member per account
create unique index profile_members_primary_idx
  on public.profile_members (user_id)
  where is_primary = true;

-- ─── Insurance Plans ──────────────────────────────────────────────────────────
-- Each profile member can have one or more insurance plans (primary, secondary, etc.).
-- payer_name and plan_name are used to look up the patient's specific negotiated
-- rate in hospital_charges (BigQuery). These values must match (via LIKE) the
-- payer_name and plan_name columns in the MRF data.
create table public.insurance_plans (
  id                uuid primary key default gen_random_uuid(),
  profile_member_id uuid not null references public.profile_members(id) on delete cascade,
  payer_name        text not null,   -- Insurer name, e.g. "AETNA", "BLUE CROSS BLUE SHIELD"
  plan_name         text not null,   -- Plan name, e.g. "PPO GOLD", "HMO SELECT"
  member_id         text,            -- Insurance member ID (for dispute letters, not analysis)
  -- Plan type determines which benchmark strategies are valid:
  --   commercial: Medicare rate (benchmark) + negotiated rate (if MRF match found)
  --   medicare:   Medicare rate is the actual payment; negotiated rate not applicable
  --   medicaid:   State-specific rates; Medicare used as approximate benchmark only
  --   tricare:    Similar to Medicare
  --   self_pay:   No insurer; discounted_cash_price from MRF shown as alternative
  plan_type         text not null default 'commercial'
                      check (plan_type in ('commercial', 'medicare', 'medicaid', 'tricare', 'self_pay')),
  is_primary_plan   boolean not null default false,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);

create index insurance_plans_member_id_idx on public.insurance_plans (profile_member_id);

-- ─── Bills: add profile member + confirmed payer/plan ─────────────────────────
-- profile_member_id: the insured person this bill belongs to (may differ from user_id)
-- payer_name / plan_name: confirmed by user at verification time; denormalized so
--   past analysis is not affected if the user later edits their insurance profile.
-- confirmed_at: timestamp when user completed pre-analysis verification; NULL means
--   the bill was submitted without the verification step (legacy or fast-track).
alter table public.bills
  add column if not exists profile_member_id uuid references public.profile_members(id) on delete set null,
  add column if not exists payer_name        text,
  add column if not exists plan_name         text,
  add column if not exists confirmed_at      timestamptz;

create index bills_profile_member_id_idx on public.bills (profile_member_id);

-- ─── Updated_at triggers ──────────────────────────────────────────────────────
create trigger profile_members_updated_at
  before update on public.profile_members
  for each row execute function public.set_updated_at();

create trigger insurance_plans_updated_at
  before update on public.insurance_plans
  for each row execute function public.set_updated_at();

-- ─── Row Level Security ───────────────────────────────────────────────────────
alter table public.profile_members enable row level security;
alter table public.insurance_plans enable row level security;

create policy "profile_members: user isolation"
  on public.profile_members for all
  using (auth.uid() = user_id);

create policy "insurance_plans: user isolation"
  on public.insurance_plans for all
  using (
    exists (
      select 1 from public.profile_members
      where profile_members.id = insurance_plans.profile_member_id
        and profile_members.user_id = auth.uid()
    )
  );
