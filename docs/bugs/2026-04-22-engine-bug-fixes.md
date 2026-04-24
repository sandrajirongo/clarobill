# Engine Bug Fix Reference — April 2026

**Date:** 2026-04-22
**Status:** In progress — fixes applied one at a time, tested after each push
**Context:** Full diagnostic performed April 22 2026 after all 3 sample test bills
returned zero errors. Root cause analysis traced 8 distinct bugs across the parser,
rules engine, and data loading pipeline.

---

## How to use this document

Each bug has:
- **What broke** — the exact symptom the user observed
- **Root cause** — the actual code defect, with file and line
- **Fix** — what was changed
- **How to test** — the specific bill and expected result to verify the fix worked
- **Status** — pending / fixed / verified

---

## Bug 1 — NCCI Unbundling Never Fires

**Status:** pending

### What broke
Bill 3 (designed to trigger NCCI unbundling) returned zero errors. No
`NCCI_UNBUNDLING` error was ever flagged for any bill.

### Root cause
`_load_ncci_pairs()` in `apps/engine/app/api/v1/bills.py:299` queries
`ncci_edit_pairs` with only `service_type` and `payer_type` filters and no CPT code
filter. For `practitioner/medicare` this matches 2,323,399 rows. Supabase PostgREST
returns at most 1000 rows per request by default. The engine receives 1000 arbitrary
pairs out of 2.3 million — a 0.04% sample. The specific pair on any test bill is
almost certainly not in those 1000 rows. Unbundling detection is permanently broken
in production regardless of the bill content.

The 120 unit tests all pass because they inject NCCI pairs directly into the
`RulesEngine` constructor and never call `_load_ncci_pairs`.

### Fix
Filter the NCCI query by `column_one_code IN (cpt_codes_on_bill)`. The unbundling
rule only fires when the column-one (comprehensive) code is on the bill, so
pre-filtering by column_one_code is both correct and sufficient. This reduces the
query from 2.3M rows to a handful of rows specific to the bill.

**File changed:** `apps/engine/app/api/v1/bills.py` — `_load_ncci_pairs()`

### How to test
Use Bill 3 (the NCCI unbundling test bill). After the fix, the analysis result must
contain at least one `NCCI_UNBUNDLING` error with `severity: critical`. The
`affected_line_item_ids` must reference the component (column-two) code line item.
The `estimated_overcharge` must equal the charge of the component code.

Also verify: a clean bill with no NCCI pairs present must still return zero
`NCCI_UNBUNDLING` errors (no false positives introduced).

---

## Bug 2 — Price Outlier Not Firing

**Status:** fixed (commit 260c43f)

### What broke
Any bill returned zero `PRICE_OUTLIER` errors regardless of how overpriced the charges were.

### Root cause
Three compounding issues:

**Issue A — Wrong modifier filter (NULL vs empty string):**
`_load_medicare_rates()` and `_load_non_payable_codes()` both filtered
`cms_pfs_indicators` with `.eq("modifier", "")`. The modifier column is stored
as `NULL` (not empty string) for base/no-modifier rows. `modifier = ''` never
matches `NULL`, so both functions always returned empty dicts — permanently
disabling PRICE_OUTLIER and non-payable code detection for every bill.
Fixed in commit 260c43f: changed `.eq("modifier", "")` → `.is_("modifier", "null")`
in both queries.

**Issue B — Empty `medicare_rates` dict (original analysis):**
`_load_medicare_rates()` also filters with `.eq("proc_stat", "A")`.
If the CPT code has any proc_stat other than `'A'` in the DB, `medicare_rates`
is empty. A `WARNING` log was added so this is now visible in Cloud Run logs.

**Issue C — Wrong threshold for plan type:**
The engine uses a single `medicare_outlier_threshold = 1.8` for all insurance types.
This is correct for commercial insurance but wrong for:
- Medicare patients: Medicare rate IS the payment; anything above it is an overcharge
- Medicaid patients: Medicaid pays 70–90% of Medicare; Medicare rate is the ceiling
- Self-pay: no contracted rate; modest markup only
- TRICARE: tracks Medicare closely at ~110–120%

### Fix
1. Add a `WARNING` log in `_load_medicare_rates` when the returned dict is empty,
   listing the CPT codes that had no rate found and why (no `proc_stat='A'` row).
2. Make `_detect_price_outliers` plan-type-aware using this threshold map:

| `plan_type` | Threshold | Reason |
|---|---|---|
| `medicare` | 1.05× | Rate IS the payment; 5% rounding tolerance only |
| `medicaid` | 1.05× | Medicaid pays less than Medicare; Medicare rate is the ceiling |
| `commercial` | 1.80× | Commercial negotiates 1.2–1.6×; flag above that band |
| `tricare` | 1.20× | TRICARE ≈ 110–120% of Medicare |
| `self_pay` | 1.20× | No contract; flag beyond modest markup |
| `None`/unknown | 1.80× | Conservative default |

3. Thread `plan_type` through to `RulesEngine` and `_detect_price_outliers`.

**Files changed:**
- `apps/engine/app/api/v1/bills.py` — `_load_medicare_rates()` (add warning log)
- `apps/engine/app/services/rules_engine.py` — `__init__`, `_detect_price_outliers`
- `apps/engine/app/api/v1/bills.py` — `RulesEngine(...)` instantiation (pass plan_type)

### How to test
Use Bill 2 (price outlier test bill, charge 4× Medicare rate).

**If plan_type is `commercial`:** Expect `PRICE_OUTLIER` with severity `warning`,
`medicare_benchmark_rate` showing the Medicare rate, and
`estimated_overcharge = billed - medicare_rate`.

**If plan_type is `medicare`:** Any charge above 1.05× the rate must flag.

**Regression check:** A bill with a charge at exactly 1.5× Medicare for a commercial
plan must NOT flag (1.5 < 1.8 threshold). A charge at 1.9× must flag.

Also check engine logs: if `medicare_rates` is empty after the fix is applied, the
warning log must appear in Cloud Run logs.

---

## Bug 3 — Total Charges Extracted Are Inaccurate

**Status:** pending

### What broke
The `total_charges` value stored in `analysis_results` did not match the actual total
on all 3 test bills. The displayed totals were consistently lower than the real bill
total.

### Root cause
`_find_charge_in_window()` in `apps/engine/app/services/parser.py:213` uses
`_AMOUNT_PATTERN.search()` which returns the **first** regex match in the string.
On any bill line with multiple dollar amounts (unit rate + total charge is the most
common format), the parser captures the unit rate (first column) instead of the total
charge (last column):

```
99214  Office Visit  1  $125.00  $250.00
                        ^-- parser captures this, not $250.00
```

The stored `total_charge` per line item and the summed `total_charges` in
`analysis_results` are therefore wrong for every bill that uses a unit-rate + total
layout.

### Fix
Replace `_AMOUNT_PATTERN.search()` with `findall()` and take the last match. The
rightmost dollar amount on a CPT code line is always the total charge — unit rates,
allowances, or other amounts appear in earlier columns.

**File changed:** `apps/engine/app/services/parser.py` — `_find_charge_in_window()`

### How to test
Use any of the 3 test bills. After the fix, the `total_charges` in the analysis
result must match the total shown on the physical bill. Check the individual
`line_items` rows in Supabase — each `total_charge` must match the rightmost dollar
amount on the corresponding line of the bill.

Also verify the parser unit tests still pass: `cd apps/engine && python -m pytest
tests/services/test_parser.py -v`

---

## Bug 4 — Duplicate Detection Misses When Date Is a Section Header

**Status:** pending

### What broke
Bill 1 (containing one duplicate line item with identical code, date, description,
quantity, and charge) returned zero `DUPLICATE_CHARGE` errors.

### Root cause
`_find_date_in_window()` in `apps/engine/app/services/parser.py:222` searches from
`max(0, start - 1)` — only one line before the CPT code line. On bills where the
service date appears as a section header above a block of line items (the most common
real-world format), only the first CPT code line is close enough to the date to pick
it up. Subsequent lines fall outside the one-line lookback and get `date.today()` as
the fallback.

Example — two duplicate lines under a date header:
```
Line 0: Service Date: 03/15/2026
Line 1: 99214  Office Visit  $350.00   ← window covers line 0, gets 2026-03-15
Line 2: 99214  Office Visit  $350.00   ← window starts at line 1, misses line 0, gets today
```

Result: item 1 has date `2026-03-15`, item 2 has date `2026-04-22` (today). The
dedup key `(cpt_code, service_date)` differs — no duplicate flagged.

### Fix
Widen the lookback window to search up to `_LOOKAHEAD_LINES` (3 lines) before the
current line, not just 1. This covers all common bill formats where a date header
sits above a block of items.

Also: if no date is found in the expanded window, scan the entire document for the
most recent date that appears before the current line — a global lookback for the
nearest preceding date. This handles formats where dates appear once per page or once
per section.

**File changed:** `apps/engine/app/services/parser.py` — `_find_date_in_window()`

### Critical dependency — rate_date accuracy

`_derive_rate_date()` in `bills.py:233` computes the representative service date
from the parsed line items by taking the most common date across all items. Every
reference data loader (`_load_ncci_pairs`, `_load_medicare_rates`, `_load_mue_limits`,
`_load_opps_rates`, `_load_ambulance_rates`, `_load_anesthesia_cf`, etc.) uses this
`rate_date` to select the correct quarterly CMS release — the one in effect at the
time of service.

If the date lookback bug causes some line items to get `date.today()` instead of the
real service date, `_derive_rate_date` will compute the wrong `rate_date`, and every
loader will query against the wrong CMS quarterly release. This means benchmark rates,
NCCI edit pairs, and MUE limits from a different quarter will be applied to the bill.

**Fixing Bug 4 is therefore a prerequisite for correct benchmark matching across all
rules — not just for duplicate detection.**

### How to test
Use Bill 1 (duplicate test bill). After the fix, the analysis result must contain
exactly one `DUPLICATE_CHARGE` error with `severity: critical`. The
`affected_line_item_ids` must reference both line item records for the duplicated
code. The `estimated_overcharge` must equal the full charge of the duplicate item.

Separately verify date matching: the `rate_date` logged in Cloud Run for each bill
must match the actual service date on the bill, not today's date.

Also run the parser tests: `cd apps/engine && python -m pytest
tests/services/test_parser.py -v` — all must still pass.

---

## Bug 5 — Sync Clients Block the Async Event Loop

**Status:** pending

### What broke
No immediate user-visible failure in single-bill testing, but under any concurrent
load the engine server freezes for the duration of every OCR call and every Claude
API call. This will cause timeouts and dropped requests in production.

### Root cause
Two violations:

**A — Anthropic client:**
`get_ai_analysis_service()` in `apps/engine/app/core/dependencies.py:39` passes
`anthropic.Anthropic` (synchronous) to `AiAnalysisService`. Both
`generate_bill_summary()` and `generate_dispute_letter()` are declared `async` but
call `self._client.messages.create()` synchronously. The `await asyncio.sleep(0)`
before each call yields for one tick then immediately blocks. An `AsyncAnthropic`
client already exists at `get_async_anthropic_client()` in `dependencies.py:31` but
is never used.

**B — Google Cloud Vision client:**
`OcrService._extract_from_image()` and `_extract_from_pdf()` in
`apps/engine/app/services/ocr.py:64,78` are declared `async` but call the
synchronous `vision.ImageAnnotatorClient` methods directly. Google's Vision client
has no async variant; the correct pattern is `asyncio.get_event_loop().run_in_executor(None, sync_call)`.

### Fix
A: Change `get_ai_analysis_service()` to pass `get_async_anthropic_client()`.
   Update `AiAnalysisService.__init__` to accept `anthropic.AsyncAnthropic`.
   Change both `messages.create()` calls to `await self._client.messages.create()`.

B: Wrap both Vision API calls with `asyncio.get_event_loop().run_in_executor(None, ...)`.
   This runs the blocking call in a thread pool without blocking the event loop.

**Files changed:**
- `apps/engine/app/core/dependencies.py` — `get_ai_analysis_service()`
- `apps/engine/app/services/ai_analysis.py` — `__init__`, both `messages.create()` calls
- `apps/engine/app/services/ocr.py` — `_extract_from_image()`, `_extract_from_pdf()`

### How to test
Submit two bills for analysis simultaneously. With the sync bug present, the second
request stalls until the first completes. After the fix, both should process
concurrently and complete in roughly the same elapsed wall time.

For a lighter check: run `cd apps/engine && python -m pytest tests/ -v` — all tests
must pass. The AI analysis tests use `test_mode=True` and do not exercise the real
client path but confirm nothing regressed.

---

## Bug 6 — `user_id` Dropped Before Pipeline; User Mismatch Cannot Be Built

**Status:** pending

### What broke
User mismatch detection (comparing the insurance and user data the patient entered
against what the bill says) does not exist and cannot be added without this fix.

### Root cause
`AnalyzeRequest` in `apps/engine/app/models/bill.py:99` declares `user_id: str` but
`analyze_bill()` in `apps/engine/app/api/v1/bills.py:58` never passes it to
`_run_analysis_pipeline`. The pipeline function has no `user_id` parameter. The
value is silently discarded at the FastAPI handler boundary. There is no way for
any pipeline code or rule to know which user submitted the bill.

### Fix
Add `user_id: str` to `_run_analysis_pipeline`'s signature and pass `body.user_id`
in the `background_tasks.add_task(...)` call. Store `user_id` for future mismatch
detection. No mismatch rule is built in this fix — this is the wiring prerequisite.

**Files changed:** `apps/engine/app/api/v1/bills.py` — `analyze_bill()`,
`_run_analysis_pipeline()` signature

### How to test
Verify `user_id` appears in the Cloud Run logs for a submitted bill (add a
`logger.info("Processing bill %s for user %s", bill_id, user_id)` statement).
No change in analysis results — this is infrastructure for future work.

---

## Bug 7 — Silent Empty Reference Data

**Status:** pending

### What broke
When any reference data loader returns an empty dict (no Medicare rates, no NCCI
pairs, no MUE limits), the engine silently produces zero errors with no indication
of whether the bill was clean or the data was absent. Impossible to distinguish in
production logs.

### Root cause
No warning logs after `_load_ncci_pairs`, `_load_medicare_rates`, and
`_load_mue_limits` return. The engine logs only "Rules engine found 0 errors in N
line items" — no information about what data was or was not available to make that
determination.

### Fix
Add `WARNING` log after each loader when the returned dict is empty:
- After `_load_ncci_pairs`: log service_type, payer_type, service_date, and CPT codes queried
- After `_load_medicare_rates`: log which CPT codes had no rate found and the rate_date used
- After `_load_mue_limits`: log which CPT codes had no MUE limit found

**File changed:** `apps/engine/app/api/v1/bills.py` — `_run_analysis_pipeline()`

### How to test
Submit a bill with a CPT code that is NOT in `cms_pfs_indicators`. Check Cloud Run
logs — must see a `WARNING` entry listing the code and confirming no rate was found.
No change in analysis results — this is observability only.

---

## Dependency Order

Bugs must be fixed and tested in this order. Each depends on the previous being
verified before the next push:

```
Bug 1 (NCCI query)        → test with Bill 3
Bug 2 (price outlier)     → test with Bill 2
Bug 3 (charge extraction) → test with all 3 bills (charges should now match)
Bug 4 (duplicate dates)   → test with Bill 1
Bug 5 (async clients)     → test with concurrent submissions
Bug 6 (user_id wiring)    → confirm in logs
Bug 7 (silent empties)    → confirm in logs
```

---

## Reference — Test Bills

| Bill | Designed to trigger | Expected error after fixes |
|---|---|---|
| Bill 1 | Duplicate charge | `DUPLICATE_CHARGE` critical, both line item IDs in affected list |
| Bill 2 | Price outlier (4× Medicare rate) | `PRICE_OUTLIER` warning, estimated overcharge = billed − Medicare rate |
| Bill 3 | NCCI unbundling | `NCCI_UNBUNDLING` critical, component code charge as overcharge |
