-- Migration: 20260420000018_ncci_mue_effective_date
-- Adds effective_date to ncci_mue_limits so MUE lookups can be date-aware.
-- A bill from 2022 should use the MUE limits that were in effect in 2022,
-- not the current values. This mirrors the existing ncci_edit_pairs design
-- which already stores effective_date + deletion_date per row.

alter table public.ncci_mue_limits
  add column effective_date date not null default '2020-01-01';

-- Replace the single-row-per-code unique constraint with one that allows
-- one row per (code, service_type, payer_type, quarter).
alter table public.ncci_mue_limits
  drop constraint ncci_mue_limits_hcpcs_code_service_type_payer_type_key;

alter table public.ncci_mue_limits
  add constraint ncci_mue_limits_unique
    unique (hcpcs_code, service_type, payer_type, effective_date);

create index ncci_mue_limits_effective_date_idx
  on public.ncci_mue_limits (effective_date);
