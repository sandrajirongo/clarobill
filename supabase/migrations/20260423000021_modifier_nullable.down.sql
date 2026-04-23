-- Revert modifier to NOT NULL DEFAULT '' in cms_pfs_indicators and cms_opps_cap.
--
-- WARNING: Any rows with modifier IS NULL must be updated to '' before applying,
-- otherwise the NOT NULL constraint will reject them.

-- ─── cms_pfs_indicators ──────────────────────────────────────────────────────

update public.cms_pfs_indicators set modifier = '' where modifier is null;

drop index if exists public.cms_pfs_indicators_base_unique;
drop index if exists public.cms_pfs_indicators_modifier_unique;
drop index if exists public.cms_pfs_indicators_lookup_idx;

alter table public.cms_pfs_indicators
  alter column modifier set not null,
  alter column modifier set default '';

create unique index cms_pfs_indicators_unique
  on public.cms_pfs_indicators (effective_from, hcpc, modifier);

create index cms_pfs_indicators_lookup_idx
  on public.cms_pfs_indicators (effective_from desc, hcpc, modifier);

-- ─── cms_opps_cap ─────────────────────────────────────────────────────────────

update public.cms_opps_cap set modifier = '' where modifier is null;

drop index if exists public.cms_opps_cap_base_unique;
drop index if exists public.cms_opps_cap_modifier_unique;
drop index if exists public.cms_opps_cap_lookup_idx;

alter table public.cms_opps_cap
  alter column modifier set not null,
  alter column modifier set default '';

create unique index cms_opps_cap_unique
  on public.cms_opps_cap (effective_from, hcpc, modifier, locality_code);

create index cms_opps_cap_lookup_idx
  on public.cms_opps_cap (effective_from desc, hcpc, modifier, locality_code);
