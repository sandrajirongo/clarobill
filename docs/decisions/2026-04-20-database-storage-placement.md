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

## Quarterly Refresh

| Table | Source | Refresh pattern |
|-------|--------|-----------------|
| `ncci_edit_pairs` | CMS MCD/MCR PTP files (Q1 each year) | Load new quarterly file with `--replace` — file is a full cumulative snapshot; old pairs not in the new file are intentionally removed |
| `ncci_mue_limits` | CMS MCR CSV + MCD TXT files (quarterly) | Load without `--replace` — each quarterly file has a distinct `effective_date`; prior quarters are preserved for historical bill lookups |
| `hospital_charges` | CMS MRF v2.0.0 files (scraped continuously) | Parser deletes then reloads all rows for a given `hospital_npi` each scrape cycle |

Use `scripts/load_ncci_all.sh` to reload all NCCI files. CMS releases new files each January, April, July, and October.

---

## Rule for Future Reference Data

When adding a new CMS or third-party reference dataset, answer these questions in order:

1. **How many rows total?** Over ~100M → lean BigQuery. Under ~50M → lean Supabase.
2. **What does one query return?** A handful of rows by key → Supabase. Aggregations over millions of rows → BigQuery.
3. **Is it queried inline during bill analysis?** Yes → Supabase (latency). No → either option is viable.
4. **How is it loaded?** Bulk GCS load job → BigQuery. Python upsert script → Supabase.

If the answers conflict, document why and lean toward the pattern that matches the dominant constraint.
