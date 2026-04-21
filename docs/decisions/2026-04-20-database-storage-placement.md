# Database and Storage Placement

**Date:** 2026-04-20
**Status:** Active

---

## Context

ClaroBill uses two distinct data stores for reference data:

- **Supabase (PostgreSQL)** — application database, also holds CMS reference tables
- **BigQuery (GCP `clarobill-prd`)** — analytical data warehouse, holds hospital price transparency data

Early in the build, hospital charge data (MRF files) went to BigQuery and CMS NCCI data went to Supabase without a documented rationale. This decision record captures the criteria so future reference data additions are placed consistently.

---

## Decision Criteria

A reference dataset belongs in **BigQuery** when all of the following are true:

1. **Volume exceeds practical Postgres limits** — hundreds of millions to billions of rows, or multi-gigabyte files that would bloat a shared Postgres instance
2. **Query pattern is bulk analytical** — the engine scans or aggregates large portions of the table per query (e.g. `GROUP BY code` across an entire hospital's charge table), not point lookups by a small set of keys
3. **Data is loaded in bulk, not row-by-row** — ingested via load jobs from GCS blobs, not from Python scripts upserting batches of hundreds

A reference dataset belongs in **Supabase** when:

1. **Volume fits comfortably in Postgres** — millions of rows with indexed access; well within Postgres's practical range
2. **Query pattern is a point lookup** — the engine filters to a small set of keys (specific CPT codes, a date range) and retrieves those rows by index; the vast majority of the table is never touched per query
3. **Latency matters** — the data is queried inline during bill analysis, where BigQuery's 1–5 second cold query overhead would add unacceptable latency to every bill processed

---

## Applied to Existing Tables

### Hospital charges → BigQuery

| Factor | Detail |
|--------|--------|
| Volume | ~7,000 hospitals × thousands of CPT codes × every payer/plan = potentially billions of rows |
| Query pattern | Bulk scan per hospital: `WHERE hospital_npi = ? AND code IN UNNEST(?)` returns many rows that are then grouped or aggregated |
| Load pattern | Parser ingests full MRF v2.0.0 files from GCS as NDJSON load jobs — individual rows are never upserted |
| Latency tolerance | Hospital charge lookups are optional enrichment; a 2–3s BigQuery cold query is acceptable |

**Conclusion:** BigQuery is the only practical option. These files cannot fit in a Postgres instance at reasonable cost, and the query pattern is analytical.

### NCCI PTP edit pairs → Supabase

| Factor | Detail |
|--------|--------|
| Volume | ~2.2M unique pairs per service type × 3 service types = ~6.6M rows. One quarterly file per year per service type is loaded; older pairs stay in the table with their original `effective_date`. |
| Query pattern | Per-bill point lookup: `WHERE service_type = ? AND payer_type = ? AND effective_date <= ? AND (deletion_date IS NULL OR deletion_date >= ?)` — returns only the pairs that were active on the bill's service date. The engine never scans the full table. |
| Load pattern | Tab-delimited CMS files, upserted in 500-row batches by `load_ncci_edits.py`. Deduplication run before upsert to comply with PostgreSQL's constraint on duplicate conflict keys. |
| Latency tolerance | Queried inline during every bill analysis; must be fast |

**Conclusion:** Supabase. Volume is manageable for Postgres with the existing unique constraint index. Point lookups by service_type + payer_type + effective_date return quickly. BigQuery would add seconds of latency on every bill analysis for no gain.

### NCCI MUE limits → Supabase

| Factor | Detail |
|--------|--------|
| Volume | ~14K codes per quarterly file × 3 service types × 2 payer types × ~28 quarters (2020–2026) = ~2M rows |
| Query pattern | Per-bill point lookup: `WHERE hcpcs_code IN (?) AND service_type = ? AND payer_type = ? AND effective_date <= ?` ordered by `effective_date DESC`. Only the CPT codes on the current bill are fetched, limited to one row per code (most recent qualifying quarter). |
| Load pattern | CSV/TXT CMS files, upserted in 500-row batches by `load_mue_limits.py`. Deduplication run before upsert. |
| Latency tolerance | Queried inline during every bill analysis; must be fast |

**Conclusion:** Supabase. Same reasoning as PTP — small indexed point lookup, latency-sensitive, well within Postgres capacity.

---

## Date-Aware Lookup Design

Both NCCI tables store historical data across quarters so the engine applies the rules that were in effect *on the bill's service date*, not today's current rules.

**Why this matters:** A bill from 2022 should be checked against the edit pairs and MUE limits that were active in 2022. Applying 2026 rules to a 2022 bill would produce false positives (flagging bundles that didn't exist yet) or false negatives (missing edits that were active then but have since been removed).

**Implementation:**

- `ncci_mue_limits` — one row per `(hcpcs_code, service_type, payer_type, effective_date)`. The engine queries `effective_date <= service_date`, orders `effective_date DESC`, and keeps the first row per code (most recent quarterly release in effect on the service date).
- `ncci_edit_pairs` — one row per `(column_one_code, column_two_code, service_type, payer_type)` with `effective_date` and `deletion_date` per row. The engine queries `effective_date <= service_date AND (deletion_date IS NULL OR deletion_date >= service_date)`, returning only pairs that were active on the service date.

Hospital charges in BigQuery do not require this treatment — MRF files represent current contracted rates, not historical snapshots.

---

## Load and Refresh Patterns

### Why upsert is the default — no pre-delete needed

Both NCCI tables use `ON CONFLICT DO UPDATE` (upsert). PostgreSQL enforces the unique constraint at the database level: a row with the same conflict key is updated in place; no duplicate can be created. Pre-deleting before an upsert is therefore never required for correctness — it only wastes time and risks statement timeouts on large tables.

`load_ncci_all.sh` uses plain upsert for all files. Re-running the script is always safe.

### The `--replace` flag on `load_ncci_edits.py` — when it is needed

The `--replace` flag exists for one specific use case: **quarterly refresh of PTP pairs**.

CMS PTP files are cumulative snapshots of *currently active* pairs. When CMS removes a pair from the edit table, it simply omits the pair from the next quarterly file — it does not mark the pair with a deletion date or send a tombstone record. This means:

- On the **initial historical load**, `--replace` must NOT be used. The DB accumulates pairs from all years, each with its own `effective_date`. Upsert is correct.
- On a **quarterly refresh** (replacing the current active ruleset with a new CMS release), `--replace` must be used. Without it, pairs that CMS removed from the new file would remain in the DB as phantom active rules that the engine would incorrectly apply to new bills.

`--replace` calls the `delete_ncci_pairs(service_type, payer_type)` RPC function (migration 20260420000020) rather than a direct DELETE. The RPC sets `statement_timeout = 300s`, bypassing the 30s PostgREST limit that causes timeouts when deleting 2M+ rows.

### MUE files — `--replace` removed entirely

MUE files do not have the same problem. Each quarterly file loads with a distinct `effective_date`, so each quarter occupies its own partition of the unique key `(hcpcs_code, service_type, payer_type, effective_date)`. There is no risk of phantom rows from a previous quarter contaminating a newer quarter's lookups — the engine always queries `effective_date <= service_date` and takes the most recent qualifying row. `--replace` was removed from `load_mue_limits.py` because it provided no correctness benefit and added unnecessary delete overhead.

### Refresh cadence

| Table | Source | Pattern |
|-------|--------|---------|
| `ncci_edit_pairs` | CMS MCD/MCR PTP files | **Initial load:** `bash scripts/load_ncci_all.sh` (upsert, no delete). **Quarterly refresh:** `python3 scripts/load_ncci_edits.py --file <new_file> --service-type <type> --payer-type <payer> --replace` |
| `ncci_mue_limits` | CMS MCR CSV + MCD TXT files | Always upsert. Run `bash scripts/load_ncci_all.sh` or load individual files. Prior quarters are preserved automatically. |
| `hospital_charges` | CMS MRF v2.0.0 files | Parser deletes then reloads all rows for a given `hospital_npi` each scrape cycle — BigQuery handles this via MERGE |

CMS releases new NCCI files each January, April, July, and October.

---

## Rule for Future Reference Data

When adding a new CMS or third-party reference dataset, answer these questions in order:

1. **How many rows total?** Over ~100M → lean BigQuery. Under ~50M → lean Supabase.
2. **What does one query return?** A handful of rows by key → Supabase. Aggregations over millions of rows → BigQuery.
3. **Is it queried inline during bill analysis?** Yes → Supabase (latency). No → either option is viable.
4. **How is it loaded?** Bulk GCS load job → BigQuery. Python upsert script → Supabase.

If the answers conflict, document why and lean toward the pattern that matches the dominant constraint.
