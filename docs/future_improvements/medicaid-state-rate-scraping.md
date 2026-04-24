# Future Work: Medicaid State Rate Scraping Pipeline

**Date:** 2026-04-22
**Status:** Planned — not built for beta
**Priority:** Post-launch, Phase 5

---

## Context

CMS does not publish a national Medicaid physician fee schedule. Unlike the Medicare
Physician Fee Schedule (a single annual ZIP file covering all ~10,000 CPT codes for
every locality in the country), Medicaid rates are set independently by each of the
50 states, DC, and US territories. Each publishes in a different format, on a
different schedule, through a different portal, and with different code coverage.

For the beta version, the engine uses the Medicare PFS rate as a proxy benchmark for
Medicaid bills with a 1.05× threshold (since Medicaid pays 70–90% of Medicare, any
charge above the Medicare rate already exceeds what Medicaid would reimburse). This is
accurate enough to catch egregious overcharges but misses overcharges in the range of
what Medicaid actually pays up to the Medicare rate.

---

## Decision

**Build a state-by-state Medicaid fee schedule scraping and normalization pipeline.**
This is explicitly out of scope for beta. It should be planned as a post-launch
data infrastructure project.

---

## What Needs to Be Built

### 1. State portal discovery and cataloguing

Each state publishes its fee schedule differently. Before any scraping can begin,
the source for each state must be identified and documented:

| State type | Common publication formats |
|---|---|
| ~15 states | Machine-readable CSV or Excel (easiest — direct download) |
| ~20 states | PDF rate tables (requires PDF extraction + normalization) |
| ~10 states | Provider portal login required (requires credentialed scraping) |
| ~5 states | Medicaid managed care only — no unified FFS fee schedule |

A one-time cataloguing pass is needed to map all 51 jurisdictions before any
automation is built.

### 2. Scraper per state (or per format class)

Rather than 50 individual scrapers, build format-class scrapers:
- **CSV/Excel scraper:** Direct download + pandas normalization → Supabase upsert
- **PDF scraper:** PDF download → pdfplumber extraction → rate parsing → Supabase upsert
- **Portal scraper:** Selenium/Playwright with state credentials → rate extraction

Each scraper must output to a normalized schema (see below).

### 3. Normalized schema: `cms_medicaid_rates` table

```sql
CREATE TABLE cms_medicaid_rates (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    state           char(2) NOT NULL,          -- FIPS state code (e.g. 'CA', 'TX')
    hcpc            varchar(10) NOT NULL,       -- CPT or HCPCS Level II code
    modifier        varchar(2) NOT NULL DEFAULT '',
    rate            numeric(10, 2) NOT NULL,    -- Medicaid fee schedule rate in USD
    effective_date  date NOT NULL,
    source_url      text,                       -- original publication URL
    loaded_at       timestamptz DEFAULT now(),
    CONSTRAINT cms_medicaid_rates_pkey UNIQUE (state, hcpc, modifier, effective_date)
);

CREATE INDEX cms_medicaid_rates_state_hcpc_idx
    ON cms_medicaid_rates (state, hcpc, modifier, effective_date DESC);
```

### 4. Rate lookup integration in `bills.py`

Once the table is populated, `_load_medicare_rates` should be extended (or a
parallel `_load_medicaid_rates` function added) that:

1. Takes `state` from the bill's locality context
2. Queries `cms_medicaid_rates` WHERE `state = ?` AND `hcpc IN (?)` AND
   `effective_date <= service_date`
3. Falls back to the Medicare PFS rate if no state Medicaid rate is available
   for a given code

The `PRICE_OUTLIER` rule threshold for `plan_type='medicaid'` should then compare
against the actual state Medicaid rate (with 1.05× tolerance) rather than the
Medicare rate proxy.

### 5. Update cadence

Most states update their fee schedules annually (January 1) with some mid-year
corrections. The scraper should be scheduled quarterly via Cloud Scheduler to
catch mid-year updates. A `last_checked` timestamp per state should be maintained
to avoid redundant downloads.

---

## Why Not Build This for Beta

- **Scope:** 50+ separate data sources, each requiring custom extraction logic.
  This is a 4–6 week engineering effort minimum.
- **Maintenance burden:** State portals change URLs, formats, and schedules without
  notice. This requires ongoing maintenance and monitoring.
- **Beta accuracy is sufficient:** The 1.05× Medicare threshold catches any charge
  above Medicare rates for Medicaid patients, which is already a strong signal.
  True Medicaid-specific flagging is a precision improvement, not a correctness fix.
- **User base:** Beta users with Medicaid coverage are a minority of the initial
  target segment. The improvement in precision does not justify the build cost
  pre-launch.

---

## Acceptance Criteria (when this is built)

- [ ] All 50 states + DC catalogued with source URL and format type
- [ ] At least the 10 highest-Medicaid-enrollment states scraped and loaded
  (CA, TX, NY, FL, IL, PA, OH, GA, NC, MI)
- [ ] `cms_medicaid_rates` table populated with ≥ 500 CPT codes per loaded state
- [ ] `_load_medicaid_rates()` in `bills.py` falls back to Medicare PFS when state
  not loaded
- [ ] `PRICE_OUTLIER` for `plan_type='medicaid'` uses state rate when available,
  Medicare proxy otherwise
- [ ] All existing tests still pass; new integration tests added for state rate lookup
- [ ] Quarterly Cloud Scheduler job created and documented
