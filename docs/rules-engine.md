# ClaroBill Rules Engine — Complete Rule Reference

All rules are implemented in `apps/engine/app/services/rules_engine.py`.
Reference data is loaded in `apps/engine/app/api/v1/bills.py`.
Error codes are defined in `apps/engine/app/models/bill.py` and mirrored in
`packages/shared/src/types/bill.ts`.

---

## Design Principles

- **Independent rules.** Every rule runs regardless of what other rules find.
  No rule depends on another's output.
- **Graceful degradation.** Each rule that requires external reference data
  (CMS tables, BigQuery) is disabled when that data is unavailable, rather
  than emitting false positives or hard-failing.
- **Conservative flagging.** The outlier threshold is 1.1× the benchmark —
  anything more than 10% above the benchmark is flagged. This is intentionally
  aggressive: medical overbilling is pervasive and the cost of a missed error
  outweighs the cost of an extra flag that turns out to be correct.
- **Strongest evidence wins the description.** When multiple rules fire on the
  same line item, each generates an independent error with its own description.
  The patient sees the strongest claim (e.g. NEGOTIATED_RATE_EXCEEDED is more
  actionable than PRICE_OUTLIER on the same item).

---

## Outlier Threshold

All price/charge comparison rules use a shared `outlier_threshold` parameter
(default `1.1`). A charge is flagged when:

```
billed_charge > benchmark_rate × outlier_threshold
```

This means anything more than 10% above the benchmark is flagged. The threshold
is configurable at `RulesEngine` instantiation but never set differently from
the default in production code.

---

## Implemented Rules

### 1. DUPLICATE_CHARGE
**Severity:** critical  
**Data source:** None (structural check on parsed line items)

**What it detects:**  
The same CPT/HCPC code billed more than once on the same service date. Duplicate
billing is explicitly prohibited by CMS and is one of the most common mechanical
billing errors. Each code should appear once per date; repeated procedures should
use the quantity field.

**Logic:**  
Builds a `(cpt_code, service_date) → first_index` map. Any subsequent occurrence
of the same pair is flagged. The estimated overcharge equals the full charge of the
duplicate item.

**Estimated overcharge:** Full charge of the duplicate line item.

---

### 2. PRICE_OUTLIER
**Severity:** warning  
**Data source:** `cms_pfs_indicators` + `cms_localities` (Supabase)

**What it detects:**  
Charges that exceed the Medicare Physician Fee Schedule non-facility rate by more
than 10%. Medicare rates are locality-adjusted using GPCI values for the patient's
state/county. The Medicare rate is used as a population benchmark — charges
dramatically above it warrant review even for non-Medicare patients, as most
private payers base their rates on Medicare multiples.

**Logic:**  
For each line item with a known CPT code:
```
rate = (rvu_work × gpci_work + nfac_pe_rvu × gpci_pe + rvu_mp × gpci_mp) × conv_fact
flag if: billed > rate × 1.1
```
Uses `effective_from <= service_date` so the quarterly release in effect at the
time of service is used automatically.

**Estimated overcharge:** `billed_charge - medicare_rate`  
**Benchmark shown to user:** Medicare non-facility rate for patient's locality

---

### 3. NCCI_UNBUNDLING
**Severity:** critical  
**Data source:** `ncci_edit_pairs` (Supabase)

**What it detects:**  
CMS NCCI (National Correct Coding Initiative) edit pair violations. The NCCI
tables define pairs of codes where one is "bundled into" the other — billing both
separately constitutes improper unbundling and represents a double-charge.

**Logic:**  
Builds a `cpt_code → set[indices]` map. For each NCCI pair `(col1, col2)` where
both codes appear on the bill, checks if modifier 59 is present on the col2 items.
Modifier 59 overrides the edit when procedures were performed on distinct anatomical
sites. Without modifier 59, the col2 charge is flagged in full.

**Estimated overcharge:** Sum of all col2 (component code) charges.  
**Note:** Modifier 59 exemption is conservative — we never flag when 59 is present,
even though some 59 uses are themselves improper. That is a separate rule category.

---

### 4. NON_PAYABLE_CODE
**Severity:** critical (proc_stat I, B) or warning (proc_stat N)  
**Data source:** `cms_pfs_indicators` + `cms_hcpcs_codes` (Supabase)

**What it detects:**  
CPT/HCPC codes that CMS has marked as non-payable:

| proc_stat | Meaning | Severity |
|-----------|---------|----------|
| `I` | Inactive — code retired, not payable under any circumstances | critical |
| `B` | Bundled — always included in another procedure, never separately payable | critical |
| `N` | Non-covered — excluded from Medicare coverage | warning |

For HCPCS Level II codes (alpha-prefix), the equivalent signals come from
`coverage_code` and `pricing_indicator` in `cms_hcpcs_codes`.

**Estimated overcharge:** Full charge of the non-payable line item.

---

### 5. TERMINATED_CODE_BILLED
**Severity:** critical  
**Data source:** `cms_hcpcs_codes` (Supabase)

**What it detects:**  
HCPCS Level II codes billed after their CMS termination date. Terminated codes
are no longer valid — claims using them will typically be denied by Medicare and
most commercial payers. The provider should have used the current replacement code.

**Logic:**  
Checks `service_date > termination_date` for any alpha-prefix HCPCS code on the
bill that has a non-null termination date in `cms_hcpcs_codes`.

**Estimated overcharge:** Full charge of the terminated-code line item.

---

### 6. ANESTHESIA_OUTLIER
**Severity:** critical (with documented time) or warning (without time)  
**Data source:** `cms_anesthesia_cf` + `cms_anesthesia_base_units` (Supabase)

**What it detects:**  
Anesthesia charges that imply implausible base unit counts. Medicare anesthesia
payment uses the formula: `payment = (base_units + time_units) × locality_CF`
where `time_units = minutes / 15`.

Working backwards from the billed charge:
- `implied_total = charge / locality_CF`
- `implied_base = implied_total - time_units` (when OCR extracted time)

**Flags:**
- `implied_base < 0` → charge less than the documented time alone (impossible)
- `implied_base > published_base + 0.5` → exceeds CMS-published base units (exact check)
- `implied_base > 25` → exceeds heuristic ceiling (when no published base units)
- `implied_total > 80` → equivalent to ~20 hours (when no OCR time available)

**Estimated overcharge:** `(implied_base - correct_base) × locality_CF`

---

### 7. FACILITY_CHARGE_OUTLIER
**Severity:** warning  
**Data source:** `cms_opps_cap` (Supabase)

**What it detects:**  
Hospital outpatient facility charges that exceed the CMS OPPS (Outpatient
Prospective Payment System) payment cap for the patient's locality. The OPPS cap
is the amount Medicare pays for an outpatient procedure. Patient cost-sharing is
calculated on the billed charge, so a facility billing 10× the OPPS cap is
inflating the patient's out-of-pocket exposure.

**Logic:** `flag if: billed > opps_cap × 1.1`

**Estimated overcharge:** `billed_charge - opps_cap`  
**Benchmark shown to user:** OPPS payment cap for patient's locality

---

### 8. AMBULANCE_CHARGE_OUTLIER
**Severity:** warning  
**Data source:** `cms_ambulance_rates` + `cms_ambulance_zip_locality` (Supabase)

**What it detects:**  
Ambulance charges that exceed the CMS Ambulance Fee Schedule (AFS) rate for the
patient's geographic area. The AFS has three tiers based on the pickup location:
urban (base rate), rural (+50%), and super-rural (+22.6% of rural).

For per-mile codes (A0425, A0435, A0436), the per-mile unit charge is compared
against the AFS per-mile benchmark when mileage was extracted from OCR. For
transport codes, the total charge is compared.

**Locality resolution:** Uses patient ZIP code → `cms_ambulance_zip_locality` →
rural indicator. Falls back to urban (lowest) rate when ZIP is unknown.

**Estimated overcharge:** `(billed - benchmark) × quantity`

---

### 9. HOSPITAL_CHARGE_OUTLIER
**Severity:** critical  
**Data source:** `hospital_charges` (BigQuery — CMS MRF price transparency files)

**What it detects:**  
Charges that exceed the hospital's own published gross charge from their CMS-mandated
Machine Readable File (MRF). Every hospital must publish their chargemaster (gross
charge) for every procedure. Billing above the hospital's own list price is an
unambiguous billing error — the patient cannot be charged more than the hospital's
own published maximum.

**Hospital identification:**
1. NPI extracted by OCR from bill header (exact match, preferred)
2. Hospital name extracted by OCR → LIKE match on `hospital_directory` → only used
   when exactly one match is found (prevents wrong-hospital charges)

**Logic:** `flag if: billed > gross_charge × 1.1`

**Estimated overcharge:** `billed_charge - gross_charge`  
**Benchmark shown to user:** Hospital's own published gross charge

---

### 11. MUE_EXCEEDED
**Severity:** critical (MAI 0, 1, 2) or warning (MAI 3)  
**Data source:** `ncci_mue_limits` (Supabase), loaded from CMS MCR MUE CSV files

**What it detects:**  
Line items where the billed quantity exceeds the CMS Medically Unlikely Edit (MUE)
limit for that HCPCS/CPT code. MUE values define the maximum units of a given code
that are clinically reasonable for a single patient on a single claim or date of service.

**MUE Adjudication Indicator (MAI) drives both check logic and severity:**

| MAI | Type | Check | Severity |
|-----|------|-------|----------|
| 0 | Unknown (MCD files) | Per-line quantity ≤ MUE | critical |
| 1 | Claim Edit | Sum of all lines, same code+date ≤ MUE | critical |
| 2 | Date of Service — Policy | Per-line quantity ≤ MUE (hard denial) | critical |
| 3 | Date of Service — Clinical | Per-line quantity ≤ MUE (documentable) | warning |

**Special case:** MUE value = 0 means the code is not separately payable under any
circumstances. Every occurrence is flagged Critical regardless of quantity.

**Estimated overcharge:** `excess_quantity × unit_charge`

**Insurance-type filtering:** Loaded with `payer_type` matching the bill's insurance
programme (mapped from `plan_type` on the bill). See decision doc for the full mapping.

---

### 10. NEGOTIATED_RATE_EXCEEDED
**Severity:** critical  
**Data source:** `hospital_charges` (BigQuery — payer-specific negotiated rates in MRF)

**What it detects:**  
Charges that exceed the specific negotiated rate your insurance company has
contracted with the hospital. This is the strongest of the three charge benchmarks:
it is the exact dollar amount your insurer agreed to pay for this specific procedure
at this specific hospital. Billing above it means the patient is being charged
outside the terms of the insurance contract.

**Hospital charges table columns used:**
- `payer_name` — insurer name (e.g. "AETNA", "BLUE CROSS BLUE SHIELD")
- `plan_name` — specific plan (e.g. "PPO GOLD", "HMO SELECT")
- `negotiated_charge` — the exact contracted rate
- `negotiated_type` — rate type: "negotiated" | "derived" | "percentage"

**Patient data required:**
- `payer_name` — collected at signup, stored in user's insurance profile
- `plan_name` — stored in user's insurance profile, confirmed per bill

**Logic:**
```
rate = MAX(negotiated_charge) WHERE
  hospital_npi = patient's hospital NPI
  AND LOWER(payer_name) LIKE '%patient payer%'
  AND LOWER(plan_name) LIKE '%patient plan%'
  AND code = cpt_code

flag if: billed > rate × 1.1
```

**Estimated overcharge:** `billed_charge - negotiated_rate`  
**Benchmark shown to user:** Insurer's contracted rate for this procedure at this hospital

---

## Rule Priority for User Communication

When multiple rules fire on the same line item, the report surfaces all of them
but orders by descending severity and specificity:

1. **NEGOTIATED_RATE_EXCEEDED** — strongest claim (your insurer's exact contract)
2. **HOSPITAL_CHARGE_OUTLIER** — strong claim (hospital's own published price)
3. **NCCI_UNBUNDLING** — structural error (CMS coding rule violation)
4. **MUE_EXCEEDED** — quantity error (CMS-defined billing limit violated)
5. **DUPLICATE_CHARGE** — structural error (mechanical billing error)
6. **NON_PAYABLE_CODE / TERMINATED_CODE_BILLED** — code-validity errors
7. **ANESTHESIA_OUTLIER** — specialty charge error
8. **FACILITY_CHARGE_OUTLIER** — facility benchmark comparison
9. **AMBULANCE_CHARGE_OUTLIER** — ambulance benchmark comparison
10. **PRICE_OUTLIER** — weakest claim (Medicare population average)

---

## Reference Data Sources

| Table | Source | Loader script |
|-------|--------|---------------|
| `cms_pfs_indicators` | CMS PFS RVU files (annual + quarterly) | `scripts/load_cms_pfs.py` |
| `cms_localities` | CMS GPCI locality file | `scripts/load_cms_pfs.py` |
| `cms_county_locality` | CMS locality county mapping | `scripts/load_cms_pfs.py` |
| `ncci_edit_pairs` | CMS MCD/MCR PTP files (.txt, tab-delimited) | `scripts/load_ncci_edits.py` |
| `ncci_mue_limits` | CMS MCR MUE CSV files (.csv) / MCD MUE .txt files | `scripts/load_mue_limits.py` |
| `cms_hcpcs_codes` | CMS HCPCS Level II annual release | `scripts/load_hcpcs.py` |
| `cms_anesthesia_cf` | CMS anesthesia CF locality files | `scripts/load_anesthesia_cf.py` |
| `cms_anesthesia_base_units` | CMS anesthesia base unit tables | `scripts/load_anesthesia_base_units.py` |
| `cms_opps_cap` | CMS OPPS Addendum B files | `scripts/load_opps_cap.py` |
| `cms_ambulance_rates` | CMS AFS PUF files | `scripts/load_ambulance_rates.py` |
| `cms_ambulance_zip_locality` | CMS AFS ZIP5 fixed-width files | `scripts/load_ambulance_zip_locality.py` |
| `hospital_directory` | Payerset hospital scrape (3,119+ hospitals) | `pipeline/scrape_hospital_mrfs.py` |
| `hospital_charges` | CMS MRF price transparency files | `pipeline/parse_hospital_mrfs.py` |
