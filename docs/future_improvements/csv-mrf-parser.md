# CSV-format MRF parser

**Status:** SUPERSEDED 2026-05-04 — see
[`docs/decisions/2026-05-04-mrf-coverage-plan.md`](../decisions/2026-05-04-mrf-coverage-plan.md)
Part 2 for the current design and Part 3 for the phased rollout (4a-4d).

The doc below is the original deferred sketch from 2026-04-29 and is kept
for historical context. The actual scope was re-measured on 2026-05-04 and
is roughly 100× the original estimate (~1.97 TB across 13,206 blobs vs
~16 GB / ~11K blobs). The new design doc supersedes the build sketch in
this file.

---

**Original status (2026-04-29):** Deferred (Phase 4d).
**Triggers re-opening:** measurable share of `mrf_archive_index.parse_status='skipped'`
rows whose `gcs_uri` ends in `.csv` or `.csv.gz`.

## Context

CMS price transparency rule allows hospitals to publish MRFs in **either**
JSON (machine-readable, schema-versioned) **or** CSV (column-mapped, vendor-
specific). Phase 4 ships JSON-only parsing because:

1. The JSON v2.0.0 schema is standardised — every implementing hospital uses
   the same root keys (`standard_charge_information`, `code_information`,
   `payers_information`). One parser handles all of them.
2. CSV is unstructured by spec — each vendor (Turquoise, Cerner, Epic,
   etc.) emits a different column header set. A single parser cannot read
   them all without per-vendor column mappings.
3. JSON dominates the actual CMS-listed file URLs we discovered in Phase 3
   (estimate >85% based on `_infer_extension` results from the scraper).

For Phase 4, CSV files are flagged in `parse_status='skipped'` with
`parse_error='unsupported format: <blob>'`. The bytes are still preserved in
`mrf-archive-clarobill-prd` so a future parser revision can backfill.

## Build sketch when re-opened

1. **Sample N=20 hospitals** that emit CSV from `mrf_archive_index` and
   collect their column headers into a fingerprint set.
2. **Cluster vendors** by header similarity. Most hospitals fall into 3–5
   buckets (Turquoise, Cerner, Epic, Waystar, custom).
3. **Author per-vendor column maps** like:
   ```python
   TURQUOISE_COLUMNS = {
       "code": "code",
       "code_type": "code_type",
       "description": "description",
       "gross_charge": "gross_charge",
       "discounted_cash_price": "discounted_cash_price",
       "min_negotiated": "minimum_negotiated_charge",
       "max_negotiated": "maximum_negotiated_charge",
       "payer_name": "payer_name",
       "plan_name": "plan_name",
       "negotiated_charge": "negotiated_dollar",
       "negotiated_type": "estimated_amount_type",
   }
   ```
4. **Vendor detection** uses the header set as the fingerprint; fall back to
   a lenient column-substring match if no exact bucket fits.
5. **Stream rows** the same way `stream_charges_v2` does — `csv.DictReader`
   with `pricing_effective_year` injected and `ChargeRow` emitted per row.
6. **Backfill pass** re-reads `parse_status='skipped'` rows from
   `mrf_archive_index` and reprocesses them.

## Why we are not doing this now

Sandra's Phase 4 directive (2026-04-29) was "ship Phase 4 now with these
answers" after explicitly saying parsing should be "as functional as possible
… we don't want to end up with almost no data because of parsing issues."
JSON parsing already covers the majority of files; CSV parsing without
proper per-vendor mappings would yield silently wrong data, which is worse
than a logged skip. We mark CSV files skipped, log them clearly, and
backfill after the column-mapping work lands.
