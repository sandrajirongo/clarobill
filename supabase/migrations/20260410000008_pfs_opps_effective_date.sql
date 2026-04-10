-- Add effective_from to cms_pfs_indicators and cms_opps_cap for sub-year precision.
--
-- Previously both tables used `year INTEGER` as the temporal key, which meant all
-- four CMS quarterly releases within a year (Jan, Apr, Jul, Oct) would collide on
-- the unique constraint and only the last-loaded release would survive.
--
-- With effective_from we store each quarterly release separately. The engine picks
-- the most recent release with effective_from <= the bill's service date, matching
-- the pattern already used by cms_anesthesia_cf.
--
-- Key data findings that motivate this change:
--   - 2024 had a Congressional CF correction (Mar 9, signed retroactive to Jan 1):
--     JAN CF = $32.7442 → JANR CF = $33.2875 (+1.66% on all ~15k active codes).
--     On a $10k bill this is ~$166. This is the primary financial motivation.
--   - OPPS 2024 mirrors the same correction: 3,901 of 3,902 facility prices changed
--     by the same 1.0166 ratio between the JAN and JANR releases.
--   - New codes are added every quarter (14–382 per release). Without sub-year dates,
--     a bill using a code added in July would return no benchmark for that code.
--
-- Backfill: existing rows are assigned Jan 1 of their stored year, which is correct
-- since all previously loaded data was the annual (APR) release treated as a single
-- year-level entry.
--
-- The lookup pattern (matching cms_anesthesia_cf) is:
--   .lte("effective_from", str(service_date)).order("effective_from", desc=True)

-- ─── cms_pfs_indicators ──────────────────────────────────────────────────────

alter table public.cms_pfs_indicators
  add column effective_from date;

update public.cms_pfs_indicators
  set effective_from = make_date(year, 1, 1);

alter table public.cms_pfs_indicators
  alter column effective_from set not null;

alter table public.cms_pfs_indicators
  drop constraint cms_pfs_indicators_year_hcpc_modifier_key;

alter table public.cms_pfs_indicators
  add constraint cms_pfs_indicators_unique
  unique (effective_from, hcpc, modifier);

drop index if exists public.cms_pfs_indicators_year_hcpc_idx;

create index cms_pfs_indicators_lookup_idx
  on public.cms_pfs_indicators (effective_from desc, hcpc, modifier);

-- ─── cms_opps_cap ─────────────────────────────────────────────────────────────

alter table public.cms_opps_cap
  add column effective_from date;

update public.cms_opps_cap
  set effective_from = make_date(year, 1, 1);

alter table public.cms_opps_cap
  alter column effective_from set not null;

alter table public.cms_opps_cap
  drop constraint cms_opps_cap_year_hcpc_modifier_locality_code_key;

alter table public.cms_opps_cap
  add constraint cms_opps_cap_unique
  unique (effective_from, hcpc, modifier, locality_code);

drop index if exists public.cms_opps_cap_lookup_idx;

create index cms_opps_cap_lookup_idx
  on public.cms_opps_cap (effective_from desc, hcpc, modifier, locality_code);
