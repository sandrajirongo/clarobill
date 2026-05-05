-- Revert: restore year-based unique constraints, remove effective_from columns.

-- ─── cms_pfs_indicators ──────────────────────────────────────────────────────

alter table public.cms_pfs_indicators
  drop constraint if exists cms_pfs_indicators_unique;

drop index if exists public.cms_pfs_indicators_lookup_idx;

alter table public.cms_pfs_indicators
  add constraint cms_pfs_indicators_year_hcpc_modifier_key
  unique (year, hcpc, modifier);

create index cms_pfs_indicators_year_hcpc_idx
  on public.cms_pfs_indicators (year, hcpc);

alter table public.cms_pfs_indicators
  drop column if exists effective_from;

-- ─── cms_opps_cap ─────────────────────────────────────────────────────────────

alter table public.cms_opps_cap
  drop constraint if exists cms_opps_cap_unique;

drop index if exists public.cms_opps_cap_lookup_idx;

alter table public.cms_opps_cap
  add constraint cms_opps_cap_year_hcpc_modifier_locality_code_key
  unique (year, hcpc, modifier, locality_code);

create index cms_opps_cap_lookup_idx
  on public.cms_opps_cap (year, hcpc, modifier, locality_code);

alter table public.cms_opps_cap
  drop column if exists effective_from;
