# Format-Specific MRF Parser Jobs

**Date:** 2026-05-08  
**Status:** Proposed  
**Author:** Sandra

---

## Problem

The current `clarobill-mrf-parser` Cloud Run Job processes all MRF formats — JSON, CSV, XLSX, TSV, ZIP — in a single job, sharded 6 ways. When it fails or stalls, there is no way to know which format caused it. All six task logs are interleaved, and a broken XLSX path crashes silently alongside a healthy JSON run.

Additionally, different formats have very different resource needs:
- JSON streams via `ijson` — moderately memory-intensive
- CSV streams via `csv.DictReader` — lightweight, 4 GiB is fine
- XLSX is loaded fully into memory by `openpyxl` — needs 16 GiB for large files
- ZIP requires recursive inner-entry dispatch — mid-range

The current job is sized for the worst case (8 GiB), wasteful for the best case (CSV), and still under-sized for XLSX.

**Format backlog as of 2026-05-04** (all sitting at `parse_status = 'skipped'`):

| Format | Blobs | Size | Status |
|---|---:|---:|---|
| `.csv` / `.csv.gz` | 11,578 | ~1,889 GB | Parser exists, `csv_vendors.py` framework built |
| `.xlsx` | 1,981 | unknown | `stream_charges_xlsx` exists |
| `.zip` | 1,628 | ~84 GB | Not yet implemented |
| `.txt` / `.txt.gz` (TSV) | small | small | `stream_charges_tsv` exists |

Total unlockable: ~1,973 GB of pricing data currently untouched.

### Gzip is compression, not a format

Gzip is a transport wrapper, not a distinct file format. A `.json.gz` that contains XLSX bytes is an XLSX file, not a JSON file and not a gzip file. There is no `clarobill-mrf-parser-gzip` job. The scraper already decompresses the first bytes to sniff the true inner format via `sniff_mrf_format()`, so it writes the inner format to `mrf_archive_index.file_format` at scrape time. Each format job decompresses transparently when it encounters a `.gz` blob — this already works in `process_blob_with_meta()` today. The rule: **`file_format` always reflects the true content format, never the compression wrapper.**

---

## Decision

Retire the monolithic `clarobill-mrf-parser` job. Replace it with **5 format-specific Cloud Run Jobs**, each responsible for exactly one true content format. The entire scraper fleet will be re-run to populate the new `file_format` column; no backfill of existing rows is needed. No new Cloud Scheduler triggers for now — manual invocation during the diagnosis phase.

| Job | `file_format` value | Handles extensions | Memory | Pre-run reset |
|---|---|---|---|---|
| `clarobill-mrf-parser-json` | `json` | `.json`, `.json.gz` (inner=JSON) | 8 GiB | none |
| `clarobill-mrf-parser-csv` | `csv` | `.csv`, `.csv.gz` (inner=CSV) | 4 GiB | auto-resets skipped CSV rows |
| `clarobill-mrf-parser-xlsx` | `xlsx` | `.xlsx`, any ext where inner=XLSX | 16 GiB | auto-resets skipped XLSX rows |
| `clarobill-mrf-parser-tsv` | `tsv` | `.txt`, `.txt.gz` (inner=TSV) | 4 GiB | none |
| `clarobill-mrf-parser-zip` | `zip` | `.zip` | 8 GiB | auto-resets skipped ZIP rows |

---

## Implementation

### 1. BQ schema change — add `file_format` to `mrf_archive_index`

New migration: `supabase/migrations` does not own BQ schema — this is a direct BQ ALTER or a script in `scripts/mrf_discovery/migrate_bq_schema.py`.

```sql
ALTER TABLE `clarobill-prd.hospital_prices.mrf_archive_index`
ADD COLUMN IF NOT EXISTS file_format STRING;
```

Values: `json`, `csv`, `xlsx`, `tsv`, `zip`. NULL for rows written before this change (all pre-existing rows are superseded by the full scraper re-run).

---

### 2. Scraper writes `file_format` at insert time (`scrape_hospital_mrfs.py`)

The scraper already calls `sniff_mrf_format(prefix_bytes, content_type, url)` before writing to GCS. It should pass the returned format string into the `mrf_archive_index` INSERT.

Key rule: `sniff_mrf_format()` already decompresses gzip and inspects the inner bytes, so a `.json.gz` containing XLSX returns `'xlsx'`, not `'json'` or `'gzip'`. The value written to `file_format` is always the true inner content format.

---

### 3. `PARSER_FORMAT` env var in `parse_hospital_mrfs.py`

Replace the original regex-on-gcs_uri approach with a clean equality filter on the new column.

**New module-level constant:**
```python
VALID_FORMATS = frozenset({"json", "csv", "xlsx", "tsv", "zip"})
```

**SQL change in `process_archive_index_pending()`** — one new WHERE clause:
```sql
AND (@format_filter = '' OR file_format = @format_filter)
```

**`main()` reads and validates the env var:**
```python
format_filter = os.environ.get("PARSER_FORMAT", "").strip().lower()
if format_filter and format_filter not in VALID_FORMATS:
    logger.error("PARSER_FORMAT=%r is invalid. Valid: %s", format_filter, sorted(VALID_FORMATS))
    sys.exit(1)
```

No change to bucket-walk mode — `PARSER_FORMAT` only applies when `PARSER_DRIVER=archive_index`.

---

### 4. ZIP unwrapping — new `pipeline/zip_unwrap.py`

This is the Phase 4c implementation from the 2026-05-04 coverage plan, which was designed but not built.

```python
def stream_zip_entries(
    file_obj: BinaryIO,
    *,
    max_depth: int = 2,
) -> Iterator[tuple[str, BinaryIO]]:
    """Yield (inner_filename, BinaryIO) for each data entry in a ZIP.

    Skips __MACOSX/, .DS_Store, and zero-byte entries.
    Recurses into inner ZIPs up to max_depth=2 (guards against Sentara-style nesting).
    """
```

Using stdlib `zipfile.ZipFile` — no new dependency.

**ZIP dispatch in `process_blob_with_meta()`:**
- Detect ZIP via extension OR `_sniff_blob_format()` returning `'zip'`
- Download full ZIP bytes, pass to `stream_zip_entries()`
- For each inner entry: re-sniff format (`json` / `csv` / `tsv`), dispatch to the appropriate `stream_charges_*` function
- Aggregate row counts across all entries; mark outer blob `parsed` if any entry produced rows
- Hospital NPI resolution: URL fallback → scraper metadata (same as CSV/TSV path, since ZIP filenames don't reliably contain NPI)

---

### 5. `deploy.sh` changes

**Remove:**
- `clarobill-mrf-parser` Cloud Run Job (delete)
- `clarobill-mrf-parser-annual` Cloud Scheduler trigger (delete)
- `clarobill-mrf-parser-midyear` Cloud Scheduler trigger (delete)

**Add:**
A helper function `_create_or_update_parser_job name format memory reset_skipped_pattern` to avoid repeating the 20-line gcloud block 5 times.

```bash
_create_or_update_parser_job clarobill-mrf-parser-json  json  8Gi  ""
_create_or_update_parser_job clarobill-mrf-parser-csv   csv   4Gi  "format not yet supported by parser: csv%"
_create_or_update_parser_job clarobill-mrf-parser-xlsx  xlsx  16Gi "format not yet supported by parser: xlsx%"
_create_or_update_parser_job clarobill-mrf-parser-tsv   tsv   4Gi  ""
_create_or_update_parser_job clarobill-mrf-parser-zip   zip   8Gi  "format not yet supported by parser: zip%"
```

All 5 jobs have `PARSER_DRIVER=archive_index` baked in. The CSV, XLSX, and ZIP jobs also have `PARSER_RESET_SKIPPED` baked in — so the first run of each automatically un-skips its own cohort without any manual intervention.

No new Cloud Scheduler triggers are created. Manual invocation during the diagnosis phase:
```bash
gcloud run jobs execute clarobill-mrf-parser-json  --region us-central1 --tasks 6
gcloud run jobs execute clarobill-mrf-parser-csv   --region us-central1 --tasks 6
gcloud run jobs execute clarobill-mrf-parser-xlsx  --region us-central1 --tasks 4
gcloud run jobs execute clarobill-mrf-parser-tsv   --region us-central1 --tasks 2
gcloud run jobs execute clarobill-mrf-parser-zip   --region us-central1 --tasks 4
```

---

### 6. `pipeline/Dockerfile` — add ZIP module

```dockerfile
COPY pipeline/zip_unwrap.py /app/
```

---

### 7. Tests

**`pipeline/tests/test_archive_index_driver.py`** — add:
- `test_format_filter_json_adds_equality_clause` — assert SQL contains `file_format = @format_filter` when `PARSER_FORMAT=json`
- `test_format_filter_empty_no_clause` — assert no format filter in SQL when `PARSER_FORMAT` unset
- `test_invalid_format_exits` — assert `sys.exit(1)` when `PARSER_FORMAT=badformat`

**`pipeline/tests/test_zip_unwrap.py`** — new file, using in-memory ZIPs:
- Single JSON entry — 1 entry yielded
- Multi-entry CSV + JSON — both yielded
- Nested ZIP recurses (depth 1 → inner entries)
- Triple-nested ZIP stops at depth 2
- `__MACOSX/` entries skipped
- Zero-byte entries skipped
- Malformed inner entry does not abort other entries

---

## Files changed

| File | Change |
|---|---|
| `scripts/mrf_discovery/migrate_bq_schema.py` | Add `file_format STRING` column to `mrf_archive_index` |
| `pipeline/scrape_hospital_mrfs.py` | Write `file_format` (true inner format) into `mrf_archive_index` INSERT |
| `pipeline/parse_hospital_mrfs.py` | `PARSER_FORMAT` env var; `WHERE file_format = @format_filter` in `process_archive_index_pending()`; ZIP dispatch in `process_blob_with_meta()` |
| `pipeline/zip_unwrap.py` | **New** — ZIP entry streaming |
| `pipeline/deploy.sh` | Retire monolithic job + 2 Scheduler triggers; add 5 format-specific jobs |
| `pipeline/Dockerfile` | Add `COPY pipeline/zip_unwrap.py /app/` |
| `pipeline/tests/test_archive_index_driver.py` | Add format filter tests |
| `pipeline/tests/test_zip_unwrap.py` | **New** — ZIP unwrap tests |
| `docs/operations/pipeline-runbook.md` | Update job inventory table |
| `CLAUDE.md` | Update manual trigger commands |

---

## What this unlocks (once CSV vendor maps are complete)

The format-specific jobs are infrastructure. The actual data they parse depends on:
- **CSV**: vendor maps in `csv_vendors.py` (Sutter framework exists; Kaiser, HCA, Mercy, Tenet are Phase 4b)
- **XLSX**: `stream_charges_xlsx` needs validation against real fixtures
- **ZIP**: the inner format determines what gets parsed; most ZIPs contain CSV or JSON
- **TSV**: `stream_charges_tsv` needs validation against the actual CDM export format

Once each format job runs, the diagnostic query is now trivial because `file_format` is a real column:
```sql
SELECT
  file_format,
  parse_status,
  COUNT(*) AS n
FROM `clarobill-prd.hospital_prices.mrf_archive_index`
GROUP BY 1, 2
ORDER BY 1, 2;
```

This is the diagnostic query that motivated the whole split. Each format's failure rate is independently readable, and no regex parsing of `gcs_uri` strings is needed.

---

## Schema changes not covered in the implementation section above

### `hospital_charges`: replace `pricing_effective_year INT64` with `pricing_effective_date DATE`

The current `hospital_charges` table uses `pricing_effective_year INT64` as both a column and partition key. This makes SCM joins (`JOIN WHERE year = YEAR(service_date)`) incorrect at year boundaries — a patient seen on 2024-01-03 with a price list effective 2024-01-01 matches correctly, but if the hospital published a mid-year update on 2024-07-01, the year join returns both price lists and it's ambiguous which applies.

The correct pattern is a "latest effective date not exceeding service date" join, which requires a DATE column:

```sql
-- SCM join: most recent price list effective before the service date
WHERE hospital_npi = @npi
  AND pricing_effective_date = (
    SELECT MAX(pricing_effective_date)
    FROM hospital_charges
    WHERE hospital_npi = @npi
      AND pricing_effective_date <= @service_date
  )
```

The table is recreated from scratch (all existing data rebuilt from the archive):

```sql
DROP TABLE IF EXISTS `clarobill-prd.hospital_prices.hospital_charges`;

CREATE TABLE `clarobill-prd.hospital_prices.hospital_charges` (
  hospital_npi              STRING,
  code_type                 STRING,
  code                      STRING,
  description               STRING,
  gross_charge              FLOAT64,
  discounted_cash_price     FLOAT64,
  min_negotiated            FLOAT64,
  max_negotiated            FLOAT64,
  payer_name                STRING,
  plan_name                 STRING,
  negotiated_charge         FLOAT64,
  negotiated_type           STRING,
  setting                   STRING,
  ccn                       STRING,
  pricing_effective_date    DATE NOT NULL    OPTIONS(description="Date from which this price list is valid. Partition key."),
  parse_run_id              STRING NOT NULL  OPTIONS(description="UUID of the parser task execution that produced this row. Forensic link to mrf_archive_index."),
  source_mrf_url            STRING,
  source_gcs_uri            STRING,
  scraped_at                TIMESTAMP
)
PARTITION BY pricing_effective_date
CLUSTER BY hospital_npi, code;
```

NPI is the rules engine join key (it is printed on every patient bill). CCN is stored for traceability but not used for joins.

Rules engine change (`apps/engine/app/services/rules_engine.py`): the SCM join above replaces `WHERE pricing_effective_year = YEAR(bill.service_date)`. If the NPI lookup returns no rows, the rule is skipped — not assumed.

---

### `parse_run_id`: forensic audit chain

Currently there is no way to trace a charge row in `hospital_charges` back to the GCS file it came from. If a charge row looks wrong, the investigation dead-ends.

`parse_run_id` is a UUID generated once per parser task execution and stamped on every `hospital_charges` row and on the `mrf_archive_index` row for the processed file:

```
bill.service_date + bill.hospital_npi
  → hospital_charges.parse_run_id
  → mrf_archive_index WHERE parse_run_id = ?
  → gcs_uri → gs://mrf-archive/...  ← immutable
```

This is added to `mrf_archive_index` as well:
- `parse_run_id STRING` — written by the parser after successful parse
- `parsed_at TIMESTAMP` — written at same time

Implementation: `main()` generates `parse_run_id = str(uuid.uuid4())` once, passes it to `process_archive_index_pending()`, which threads it through to every `ChargeRow` and the `mrf_archive_index` UPDATE.

---

## Out of scope for this change

- Cloud Scheduler triggers for format-specific jobs (add after diagnosis confirms reliability)
- New CSV vendor maps (Kaiser, HCA, Mercy, Tenet — Phase 4b, separate session)
- Discovery URL improvements (separate session)
- XLSX vendor validation against real fixtures (can run in parallel with this)
