# NCCI Data Files — Assessment

**Files location:** `data/ncci/` (6 files, Q1 2026, effective 2026-01-01 – 2026-03-31)

---

## What's in the Directory

```
MCD-PTP-PractitionerServices-Effective_01012026.txt      177 MB
MCD-PTP-OutpatientHospitalServices-Effective_01012026.txt 132 MB
MCD-PTP-DMEServices-Effective_01012026.txt                2.5 MB
MCD-MUE-PractitionerServices-Effective_01012026.txt       510 KB
MCD-MUE-OutpatientHospitalServices-Effective_01012026.txt 505 KB
MCD-MUE-DMEServices-Effective_01012026.txt                 92 KB
```

---

## File Type 1: PTP (Procedure-to-Procedure Edits)

**What they are:** Each row defines a pair of codes where `Col1` (the "comprehensive" code) cannot be billed together with `Col2` (the "component" code) on the same claim, unless a bypass modifier (typically `59`) is present.

**Columns:**
```
Col1                  — Comprehensive HCPCS/CPT code
Col2                  — Component code
EffDt                 — Effective date (YYYYMMDD)
DelDt                 — Deletion date (YYYYMMDD, blank = still active)
ModifierIndicator     — 0 = modifier not allowed, 1 = modifier may override, 9 = N/A
PTP Edit Rationale    — Text description
```

**Are these the right files?** Yes. This is exactly the data the existing `_detect_ncci_unbundling` rule in the engine needs. The rule already uses a `dict[str, set[str]]` of `col1_code → {col2_codes}`, which maps directly to this format.

**Three service-type variants:**
- **PractitionerServices** — physician/professional claims (most bills users upload will be this type)
- **OutpatientHospitalServices** — hospital outpatient facility claims (EOBs from hospital visits)
- **DMEServices** — durable medical equipment supplier claims

For most beta users, **PractitionerServices** is the highest-priority file to load. A bill type classifier (or a flag from the user) would allow selecting the right file at analysis time.

---

## File Type 2: MUE (Medically Unlikely Edits)

**What they are:** Each row defines the maximum number of units of a given HCPCS/CPT code that can be billed on a single claim line on a single date of service. Billing above the MUE value is a red flag.

**Columns:**
```
HCPCS/CPT Code        — The procedure code
[ServiceType] MUE Values — Maximum allowed units (integer)
MUE Rationale         — Reason: "Code Descriptor / CPT Instruction", "CMS Policy", etc.
```

**Are these the right files?** Yes for future use — but the engine currently has **no MUE detection rule**. To use these files, you would need to:
1. Create a `ncci_mue_limits` database table
2. Write a loader script (`scripts/load_mue_limits.py`)
3. Add `_detect_mue_violations` to the `RulesEngine` class

The MUE check would flag line items where `quantity > mue_value` for a given code/service-date, which is a very high-value check for catching billing quantity inflation.

---

## Current Engine Integration

The engine's `_detect_ncci_unbundling` rule is wired to a `ncci_edit_pairs` DB table:

```python
# bills.py:248
def _load_ncci_pairs(supabase):
    response = supabase.table("ncci_edit_pairs")
        .select("column_one_code,column_two_code")
        .is_("deletion_date", "null")
        .execute()
```

DB schema (`ncci_edit_pairs`):
```sql
column_one_code    text   -- comprehensive code
column_two_code    text   -- component code
effective_date     date
deletion_date      date   -- null = still active
modifier_indicator integer (0, 1, or 9)
```

The loader script `scripts/load_ncci_edits.py` was written to load this table, but it has a **format mismatch** with the new `.txt` files.

---

## Loader Script Issues to Fix

The existing `load_ncci_edits.py` expects a CSV file. The `.txt` files are **tab-delimited** with a **multi-line quoted preamble** before the header row. The loader needs these changes:

1. **Delimiter:** Change `csv.reader` to use `delimiter='\t'`
2. **Preamble skipping:** The first several rows are a quoted copyright/disclaimer block. Skip rows until the actual header (`Col1\tCol2\t...`) is found, not just `row[0].isdigit()`
3. **Column mapping:** The PTP files use `Col1, Col2, EffDt, DelDt, ModifierIndicator...` — map these by position (same as current loader) or by header name after finding the header row
4. **Service type flag:** Add a `--service-type` argument (`practitioner`, `outpatient`, `dme`) to tag rows, enabling the engine to load the right set based on bill type

**Minimal fix (just make it work):**
```python
# Skip preamble: read until we hit a row starting with a 5-char code or "Col1"
with path.open(newline='', encoding='utf-8-sig') as f:
    reader = csv.reader(f, delimiter='\t')
    data_started = False
    for row in reader:
        if not data_started:
            if row and row[0].strip() in ('Col1', 'HCPCS/CPT Code'):
                data_started = True  # next row is data
            continue
        # process row
```

---

## Recommended Next Steps

**Priority 1 — Load PTP data (unblocks NCCI rule for production):**
1. Fix `load_ncci_edits.py` for tab-delimited format + preamble
2. Run against `MCD-PTP-PractitionerServices-Effective_01012026.txt` first
3. Optionally tag rows with `service_type = 'practitioner'`

**Priority 2 — Add service-type awareness:**
- Add `service_type` column to `ncci_edit_pairs` table (migration required)
- Load all three PTP files
- Pass bill context (practitioner vs. outpatient vs. DME) to the engine at analysis time

**Priority 3 — Implement MUE detection:**
1. Create `ncci_mue_limits` table: `(id, hcpcs_code, service_type, mue_value, mue_rationale)`
2. Write `scripts/load_mue_limits.py`
3. Add `_detect_mue_violations` rule to `RulesEngine`:
   - Flag any line item where `item.quantity > mue_value` for that code
   - Severity: `critical` (quantity inflation is a significant billing error)
   - Estimated overcharge: `(item.quantity - mue_value) * item.unit_charge`

---

## Note on "MCD" File Prefix

The `MCD-` prefix in the filenames stands for **Medicare** (from CMS's internal naming convention), not Medicaid. The preamble explicitly states: *"This file should NOT be used by state Medicaid programs as their edit file"* — meaning these are Medicare/commercial payer NCCI edits. State Medicaid programs use separately published state-specific files.
