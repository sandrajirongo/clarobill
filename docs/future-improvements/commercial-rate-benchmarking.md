# Future Improvement: Commercial Insurance Rate Benchmarking

**Status:** Partially built — exact negotiated rate check exists but has narrow coverage  
**Priority:** High — commercial is the largest plan type in our user base  
**Related:** `apps/engine/app/api/v1/bills.py` (`_load_negotiated_charges`, `_detect_negotiated_rate_exceeded`)

---

## What we currently do for commercial plans

The engine handles commercial plan benchmarking in two tiers:

### Tier 1 — Exact negotiated rate (NEGOTIATED_RATE_EXCEEDED rule)

`_load_negotiated_charges()` queries the hospital's own MRF price transparency file in BigQuery,
filtered to the patient's specific payer and plan name. When it finds a match, the engine
compares the billed charge directly against the contracted rate — the strongest possible
benchmark, because this is the exact dollar amount the hospital agreed to accept.

**This only fires when all of the following are true:**
1. The hospital is in our BigQuery `hospital_directory` (currently ~3,100 of ~7,000)
2. The hospital published per-payer negotiated rates in their MRF (not all do — many publish
   only gross charges, or publish negotiated rates as percentage multipliers rather than dollar amounts)
3. The patient's payer name and plan name are confirmed (user completed the insurance step)
4. The payer/plan name matches the MRF data (MRF naming conventions vary wildly — "Blue Cross
   Blue Shield of California" vs "BCBS CA" vs "Anthem Blue Cross" are all the same payer but
   may not substring-match)

In practice, this fires on a small minority of commercial bills.

### Tier 2 — Medicare proxy (PRICE_OUTLIER rule)

For any commercial bill where Tier 1 produces no data, the engine falls back to:
```
flag if charge > medicare_rate × 1.80
```

1.80× Medicare is intentionally permissive. Most commercial rates are 1.2–1.6× Medicare.
Using 1.80× means we only flag charges that exceed the highest plausible commercial rate —
catching only the most egregious overcharges, not the typical 10–30% above-contract overcharge
that is far more common.

### The gap

A user with commercial insurance (the most common plan type) who goes to a hospital not in our
BigQuery database — or whose hospital does not publish per-payer rates — gets only the 1.80×
Medicare fallback. A charge of 1.6× Medicare would not be flagged even if it is 40% above what
their insurance actually contracted to pay.

---

## What good commercial benchmarking would look like

### Option A — Scale the MRF pipeline (highest value, already planned)

The MRF discovery pipeline (`docs/future_improvements/mrf-discovery-pipeline.md`) is designed
to expand hospital coverage from ~3,100 to ~7,000 hospitals. Hospital MRF files contain
per-payer negotiated rates for most major commercial insurers. Once the pipeline is built:

- Coverage of `NEGOTIATED_RATE_EXCEEDED` goes from ~45% of hospitals to ~98%
- Per-payer rate accuracy improves dramatically — no more 1.80× proxy for most commercial bills

This is the right long-term fix and is already planned. No new data infrastructure needed beyond
what the MRF pipeline already designs.

**Dependency:** MRF discovery pipeline must be built first.

### Option B — Per-payer national rate distribution

Once we have negotiated rates from ~7,000 hospitals across all major payers, we can aggregate:

```sql
SELECT
  payer_name,
  code,
  PERCENTILE_CONT(negotiated_charge, 0.5) AS median_rate,
  PERCENTILE_CONT(negotiated_charge, 0.75) AS p75_rate,
  PERCENTILE_CONT(negotiated_charge, 0.90) AS p90_rate
FROM hospital_charges
WHERE negotiated_type IN ('negotiated', 'derived')
  AND negotiated_charge > 0
GROUP BY payer_name, code
```

This produces a national commercial rate distribution per payer per code. A charge above
the p90 for that payer nationally is a strong signal of an overcharge even without a
hospital-specific match.

**How it would be used:**
- User confirms "Blue Shield of California" as their payer
- We fuzzy-match to payer groups in our distribution table
- If billed charge > p90 for that payer nationally → flag as COMMERCIAL_RATE_OUTLIER
- Threshold: p90 is conservative (only flags outliers), p75 is tighter

**New table: `commercial_rate_benchmarks`**
```sql
CREATE TABLE commercial_rate_benchmarks (
  payer_group     TEXT NOT NULL,   -- normalized payer name (e.g. "blue_cross_blue_shield")
  code            TEXT NOT NULL,
  median_rate     NUMERIC(10,2),
  p75_rate        NUMERIC(10,2),
  p90_rate        NUMERIC(10,2),
  sample_count    INT,             -- number of hospitals in the distribution
  as_of_date      DATE NOT NULL,
  PRIMARY KEY (payer_group, code, as_of_date)
);
```

**Dependency:** MRF discovery pipeline + sufficient MRF data loaded to build a meaningful distribution.

### Option C — FAIR Health commercial benchmarks (paid data)

FAIR Health is a non-profit that maintains the largest database of private insurance claims in
the US (~40 billion claims). They publish benchmark rates for commercial procedures by geography.

- **Cost:** FAIR Health API access ranges from ~$5,000–$50,000/year depending on query volume
- **Coverage:** All CPT codes, all US ZIP codes, all major commercial payers (aggregated)
- **Format:** API endpoint returning the 50th/80th/90th percentile charge for a code by ZIP

This would give us a commercial rate benchmark even before the MRF pipeline is built. The
tradeoff is dependency on a paid vendor and ongoing licensing cost.

**Not recommended for beta** — the MRF pipeline covers the same ground at near-zero cost once
built. Worth revisiting if MRF pipeline is delayed beyond Q3 post-launch.

### Option D — State all-payer claims databases (APCDs)

~25 states operate All-Payer Claims Databases that capture commercial insurance claim data.
These are authoritative but access varies by state:

- Some states provide bulk data access for researchers (slow, requires application)
- Some states provide API access (rare)
- Some states restrict access to in-state researchers only

Coverage is incomplete nationally and the administrative overhead to access APCD data in 25
states is significant. Not recommended as a primary path.

---

## Recommended implementation sequence

**Now (already built):**
- Exact negotiated rate via hospital MRF BigQuery data — works when hospital is in database and payer matches
- 1.80× Medicare fallback for all other commercial bills

**Post-launch Phase 1 (build MRF pipeline):**
- Expand hospital MRF coverage from ~3,100 → ~7,000 hospitals
- `NEGOTIATED_RATE_EXCEEDED` fires on vastly more commercial bills with exact rates

**Post-launch Phase 2 (aggregate distribution):**
- Build `commercial_rate_benchmarks` from aggregated MRF data
- Add `COMMERCIAL_RATE_OUTLIER` rule using p90 national distribution per payer
- Tighten the fallback threshold from 1.80× to something informed by actual distribution data

**Later (optional):**
- Evaluate FAIR Health API if distribution coverage is still thin after Phase 1+2

---

## Payer name normalization (prerequisite for Phase 2)

The biggest practical challenge for any cross-hospital commercial rate analysis is that MRF
files use inconsistent payer naming. The same insurer appears as:

| Hospital A MRF | Hospital B MRF | Hospital C MRF |
|---|---|---|
| "Blue Cross Blue Shield of California" | "BCBS CA" | "Anthem Blue Cross" |
| "UnitedHealthcare Choice Plus" | "UHC" | "United Healthcare" |
| "Aetna PPO" | "Aetna" | "AETNA HEALTH INC" |

Before building any national rate distribution, a payer normalization table is needed:

```sql
CREATE TABLE payer_name_aliases (
  alias           TEXT NOT NULL PRIMARY KEY,  -- as it appears in MRF data
  payer_group     TEXT NOT NULL,              -- normalized key
  payer_display   TEXT NOT NULL              -- human-readable name for reports
);
```

This table would be seeded from CMS's payer taxonomy data and refined manually as new MRF
naming variations are discovered. The `CONTAINS_SUBSTR` matching in `_load_negotiated_charges`
is a stopgap — normalization is the long-term solution.

---

## Engine changes required (Phase 2)

### New rule in rules_engine.py

```python
def _detect_commercial_rate_outlier(
    self, line_items: list[ParsedLineItem]
) -> list[DetectedError]:
    """Flag commercial charges above the p90 national rate for this payer group.

    Only fires when:
      - plan_type is 'commercial'
      - commercial_benchmarks is populated (payer matched our normalization table)
      - charge exceeds the p90 benchmark for this payer group + code combination
    """
    ...
```

### New RulesEngine constructor parameter

```python
commercial_benchmarks: dict[str, Decimal] | None = None  # cpt_code → p90_rate
```

### New loader in bills.py

```python
def _load_commercial_benchmarks(
    bq: bigquery.Client | None,
    cpt_codes: list[str],
    payer_name: str | None,
    rate_date: date,
) -> dict[str, Decimal]:
    """Load p90 national commercial rates for this payer group and code set."""
    ...
```

---

*Document created: April 2026*  
*Owner: ClaroBill Engineering*  
*Related: `docs/future_improvements/mrf-discovery-pipeline.md`,
`apps/engine/app/api/v1/bills.py`, `apps/engine/app/services/rules_engine.py`*
