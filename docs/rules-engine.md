# ClaroBill Rules Engine — Complete Rule Reference

All rules are implemented in `apps/engine/app/services/rules_engine.py`.
Reference data is loaded in `apps/engine/app/api/v1/bills.py`.
Error codes are defined in `apps/engine/app/models/bill.py` and mirrored in
`packages/shared/src/types/bill.ts`.

---

## Pipeline Overview

The rules engine is the fourth stage of the analysis pipeline:

```
Upload → OCR (Google Vision) → Parser → Rules Engine → AI Summary → PDF Report
```

`bills.py` orchestrates the pipeline. Before instantiating `RulesEngine`, it loads
all reference data from Supabase (CMS tables) and BigQuery (hospital MRF data).
The engine receives all data it needs at construction time — it does no I/O.

**Data loading flow in `bills.py`:**

| Loader function | Data source | Enables |
|---|---|---|
| `_load_medicare_rates()` | `cms_pfs_indicators` + `cms_localities` | PRICE_OUTLIER |
| `_load_opps_rates()` | `cms_opps_cap` | FACILITY_CHARGE_OUTLIER |
| `_load_ambulance_rates()` | `cms_ambulance_rates` + `cms_ambulance_zip_locality` | AMBULANCE_CHARGE_OUTLIER |
| `_load_ncci_pairs()` | `ncci_edit_pairs` | NCCI_UNBUNDLING |
| `_load_mue_limits()` | `ncci_mue_limits` | MUE_EXCEEDED |
| `_load_non_payable_codes()` | `cms_pfs_indicators` | NON_PAYABLE_CODE |
| `_load_hcpcs_code_data()` | `cms_hcpcs_codes` | NON_PAYABLE_CODE, TERMINATED_CODE_BILLED |
| `_load_anesthesia_cf()` | `cms_anesthesia_cf` | ANESTHESIA_OUTLIER |
| `_load_anesthesia_base_units()` | `cms_anesthesia_base_units` | ANESTHESIA_OUTLIER (exact mode) |
| `_load_hospital_charges()` | BigQuery `hospital_charges` (gross) | HOSPITAL_CHARGE_OUTLIER |
| `_load_negotiated_charges()` | BigQuery `hospital_charges` (per-payer) | NEGOTIATED_RATE_EXCEEDED |
| `_load_negotiated_ceiling()` | BigQuery `hospital_charges` (max_negotiated) | NEGOTIATED_CEILING_EXCEEDED |
| (no loader — curated module) | `app/data/redundant_clinical_pairs.py` | REDUNDANT_CLINICAL_PAIR |

**Locality resolution:** `_resolve_locality()` resolves a 7-character CMS MAC locality
code from the patient's state + county. This code drives GPCI-adjusted Medicare rate
calculation and OPPS/ambulance rate lookup. Falls back to national average (`0000000`)
when state is not provided.

---

## Design Principles

- **Independent rules.** Every rule runs regardless of what other rules find.
  No rule depends on another's output — except for the waterfall suppression below.
- **Graceful degradation.** Each rule that requires external data is disabled when
  that data is unavailable (empty dict), rather than emitting false positives or failing.
- **Conservative thresholds.** The `exact_price_threshold` (1.1×) is intentionally
  tight for exact-benchmark rules. The `medicare_outlier_threshold` (1.8×) is
  intentionally loose for Medicare proxy rules — to avoid false positives on normal
  commercial bills where 1.2–1.6× Medicare is standard.
- **Strongest evidence wins the description.** Multiple rules can fire on the same
  line item. Each generates an independent error. The patient sees all of them —
  the AI summary surfaces the most actionable finding.

---

## Benchmark Hierarchy

When multiple benchmarks are available for the same charge, all applicable rules
fire independently. The hierarchy determines how assertive the report language should be:

| Rule | Benchmark | Confidence | Severity |
|---|---|---|---|
| NEGOTIATED_RATE_EXCEEDED | Exact payer/plan contracted rate | Highest — patient's specific contract | critical |
| HOSPITAL_CHARGE_OUTLIER | Hospital's own published gross charge | High — hospital's own list price | critical |
| NEGOTIATED_CEILING_EXCEEDED | Hospital-wide max negotiated (all payers) | Medium — not patient-specific | warning |
| FACILITY_CHARGE_OUTLIER | OPPS Medicare payment cap | Lower — proxy for commercial | warning |
| AMBULANCE_CHARGE_OUTLIER | CMS Ambulance Fee Schedule | Lower — proxy | warning |
| PRICE_OUTLIER | Commercial: Medicare × service-type multiplier (1.40–2.64×). Others: Medicare × plan multiplier | Weakest — population proxy | warning |
| REDUNDANT_CLINICAL_PAIR | Curated payer-policy redundancy list (non-NCCI) | Medium — payer policy varies | warning |

**Report language guidance:** NEGOTIATED_RATE_EXCEEDED and HOSPITAL_CHARGE_OUTLIER
warrant assertive language ("you were overcharged"). NEGOTIATED_CEILING_EXCEEDED and
Medicare-proxy rules warrant hedged language ("warrants a closer look").

---

## Waterfall Deduplication

`run()` prevents double-counting savings across rules:

**1. Fully removed line items:** DUPLICATE_CHARGE and NCCI_UNBUNDLING mean a line
item should not exist on the final bill. Pricing rules (PRICE_OUTLIER, etc.) on a
removed line item would report an "overcharge" on charges that don't exist once
corrected — inflating savings. The `_without_removed()` helper filters these out.
- Duplicate instance (affected_indices[1]) → removed
- NCCI col2 (component) code indices → removed

**2. Multi-pair NCCI components:** A single component code can be bundled into
multiple comprehensive codes on the same bill (e.g., 93010 is a component of both
93000 and 99284). Its charge is counted only in the first NCCI error. Subsequent
errors set `estimated_overcharge=0` so the savings total is accurate. All errors
still appear in the report and dispute letter.

**3. MUE=0 + NON_PAYABLE_CODE:** Bundled codes (proc_stat='B') often also have
MUE=0 in CMS tables. Both rules would otherwise fire on the same line item for the
same underlying problem. `_detect_mue_violations` skips MUE=0 for codes already
present in `_non_payable_codes` — one finding per issue.

---

## Quantity Handling

All pricing rules compare the **per-unit charge** against the per-unit benchmark rate,
then multiply the overcharge by quantity:

```python
billed = Decimal(str(item.unit_charge))
if billed > benchmark * threshold:
    overcharge = (billed - benchmark) * item.quantity
```

Comparing `total_charge` directly against a per-unit benchmark produces an inflated
overcharge figure for multi-unit line items. Most CPT codes bill at quantity=1, but
ambulance mileage (A0425), lab panels, and some physical therapy codes can have
quantity > 1.

---

## Rule Run Order

```python
# 1. Structural/identity errors (run first — drive waterfall suppression)
duplicate_errors = self._detect_duplicates(line_items)
ncci_errors, ncci_component_indices = self._detect_ncci_unbundling(line_items)

# 2. All remaining rules — suppressed for fully-removed indices
self._detect_price_outliers(line_items)
self._detect_non_payable_codes(line_items)
self._detect_anesthesia_outliers(line_items)
self._detect_facility_outliers(line_items)
self._detect_ambulance_outliers(line_items)
self._detect_terminated_codes(line_items)
self._detect_hospital_charge_outliers(line_items)
self._detect_negotiated_rate_exceeded(line_items)
self._detect_negotiated_ceiling_exceeded(line_items)
self._detect_mue_violations(line_items)
```

---

## Rules Reference

### DUPLICATE_CHARGE
**Severity:** critical  
**Data source:** None (structural check on parsed line items)

**What it detects:**  
The same CPT/HCPC code + modifier + service date billed more than once. Duplicate
billing is explicitly prohibited by CMS. Each code should appear once per date;
repeated procedures should use the quantity field instead.

**Key detail — modifier is included in the dedup key.** Two line items with the
same base code but different modifiers on the same date are NOT duplicates:
- `99213` + `99213-25` = E&M plus a separately identifiable procedure (modifier 25 correct)
- `99213-LT` + `99213-RT` = bilateral procedures, one per side

**Estimated overcharge:** Full charge of the duplicate line item.

---

### NCCI_UNBUNDLING
**Severity:** critical  
**Data source:** `ncci_edit_pairs` (Supabase)

**What it detects:**  
CMS NCCI (National Correct Coding Initiative) PTP edit pair violations. The NCCI
tables define code pairs where one code is bundled into the other. Billing both
separately is improper unbundling.

**Override modifiers:** CMS modifiers 59, XE, XS, XP, and XU all override NCCI
edits when applicable. The engine checks all five — not just 59 (CMS introduced
the X modifiers in 2015 as preferred alternatives to 59).

| Modifier | Meaning |
|---|---|
| 59 | Distinct procedural service |
| XE | Distinct encounter |
| XS | Separate structure (different anatomical site) |
| XP | Separate practitioner |
| XU | Unusual non-overlapping service |

**Service type querying:** Both `practitioner` and `outpatient` NCCI tables are
always queried — outpatient hospital bills are not reliably auto-detected without
revenue codes, so querying both avoids missed pairs.

**Estimated overcharge:** Sum of all col2 (component code) charges.

---

### PRICE_OUTLIER
**Severity:** warning  
**Data source:** `cms_pfs_indicators` + `cms_localities` (Supabase)

**What it detects:**  
Charges that exceed a plan-type-aware benchmark rate. For commercial patients the
benchmark is an estimated commercial rate (Medicare × service-type multiplier), not
the raw Medicare rate. This produces credible, insurance-relevant savings estimates
and avoids confusing commercially-insured patients with Medicare comparisons.

**Thresholds and benchmarks by plan type:**

| Plan type | Benchmark | Threshold | Rationale |
|---|---|---|---|
| medicare / medicaid | Medicare rate | 1.05× | Medicare rate IS the payment ceiling |
| tricare / self_pay | Medicare rate | 1.20× | Tracks Medicare closely |
| commercial — outpatient hospital | Medicare × 2.64 | exceeds commercial rate | Outpatient hospital commercial avg = 264% of Medicare |
| commercial — physician/practitioner | Medicare × 1.40 | exceeds commercial rate | Physician commercial avg = 140% of Medicare |
| commercial — inpatient/unknown | Medicare × 2.00 | exceeds commercial rate | Conservative midpoint |
| unknown plan type | Medicare rate | 1.80× | Fallback — no insurance context |

**Service type determination (commercial only):**  
The service type drives the commercial multiplier selection:
- `outpatient` — bill has a confirmed `hospital_name` (facility claim proxy; revenue codes not yet parsed)
- `practitioner` — default for non-hospital, non-DME bills
- `dme` — bill contains HCPCS Level II DME supply codes (A/E/K/L prefixes)

For commercial patients, descriptions reference "typical commercial insurance rate ~$X"
with no mention of Medicare — irrelevant to a commercially-insured patient.

**Rate formula (Medicare base):**  
```
medicare_rate = (rvu_work × gpci_work + nfac_pe_rvu × gpci_pe + rvu_mp × gpci_mp) × conv_fact
commercial_benchmark = medicare_rate × multiplier
```
Uses `effective_from <= service_date` so the quarterly release in effect at the
time of service is used automatically.

**Estimated overcharge:**
- Commercial: `(unit_charge - commercial_benchmark) × quantity`
- All other plan types: `(unit_charge - medicare_rate) × quantity`

The raw `medicare_benchmark_rate` field is always stored on the error record for
internal use regardless of which benchmark is shown to the patient.

---

### NON_PAYABLE_CODE
**Severity:** critical (`I`, `B`) or warning (`N`)  
**Data source:** `cms_pfs_indicators` (CPT codes), `cms_hcpcs_codes` (HCPCS Level II)

**What it detects:**  
Codes that CMS has marked non-payable:

| proc_stat | Meaning | Severity |
|---|---|---|
| `I` | Inactive — code retired, not payable | critical |
| `B` | Bundled — always included in another procedure, never separately payable | critical |
| `N` | Non-covered — excluded from Medicare coverage | warning |

For HCPCS Level II codes, the engine reads `coverage_code` and `pricing_indicator`
from `cms_hcpcs_codes` and maps them to equivalent proc_stat values.

**Estimated overcharge:** Full charge of the non-payable line item.

---

### ANESTHESIA_OUTLIER
**Severity:** critical (with documented time) or warning (without)  
**Data source:** `cms_anesthesia_cf` + `cms_anesthesia_base_units` (Supabase)

**What it detects:**  
Anesthesia charges that imply implausible base unit counts. Medicare anesthesia
payment formula: `payment = (base_units + time_units) × locality_CF`
where `time_units = minutes / 15`.

**Working backwards from the billed charge:**
- `implied_total = charge / locality_CF`
- `implied_base = implied_total - time_units` (when OCR extracted time)

**Detection modes:**

| Condition | Check | Severity |
|---|---|---|
| `implied_base < 0` | Charge < cost of documented time alone | critical |
| `implied_base > published_base + 0.5` | Exceeds CMS-published base units | critical |
| `implied_base > 25` | Exceeds heuristic ceiling (no published base units) | critical |
| `implied_total > 80` | ~20 hours — physically impossible (no OCR time) | warning |

**Estimated overcharge:** `(implied_base - correct_base) × locality_CF`

---

### FACILITY_CHARGE_OUTLIER
**Severity:** warning  
**Data source:** `cms_opps_cap` (Supabase)

**What it detects:**  
Hospital outpatient facility charges exceeding the CMS OPPS (Outpatient Prospective
Payment System) payment cap for the patient's locality. The OPPS cap is what Medicare
pays — patient cost-sharing is calculated on the billed charge, so inflated billed
amounts directly harm the patient.

**Threshold:** 1.80× OPPS cap (same medicare_outlier_threshold as PRICE_OUTLIER)

**Estimated overcharge:** `(unit_charge - opps_cap) × quantity`

---

### AMBULANCE_CHARGE_OUTLIER
**Severity:** warning  
**Data source:** `cms_ambulance_rates` + `cms_ambulance_zip_locality` (Supabase)

**What it detects:**  
Ambulance charges exceeding the CMS Ambulance Fee Schedule (AFS) rate for the
patient's area. Three rate tiers: urban (base), rural (+50%), super-rural (+22.6%).

**Locality resolution:** Patient ZIP → `cms_ambulance_zip_locality` → rural indicator.
Falls back to urban (lowest) rate when ZIP is unknown.

**Per-mile code handling (A0425, A0435, A0436):**  
When quantity > 1, compares `unit_charge` against the per-mile AFS benchmark.
When quantity = 1 (mileage unknown), compares `total_charge` conservatively.

**Estimated overcharge:** `(billed_per_unit - benchmark) × quantity`

---

### TERMINATED_CODE_BILLED
**Severity:** critical  
**Data source:** `cms_hcpcs_codes` (Supabase)

**What it detects:**  
HCPCS Level II codes billed after their CMS termination date. Terminated codes
are no longer valid — claims will be denied. The correct replacement code should
have been used.

**Note:** Only HCPCS Level II (alpha-prefix) codes are checked here. Retired CPT
codes are caught by NON_PAYABLE_CODE via `proc_stat='I'` (within the current data
window — pre-2024 retirements are a known gap; see `docs/future_improvements/terminated-cpt-codes-coverage.md`).

**Estimated overcharge:** Full charge of the terminated-code line item.

---

### HOSPITAL_CHARGE_OUTLIER
**Severity:** critical  
**Data source:** BigQuery `hospital_charges` (gross_charge column)

**What it detects:**  
Charges exceeding the hospital's own published gross charge from their CMS-mandated
Machine Readable File (MRF). Billing above the hospital's own list price is an
unambiguous billing error — no justification exists for charging a patient more than
the hospital's own published maximum.

**Hospital identification (in priority order):**
1. NPI extracted by OCR from bill header — exact match, unambiguous
2. Hospital name extracted by OCR → `hospital_directory` name match → used only
   when exactly one hospital matches (prevents wrong-facility charges)

**Threshold:** 1.10× gross charge  
**Estimated overcharge:** `(unit_charge - gross_charge) × quantity`

---

### NEGOTIATED_RATE_EXCEEDED
**Severity:** critical  
**Data source:** BigQuery `hospital_charges` (negotiated_charge column, per-payer rows)

**What it detects:**  
Charges exceeding the patient's specific insurer-contracted rate. This is the
strongest price benchmark — the exact dollar amount the insurer agreed to accept
from this hospital for this procedure. In-network providers cannot collect more
than their contracted rate.

**Payer matching (in priority order):**
1. `payer_name_aliases` JOIN: maps the user's payer name to a canonical `payer_group`,
   then queries all known MRF alias strings for that group via exact IN() match.
   More accurate than substring matching — eliminates "Anthem Blue Cross" vs "BCBS CA"
   naming mismatches.
2. CONTAINS_SUBSTR fallback: used when `payer_name_aliases` table is empty or
   the user's payer name has no canonical alias.

**Excluded rate types:** `negotiated_type = 'percentage'` rates are excluded — they
are multipliers of billed charges (circular) and cannot be directly compared.
Only `'negotiated'` and `'derived'` dollar amounts are used.

**Data required for this rule to fire:**
- Hospital in our BigQuery database AND hospital published per-payer rates in their MRF
- User confirmed payer name + plan name
- Payer name matches the MRF data (via alias table or substring)

**Threshold:** 1.10× negotiated rate  
**Estimated overcharge:** `(unit_charge - negotiated_rate) × quantity`

---

### NEGOTIATED_CEILING_EXCEEDED
**Severity:** warning  
**Data source:** BigQuery `hospital_charges` (max_negotiated column)

**What it detects:**  
Charges exceeding the highest negotiated rate any insurer pays at this hospital for
this code. `max_negotiated` is extracted from the hospital's MRF `standard_charges`
level — it represents the hospital-wide ceiling across all payers.

**When it fires:**  
- `negotiated_ceiling` is loaded (hospital is in our BigQuery database)
- The code does NOT already have an exact rate in `negotiated_charges` (to prevent
  double-reporting — the ceiling is suppressed for any code where the exact rate fired)
- Billed charge exceeds the ceiling rate × 1.10×

**Why warning, not critical:** The ceiling is cross-payer, not patient-specific. It
proves the charge exceeds what any insurer pays — strong evidence of an overcharge —
but we cannot state with certainty what this specific patient's plan would have paid.
Report language should say "warrants a closer look" rather than "you were overcharged."

**Relationship to NEGOTIATED_RATE_EXCEEDED:**  
These rules form a tiered fallback:
1. Exact payer/plan rate fires → NEGOTIATED_RATE_EXCEEDED (critical)
2. Exact rate unavailable but ceiling fires → NEGOTIATED_CEILING_EXCEEDED (warning)
3. Neither fires → PRICE_OUTLIER using commercial rate benchmark (weakest fallback)

**Threshold:** 1.10× max_negotiated ceiling  
**Estimated overcharge:** `(unit_charge - ceiling_rate) × quantity`

---

### MUE_EXCEEDED
**Severity:** critical (MAI 0, 1, 2) or warning (MAI 3)  
**Data source:** `ncci_mue_limits` (Supabase)

**What it detects:**  
Line items where billed quantity exceeds the CMS Medically Unlikely Edit (MUE) limit.
MUE values define the maximum units of a given code that are clinically plausible for
a single patient on a single claim or date of service.

**MUE Adjudication Indicator (MAI) drives check logic and severity:**

| MAI | Type | Check | Severity |
|---|---|---|---|
| 0 | Unknown (MCD files omit this field) | Per-line quantity ≤ MUE | critical |
| 1 | Claim Edit | Sum of all lines, same code+date ≤ MUE | critical |
| 2 | Date of Service — Policy (hard denial) | Per-line quantity ≤ MUE | critical |
| 3 | Date of Service — Clinical (documentable) | Per-line quantity ≤ MUE | warning |

**Special case:** MUE value = 0 means the code is not separately payable. Every
occurrence is flagged critical — unless NON_PAYABLE_CODE already covers the same
code (bundled codes often have both proc_stat='B' and MUE=0; only one finding fires).

**Estimated overcharge:** `excess_quantity × unit_charge`

---

### REDUNDANT_CLINICAL_PAIR
**Severity:** warning  
**Data source:** Hand-curated allowlist at `apps/engine/app/data/redundant_clinical_pairs.py`

**What it detects:**  
Pairs of CPT codes that are clinically redundant when billed for the same encounter
but are NOT formal CMS NCCI PTP edits. Commercial payer medical-policy documents
routinely deny these pairs even though CMS does not formally bundle them. Filling
this gap converts "the engine isn't catching this overcharge" into a real finding
with hedged language that respects the payer-policy uncertainty.

**Curated categories (as of 2026-04-29):**

| Category | Pair | Suppression modifier(s) | Why redundant |
|---|---|---|---|
| OB ultrasound | 76801 ↔ 76817 | 59, XS | Transabdominal first-trimester complete + transvaginal — typically alternatives, not complements |
| OB ultrasound | 76805 ↔ 76817 | 59, XS | Transabdominal after first trimester + transvaginal — same logic |
| OB ultrasound | 76815 ↔ 76817 | 59, XS | Limited + transvaginal — transvaginal typically supplants the limited study |
| OB ultrasound | 76817 ↔ 76819 | 59, XS | Transvaginal + biophysical profile — BPP includes ultrasound assessment |
| Lab panel | 86900 ↔ 86901 | (none) | ABO + Rh = single "type and Rh" panel in clinical practice |
| Lab panel | 82565 ↔ 82550 | (none) | Creatinine + creatine kinase outside muscle/cardiac workup |
| E&M with procedure | 36415 ↔ 99211 | 25 | Routine venipuncture is bundled into a minimal-level E&M |

**How a pair gets added:** see the curation criteria in
`apps/engine/app/data/redundant_clinical_pairs.py` module docstring. Every entry
must (a) not be in NCCI PTP, (b) cite a documented payer-policy reason, (c) not
depend on diagnosis to determine redundancy, and (d) include a suppression
modifier when one applies.

**Dedup against NCCI:** if a pair is added that *is* in NCCI on a given bill, NCCI
wins and this rule stays silent. The check happens in `_ncci_flagged_code_pairs()`.

**Estimated overcharge:** the cheaper line item's `total_charge`. Hedged language
in the report description: "Ask the hospital to justify both charges or remove CPT
\<cheaper code\>." Severity is `warning` because payer policy varies — the
expected user action is to request justification, not to demand a refund.

---

## Reference Data Sources

| Table | Source | Loader |
|---|---|---|
| `cms_pfs_indicators` | CMS PFS RVU files (quarterly) | `scripts/load_cms_pfs.py` |
| `cms_localities` | CMS GPCI locality file | `scripts/load_cms_pfs.py` |
| `cms_county_locality` | CMS locality county mapping | `scripts/load_county_locality.py` |
| `ncci_edit_pairs` | CMS MCD/MCR PTP files (.txt, tab-delimited) | `scripts/load_ncci_edits.py` |
| `ncci_mue_limits` | CMS MCR MUE CSV / MCD MUE .txt | `scripts/load_mue_limits.py` |
| `cms_hcpcs_codes` | CMS HCPCS Level II annual release | `scripts/load_hcpcs_codes.py` |
| `cms_anesthesia_cf` | CMS anesthesia CF locality files | `scripts/load_anesthesia_cf.py` |
| `cms_anesthesia_base_units` | CMS anesthesia base unit tables | `scripts/load_anesthesia_base_units.py` |
| `cms_opps_cap` | CMS OPPS Addendum B files | `scripts/load_opps_cap.py` |
| `cms_ambulance_rates` | CMS AFS PUF files | `scripts/load_ambulance_rates.py` |
| `cms_ambulance_zip_locality` | CMS AFS ZIP5 fixed-width files | `scripts/load_ambulance_zip_locality.py` |
| `hospital_directory` | CMS-direct discovery pipeline (~13,833 US civilian hospitals) | `scripts/mrf_discovery/stage*.py` (annual) |
| `hospital_charges` | CMS MRF price transparency files (effective-dated by year) | `pipeline/parse_hospital_mrfs.py` (weekly) |
| `mrf_archive_index` | Canonical index of MRF files archived to GCS | `pipeline/scrape_hospital_mrfs.py` (weekly, Phase 4 onward) |
| `payer_name_aliases` | Manual curation + CMS payer taxonomy | `scripts/seed_payer_normalizations.py` |

---

## Known Gaps and Future Work

See `docs/future_improvements/` for detailed design docs on:

- **Terminated CPT codes (pre-2024):** Codes retired before our data window are
  invisible — `cms_pfs_indicators` only contains data from 2024 onward. Codes
  retired in 2008 are absent from the table and produce no findings.
  See `terminated-cpt-codes-coverage.md`.

- **Commercial rate benchmarking:** For commercial patients where neither the
  exact payer rate nor the ceiling fires, the 1.80× Medicare fallback is the
  only benchmark — and it only catches extreme outliers, not the typical 10–30%
  above-contract overcharge. See `commercial-rate-benchmarking.md`.

- **MRF discovery pipeline:** Pivoted on 2026-04-28 from third-party Payerset scrape
  (~3,100 hospitals) to CMS-direct discovery (~13,833 US civilian hospitals after
  filtering distinct-part units, federal facilities, and non-US rows). Phase 1-2
  done + applied to BQ; Stages 1-2 of discovery shipped + applied; Stages 3-6
  pending. Effective-dating (`pricing_effective_year`) is enforced at schema level
  to prevent comparing a 2026 bill against an unknown-vintage chargemaster.
  See `docs/decisions/2026-04-28-cms-direct-mrf-discovery.md` and
  `docs/future_improvements/mrf-discovery-pipeline.md`.

---

*Last updated: April 29 2026 (added REDUNDANT_CLINICAL_PAIR + Phase 4 effective-dated MRF pipeline references)*  
*Owner: ClaroBill Engineering*
