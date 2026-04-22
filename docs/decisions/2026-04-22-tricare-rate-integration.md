# Future Work: TRICARE Maximum Allowable Charge Integration

**Date:** 2026-04-22
**Status:** Planned — not built for beta
**Priority:** Post-launch, Phase 5

---

## Context

TRICARE is the healthcare program for active-duty military, veterans, and their
dependents, administered by the Defense Health Agency (DHA). TRICARE uses the same
RVU-based fee schedule methodology as Medicare but applies its own locality-adjusted
conversion factors, resulting in rates that are typically 110–120% of the equivalent
Medicare rate.

DHA publishes TRICARE Maximum Allowable Charges (TMAC) annually. These are the maximum
amounts TRICARE will pay for each CPT/HCPCS code in each locality, calculated as:

```
TRICARE rate = (RVU work × GPCI work + nonfacility PE RVU × GPCI PE + MP RVU × GPCI MP)
               × TRICARE conversion factor
```

TRICARE conversion factors are published separately from Medicare conversion factors
and differ slightly by locality.

For beta, the engine uses the Medicare PFS rate as a proxy for TRICARE bills with a
1.2× threshold (TRICARE pays ~110–120% of Medicare, so 1.2× gives a modest margin
above the expected maximum reimbursement). This catches egregious overcharges but
does not use the exact TRICARE rate.

---

## Decision

**Load TRICARE Maximum Allowable Charges from DHA published files.**
This is explicitly out of scope for beta. Build post-launch alongside or after the
Medicaid rate pipeline.

---

## What Needs to Be Built

### 1. Data source

DHA publishes TRICARE rates at:
- **URL:** `https://www.tricare.mil/pls/capp`
- **Format:** The TRICARE TMAC files are available as locality-specific rate tables
  (similar in structure to the Medicare GPCI + PFS combination).
- **Update cadence:** Annual (January 1), with mid-year corrections as needed.

The DHA also publishes locality files defining TRICARE geographic areas. TRICARE
localities do not map 1:1 to CMS MAC localities, so a separate locality resolution
table is required.

### 2. Normalized schema: `tricare_rates` + `tricare_localities` tables

```sql
CREATE TABLE tricare_localities (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    tricare_area    varchar(10) NOT NULL,       -- TRICARE area code (e.g. 'NORTH', 'SOUTH')
    state           char(2) NOT NULL,
    county_name     varchar(100),
    is_rest_of_state boolean DEFAULT false,
    year            int NOT NULL,
    CONSTRAINT tricare_localities_unique UNIQUE (state, county_name, year)
);

CREATE TABLE tricare_rates (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    hcpc            varchar(10) NOT NULL,
    modifier        varchar(2) NOT NULL DEFAULT '',
    tricare_area    varchar(10) NOT NULL,
    rate            numeric(10, 2) NOT NULL,
    effective_date  date NOT NULL,
    loaded_at       timestamptz DEFAULT now(),
    CONSTRAINT tricare_rates_unique UNIQUE (hcpc, modifier, tricare_area, effective_date)
);

CREATE INDEX tricare_rates_lookup_idx
    ON tricare_rates (hcpc, tricare_area, effective_date DESC);
```

### 3. Loader script: `scripts/load_tricare_rates.py`

Follows the same pattern as `scripts/load_cms_pfs.py`:
- Downloads TMAC files from DHA
- Normalizes to the `tricare_rates` schema
- Upserts via the Supabase service role client
- Handles the TRICARE locality file to populate `tricare_localities`

### 4. Rate lookup integration in `bills.py`

Add `_load_tricare_rates(supabase, cpt_codes, state, county, rate_date)` that:
1. Resolves the TRICARE area from `tricare_localities` using state/county
2. Queries `tricare_rates` WHERE `hcpc IN (?)` AND `tricare_area = ?` AND
   `effective_date <= service_date`
3. Falls back to the Medicare PFS rate (× 1.15 approximation) if the TRICARE
   table is empty or the locality cannot be resolved

The `PRICE_OUTLIER` threshold for `plan_type='tricare'` should then be 1.05× the
actual TRICARE TMAC rate rather than 1.2× the Medicare proxy.

### 5. NCCI context

TRICARE already maps to `payer_type='medicare'` for NCCI PTP and MUE lookups —
this is correct and does not need to change. TRICARE follows Medicare NCCI edits.

---

## Why Not Build This for Beta

- **Scope:** Requires parsing a new set of DHA locality and rate files that are
  structurally similar to CMS PFS files but not identical. Estimated 1–2 weeks.
- **Beta accuracy is sufficient:** At 1.2× Medicare proxy, the engine catches
  any TRICARE overcharge above roughly 120% of the Medicare rate. The TRICARE
  rate is almost never more than 120% of Medicare, so false negatives are rare.
- **User base:** Active military and veterans are a meaningful but not dominant
  segment of the beta user base. TRICARE-specific precision is a v2 improvement.

---

## Acceptance Criteria (when this is built)

- [ ] `tricare_localities` table populated for all TRICARE geographic areas
- [ ] `tricare_rates` table populated for the current year
- [ ] `_load_tricare_rates()` in `bills.py` falls back to Medicare proxy when
  TRICARE table is empty or locality unresolvable
- [ ] `PRICE_OUTLIER` for `plan_type='tricare'` uses TMAC rate when available
- [ ] Loader script added to `scripts/` with usage documented in `scripts/README.md`
- [ ] All existing tests still pass; new tests added for TRICARE rate lookup
- [ ] Annual Cloud Scheduler update job documented
