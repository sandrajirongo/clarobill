# Engine & Parser Bug Tracker

**Status:** ARCHIVED 2026-05-05 — superseded by the unified [bug-fix campaign tracker](../playbooks/bug-fix-campaign.md). The findings here were folded into the campaign's S/H/M scheme during the 2026-05-04 audit.

Bugs identified during thorough review of `apps/engine/app/services/rules_engine.py`,
`apps/engine/app/api/v1/bills.py`, and `apps/engine/app/services/parser.py`.

Status values: `open` | `in progress` | `fixed`

---

## BUG-001 — Duplicate detection ignores modifiers

**Status:** fixed (April 23 2026)
**Severity:** high
**File:** `apps/engine/app/services/rules_engine.py:207`

### Issue

The dedup key is `(cpt_code, service_date)` — modifier is excluded. Two line items with the
same CPT code on the same date but different modifiers are legitimate billing in many situations:

- `99213` + `99213-25` — modifier 25 means a separately identifiable E&M service was performed
  alongside a procedure on the same day. This is one of the most common correct outpatient billing
  patterns.
- `99213-LT` + `99213-RT` — bilateral procedures billed once per side.
- `99213-59` appearing twice — distinct anatomical sites or distinct encounters.

The engine flags the second line as `DUPLICATE_CHARGE` and tells the patient they were
overcharged, falsely accusing the provider of fraud.

### Proposed fix

Include modifier in the key:

```python
# rules_engine.py:207
key = (item.cpt_code, str(item.service_date), item.modifier or "")
```

Two entries of `99213` with no modifier on the same date are still caught. `99213` vs `99213-25`
on the same date are left alone.

---

## BUG-002 — Price outlier overcharge wrong for multi-quantity items

**Status:** fixed (April 23 2026)
**Severity:** high
**Files:**
- `apps/engine/app/services/rules_engine.py:245` (`_detect_price_outliers`)
- `apps/engine/app/services/rules_engine.py:749` (`_detect_facility_outliers`)
- `apps/engine/app/services/rules_engine.py:662` (`_detect_hospital_charge_outliers`)
- `apps/engine/app/services/rules_engine.py:709` (`_detect_negotiated_rate_exceeded`)

### Issue

All four pricing rules compare `total_charge` against a per-unit Medicare/benchmark rate, then
calculate overcharge as `total_charge - benchmark_rate` (subtracting one unit's rate from the
total for all units).

Concrete example — ambulance mileage A0425, quantity=12, unit_charge=$9.50, total=$114.00,
Medicare rate=$7.00/mile:

```
Current:  114.00 > 7.00 × 1.8 = 12.60  →  flagged
          overcharge = 114.00 - 7.00 = $107.00  ← WRONG (3× too high)

Correct:  9.50 > 7.00 × 1.8 = 12.60   →  not flagged at all (correct — 9.50 < 12.60)
          if flagged: overcharge = (9.50 - 7.00) × 12 = $30.00
```

The comparison threshold is also wrong: a 5% per-unit overcharge on 12 units makes the total
look like a huge violation even if the per-unit rate is within tolerance.

Most CPT codes are billed at quantity=1 so this rarely triggers in practice, but ambulance codes
always have quantity > 1, and some inpatient codes can too.

### Proposed fix

Compare per unit, scale overcharge by quantity, in all four methods:

```python
billed = Decimal(str(item.unit_charge))
if benchmark > 0 and billed > benchmark * threshold:
    overcharge = (billed - benchmark) * item.quantity
```

Update description strings to reference the per-unit charge and mention quantity when > 1.

---

## BUG-003 — NCCI modifier check misses XE/XS/XP/XU

**Status:** fixed (April 23 2026)
**Severity:** medium
**File:** `apps/engine/app/services/rules_engine.py:315`

### Issue

The NCCI override check only looks for modifier 59:

```python
if any(item.modifier == "59" for item in col2_items):
    continue
```

CMS introduced four "X modifiers" in 2015 as more precise, preferred alternatives to modifier 59:

| Modifier | Meaning |
|----------|---------|
| XE | Distinct encounter (different session, same day) |
| XS | Separate structure (different anatomical site) |
| XP | Separate practitioner |
| XU | Unusual non-overlapping service |

Medicare specifically instructs providers that XE/XS/XP/XU are preferable to 59 when applicable.
A provider billing `93010-XE` alongside `99213` is using the preferred CMS method — but the engine
flags them for NCCI unbundling and tells the patient they are owed a refund for a correctly billed
charge.

### Proposed fix

Add a module-level constant and update the check:

```python
# Module level constant
_NCCI_OVERRIDE_MODIFIERS: frozenset[str] = frozenset({"59", "XE", "XS", "XP", "XU"})

# rules_engine.py:315
if any(item.modifier in _NCCI_OVERRIDE_MODIFIERS for item in col2_items):
    continue
```

---

## BUG-004 — PostgREST silently truncates NCCI pairs on large bills

**Status:** fixed (April 23 2026)
**Severity:** medium
**File:** `apps/engine/app/api/v1/bills.py:340`

### Issue

`_load_ncci_pairs` has no `.limit()` call. PostgREST's default row cap is 1000. For a hospital
outpatient bill with 30+ CPT codes where each code can be `column_one_code` for 30-50 pairs,
the result set can exceed 1000 rows. PostgREST silently returns 1000 and drops the rest — no
error, no warning.

The existing warning log only fires when `len(pairs) == 0`. A partial result (999 pairs returned,
200 silently dropped) sets `pairs` to a non-empty dict and no warning fires. Some NCCI violations
are missed with no indication anything went wrong. Which pairs are dropped depends on DB internal
ordering — effectively random.

Simple 5-code bills are fine. Hospital bills with 50+ codes almost certainly hit this limit.

### Proposed fix

Add an explicit high limit and log if it is reached:

```python
response = query.limit(10000).execute()

pairs: dict[str, set[str]] = {}
for row in response.data:
    pairs.setdefault(row["column_one_code"], set()).add(row["column_two_code"])

if len(response.data) >= 10000:
    logger.warning(
        "NCCI pairs result hit the 10000-row limit for cpt_codes=%s — "
        "some pairs may be silently missing. Consider paginating this query.",
        unique_codes,
    )
```

If bills with hundreds of codes ever need to be supported, replace with batched requests over
chunks of `unique_codes`.

---

## BUG-005 — MUE=0 double-reports with NON_PAYABLE_CODE

**Status:** fixed (April 23 2026)
**Severity:** low
**File:** `apps/engine/app/services/rules_engine.py:802`

### Issue

A bundled code (proc_stat='B') often also has MUE=0 in CMS tables. Both
`_detect_non_payable_codes` and `_detect_mue_violations` fire independently for the same line
item. The user sees two separate critical findings for the same underlying problem: one saying
the code is bundled, another saying MUE=0. The waterfall suppression doesn't prevent this because
both rules run independently before any suppression logic.

### Proposed fix

Skip MUE=0 inside `_detect_mue_violations` for codes already present in `self._non_payable_codes`:

```python
if mue_value == 0:
    if item.cpt_code in self._non_payable_codes:
        continue  # already covered by NON_PAYABLE_CODE rule
    errors.append(...)
    continue
```

---

## BUG-006 — Single rate_date used for all line items on cross-quarter bills

**Status:** fixed (April 23 2026)
**Severity:** low
**File:** `apps/engine/app/api/v1/bills.py:154`

### Issue

`_derive_rate_date` picks the most common service date across all line items, then uses it for
every reference data query on the entire bill. If a bill spans a CMS quarterly release boundary
(e.g., services on December 31 and January 1), line items on the minority side of the boundary
are benchmarked against the wrong quarter's rates.

Example: A December service is benchmarked against January rates. If the conversion factor
increased for the new year, the engine calculates a lower overcharge than the December rate
would have produced — or fails to flag a charge that was an outlier under December rates.

Low frequency: only affects bills that span Jan 1, Apr 1, Jul 1, or Oct 1.

### Proposed fix

Derive `rate_date` per line item and pass it through each loader call, so each code is
benchmarked against the quarterly release that was in effect on its own service date. This is
a larger refactor than the other fixes here — the loaders currently accept a single `rate_date`
and return a single dict. Would need to either batch by rate_date or extend the query to return
all releases and let the mapping code select the right one per code.

---

## BUG-007 — Modifier pattern captures non-modifier 2-char tokens

**Status:** fixed (April 23 2026)
**Severity:** low
**File:** `apps/engine/app/services/parser.py:20`

### Issue

```python
_MODIFIER_PATTERN = re.compile(r"\b(?:\d{5}|[A-Z]\d{4})\s+([A-Z0-9]{2})\b")
```

Any 2-character alphanumeric token immediately following a CPT code is captured as a modifier.
On a line like `99213 ER VISIT` or `99213 OR ROOM CHARGE`, "ER" and "OR" would be stored as the
modifier for that line item. These are not valid CMS modifiers. The practical damage is limited
because the engine only uses modifier values for equality checks ("59", "XE", etc.) — an invalid
modifier like "ER" never matches any of those and is harmlessly ignored. But it produces confusing
`modifier: "ER"` entries in stored line items and the report.

### Proposed fix

One option is a whitelist of known valid CMS modifiers (~200 codes). A simpler heuristic is to
only capture the modifier if the CPT code line contains no other words after the 2-char token
(i.e., the modifier is the last meaningful token before the charge), or to require the 2-char
token to appear on a known allowed-modifier list loaded from CMS data. Neither is trivial.

Lower priority: has no effect on reported errors or savings calculations.
