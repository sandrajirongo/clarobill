-- Make modifier column nullable in cms_pfs_indicators and cms_opps_cap.
--
-- The original schema defined modifier TEXT NOT NULL DEFAULT '', but the CMS source
-- files and loader scripts store NULL for rows with no modifier. PostgreSQL unique
-- constraints treat each NULL as distinct, so the NOT NULL constraint was the only
-- thing preventing duplicate base rows — and that constraint was silently violated
-- by the bulk-insert RPC functions.
--
-- The engine queries now use .is_("modifier", "null") which correctly matches NULLs.
-- This migration aligns the schema with the actual data.
--
-- Uniqueness is preserved via partial unique indexes, which give the correct semantics:
--   - base (no-modifier) rows: unique on (effective_from, hcpc) WHERE modifier IS NULL
--   - modifier rows: unique on (effective_from, hcpc, modifier) WHERE modifier IS NOT NULL
-- A standard UNIQUE on (effective_from, hcpc, modifier) would treat NULLs as distinct
-- and allow unlimited duplicate base rows, which is wrong.

-- ─── cms_pfs_indicators ──────────────────────────────────────────────────────

alter table public.cms_pfs_indicators
  drop constraint cms_pfs_indicators_unique;

drop index if exists public.cms_pfs_indicators_lookup_idx;

alter table public.cms_pfs_indicators
  alter column modifier drop not null,
  alter column modifier drop default;

-- Partial unique index: at most one base row per (effective_from, hcpc)
create unique index cms_pfs_indicators_base_unique
  on public.cms_pfs_indicators (effective_from, hcpc)
  where modifier is null;

-- Partial unique index: at most one row per (effective_from, hcpc, modifier) for modifier rows
create unique index cms_pfs_indicators_modifier_unique
  on public.cms_pfs_indicators (effective_from, hcpc, modifier)
  where modifier is not null;

-- Lookup index scoped to base rows — matches the .is_("modifier", "null") query pattern
create index cms_pfs_indicators_lookup_idx
  on public.cms_pfs_indicators (effective_from desc, hcpc)
  where modifier is null;

-- ─── cms_opps_cap ─────────────────────────────────────────────────────────────

alter table public.cms_opps_cap
  drop constraint cms_opps_cap_unique;

drop index if exists public.cms_opps_cap_lookup_idx;

alter table public.cms_opps_cap
  alter column modifier drop not null,
  alter column modifier drop default;

create unique index cms_opps_cap_base_unique
  on public.cms_opps_cap (effective_from, hcpc, locality_code)
  where modifier is null;

create unique index cms_opps_cap_modifier_unique
  on public.cms_opps_cap (effective_from, hcpc, modifier, locality_code)
  where modifier is not null;

create index cms_opps_cap_lookup_idx
  on public.cms_opps_cap (effective_from desc, hcpc, locality_code)
  where modifier is null;
