-- Migration: 20260406000001_initial_schema
-- Creates core tables for ClaroBill: bills, line_items, analysis_results, payments

-- Enable UUID generation
create extension if not exists "pgcrypto";

-- ─── Bills ────────────────────────────────────────────────────────────────────
-- One row per uploaded medical bill. user_id references auth.users (Supabase Auth).
create table public.bills (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references auth.users(id) on delete cascade,
  file_name     text not null,
  -- Path within Supabase Storage bucket 'bills'
  file_path     text not null unique,
  file_size     integer not null check (file_size > 0 and file_size <= 20971520), -- 20MB max
  mime_type     text not null check (mime_type in ('application/pdf', 'image/jpeg', 'image/png')),
  status        text not null default 'uploading'
                  check (status in ('uploading', 'ocr_processing', 'analyzing', 'complete', 'failed')),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

create index bills_user_id_idx on public.bills (user_id);
create index bills_status_idx on public.bills (status);

-- ─── Line Items ───────────────────────────────────────────────────────────────
-- Individual CPT-coded charges extracted from a bill via OCR + parsing.
create table public.line_items (
  id                  uuid primary key default gen_random_uuid(),
  bill_id             uuid not null references public.bills(id) on delete cascade,
  cpt_code            text not null,
  description         text not null default '',
  service_date        date not null,
  quantity            integer not null default 1 check (quantity > 0),
  unit_charge         numeric(10, 2) not null check (unit_charge >= 0),
  total_charge        numeric(10, 2) not null check (total_charge >= 0),
  -- HCPCS modifier (e.g. '59' for distinct procedure, '25' for E&M same day)
  modifier            text,
  -- Diagnosis code pointers linking to claim form box 21 (e.g. ['A', 'B'])
  diagnosis_pointers  text[] not null default '{}'
);

create index line_items_bill_id_idx on public.line_items (bill_id);
create index line_items_cpt_code_idx on public.line_items (cpt_code);

-- ─── Analysis Results ─────────────────────────────────────────────────────────
-- AI + rules engine output for a bill. One-to-one with bills.
create table public.analysis_results (
  id                      uuid primary key default gen_random_uuid(),
  bill_id                 uuid not null unique references public.bills(id) on delete cascade,
  -- JSON array of BillingError objects (typed on the application layer)
  errors                  jsonb not null default '[]',
  total_charges           numeric(10, 2) not null,
  estimated_fair_value    numeric(10, 2) not null,
  total_potential_savings numeric(10, 2) not null,
  ai_summary              text not null default '',
  -- Storage paths for generated PDF report and dispute letter
  dispute_letter_url      text,
  report_url              text,
  created_at              timestamptz not null default now()
);

-- ─── Payments ─────────────────────────────────────────────────────────────────
-- Stripe payment records. Keeps billing separate from bill analysis.
create table public.payments (
  id                  uuid primary key default gen_random_uuid(),
  user_id             uuid not null references auth.users(id) on delete restrict,
  bill_id             uuid not null references public.bills(id) on delete restrict,
  stripe_session_id   text not null unique,
  stripe_payment_intent text,
  amount_cents        integer not null check (amount_cents > 0),
  currency            text not null default 'usd',
  status              text not null default 'pending'
                        check (status in ('pending', 'complete', 'failed', 'refunded')),
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

create index payments_user_id_idx on public.payments (user_id);
create index payments_stripe_session_id_idx on public.payments (stripe_session_id);

-- ─── Medicare Fee Schedule (reference data) ───────────────────────────────────
-- Loaded from CMS data via scripts/load_fee_schedule.py
create table public.medicare_fee_schedule (
  id              uuid primary key default gen_random_uuid(),
  cpt_code        text not null,
  -- MAC locality code (e.g. '0101' for Alabama MAC 1)
  locality_code   text not null,
  -- Facility vs non-facility (most outpatient = non-facility)
  facility_rate   numeric(10, 2) not null,
  non_facility_rate numeric(10, 2) not null,
  -- Year the schedule applies to
  year            integer not null,
  unique (cpt_code, locality_code, year)
);

create index medicare_fee_schedule_cpt_idx on public.medicare_fee_schedule (cpt_code);

-- ─── NCCI Edit Pairs (reference data) ────────────────────────────────────────
-- CMS National Correct Coding Initiative edit pairs for unbundling detection.
-- Loaded from scripts/load_ncci_edits.py
create table public.ncci_edit_pairs (
  id              uuid primary key default gen_random_uuid(),
  column_one_code text not null,  -- The "comprehensive" code
  column_two_code text not null,  -- The "component" code that can't be billed with column_one
  -- 0 = modifier not allowed; 1 = modifier may override; 9 = not applicable
  modifier_indicator integer not null check (modifier_indicator in (0, 1, 9)),
  effective_date  date not null,
  deletion_date   date,
  unique (column_one_code, column_two_code)
);

create index ncci_edit_pairs_col1_idx on public.ncci_edit_pairs (column_one_code);

-- ─── updated_at triggers ──────────────────────────────────────────────────────
create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger bills_updated_at
  before update on public.bills
  for each row execute function public.set_updated_at();

create trigger payments_updated_at
  before update on public.payments
  for each row execute function public.set_updated_at();

-- ─── Row Level Security ───────────────────────────────────────────────────────
-- Users can only access their own data. Enforced at DB level, not just app layer.

alter table public.bills enable row level security;
alter table public.line_items enable row level security;
alter table public.analysis_results enable row level security;
alter table public.payments enable row level security;

-- bills: users see only their own bills
create policy "bills: user isolation"
  on public.bills for all
  using (auth.uid() = user_id);

-- line_items: users see items for their own bills
create policy "line_items: user isolation"
  on public.line_items for all
  using (
    exists (
      select 1 from public.bills
      where bills.id = line_items.bill_id
        and bills.user_id = auth.uid()
    )
  );

-- analysis_results: users see results for their own bills
create policy "analysis_results: user isolation"
  on public.analysis_results for all
  using (
    exists (
      select 1 from public.bills
      where bills.id = analysis_results.bill_id
        and bills.user_id = auth.uid()
    )
  );

-- payments: users see only their own payments
create policy "payments: user isolation"
  on public.payments for all
  using (auth.uid() = user_id);

-- Reference tables are public read-only
alter table public.medicare_fee_schedule enable row level security;
alter table public.ncci_edit_pairs enable row level security;

create policy "medicare_fee_schedule: public read"
  on public.medicare_fee_schedule for select using (true);

create policy "ncci_edit_pairs: public read"
  on public.ncci_edit_pairs for select using (true);
