# Future Improvement: Revenue Code Extraction for Facility vs. Professional Bill Classification

**Status:** Not built — current implementation uses `hospital_name` as a proxy  
**Priority:** Medium — improves PRICE_OUTLIER benchmark accuracy for edge cases  
**Related:** `apps/engine/app/services/parser.py`, `apps/engine/app/api/v1/bills.py` (`_derive_ncci_context`)

---

## Background

When a patient receives care at a hospital, two different types of bills may be generated:

- **Facility claim (UB-04 / CMS-1450)** — billed by the hospital for the use of its facilities,
  staff, equipment, and supplies. Contains revenue codes identifying each department or service
  category. Commercial insurers pay hospitals approximately 264% of the Medicare rate for
  outpatient facility services.

- **Professional claim (CMS-1500)** — billed by the physician or other provider for their
  professional services. Does not contain revenue codes. Commercial insurers pay physicians
  approximately 140% of the Medicare rate.

The correct commercial rate multiplier for PRICE_OUTLIER depends on which type of bill is
being analyzed. Using the wrong multiplier produces either understated savings (treating a
facility claim as a physician bill) or overstated savings (treating a physician bill as a
facility claim).

---

## Current implementation

`_derive_ncci_context()` in `bills.py` infers service type from CPT codes and plan type:
- Returns `"dme"` if the bill contains HCPCS Level II DME/supply codes (A/E/K/L prefixes)
- Returns `"practitioner"` for all other bills (default)

After calling `_derive_ncci_context()`, the pipeline overrides `service_type` to `"outpatient"`
when `hospital_name` is confirmed:

```python
# bills.py — _run_analysis_pipeline
service_type, payer_type = _derive_ncci_context(cpt_codes, plan_type)
if hospital_name and service_type == "practitioner":
    service_type = "outpatient"
```

**Why this works well in practice:** Most hospital bills go through the pre-analysis
verification step where the user confirms the hospital name. A confirmed `hospital_name`
is a reliable signal that the bill originated from a facility.

**Where it breaks down:**
- Hospital bills where the parser failed to extract a hospital name from OCR
- Cases where the user skipped or cleared the hospital name field
- Physician group practices operating inside a hospital building that do not bill as a facility

Revenue code extraction would replace this heuristic with a definitive, code-level signal.

---

## What revenue codes are

Revenue codes are 3–4 digit codes maintained by the National Uniform Billing Committee (NUBC).
They appear exclusively on UB-04 (CMS-1450) facility claim forms in a dedicated column labeled
`REV. CODE` or `REVENUE CODE`.

Common examples:

| Revenue Code | Description |
|---|---|
| 0360 / 036x | Operating Room |
| 0450 / 045x | Emergency Room |
| 0301 / 030x | Laboratory — Chemistry |
| 0270 / 027x | Medical/Surgical Supplies |
| 0260 / 026x | IV Solutions |
| 0636 | Drugs requiring detailed coding |
| 0001 | Total charge line (always last on the bill) |

The presence of **any** revenue code on a bill definitively identifies it as a UB-04 facility
claim. No look-up table is needed for the service type classification use case — detection
alone is sufficient.

---

## Data requirements

### For service type classification only

No external data needed. Revenue codes are recognizable from their format (3–4 digit codes in
the `0xxx` range) and the UB-04 form header (`REV. CODE` column label).

### For revenue code descriptions (optional enrichment)

CMS publishes a revenue code reference as part of the OPPS quarterly update files. We already
load `cms_opps_cap` which contains OPPS payment rates organized by revenue code category.
A simple reference table of revenue code → description could be derived from this data with
no new data pipeline required.

---

## Implementation plan

### Step 1 — Detect the `REV. CODE` column header (high confidence)

The most reliable signal is the column header that appears on all UB-04 forms. Add a
pattern to `parser.py`:

```python
_REVENUE_CODE_HEADER_PATTERN = re.compile(
    r"\bREV(?:ENUE)?\.?\s*(?:CODE|CD)\b",
    re.IGNORECASE,
)

def has_revenue_codes(raw_text: str) -> bool:
    """Return True if the OCR text contains a UB-04 revenue code column header."""
    return bool(_REVENUE_CODE_HEADER_PATTERN.search(raw_text))
```

If this header is found, the bill is a UB-04 facility claim with high confidence.

### Step 2 — Extract individual revenue codes (optional, for enrichment)

Revenue codes appear as 3–4 digit numbers in the `0xxx` range, typically one per line item.
Extraction is harder than header detection because `0360` is indistinguishable from other
4-digit numbers in raw OCR output without column position context.

The safest extraction approach is proximity-based: after detecting the `REV. CODE` header,
find the column position of that header and extract numbers from that column window using
Google Vision's bounding box coordinates (available in the full Vision API response, not
just the text output).

This requires storing Vision API bounding box data rather than just the concatenated text
string, which is a more substantial parser change.

**Recommendation:** Defer full revenue code extraction. Header detection alone is sufficient
for service type classification, and header detection is a 5-line parser addition.

### Step 3 — Wire into `_run_analysis_pipeline`

Replace the `hospital_name` heuristic with the revenue code detection result:

```python
# Before (current):
if hospital_name and service_type == "practitioner":
    service_type = "outpatient"

# After:
has_facility_claim = parser.has_revenue_codes(raw_text)
if (has_facility_claim or hospital_name) and service_type == "practitioner":
    service_type = "outpatient"
```

`raw_text` is already available in the pipeline at this point (it is the output of the
OCR step). No additional API calls or data loading required.

---

## Risk and edge cases

**False positives on header detection:** The string "REV. CODE" is unlikely to appear in
medical bill text for any reason other than the UB-04 revenue code column. Risk is low.

**Missing header in OCR output:** If Google Vision does not capture the column header
(e.g. it is in a very small font, or the bill is a scan of a summary page rather than the
full UB-04), the header detection falls back to the existing `hospital_name` heuristic.
These two signals are additive — either one triggers the outpatient classification.

**UB-04 with no revenue codes visible:** Hospital systems sometimes produce patient-facing
"itemized statements" derived from UB-04 data that omit the revenue code column. These
look like facility bills but lack the UB-04 structure. The `hospital_name` heuristic
continues to cover this case.

**Physician-hospital hybrid bills:** Some large academic medical centers submit professional
and facility charges on a single bill. These are uncommon and the correct classification
depends on whether the dominant charges are facility or professional — a problem that exists
regardless of revenue code detection.

---

## Effort estimate

| Step | Effort | Value |
|---|---|---|
| Header detection (`has_revenue_codes`) | ~1 hour | Closes the `hospital_name` failure edge case |
| Wire into pipeline | ~30 minutes | Completes the feature |
| Full revenue code extraction with bounding boxes | 2–3 days | Optional enrichment only |

**Recommended scope:** Steps 1 and 2 (header detection + pipeline wiring) only. Full
extraction is disproportionate effort for the marginal gain.

---

## Related improvements

- `docs/future_improvements/commercial-rate-benchmarking.md` — once the MRF pipeline has
  broad hospital coverage, `NEGOTIATED_RATE_EXCEEDED` will fire on most commercial bills and
  PRICE_OUTLIER will be a rare fallback — reducing the practical impact of this improvement
- `docs/rules-engine.md` — documents current `hospital_name` proxy and the commercial rate
  multiplier table that this improvement would make more accurate

---

*Document created: April 2026*  
*Owner: ClaroBill Engineering*
