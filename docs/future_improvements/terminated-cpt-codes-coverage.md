# Future Improvement: Terminated CPT Code Detection

**Status:** Planned — requires external data source not currently loaded  
**Priority:** Medium  
**Related bug tracker:** N/A (data gap, not a code bug)

---

## What the gap is

The engine has two rules for detecting codes that should not be billed:

- **`_detect_non_payable_codes`** (`rules_engine.py`) — catches CPT codes currently in
  `cms_pfs_indicators` with `proc_stat IN ('I', 'B', 'N')`. Inactive (`I`) is how CMS marks
  retired CPT codes in the PFS file.
- **`_detect_terminated_codes`** (`rules_engine.py`) — catches **HCPCS Level II codes only**
  (alpha prefix: A0425, J1234) with a non-null `termination_date` in `cms_hcpcs_codes`.

Neither rule covers CPT codes that were deleted **before our loaded CMS PFS data window**.
The current database contains PFS data from 2024 onward. A CPT code retired in 2008 will not
appear in any loaded CMS PFS file — it is completely absent from `cms_pfs_indicators`. When the
engine queries for it, zero rows are returned, no findings are generated, and the overcharge goes
undetected.

`_load_non_payable_codes` acknowledges this explicitly:
> "Codes not present in cms_pfs_indicators are ignored — we only flag what we can confirm,
> not codes we simply don't recognise."

### Confirmed test case

A test bill contained a CPT code deleted effective **2008-01-01**, billed with a service date
of **2022-11-14**. The engine produced zero findings for that line item.

---

## Why it matters

Providers occasionally use retired codes — either by mistake, because their billing software has
not been updated, or in rare cases intentionally (a retired code may have had a higher
reimbursement rate when it was active). Billing a deleted CPT code means the claim will be denied
by Medicare and most commercial payers, leaving the patient responsible for a charge that should
never have been submitted in that form.

CPT codes deleted before 2020 are the most likely to be missed: they were retired before our
data window and will not appear in any file we have loaded.

---

## Why we don't have this data yet

CMS PFS files only contain codes that were active during that filing period. A code retired in
2008 last appeared in the 2007 or 2008 PFS annual file. Loading those vintage files would capture
it with `proc_stat='I'`, but:

1. Pre-2020 CMS PFS files use slightly different formats (the PPRRVU format with different column
   positions for some years) — the current loader (`scripts/load_cms_pfs.py`) would need format
   detection for those vintages.
2. The AMA owns the CPT code system and publishes authoritative deletion dates in their annual
   CPT code change files, but those files are proprietary and require a license.
3. CMS publishes the "Medicare Physician Fee Schedule Addenda" which tracks code status changes
   and is free — but it is published only for the current year, not historical vintages.

---

## Options to fix this

### Option A — Load historical CMS PFS vintages (2008–2019)

Download and load the CMS PFS PPRRVU files from the years covering the gap. These files include
retired codes with `proc_stat='I'`. The existing query `effective_from <= rate_date` would
automatically pick them up for historical bills.

**Pros:**
- Uses existing loader infrastructure and database schema.
- No new data source or licensing required.
- Historical bills are benchmarked against the rates actually in effect at time of service.

**Cons:**
- CMS PPRRVU format changed slightly between 2008 and 2020 (column order, header format).
  The `load_indicators_pprrvu()` function would need format detection for older vintages.
- Adds ~15 years × ~10,000 rows ≈ 150,000 rows to `cms_pfs_indicators`. Manageable.
- CMS PPRRVU files older than ~5 years may be harder to locate (CMS does not guarantee
  indefinite archive availability — Wayback Machine may be needed).

### Option B — Dedicated deleted CPT codes table (recommended)

Create a separate table `cms_deleted_cpt_codes (cpt_code TEXT, deleted_effective DATE)` and a
corresponding rule that checks it directly, separate from the PFS data pipeline.

Data source options:
- **CMS "Relative Value Files" archived by CMS or third parties** — these include code status
  history and are free. The CMS website maintains archives back to at least 2010.
- **AMA CPT code change files** — authoritative but proprietary ($500–2,000/year for a license).
- **Manual curation** — for the highest-impact cases, maintain a curated list of commonly
  misused retired codes. A list of the top 100 frequently misused retired codes would cover the
  vast majority of real-world billing errors of this type.

**Pros:**
- Surgical — no changes to the PFS loading pipeline.
- Easy to add to incrementally (one row per deleted code).
- Can include a `reason` field (retired, consolidated into X, replaced by Y) for better report copy.

**Cons:**
- Requires either a data source or manual curation effort.
- May not be exhaustive without a paid AMA license.

### Option C — Flag unknown CPT codes (heuristic)

If a CPT code appears on a bill but has NO entry in `cms_pfs_indicators` for any `effective_from`
(not filtered by date), treat it as suspicious and emit a lower-severity finding.

**Pros:** No new data required, catches all missing codes.

**Cons:**
- High false positive risk: any code we haven't loaded yet (e.g., a code added in 2027 if our
  data is from 2026) would also be flagged.
- Requires a query without the `effective_from` filter, which returns a larger result set.
- The finding would be vague ("code not found in our database") rather than specific
  ("code retired effective 2008-01-01").

Not recommended as the primary approach, but could serve as a low-severity fallback.

---

## Recommended implementation plan

**Phase 1 (no data yet):** Add Option C as a low-severity `UNKNOWN_CODE` warning. Any CPT code
absent from `cms_pfs_indicators` entirely (not just filtered by date) gets flagged with a
"we could not verify this code" message. Gives users a signal without making a definitive claim.

**Phase 2 (after data is sourced):** Source the CMS Relative Value File archives for 2008–2023.
Build a one-time loader that extracts codes with `proc_stat='I'` and their last-active year.
Load into a dedicated `cms_deleted_cpt_codes` table. Wire a new `TERMINATED_CPT_CODE` rule that
checks this table and fires a `critical` finding with the specific deletion date.

---

## Engine changes required (Phase 2)

### New table

```sql
CREATE TABLE cms_deleted_cpt_codes (
  cpt_code        TEXT NOT NULL,
  deleted_effective DATE NOT NULL,
  replaced_by     TEXT,        -- replacement code if one exists
  reason          TEXT,        -- human-readable reason for deletion
  PRIMARY KEY (cpt_code)
);
```

### New loader function in bills.py

```python
def _load_deleted_cpt_codes(
    supabase: Client,
    cpt_codes: list[str],
) -> dict[str, date]:
    """Return a map of cpt_code → deleted_effective for any deleted codes on the bill."""
    ...
```

### New rule in rules_engine.py

```python
def _detect_terminated_cpt_codes(
    self, line_items: list[ParsedLineItem]
) -> list[DetectedError]:
    """Flag CPT codes billed after their CMS deletion date."""
    ...
```

### New RulesEngine constructor parameter

```python
deleted_cpt_codes: dict[str, date] | None = None
```

---

*Document created: April 2026*  
*Owner: ClaroBill Engineering*  
*Related: `apps/engine/app/services/rules_engine.py`, `apps/engine/app/api/v1/bills.py`,
`scripts/load_cms_pfs.py`*
