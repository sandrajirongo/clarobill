# Rules Engine Architecture

**Date:** 2026-04-19  
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
| Medicare PFS rates | CMS Physician Fee Schedule ZIP file | `cms_physician_fee_schedule` | PRICE_OUTLIER |
| NCCI edit pairs | CMS NCCI edits (Column 1/Column 2) | `cms_ncci_edits` | NCCI_UNBUNDLING |
| CPT proc_stat flags | CMS PFS status indicators | `cms_pfs_indicators` | NON_PAYABLE_CODE |
| HCPCS Level II codes | CMS HCPCS code file | `cms_hcpcs_codes` | NON_PAYABLE_CODE, TERMINATED_CODE_BILLED |
| Anesthesia conversion factor | CMS PFS locality file | `cms_anesthesia_cf` | ANESTHESIA_OUTLIER |
| Anesthesia base units | CMS PFS anesthesia base unit table | `cms_anesthesia_base_units` | ANESTHESIA_OUTLIER |
| OPPS payment caps | CMS OPPS addendum B | `cms_opps_rates` | FACILITY_CHARGE_OUTLIER |
| Ambulance Fee Schedule | CMS AFS final rule tables | `cms_ambulance_fee_schedule` | AMBULANCE_CHARGE_OUTLIER |
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

### 10. NEGOTIATED_RATE_EXCEEDED

**What:** Flags charges exceeding 1.1× the insurer-specific contracted rate for this hospital.

**Why it fires:** The negotiated rate is the exact dollar amount the patient's insurer has contractually agreed to pay this hospital for each procedure. In-network providers cannot bill above their contracted rate. Billing above it is either an error or improper balance-billing.

**This is the strongest benchmark in the engine.** When available, it should be considered definitive evidence of a billing error.

**Data source:** Hospital MRFs, filtered to `payer_name` + `plan_name` for the patient's plan.

**Severity:** Critical

---

## Insurance Type Implications

The engine applies all rules regardless of insurance type, but the interpretation varies:

| Insurance Type | Price benchmark interpretation |
|----------------|-------------------------------|
| Medicare | Medicare rates are their own rates — PRICE_OUTLIER flags at 1.8× (unusual even for Medicare) |
| Medicaid | Medicaid pays ~70–90% of Medicare; flagging at 1.8× Medicare still catches egregious outliers |
| Commercial | Typically pays 120–250% of Medicare; 1.8× threshold set above this range to avoid false positives |
| Self-pay | No insurer contract; PRICE_OUTLIER and HOSPITAL_CHARGE_OUTLIER most relevant |
| TRICARE | Published rates similar to Medicare; 1.8× threshold appropriate |

For all insurance types: NEGOTIATED_RATE_EXCEEDED (when available) and HOSPITAL_CHARGE_OUTLIER are more definitive than PRICE_OUTLIER, because they compare against the actual agreed price rather than the Medicare floor.

---

## Architecture Notes

- Rules run independently. No rule depends on another's output — this makes the engine testable in isolation and prevents error compounding.
- All rules return `DetectedError` objects; the caller accumulates and stores them.
- Rules that require optional data (OPPS, AFS, hospital MRF) are silently skipped when that data is not loaded, so the engine degrades gracefully without crashing.
- The engine is instantiated fresh for each bill analysis in `bills.py`. All reference data is loaded at that point, scoped to the bill's CPT codes and locality to minimize database load.
