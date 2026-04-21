# Rules Engine Architecture

**Date:** 2026-04-19  
**Updated:** 2026-04-20 — Added MUE detection, insurance-type-aware NCCI loading, date-aware NCCI lookups for historical bills  
**Status:** Active

---

## Context

ClaroBill's rules engine is the core analytical layer of the product. It receives a parsed list of line items from a medical bill and applies a battery of rules to detect billing errors. This document explains what each rule does, why the engine is designed the way it is, and the deliberate choices behind the data sources and thresholds.

---

## Why Medicare Is the Primary Benchmark

Medicare is the *only publicly available, nationally consistent price schedule* for medical procedures in the United States. Specifically:

- **CMS Physician Fee Schedule (PFS):** Published annually by the Centers for Medicare & Medicaid Services. Covers ~10,000 CPT codes with locality-adjusted rates for every county in the country.
- **Outpatient Prospective Payment System (OPPS):** Published rates for procedures performed in hospital outpatient settings.
- **Ambulance Fee Schedule (AFS):** Published rates for ambulance services, adjusted by urban/rural/super-rural geography.

No equivalent public benchmark exists for commercial insurance. Medicaid rates vary by state and are not published in a machine-readable national format. Commercial payer rates are trade secrets negotiated privately between providers and insurers.

**Medicare is used as a floor signal, not an exact payment target.** It tells us what the federal government has determined is a reasonable payment for a procedure in a given geography. Charges well above this floor — after accounting for normal commercial markup — are statistically unlikely to be legitimate and warrant review.

**Age is not a limitation.** While Medicare *coverage* is primarily for people 65+, the Medicare *fee schedule* is the published benchmark for what procedures cost. A 30-year-old on commercial insurance who is charged $1,200 for a procedure that Medicare pays $80 has the same grounds for dispute as a 70-year-old on Medicare.

---

## Threshold Design

The engine uses two distinct threshold types because different benchmarks have different precision:

### `medicare_outlier_threshold` = 1.8 (80% above Medicare)

Used for rules where the benchmark is a Medicare-published rate:
- **PRICE_OUTLIER** — charge vs. Medicare PFS non-facility rate
- **FACILITY_CHARGE_OUTLIER** — facility charge vs. OPPS cap
- **AMBULANCE_CHARGE_OUTLIER** — ambulance charge vs. AFS rate

**Why 1.8×?** Commercial payers negotiate rates with providers, typically landing at 120–250% of Medicare (1.2–2.5×). The average is roughly 1.4–1.5× for most procedures. A threshold of 1.8× therefore:

- **Does not flag** a $140 charge for a procedure Medicare pays $100 (1.4× = normal commercial)
- **Does not flag** a $150 charge for a procedure Medicare pays $100 (1.5× = high-end but not unusual)
- **Flags** a $185 charge for a procedure Medicare pays $100 (1.85× = exceeds maximum expected commercial markup)

Setting the threshold too low (e.g. 1.1×) would generate false positives on every commercial bill, destroying signal and trust. 1.8× is calibrated to catch only the outliers that even generous commercial markups cannot explain.

### `exact_price_threshold` = 1.1 (10% above agreed/published price)

Used for rules where the benchmark is the exact agreed or published price:
- **HOSPITAL_CHARGE_OUTLIER** — charge vs. hospital's own chargemaster (gross charge)
- **NEGOTIATED_RATE_EXCEEDED** — charge vs. the specific rate the insurer contracted with this hospital

**Why 1.1×?** These benchmarks are not approximations — they are the actual agreed or published price for this patient at this hospital under this plan. There is no insurance-type ambiguity. The 10% tolerance exists solely to handle minor rounding and situations where a unit charge vs. total charge discrepancy causes a small apparent overage. Anything above 10% over an agreed price is an error.

---

## Data Sources

| Data | Source | Table in Supabase | Used By |
|------|---------|-------------------|---------|
| Medicare PFS rates | CMS Physician Fee Schedule ZIP file | `cms_pfs_indicators` | PRICE_OUTLIER |
| NCCI PTP edit pairs | CMS MCD/MCR PTP files (tab-delimited) | `ncci_edit_pairs` | NCCI_UNBUNDLING |
| NCCI MUE limits | CMS MCR MUE CSV + MCD TXT files (2020–2026, all quarters) | `ncci_mue_limits` | MUE_EXCEEDED |
| CPT proc_stat flags | CMS PFS status indicators | `cms_pfs_indicators` | NON_PAYABLE_CODE |
| HCPCS Level II codes | CMS HCPCS code file | `cms_hcpcs_codes` | NON_PAYABLE_CODE, TERMINATED_CODE_BILLED |
| Anesthesia conversion factor | CMS PFS locality file | `cms_anesthesia_cf` | ANESTHESIA_OUTLIER |
| Anesthesia base units | CMS PFS anesthesia base unit table | `cms_anesthesia_base_units` | ANESTHESIA_OUTLIER |
| OPPS payment caps | CMS OPPS addendum B | `cms_opps_cap` | FACILITY_CHARGE_OUTLIER |
| Ambulance Fee Schedule | CMS AFS final rule tables | `cms_ambulance_rates` | AMBULANCE_CHARGE_OUTLIER |
| Hospital gross charges | CMS price transparency MRF files | BigQuery `hospital_charges` | HOSPITAL_CHARGE_OUTLIER |
| Negotiated rates | CMS price transparency MRF files | BigQuery `hospital_charges` | NEGOTIATED_RATE_EXCEEDED |

---

## Rules Reference

### 1. DUPLICATE_CHARGE

**What:** Flags identical CPT code + service date combinations billed more than once.

**Why it fires:** Each CPT code should appear once per service date unless the quantity field reflects repetition (e.g., daily hospital visits billed with quantity=3). A duplicate CPT on the same date with quantity=1 is almost certainly an error.

**Estimated overcharge:** Full charge of the duplicate line item.

**Severity:** Critical

---

### 2. PRICE_OUTLIER

**What:** Flags charges exceeding 1.8× the Medicare PFS non-facility rate for that CPT code.

**Why it fires:** Even with the most generous commercial markup, legitimate charges rarely exceed 1.5× Medicare. Charges above 1.8× suggest upcoding, billing for bundled supplies, or data entry error.

**Benchmark:** Medicare PFS non-facility rate, locality-adjusted.

**Estimated overcharge:** Billed amount minus Medicare rate (not minus threshold — we report how much above Medicare, not how much above the threshold).

**Severity:** Warning (not critical because commercial plans legitimately pay above Medicare; the patient should ask for justification, not assume fraud).

---

### 3. NCCI_UNBUNDLING

**What:** Detects pairs of CPT codes where one is defined by CMS as a component of the other.

**Why it fires:** CMS NCCI edits define thousands of procedure pairs where billing both codes separately ("unbundling") is improper. The component procedure's payment is included in the comprehensive procedure.

**Override:** Modifier 59 (Distinct Procedural Service) on the component code is respected — it legitimately overrides some NCCI edits when procedures occur on distinct anatomical sites.

**Estimated overcharge:** Full charge of the component (bundled) code.

**Severity:** Critical

---

### 4. NON_PAYABLE_CODE

**What:** Flags CPT/HCPCS codes that CMS has marked as non-payable in the Physician Fee Schedule.

**proc_stat values checked:**
- `I` (Inactive): Code has been retired. Medicare will not pay it.
- `B` (Bundled): Payment is always included in another procedure. Billing separately is improper unbundling.
- `N` (Non-covered): Service is excluded from Medicare. Patient may not be required to pay without an Advance Beneficiary Notice (ABN).

**Severity:** Critical for I/B, Warning for N.

---

### 5. ANESTHESIA_OUTLIER

**What:** Flags anesthesia charges that imply impossible or implausible unit counts.

**Why it fires:** Anesthesia is billed by a formula: `(base units + time units) × locality conversion factor`. Working backwards from the billed charge, the engine derives implied base and total units. Impossible values (implied base < 0, implied base > 25, implied total > 80) indicate a billing error or incorrect conversion factor application.

**How time units are derived:** `anesthesia_minutes / 15` (one unit = 15 minutes, per CMS rules).

**Severity:** Critical for impossible values, Warning for ceiling breaches when no OCR time is available.

---

### 6. FACILITY_CHARGE_OUTLIER

**What:** Flags hospital outpatient facility charges exceeding 1.8× the OPPS payment cap.

**Why it fires:** The OPPS cap is Medicare's determined payment for outpatient procedures. Charges well above this rate affect the patient's cost-sharing and may reflect facility fee inflation.

**When active:** Only when OPPS rates are loaded for the locality (requires the bill to be identified as a hospital outpatient bill and the locality code to be resolved).

**Severity:** Warning

---

### 7. AMBULANCE_CHARGE_OUTLIER

**What:** Flags ambulance charges exceeding 1.8× the Medicare Ambulance Fee Schedule rate.

**Why it fires:** Ambulance billing fraud and error are among the most common in healthcare (per the OIG). The AFS publishes locality-adjusted rates for urban, rural, and super-rural areas. The applicable tier is selected based on the patient's ZIP code.

**Per-mile codes:** For mileage codes (A0425, A0435, A0436), the per-mile unit charge is compared against the AFS per-mile benchmark when quantity > 1.

**Severity:** Warning

---

### 8. TERMINATED_CODE_BILLED

**What:** Flags HCPCS Level II codes billed after their CMS termination date.

**Why it fires:** CMS terminates codes when they are replaced or withdrawn. Using a terminated code for a service after its termination date means the provider used an invalid billing code — the claim will be denied by Medicare and most commercial payers.

**Note:** CPT code validity is handled via `proc_stat` in NON_PAYABLE_CODE. This rule covers HCPCS Level II only (alpha-prefix codes).

**Severity:** Critical

---

### 9. HOSPITAL_CHARGE_OUTLIER

**What:** Flags charges exceeding 1.1× the hospital's own published gross charge (chargemaster rate).

**Why it fires:** Under CMS price transparency rules, hospitals must publish their gross charge (list price) for every service. Billing a patient more than the hospital's own published list price is an unambiguous error — there is no insurance type or geography argument that justifies it.

**Data source:** Hospital Machine-Readable Files (MRFs), ingested into BigQuery's `hospital_charges` table. Matched by hospital NPI or name.

**Severity:** Critical

---

### 11. MUE_EXCEEDED

**What:** Flags line items where the billed quantity exceeds the CMS Medically Unlikely Edit (MUE) limit for that code.

**Why it fires:** CMS publishes MUE values defining the maximum units of a given CPT/HCPCS code that are clinically reasonable for a single patient on a single date of service. Billing above this limit strongly indicates quantity inflation or a billing error.

**MUE Adjudication Indicator (MAI) determines how the check is applied:**
- `1` (Claim Edit): Sum all lines with the same code and service date; the total must not exceed the MUE. Severity: Critical.
- `2` (Date of Service — Policy): Each individual line must not exceed the MUE. Hard denial; cannot be overridden. Severity: Critical.
- `3` (Date of Service — Clinical): Each line must not exceed the MUE, but the limit can be exceeded with supporting clinical documentation. Severity: Warning.
- `0` (Unknown — MCD files omit the MAI column): Treated as indicator 2 conservatively. Severity: Critical.

**MUE value of 0:** The code is not separately payable under any circumstances — flag every occurrence as Critical regardless of quantity.

**Data source:** CMS MCR MUE CSV files (Medicare, with MAI) and MCD TXT files (Medicaid, no MAI column — MAI stored as 0 and treated as indicator 2). Loaded quarterly for 2020–2026 via `scripts/load_mue_limits.py`. Each row carries an `effective_date`; the lookup returns the most recent quarterly release whose `effective_date` is on or before the bill's service date.

**When active:** Only when MUE limits are loaded for the bill's service_type/payer_type combination.

**Severity:** Critical (indicators 0, 1, 2) or Warning (indicator 3).

---

### 10. NEGOTIATED_RATE_EXCEEDED

**What:** Flags charges exceeding 1.1× the insurer-specific contracted rate for this hospital.

**Why it fires:** The negotiated rate is the exact dollar amount the patient's insurer has contractually agreed to pay this hospital for each procedure. In-network providers cannot bill above their contracted rate. Billing above it is either an error or improper balance-billing.

**This is the strongest benchmark in the engine.** When available, it should be considered definitive evidence of a billing error.

**Data source:** Hospital MRFs, filtered to `payer_name` + `plan_name` for the patient's plan.

**Severity:** Critical

---

## Insurance Type Implications

### Price benchmarks (PRICE_OUTLIER, FACILITY_CHARGE_OUTLIER, AMBULANCE_CHARGE_OUTLIER)

The 1.8× Medicare threshold is applied consistently regardless of insurance type:

| Insurance Type | Price benchmark interpretation |
|----------------|-------------------------------|
| Medicare | Medicare rates are their own rates — PRICE_OUTLIER flags at 1.8× (unusual even for Medicare) |
| Medicaid | Medicaid pays ~70–90% of Medicare; flagging at 1.8× Medicare still catches egregious outliers |
| Commercial | Typically pays 120–250% of Medicare; 1.8× threshold set above this range to avoid false positives |
| Self-pay | No insurer contract; PRICE_OUTLIER and HOSPITAL_CHARGE_OUTLIER most relevant |
| TRICARE | Published rates similar to Medicare; 1.8× threshold appropriate |

For all insurance types: NEGOTIATED_RATE_EXCEEDED (when available) and HOSPITAL_CHARGE_OUTLIER are more definitive than PRICE_OUTLIER, because they compare against the actual agreed price rather than the Medicare floor.

### NCCI and MUE selection (insurance-type-aware)

NCCI PTP edit pairs and MUE limits are loaded from the database filtered by `service_type` and `payer_type`. The mapping from the bill's `plan_type` to these parameters is:

| Bill `plan_type` | NCCI `payer_type` loaded | Rationale |
|-----------------|--------------------------|-----------|
| `medicare` | `medicare` | Direct match — CMS MCR/MCD files apply |
| `medicaid` | `medicaid` | CMS national NCCI files are the Medicaid standard; state-specific files use `payer_type='medicaid'` when loaded |
| `commercial` | `medicare` | Medicare NCCI is the industry floor standard; commercial payers incorporate it |
| `tricare` | `medicare` | TRICARE uses Medicare-aligned NCCI edits |
| `self_pay` | `medicare` | Conservative default — NCCI unbundling is improper regardless of payer |
| `null` (unknown) | `medicare` | Conservative default |

**Service type detection:** The service type (`practitioner`, `outpatient`, `dme`) is inferred from the CPT/HCPCS codes on the bill:
- Codes starting with A0–A9, E0–E1, K0, L0–L9 → `dme`
- All other bills → `practitioner` (default; covers the vast majority of physician/professional claims)
- `outpatient` is not yet auto-detected (requires revenue codes not extracted by the current parser)

**Current data loaded:** CMS MCD PTP files (Q1 2026) for all three service types — loaded via `scripts/load_ncci_edits.py --replace`. MUE limits (MCR CSV for Medicare, MCD TXT for Medicaid) for all quarters 2020–2026 — loaded via `scripts/load_mue_limits.py`. Use `scripts/load_ncci_all.sh` to (re)load all files at once.

**Refreshing quarterly:** CMS releases new NCCI files each quarter (January, April, July, October). For PTP, load the new quarterly file with `--replace` — the file is a full snapshot so old pairs are wiped. For MUE, load without `--replace` — each quarterly file has a distinct `effective_date` and rows are upserted, leaving prior quarters intact for historical lookups.

---

## Date-Aware NCCI Lookups

### Why date-awareness matters

NCCI rules change every quarter. CMS adds new edit pairs, removes old ones, and revises MUE limits. If the engine always applied the *current* quarter's rules to every bill, it would produce wrong results for historical bills — flagging procedures that were not yet bundled at the time of service, or missing edits that were active then but have since been removed.

Both lookups are now scoped to the bill's service date via `rate_date`, which is derived from the earliest service date on the bill.

### MUE lookup (`_load_mue_limits`)

Queries `ncci_mue_limits` with `effective_date <= service_date`, orders by `effective_date DESC`, and keeps the first (most recent qualifying) row per code. This returns the MUE limit from the quarterly release that was in effect on the date of service.

**Example — 2022 bill:** A bill with a service date of 2022-07-15 queries for `effective_date <= 2022-07-15`. The Q3 2022 release (`effective_date = 2022-07-01`) is the most recent qualifying row and is used. The Q1 2026 values — which may differ — are not applied.

### PTP lookup (`_load_ncci_pairs`)

Queries `ncci_edit_pairs` with:
- `effective_date <= service_date` — the pair must have been active by the date of service
- `deletion_date IS NULL OR deletion_date >= service_date` — the pair must not have been retired before the date of service

This means a pair added in 2024 is **excluded** from a 2022 bill analysis, and a pair that was active in 2022 but deleted in 2023 is **included**. Without this filter, a 2022 bill would be checked against today's edit rules, which could generate false positives (flagging bundles that didn't exist yet) or false negatives (missing edits that were active in 2022).

**Concrete 2022 example:**

| Pair | CMS effective_date | CMS deletion_date | Applies to 2022-07-15 bill? |
|------|--------------------|-------------------|-----------------------------|
| 99213 → 36415 | 2020-01-01 | NULL | Yes — active since 2020, still active |
| 27447 → 27370 | 2020-01-01 | NULL | Yes — active since 2020, still active |
| 99291 → 99213 | 2020-01-01 | NULL | Yes — active since 2020, still active |
| 12345 → 67890 (hypothetical new edit) | 2024-01-01 | NULL | No — added after service date |
| 11111 → 22222 (hypothetical retired edit) | 2020-01-01 | 2021-12-31 | No — was retired before service date |
| 33333 → 44444 (hypothetical active-in-2022) | 2020-01-01 | 2023-06-30 | Yes — was still active on 2022-07-15 |

### Fallback when no service date is available

If `rate_date` cannot be derived (no parseable service dates on the bill), `_load_ncci_pairs` falls back to `deletion_date IS NULL` (current active pairs) and `_load_mue_limits` returns any available row for the code. This is documented in both functions.

---

## Architecture Notes

- Rules run independently. No rule depends on another's output — this makes the engine testable in isolation and prevents error compounding.
- All rules return `DetectedError` objects; the caller accumulates and stores them.
- Rules that require optional data (OPPS, AFS, hospital MRF) are silently skipped when that data is not loaded, so the engine degrades gracefully without crashing.
- The engine is instantiated fresh for each bill analysis in `bills.py`. All reference data is loaded at that point, scoped to the bill's CPT codes and locality to minimize database load.
