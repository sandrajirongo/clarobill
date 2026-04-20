-- Migration: 20260420000017_ncci_insurance_mue
-- Adds insurance-type and service-type awareness to NCCI edits, and creates the
-- ncci_mue_limits table for Medically Unlikely Edit (MUE) violation detection.

-- ─── Extend ncci_edit_pairs ───────────────────────────────────────────────────
-- service_type: which bill type the PTP edit applies to
-- payer_type:   which insurance programme's NCCI file the edit came from
alter table public.ncci_edit_pairs
  add column service_type text not null default 'practitioner'
    check (service_type in ('practitioner', 'outpatient', 'dme')),
  add column payer_type text not null default 'medicare'
    check (payer_type in ('medicare', 'medicaid'));

-- Replace the old unique constraint with one that includes both new columns so
-- the same code pair can exist once per (service_type, payer_type) combination.
alter table public.ncci_edit_pairs
  drop constraint ncci_edit_pairs_column_one_code_column_two_code_key;

alter table public.ncci_edit_pairs
  add constraint ncci_edit_pairs_unique
    unique (column_one_code, column_two_code, service_type, payer_type);

-- Backfill existing rows (loaded from MCD PTP Practitioner file = Medicare practitioner)
update public.ncci_edit_pairs
  set service_type = 'practitioner', payer_type = 'medicare';

-- ─── Add plan_type to bills ───────────────────────────────────────────────────
-- Persists the insurance type confirmed at verification time.
-- Used by the engine to select the correct NCCI edit set and apply rules
-- at the appropriate severity level for the payer.
alter table public.bills
  add column plan_type text
    check (plan_type in ('commercial', 'medicare', 'medicaid', 'tricare', 'self_pay'));

-- ─── ncci_mue_limits ─────────────────────────────────────────────────────────
-- Maximum allowed units per HCPCS/CPT code per claim / date of service.
-- Loaded from CMS MUE files via scripts/load_mue_limits.py.
create table public.ncci_mue_limits (
  id                    uuid primary key default gen_random_uuid(),
  hcpcs_code            text not null,
  service_type          text not null default 'practitioner'
                          check (service_type in ('practitioner', 'outpatient', 'dme')),
  payer_type            text not null default 'medicare'
                          check (payer_type in ('medicare', 'medicaid')),
  mue_value             integer not null check (mue_value >= 0),
  -- CMS MUE Adjudication Indicator (MAI):
  --   0 = Unknown — MCD files do not include this field; treat conservatively
  --   1 = Claim Edit — sum all lines with same code+date; must not exceed MUE
  --   2 = Date of Service Edit: Policy — each individual line must not exceed MUE (hard denial)
  --   3 = Date of Service Edit: Clinical — each line must not exceed MUE (may be overridden
  --       with supporting documentation; flag as warning)
  adjudication_indicator integer not null default 0
                          check (adjudication_indicator in (0, 1, 2, 3)),
  mue_rationale         text not null default '',
  unique (hcpcs_code, service_type, payer_type)
);

create index ncci_mue_limits_hcpcs_idx on public.ncci_mue_limits (hcpcs_code);
create index ncci_mue_limits_service_payer_idx on public.ncci_mue_limits (service_type, payer_type);

alter table public.ncci_mue_limits enable row level security;
create policy "ncci_mue_limits: public read"
  on public.ncci_mue_limits for select using (true);
