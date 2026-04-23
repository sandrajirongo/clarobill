# Engine Bug Fix Reference — April 2026

**Date:** 2026-04-22
**Status:** All 7 bugs resolved as of April 23 2026
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
- **Status** — fixed with commit SHA

---

## Bug 1 — NCCI Unbundling Never Fires

**Status:** Fixed — commit `7a9a8a1` (CPT filter) + `032243b` (WARNING log)

### What broke
Bill 3 (designed to trigger NCCI unbundling) returned zero errors. No
`NCCI_UNBUNDLING` error was ever flagged for any bill.

### Root cause
`_load_ncci_pairs()` in `apps/engine/app/api/v1/bills.py` queries
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
query from 2.3M rows to a handful of rows specific to the bill. Added WARNING log
when result is empty so silent zero-error results can be distinguished from clean bills.

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

**Status:** Fixed — commit `124f3b8`

### What broke
Bill 2 (designed with a charge 4× the Medicare non-facility rate) returned zero
errors. No `PRICE_OUTLIER` error was flagged.

### Root cause
Two compounding issues:

**Issue A — Empty `medicare_rates` dict:**
`_load_medicare_rates()` filters `cms_pfs_indicators` with `.eq("proc_stat", "A")`.
If the CPT code on the test bill has any proc_stat other than `'A'` in the DB — or
has no row at all — `medicare_rates` is an empty dict. The rules engine then hits
`continue` for every line item (no rate to compare against) and silently produces
zero price outlier errors. There is no log warning when this happens.

**Issue B — Wrong threshold for plan type:**
The engine used a single `medicare_outlier_threshold = 1.8` for all insurance types.
This is correct for commercial insurance but wrong for Medicare, Medicaid, self-pay,
and TRICARE patients.

### Fix
1. Added a `WARNING` log in `_load_medicare_rates` when the returned dict is empty.
2. Made `_detect_price_outliers` plan-type-aware with this threshold map:

| `plan_type` | Threshold | Reason |
|---|---|---|
| `medicare` | 1.05× | Rate IS the payment; 5% rounding tolerance only |
| `medicaid` | 1.05× | Medicaid pays less than Medicare; Medicare rate is the ceiling |
| `commercial` | 1.80× | Commercial negotiates 1.2–1.6×; flag above that band |
| `tricare` | 1.20× | TRICARE ≈ 110–120% of Medicare |
| `self_pay` | 1.20× | No contract; flag beyond modest markup |
| `None`/unknown | 1.80× | Conservative default |

3. Threaded `plan_type` through to `RulesEngine` and `_detect_price_outliers`.

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

---

## Bug 3 — Total Charges Extracted Are Inaccurate

**Status:** Fixed — commit `032243b`

### What broke
The `total_charges` value stored in `analysis_results` did not match the actual total
on all 3 test bills. The displayed totals were consistently lower than the real bill
total.

### Root cause
`_find_charge_in_window()` in `apps/engine/app/services/parser.py` used
`_AMOUNT_PATTERN.search()` which returns the **first** regex match in the string.
On any bill line with multiple dollar amounts (unit rate + total charge is the most
common format), the parser captured the unit rate (first column) instead of the total
charge (last column):

```
99214  Office Visit  1  $125.00  $250.00
                        ^-- parser captured this, not $250.00
```

### Fix
Replaced `_AMOUNT_PATTERN.search()` with `findall()` and take the last match. The
rightmost dollar amount on a CPT code line is always the total charge — unit rates,
allowances, or other amounts appear in earlier columns. Applied to both Pass 1
(proximity search) and Pass 2 (column-interleaved fallback).

**File changed:** `apps/engine/app/services/parser.py` — `_find_charge_in_window()`

---

## Bug 4 — Duplicate Detection Misses When Date Is a Section Header

**Status:** Fixed — commit `032243b`

### What broke
Bill 1 (containing one duplicate line item with identical code, date, description,
quantity, and charge) returned zero `DUPLICATE_CHARGE` errors.

### Root cause
`_find_date_in_window()` searched from `max(0, start - 1)` — only one line before
the CPT code line. On bills where the service date appears as a section header above
a block of line items, only the first CPT code gets the correct date. Subsequent
items fall outside the one-line lookback and get `date.today()` as fallback.

Example — two duplicate lines under a date header:
```
Line 0: Service Date: 03/15/2026
Line 1: 99214  Office Visit  $350.00   ← window covers line 0, gets 2026-03-15
Line 2: 99214  Office Visit  $350.00   ← window starts at line 1, misses line 0, gets today
```

Result: item 1 has date `2026-03-15`, item 2 has date `2026-04-22`. The dedup key
`(cpt_code, service_date)` differs — no duplicate flagged.

This bug also caused `_derive_rate_date()` to compute the wrong representative date,
making every reference data loader query the wrong CMS quarterly release.

### Fix
Implemented two-phase date search:
- Phase 1: ±`LOOKAHEAD_LINES` proximity search (same as before, but widened)
- Phase 2: Global backwards scan through all preceding lines to catch section-header
  dates regardless of distance

**File changed:** `apps/engine/app/services/parser.py` — `_find_date_in_window()`

---

## Bug 5 — Sync Clients Block the Async Event Loop

**Status:** Fixed — commit `032243b`

### What broke
No immediate failure in single-bill testing, but under concurrent load the engine
server stalls for the duration of every OCR and Claude API call.

### Root cause
Two violations:

**A — Anthropic client:** `AiAnalysisService` was using `anthropic.Anthropic`
(synchronous) despite being declared `async`. An `AsyncAnthropic` client existed in
`dependencies.py` but was never wired to the service.

**B — Google Cloud Vision:** `OcrService` called synchronous Vision client methods
directly inside `async` functions. Google Vision has no async variant.

### Fix
A: `get_ai_analysis_service()` now passes `get_async_anthropic_client()` (AsyncAnthropic).
   Both `messages.create()` calls are `await`ed.

B: Both Vision API calls wrapped with `asyncio.get_running_loop().run_in_executor()`
   to run the blocking call in a thread pool without blocking the event loop.

**Files changed:**
- `apps/engine/app/core/dependencies.py`
- `apps/engine/app/services/ai_analysis.py`
- `apps/engine/app/services/ocr.py`

---

## Bug 6 — `user_id` Dropped Before Pipeline

**Status:** Fixed — commit `032243b`

### What broke
`user_id` from `AnalyzeRequest` was silently discarded at the FastAPI handler
boundary and never passed to `_run_analysis_pipeline`.

### Fix
Added `user_id: str` to `_run_analysis_pipeline`'s signature. Passed `body.user_id`
in the `background_tasks.add_task(...)` call. Used in storage paths:
`{user_id}/{bill_id}/report.pdf` and `{user_id}/{bill_id}/dispute-letter.docx`.

**File changed:** `apps/engine/app/api/v1/bills.py`

---

## Bug 7 — Silent Empty Reference Data

**Status:** Fixed — commit `032243b` (medicare_rates, mue_limits) + `7a9a8a1` (ncci_pairs)

### What broke
When reference data loaders returned empty results the engine produced zero errors
with no log indication of whether the bill was clean or data was absent.

### Fix
Added `WARNING` logs after the three loaders whose absence disables a detection rule:
- `_load_ncci_pairs`: logs service_type, payer_type, service_date, and CPT codes when empty
- `_load_medicare_rates`: logs CPT codes and rate_date when no rates found
- `_load_mue_limits`: logs CPT codes when no MUE limits found

Note: `_load_non_payable_codes` intentionally has no empty warning — an empty result
means none of the bill's codes are non-payable, which is the normal happy-path case
for most bills. A WARNING there would fire on the majority of clean bills.

**File changed:** `apps/engine/app/api/v1/bills.py` — three loader functions

---

## Dependency Order

Bugs were fixed and tested in this order:

```
Bug 1 (NCCI query)        → commit 7a9a8a1 → tested with Bill 3
Bug 2 (price outlier)     → commit 124f3b8 → tested with Bill 2
Bug 3 (charge extraction) → commit 032243b → tested with all 3 bills
Bug 4 (duplicate dates)   → commit 032243b → tested with Bill 1
Bug 5 (async clients)     → commit 032243b → concurrent submission test
Bug 6 (user_id wiring)    → commit 032243b → confirmed in Cloud Run logs
Bug 7 (silent empties)    → commits 032243b + 7a9a8a1 → confirmed in logs
```

---

## Reference — Test Bills

| Bill | Designed to trigger | Expected error after fixes |
|---|---|---|
| Bill 1 | Duplicate charge | `DUPLICATE_CHARGE` critical, both line item IDs in affected list |
| Bill 2 | Price outlier (4× Medicare rate) | `PRICE_OUTLIER` warning, estimated overcharge = billed − Medicare rate |
| Bill 3 | NCCI unbundling | `NCCI_UNBUNDLING` critical, component code charge as overcharge |
