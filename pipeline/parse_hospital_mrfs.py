"""Parse hospital MRF files from GCS and load charges into BigQuery.

Cloud Run Job — triggered by Cloud Scheduler weekly, after the scraper job.

Reads all files under gs://mrf-staging/raw/, parses each MRF
according to CMS JSON schema v2.0.0, and loads the normalised charge rows
into BigQuery hospital_charges.

For each hospital processed:
  1. Read hospital context (hospital_name, mrf_url, state) from GCS blob metadata
  2. Extract NPI from the MRF JSON root object (authoritative source)
  3. Stream-parse the JSON file using hospital_mrf_utils
  4. Write normalised rows as NDJSON to a GCS staging blob
  5. DELETE existing rows for this NPI from hospital_charges (idempotent)
  6. Run a BigQuery load job from the staging blob → hospital_charges
  7. Update hospital_directory.last_scraped (joined on mrf_url)
  8. Backfill hospital_directory.hospital_npi if it was previously NULL
  9. Delete the raw MRF blob (prevents double-processing if scheduler overlaps)

--- Running locally ---
  export GOOGLE_APPLICATION_CREDENTIALS=/path/to/pipeline-sa-key.json
  export GCP_PROJECT_ID=clarobill-prd
  python pipeline/parse_hospital_mrfs.py

--- Cloud Run Job ---
  gcloud run jobs execute clarobill-mrf-parser --region us-central1
"""

import csv
import gzip
import io
import json
import logging
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterator

from google.cloud import bigquery, storage

# Phase 4 helpers + sibling modules in pipeline/
import effective_year
from hospital_mrf_utils import (
    ChargeRow,
    extract_mrf_date,
    extract_npi_from_mrf_root,
    extract_npi_from_url,
    stream_charges_csv,
    stream_charges_v2,
)
from csv_vendors import CsvVendorNotIdentified

# SF5 (Phase 8.4): centralised DML helper that asserts num_dml_affected_rows.
# Two-candidate sys.path so the import works both in the container (/app/scripts/)
# and in dev (<repo-root>/scripts/). Mirrors the pattern in archive_writer.py.
_THIS_PARSE = __import__("pathlib").Path(__file__).resolve()
for _bq_candidate in (
    _THIS_PARSE.parent / "scripts" / "mrf_discovery",         # container: /app/scripts/mrf_discovery/
    _THIS_PARSE.parent.parent / "scripts" / "mrf_discovery",  # dev: <repo>/scripts/mrf_discovery/
):
    if (_bq_candidate / "bq_checkpoint.py").exists():
        sys.path.insert(0, str(_bq_candidate))
        break
from bq_checkpoint import run_dml_with_count  # noqa: E402

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

GCP_PROJECT = os.environ.get("GCP_PROJECT_ID", "clarobill-prd")
BQ_DATASET = os.environ.get("BIGQUERY_DATASET", "hospital_prices")
GCS_BUCKET = os.environ.get("GCS_MRF_STAGING_BUCKET", "mrf-staging")

RAW_PREFIX = "raw/"          # where scraper writes MRF files
STAGING_PREFIX = "staging/"  # temp NDJSON files during BigQuery load

# BigQuery schema for hospital_charges.
#
# Phase 4: pricing_effective_year is REQUIRED and the partition key. This is
# the contract between scraper, parser, and rules engine — the rules engine
# joins bills to charges on this column. NEVER allow NULL here; the
# effective_year module guarantees a value via a 3-source fallback.
HOSPITAL_CHARGES_SCHEMA = [
    # Order matches the deployed BQ schema (clarobill-prd.hospital_prices.hospital_charges).
    # Day-level effective_date was dropped in Phase 4 — pricing_effective_year is the
    # date dimension, and source_mrf_url + source_gcs_uri carry forward MRF provenance
    # so any row can be traced back to the immutable archive blob it came from.
    bigquery.SchemaField("hospital_npi", "STRING"),  # NULLABLE — extracted from MRF content
    bigquery.SchemaField("code_type", "STRING"),
    bigquery.SchemaField("code", "STRING"),
    bigquery.SchemaField("description", "STRING"),
    bigquery.SchemaField("gross_charge", "FLOAT64"),
    bigquery.SchemaField("discounted_cash_price", "FLOAT64"),
    bigquery.SchemaField("min_negotiated", "FLOAT64"),
    bigquery.SchemaField("max_negotiated", "FLOAT64"),
    bigquery.SchemaField("payer_name", "STRING"),
    bigquery.SchemaField("plan_name", "STRING"),
    bigquery.SchemaField("negotiated_charge", "FLOAT64"),
    bigquery.SchemaField("negotiated_type", "STRING"),
    bigquery.SchemaField("setting", "STRING"),
    bigquery.SchemaField("pricing_effective_year", "INT64", mode="REQUIRED"),
    bigquery.SchemaField("source_mrf_url", "STRING"),
    bigquery.SchemaField("source_gcs_uri", "STRING"),
    bigquery.SchemaField("scraped_at", "TIMESTAMP"),
]

CHARGES_TABLE = f"{GCP_PROJECT}.{BQ_DATASET}.hospital_charges"
DIRECTORY_TABLE = f"{GCP_PROJECT}.{BQ_DATASET}.hospital_directory"
ARCHIVE_INDEX_TABLE = f"{GCP_PROJECT}.{BQ_DATASET}.mrf_archive_index"

# Success-path bookkeeping is batched to avoid the per-blob DML serialization
# failures that hit the 2026-05-04 8pxsj run (Incident 6). 6 concurrent tasks
# × 4 per-blob UPDATEs overwhelmed BQ's table-level DML lock. Batching collapses
# that to 2 MERGE statements per flush interval across all tasks.
FLUSH_EVERY_BLOBS = 100   # flush after this many successful parses
FLUSH_EVERY_SECS  = 300   # or after 5 minutes, whichever comes first

_PARSEABLE_EXTENSIONS = (".json", ".json.gz", ".json.gzip", ".csv", ".csv.gz")


def build_clients() -> tuple[bigquery.Client, storage.Client]:
    """Build BigQuery and GCS clients using Application Default Credentials."""
    return bigquery.Client(project=GCP_PROJECT), storage.Client(project=GCP_PROJECT)


def list_raw_blobs(bucket: storage.Bucket) -> list[storage.Blob]:
    """List all MRF blobs in the raw/ prefix, sorted by name.

    Reloads each blob to ensure custom metadata is present — list_blobs() does
    not always populate metadata in the returned Blob objects.
    """
    blobs = list(bucket.list_blobs(prefix=RAW_PREFIX))
    blobs = [b for b in blobs if not b.name.endswith("/")]
    blobs.sort(key=lambda b: b.name)
    logger.info("Found %d raw MRF files to process", len(blobs))
    return blobs


def _get_blob_metadata(bucket: storage.Bucket, blob: storage.Blob) -> dict[str, str]:
    """Return the custom metadata dict for a GCS blob, reloading if necessary.

    The scraper stores hospital context in blob metadata so the parser doesn't
    need to re-query BigQuery to know which hospital a file belongs to.
    Keys: hospital_name, mrf_url, state, hospital_npi (may be empty string).
    """
    # Reload to guarantee metadata is populated (list_blobs can omit it).
    fresh = bucket.get_blob(blob.name)
    if fresh and fresh.metadata:
        return dict(fresh.metadata)
    return {}


def _open_mrf_blob(blob: storage.Blob) -> io.RawIOBase:
    """Stream-open a GCS blob, decompressing gzip on the fly."""
    stream = blob.open("rb")
    if blob.name.endswith(".gz") or blob.name.endswith(".gzip"):
        return gzip.open(stream, "rb")  # type: ignore[return-value]
    return stream


def _write_ndjson_to_gcs(
    rows: Iterator[ChargeRow],
    bucket: storage.Bucket,
    staging_blob_name: str,
) -> int:
    """Write ChargeRow objects as NDJSON to a GCS staging blob.

    Streams rows in memory in 16 MB chunks rather than buffering everything.
    Returns the total number of rows written.
    """
    blob = bucket.blob(staging_blob_name)
    row_count = 0
    CHUNK_SIZE = 16 * 1024 * 1024  # 16 MB

    with blob.open("wb") as gcs_file:
        chunk = io.BytesIO()
        for row in rows:
            line = (json.dumps(row.to_bq_row()) + "\n").encode()
            chunk.write(line)
            row_count += 1
            if chunk.tell() >= CHUNK_SIZE:
                chunk.seek(0)
                gcs_file.write(chunk.read())
                chunk = io.BytesIO()
        # Flush remaining
        if chunk.tell() > 0:
            chunk.seek(0)
            gcs_file.write(chunk.read())

    return row_count


def load_charges_from_gcs(bq: bigquery.Client, staging_uri: str) -> bigquery.LoadJob:
    """Run a BigQuery load job from the staging NDJSON file into hospital_charges.

    Phase 4: append-only. Sandra's Q3 decision was MAX(scraped_at) over append-
    only rows rather than the legacy DELETE+LOAD pattern. The rules engine
    selects the freshest row per (hospital_npi, code, payer) using a window
    function. This preserves history (we can see how a price changed across
    Feb and Aug republications) and removes the race condition where a slow
    DELETE could leave the table empty for a hospital between scrapes.
    """
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        schema=HOSPITAL_CHARGES_SCHEMA,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        ignore_unknown_values=True,  # tolerate extra fields in malformed MRFs
    )
    job = bq.load_table_from_uri(staging_uri, CHARGES_TABLE, job_config=job_config)
    job.result()
    return job


def update_archive_index_status(
    bq: bigquery.Client,
    mrf_url: str,
    status: str,
    error: str | None = None,
) -> None:
    """Mark mrf_archive_index rows for this MRF URL as parsed/failed/skipped.

    Phase 4: the scraper inserts archive_index rows with parse_status='pending'.
    The parser flips them to 'parsed' on success, 'failed' on exception, or
    'skipped' for unparseable formats (e.g. CSV today). We match on
    source_mrf_url + parse_status='pending' so re-runs don't re-stamp older
    successfully-parsed rows.

    status must be one of: 'parsed', 'failed', 'skipped'.
    """
    if status not in ("parsed", "failed", "skipped"):
        raise ValueError(f"Invalid parse_status: {status!r}")
    sql = f"""
        UPDATE `{ARCHIVE_INDEX_TABLE}`
        SET parse_status = @status,
            parse_error = @error,
            parsed_at = CURRENT_TIMESTAMP()
        WHERE source_mrf_url = @url
          AND parse_status = 'pending'
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("status", "STRING", status),
            bigquery.ScalarQueryParameter("error", "STRING", error),
            bigquery.ScalarQueryParameter("url", "STRING", mrf_url),
        ]
    )
    # SF5 + SF6 (Phase 8.4): use run_dml_with_count to verify the UPDATE
    # actually flipped the parse_status row. SF6 also says: this UPDATE
    # is the data-flow control plane for the parser's work queue, not
    # mere "bookkeeping". A swallowed failure here means the row stays
    # 'pending' forever and the parser re-processes the same blob on
    # every run, polluting hospital_charges with duplicates. Bubble up
    # to the caller (process_blob_with_meta) so a failed UPDATE is
    # treated as a failed parse instead of being papered over.
    affected = run_dml_with_count(
        bq, sql, job_config=job_config, label=f"archive_index status update {mrf_url}"
    )
    if affected == 0:
        logger.warning(
            "archive_index status update for %s affected 0 rows — row may be missing",
            mrf_url,
        )


def update_archive_index_npi(bq: bigquery.Client, mrf_url: str, hospital_npi: str) -> None:
    """Backfill mrf_archive_index.hospital_npi after a successful parse.

    The scraper stores whatever NPI was known at scrape time (often NULL for
    hospitals discovered without an NPPES match). The parser resolves the NPI
    via JSON > URL > metadata cascade. Writing the resolved value back lets
    `mrf_archive_index` serve as a queryable parse-provenance table — useful
    for backfilling hospital_charges and for verifying coverage by hospital.

    Only updates rows that currently have no NPI; never overwrites an existing
    value, and only the row matching this exact URL (so re-publications under
    a new URL get their own row keyed on the new URL).
    """
    if not hospital_npi:
        return
    sql = f"""
        UPDATE `{ARCHIVE_INDEX_TABLE}`
        SET hospital_npi = @hospital_npi
        WHERE source_mrf_url = @mrf_url
          AND (hospital_npi IS NULL OR hospital_npi = '')
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("hospital_npi", "STRING", hospital_npi),
            bigquery.ScalarQueryParameter("mrf_url", "STRING", mrf_url),
        ]
    )
    # SF5 (Phase 8.4): verify the UPDATE actually wrote a row.
    try:
        run_dml_with_count(
            bq, sql, job_config=job_config, label=f"archive_index NPI backfill {mrf_url}"
        )
    except Exception as exc:
        logger.warning("archive_index NPI backfill failed for %s: %s", mrf_url, exc)


def mark_last_scraped(bq: bigquery.Client, mrf_url: str, scraped_at: str) -> None:
    """Update hospital_directory.last_scraped after successful charge load.

    Joins on mrf_url because hospital_npi may still be NULL for newly-added
    hospitals whose NPI hasn't been extracted from their MRF yet.
    """
    sql = f"""
        UPDATE `{DIRECTORY_TABLE}`
        SET last_scraped = @scraped_at
        WHERE mrf_url = @mrf_url
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("scraped_at", "TIMESTAMP", scraped_at),
            bigquery.ScalarQueryParameter("mrf_url", "STRING", mrf_url),
        ]
    )
    # SF5 (Phase 8.4): verify the UPDATE wrote a row.
    run_dml_with_count(bq, sql, job_config=job_config, label="hospital_directory.last_scraped")


def update_hospital_npi(bq: bigquery.Client, mrf_url: str, hospital_npi: str) -> None:
    """Backfill hospital_directory.hospital_npi extracted from the MRF file.

    Called once per hospital after the NPI is successfully read from the MRF
    JSON root.  Only updates rows where hospital_npi is currently NULL so that
    manually-set or previously-resolved NPIs are not overwritten.
    """
    sql = f"""
        UPDATE `{DIRECTORY_TABLE}`
        SET hospital_npi = @hospital_npi
        WHERE mrf_url = @mrf_url AND hospital_npi IS NULL
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("hospital_npi", "STRING", hospital_npi),
            bigquery.ScalarQueryParameter("mrf_url", "STRING", mrf_url),
        ]
    )
    # SF5 (Phase 8.4): verify the UPDATE wrote a row.
    affected = run_dml_with_count(
        bq, sql, job_config=job_config, label=f"hospital_directory.hospital_npi {mrf_url}"
    )
    logger.info("Backfilled hospital_npi=%s for mrf_url=%s (%d rows)", hospital_npi, mrf_url, affected)


# ---------------------------------------------------------------------------
# Batched success-path bookkeeping (replaces 4 per-blob UPDATEs on the happy
# path — see FLUSH_EVERY_BLOBS / FLUSH_EVERY_SECS constants above).
# Failure-path writes (failed / skipped status) are NOT batched: they are
# the work-queue control signal and must be visible immediately so the next
# run's skip-set is accurate.
# ---------------------------------------------------------------------------

def _bq_str(s: str) -> str:
    """Escape a string for a BQ SQL literal. All values are internal (URLs/NPIs)."""
    return "'" + s.replace("'", "''") + "'"


def _merge_archive_index_parsed(bq: bigquery.Client, records: list[dict[str, str]]) -> None:
    """Single MERGE: flip all buffered pending rows to parsed and backfill NPI."""
    rows_sql = " UNION ALL ".join(
        f"SELECT {_bq_str(r['mrf_url'])} AS u, {_bq_str(r.get('hospital_npi') or '')} AS n"
        for r in records
    )
    sql = f"""
    MERGE `{ARCHIVE_INDEX_TABLE}` AS t
    USING ({rows_sql}) AS s ON t.source_mrf_url = s.u AND t.parse_status = 'pending'
    WHEN MATCHED THEN UPDATE SET
      parse_status = 'parsed',
      parse_error  = NULL,
      parsed_at    = CURRENT_TIMESTAMP(),
      hospital_npi = CASE
        WHEN (t.hospital_npi IS NULL OR t.hospital_npi = '') AND s.n != ''
        THEN s.n ELSE t.hospital_npi END
    """
    job = bq.query(sql)
    job.result()
    logger.info("archive_index batch MERGE: %d rows → parsed", int(job.num_dml_affected_rows or 0))


def _merge_directory_scraped(bq: bigquery.Client, records: list[dict[str, str]]) -> None:
    """Single MERGE: update last_scraped and backfill hospital_npi in hospital_directory."""
    rows_sql = " UNION ALL ".join(
        f"SELECT {_bq_str(r['mrf_url'])} AS u, "
        f"TIMESTAMP({_bq_str(r['scraped_at'])}) AS ts, "
        f"{_bq_str(r.get('hospital_npi') or '')} AS n"
        for r in records
    )
    sql = f"""
    MERGE `{DIRECTORY_TABLE}` AS t
    USING ({rows_sql}) AS s ON t.mrf_url = s.u
    WHEN MATCHED THEN UPDATE SET
      last_scraped = s.ts,
      hospital_npi = CASE
        WHEN t.hospital_npi IS NULL AND s.n != ''
        THEN s.n ELSE t.hospital_npi END
    """
    job = bq.query(sql)
    job.result()
    logger.info("hospital_directory batch MERGE: %d rows updated", int(job.num_dml_affected_rows or 0))


@dataclass
class _SuccessBuffer:
    """Accumulates post-parse bookkeeping for successful blobs; flushed in batches.

    Replaces the 4 per-blob success-path UPDATE calls with two MERGE statements
    per flush. Callers MUST call flush() after the parse loop to commit the
    final partial batch.
    """
    _archive:  list[dict[str, str]] = field(default_factory=list)
    _directory: list[dict[str, str]] = field(default_factory=list)
    _last_flush_at: float = field(default_factory=time.monotonic, compare=False, repr=False)

    def record(self, mrf_url: str, hospital_npi: str, scraped_at: str) -> None:
        self._archive.append({"mrf_url": mrf_url, "hospital_npi": hospital_npi})
        self._directory.append({"mrf_url": mrf_url, "scraped_at": scraped_at, "hospital_npi": hospital_npi})

    def needs_flush(self) -> bool:
        return (
            len(self._archive) >= FLUSH_EVERY_BLOBS
            or (bool(self._archive) and time.monotonic() - self._last_flush_at >= FLUSH_EVERY_SECS)
        )

    def flush(self, bq: bigquery.Client) -> int:
        """Write buffered records to BQ. Returns the number of records flushed."""
        n = len(self._archive)
        if n == 0:
            return 0
        try:
            _merge_archive_index_parsed(bq, self._archive)
        except Exception as exc:
            logger.error("archive_index batch flush failed (%d records): %s", n, exc)
        try:
            _merge_directory_scraped(bq, self._directory)
        except Exception as exc:
            logger.error("hospital_directory batch flush failed (%d records): %s", n, exc)
        self._archive.clear()
        self._directory.clear()
        self._last_flush_at = time.monotonic()
        logger.info("Flushed %d success-bookkeeping records to BQ", n)
        return n


def _is_parseable_extension(blob_name: str) -> bool:
    """True if the parser knows how to handle this blob's format today.

    JSON / JSON-gzip are supported. CSV/XLSX/ZIP are skipped with a logged
    'skipped' status in mrf_archive_index — see _PARSEABLE_EXTENSIONS.
    """
    name = blob_name.lower()
    return any(name.endswith(ext) for ext in _PARSEABLE_EXTENSIONS)


def _sniff_blob_format(blob: storage.Blob) -> str:
    """Sniff the first 4 KiB of a blob and return one of:
    'json' | 'html' | 'xlsx' | 'pdf' | 'empty' | 'unknown'.

    The scraper saves whatever the source URL returned, so a blob with a
    .json or .json.gz suffix may actually contain HTML (404 page, marketing
    landing page) or XLSX. Walking ijson over those would burn 5-10s per
    blob to produce zero rows. This pre-flight aborts in <1s when the
    content is clearly not JSON.

    For .gz blobs we decompress what we have first; partial gzip data is
    enough to read the opening braces and HTML markers.
    """
    try:
        head = blob.download_as_bytes(start=0, end=4095, raw_download=True)
    except Exception:
        return "unknown"
    if blob.name.endswith(".gz") or blob.name.endswith(".gzip"):
        try:
            head = gzip.GzipFile(fileobj=io.BytesIO(head), mode="rb").read(4096)
        except Exception:
            return "unknown"
    if not head:
        return "empty"
    s = head.lstrip(b"\xef\xbb\xbf").lstrip()
    if s.startswith(b"{") or s.startswith(b"["):
        return "json"
    if s[:1] == b"<":
        return "html"
    if s.startswith(b"PK\x03\x04"):
        return "xlsx"
    if s.startswith(b"%PDF"):
        return "pdf"
    return "unknown"


def process_blob(
    blob: storage.Blob,
    bq: bigquery.Client,
    bucket: storage.Bucket,
    success_buffer: _SuccessBuffer | None = None,
) -> bool:
    """Bucket-walk entry point. Reads metadata from staging blob, then parses."""
    meta = _get_blob_metadata(bucket, blob)
    return process_blob_with_meta(
        blob, meta, bq, bucket,
        delete_source_on_success=True,
        success_buffer=success_buffer,
    )


def process_blob_with_meta(
    blob: storage.Blob,
    meta: dict[str, str],
    bq: bigquery.Client,
    staging_bucket: storage.Bucket,
    *,
    delete_source_on_success: bool,
    success_buffer: _SuccessBuffer | None = None,
) -> bool:
    """Parse one MRF blob and load its charges into BigQuery.

    Returns True on success, False on any error (logs details and continues
    to the next hospital so one bad MRF doesn't abort the entire run).

    Args:
      blob: The MRF source blob — staging or archive bucket. The function
            reads its bytes via blob.open()/download_as_bytes() and never
            assumes a particular bucket.
      meta: Hospital context dict with at minimum {mrf_url, hospital_name,
            hospital_npi, last_modified}. In bucket-walk mode this is the
            scraper-stamped blob metadata; in archive-index mode this is
            built from the archive_index row.
      staging_bucket: Bucket for the per-parse NDJSON staging file
            (always mrf-staging regardless of where the source blob lives).
      delete_source_on_success: True for staging blobs (delete after parse
            to prevent re-processing), False for archive blobs (immutable;
            never delete from the immutable archive).

    NPI strategy is a fallback chain — JSON root → URL → scraper metadata.
    Strict mode rejects blobs that yield no NPI (was a silent NULL-NPI
    write before commit cb9b420).
    """
    mrf_url = meta.get("mrf_url") or ""
    hospital_name = meta.get("hospital_name") or blob.name
    label = hospital_name

    if not mrf_url:
        logger.error("Blob %s has no mrf_url metadata — skipping", blob.name)
        return False

    # Format gate — skip non-JSON formats cleanly. The archive still has the
    # bytes; a future parser revision will handle CSV. Today, a CSV file
    # crashing the parser would be a bigger data outage than just skipping.
    if not _is_parseable_extension(blob.name):
        logger.warning(
            "[%s] Format not yet supported by parser: %s — marking skipped",
            label, blob.name,
        )
        update_archive_index_status(
            bq, mrf_url, "skipped",
            error=f"unsupported format: {blob.name}",
        )
        # Do NOT delete the staging blob — preserves a forensic copy until
        # the CSV parser ships. The archive bucket already has the immutable
        # copy, so this is belt-and-suspenders.
        return False

    is_csv = blob.name.lower().endswith((".csv", ".csv.gz"))

    # Content sniff for JSON blobs — the scraper saved whatever the source URL
    # returned, so a .json blob may actually contain HTML (404 page, marketing
    # landing page). Skip this check for CSV: CSV has no magic bytes and the
    # extension is the only reliable signal.
    if not is_csv:
        fmt = _sniff_blob_format(blob)
        if fmt != "json":
            logger.warning(
                "[%s] Content is %s, not JSON — marking failed (path was %s)",
                label, fmt, blob.name,
            )
            update_archive_index_status(
                bq, mrf_url, "failed",
                error=f"content-sniff: {fmt}",
            )
            return False

    logger.info("[%s] Processing %s", label, blob.name)
    scraped_at = datetime.now(timezone.utc).isoformat()

    # For JSON: read last_updated_on from MRF root for effective-year resolution.
    # For CSV: no JSON root, so pass None; http_last_modified from blob metadata
    # or calendar year fallback will handle it.
    json_last_updated = None if is_csv else _read_mrf_date(blob)
    http_last_modified = meta.get("last_modified") or None
    pricing_effective_year, year_source = effective_year.resolve_year(
        json_last_updated_on=json_last_updated,
        http_last_modified=http_last_modified,
    )
    logger.info(
        "[%s] pricing_effective_year=%d (source=%s)",
        label, pricing_effective_year, year_source,
    )

    source_mrf_url = mrf_url
    source_gcs_uri: str | None = None

    # NPI resolution chain.
    # JSON: MRF root → URL → scraper metadata.
    # CSV:  URL → scraper metadata → CSV metadata row (rows 1-2 of the file).
    hospital_npi = (
        ("" if is_csv else _read_mrf_npi(blob))
        or extract_npi_from_url(mrf_url)
        or meta.get("hospital_npi")
        or (is_csv and _read_csv_meta_npi(blob))
        or ""
    )
    if not hospital_npi:
        logger.warning(
            "[%s] No NPI from JSON, URL, or metadata — marking failed (url=%s)",
            label, mrf_url,
        )
        update_archive_index_status(
            bq, mrf_url, "failed",
            error="no NPI resolvable from JSON root, URL, or scraper metadata",
        )
        return False

    staging_blob_name = f"{STAGING_PREFIX}{uuid.uuid4()}.ndjson"
    staging_uri = f"gs://{GCS_BUCKET}/{staging_blob_name}"

    try:
        with _open_mrf_blob(blob) as f:
            if is_csv:
                rows = stream_charges_csv(
                    f, hospital_npi, pricing_effective_year, scraped_at,
                    source_mrf_url=source_mrf_url, source_gcs_uri=source_gcs_uri,
                )
            else:
                rows = stream_charges_v2(
                    f, hospital_npi, pricing_effective_year, scraped_at,
                    source_mrf_url=source_mrf_url, source_gcs_uri=source_gcs_uri,
                )
            row_count = _write_ndjson_to_gcs(rows, staging_bucket, staging_blob_name)

        if row_count == 0:
            logger.warning("[%s] No charge rows parsed — skipping load", label)
            staging_bucket.blob(staging_blob_name).delete()
            update_archive_index_status(
                bq, mrf_url, "failed",
                error="no charge rows extracted from MRF",
            )
            return False

        logger.info("[%s] Parsed %d charge rows (year=%d)", label, row_count, pricing_effective_year)

        # Append-only: no DELETE. The rules engine deduplicates by
        # MAX(scraped_at) per (hospital_npi, code, payer, plan).
        load_charges_from_gcs(bq, staging_uri)
        logger.info("[%s] Loaded %d rows to hospital_charges", label, row_count)

        # Bookkeeping: buffer the success record if a buffer was provided; fall
        # back to immediate per-row writes for single-task / test scenarios.
        if success_buffer is not None:
            success_buffer.record(mrf_url, hospital_npi, scraped_at)
        else:
            mark_last_scraped(bq, mrf_url, scraped_at)
            if hospital_npi:
                update_hospital_npi(bq, mrf_url, hospital_npi)
            update_archive_index_status(bq, mrf_url, "parsed")
            update_archive_index_npi(bq, mrf_url, hospital_npi)

        # Delete the source MRF blob only when it was the ephemeral staging
        # copy. Archive-bucket blobs are immutable forensic evidence and
        # MUST never be deleted by the parser.
        if delete_source_on_success:
            blob.delete()
        staging_bucket.blob(staging_blob_name).delete()
        return True

    except Exception as exc:
        logger.error("[%s] Failed: %s", label, exc, exc_info=True)
        try:
            staging_bucket.blob(staging_blob_name).delete()
        except Exception:
            pass
        update_archive_index_status(
            bq, mrf_url, "failed",
            error=f"{type(exc).__name__}: {exc}"[:1000],
        )
        return False


# A single gzip deflate block can be up to 65 KB compressed. Download 128 KB
# so we almost always have enough compressed data to decode the full first block,
# which contains the root metadata (hospital_npi, last_updated_on).
_HEADER_DOWNLOAD_SIZE = 131072  # 128 KB

def _read_header_bytes(blob: storage.Blob) -> bytes:
    """Download the first 128 KB of an MRF blob, decompressing gzip if needed.

    The MRF root metadata (last_updated_on, NPI) is always near the start of
    the file. 128 KB is enough to span at least one full gzip deflate block
    (max ~65 KB compressed) so decompression reliably yields the header JSON.

    For gzip files we read in 4 KB chunks and collect partial output. Per-chunk
    EOFError handling means we keep whatever was decoded before truncation rather
    than discarding it all.

    Returns empty bytes on any error.
    """
    try:
        raw = blob.download_as_bytes(start=0, end=_HEADER_DOWNLOAD_SIZE)
        if blob.name.endswith(".gz") or blob.name.endswith(".gzip"):
            decoded = io.BytesIO()
            try:
                with gzip.GzipFile(fileobj=io.BytesIO(raw)) as gz:
                    while decoded.tell() < 16384:  # stop after 16 KB of decoded output
                        try:
                            chunk = gz.read(4096)
                        except EOFError:
                            # End of the compressed region we downloaded — stop.
                            break
                        if not chunk:
                            break
                        decoded.write(chunk)
            except (gzip.BadGzipFile, OSError):
                pass  # return whatever we decoded before the error
            return decoded.getvalue()
        return raw
    except Exception:
        return b""


def _read_mrf_date(blob: storage.Blob) -> str | None:
    """Extract last_updated_on from the MRF blob header."""
    header = _read_header_bytes(blob)
    if not header:
        return None
    match = re.search(rb'"last_updated_on"\s*:\s*"([^"]{4,20})"', header)
    if match:
        return match.group(1).decode("utf-8", errors="replace")[:10]
    match = re.search(rb'"version_date"\s*:\s*"([^"]{4,20})"', header)
    if match:
        return match.group(1).decode("utf-8", errors="replace")[:10]
    return None


def _read_csv_meta_npi(blob: storage.Blob) -> str:
    """Extract NPI from the CMS standard CSV metadata rows (rows 1 and 2).

    Reads the first 4 KiB of the blob (enough for both header rows in every
    observed MRF) and delegates to _extract_npi_from_csv_meta.
    """
    try:
        head = blob.download_as_bytes(start=0, end=4095, raw_download=True)
        if blob.name.lower().endswith(".gz"):
            head = gzip.GzipFile(fileobj=io.BytesIO(head), mode="rb").read(4096)
    except Exception:
        return ""
    text = head.lstrip(b"\xef\xbb\xbf").decode("utf-8", errors="replace")
    lines = text.splitlines()
    reader = csv.reader(lines)
    try:
        header_row = next(reader)
        values_row = next(reader)
    except StopIteration:
        return ""
    from hospital_mrf_utils import _extract_npi_from_csv_meta
    return _extract_npi_from_csv_meta(header_row, values_row)


def _read_mrf_npi(blob: storage.Blob) -> str | None:
    """Extract the hospital NPI from the MRF blob header.

    CMS v2.0.0 MRFs include the NPI in the root object under various key names.
    We search with regex rather than fully parsing the header slice, since the
    slice is not valid JSON on its own.

    Handles both formats hospitals use:
      - String:  "hospital_npi": "1234567890"
      - Integer: "hospital_npi": 1234567890

    Returns a 10-digit NPI string or None.
    """
    header = _read_header_bytes(blob)
    if not header:
        return None
    for key in (b"hospital_npi", b"npi", b"provider_npi"):
        # String format: "hospital_npi": "1234567890"
        m = re.search(rb'"' + key + rb'"\s*:\s*"(\d{10})"', header)
        if m:
            return m.group(1).decode()
        # Integer format: "hospital_npi": 1234567890
        m = re.search(rb'"' + key + rb'"\s*:\s*(\d{10})\b', header)
        if m:
            return m.group(1).decode()
    return None


def _task_shard(items: list, task_index: int, task_count: int) -> list:
    """Return the slice of items assigned to this Cloud Run task instance.

    Cloud Run Jobs injects CLOUD_RUN_TASK_INDEX (0-based) and
    CLOUD_RUN_TASK_COUNT when --tasks > 1. Slice pattern items[i::n] gives
    each task a roughly equal share with no gaps or overlaps.
    """
    return items[task_index::task_count]


def _blob_from_gcs_uri(gcs: storage.Client, gcs_uri: str) -> storage.Blob:
    """Resolve a `gs://bucket/path` URI to a Blob handle.

    Used by the archive_index-driven parser path so the same blob open/read
    code path works on both staging and immutable-archive buckets.
    """
    if not gcs_uri.startswith("gs://"):
        raise ValueError(f"Invalid GCS URI (no gs:// prefix): {gcs_uri}")
    rest = gcs_uri[5:]
    bucket_name, _, blob_name = rest.partition("/")
    if not bucket_name or not blob_name:
        raise ValueError(f"Malformed GCS URI: {gcs_uri}")
    return gcs.bucket(bucket_name).blob(blob_name)


def reset_skipped_to_pending(
    bq: bigquery.Client,
    error_pattern: str | None = None,
) -> int:
    """SF1 (Phase 8.2) companion to reset_failed_to_pending.

    When the parser meets a CSV/XLSX/ZIP it currently writes parse_status
    = 'skipped' to mrf_archive_index. The archive_index-driver picks up
    only 'pending' rows, so once skipped a URL is permanently bypassed —
    even when a future parser version adds support for that format. This
    is a structural coverage hole: when CSV parser ships (Phase 5
    backlog), the historical CSV cohort (~11k+1.9k blobs) won't get
    re-evaluated by any current job.

    The fix: this helper flips rows back to 'pending' just like
    reset_failed_to_pending. Operators run it (via PARSER_RESET_SKIPPED=true
    env var or a one-off script) AFTER deploying CSV parser support, so
    the next archive_index-driven run picks them up.

    Args:
      error_pattern: SQL LIKE pattern to scope the reset (e.g.,
                     'unsupported format%' to only retry CSV/XLSX/ZIP).
                     None resets ALL 'skipped' rows.

    Returns the number of rows reset.
    """
    where_clause = "parse_status = 'skipped'"
    params: list[bigquery.ScalarQueryParameter] = []
    if error_pattern:
        where_clause += " AND parse_error LIKE @pattern"
        params.append(bigquery.ScalarQueryParameter("pattern", "STRING", error_pattern))
    sql = f"""
        UPDATE `{ARCHIVE_INDEX_TABLE}`
        SET parse_status = 'pending',
            parsed_at = NULL,
            parse_error = CONCAT('reset for retry (was skipped): ', IFNULL(parse_error, 'unknown'))
        WHERE {where_clause}
    """
    job = bq.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params))
    job.result()
    n = int(job.num_dml_affected_rows or 0)
    logger.info("Reset %d skipped rows to pending (pattern=%r)", n, error_pattern)
    return n


def reset_failed_to_pending(
    bq: bigquery.Client,
    error_pattern: str | None = None,
) -> int:
    """Flip historical mrf_archive_index 'failed' rows back to 'pending' for retry.

    The pre-2026-05-04 parser silently wrote rows with NULL hospital_npi when
    JSON internals lacked one, marking the archive blob 'parsed'. The 5/4
    investigation reclassified that cohort to 'failed'. With the URL-NPI
    fallback shipped in cb9b420 + the scrape-time validation in e2745d4,
    those blobs are now retryable — but the bucket walk skips terminal-state
    rows by URL, and most of those staging blobs were deleted post-parse.
    The archive_index-driven mode reads from gcs_uri (immutable archive),
    so resetting these rows to 'pending' enables a clean retry pass.

    Args:
      error_pattern: SQL LIKE pattern to scope the reset (e.g.,
                     'parsed with NULL NPI%' to only retry the NPI cohort).
                     None resets ALL 'failed' rows — use with caution.

    Returns the number of rows reset.
    """
    where_clause = "parse_status = 'failed'"
    params = []
    if error_pattern:
        where_clause += " AND parse_error LIKE @pattern"
        params.append(bigquery.ScalarQueryParameter("pattern", "STRING", error_pattern))
    sql = f"""
        UPDATE `{ARCHIVE_INDEX_TABLE}`
        SET parse_status = 'pending',
            parsed_at = NULL,
            parse_error = CONCAT('reset for retry: ', IFNULL(parse_error, 'unknown'))
        WHERE {where_clause}
    """
    job = bq.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params))
    job.result()
    n = int(job.num_dml_affected_rows or 0)
    logger.info("Reset %d failed rows to pending (pattern=%r)", n, error_pattern)
    return n


def process_archive_index_pending(
    bq: bigquery.Client,
    gcs: storage.Client,
    staging_bucket: storage.Bucket,
    limit: int | None = None,
    task_index: int = 0,
    task_count: int = 1,
) -> tuple[int, int]:
    """Drive parsing from `mrf_archive_index` instead of walking the staging bucket.

    For each pending archive_index row, opens the blob at gcs_uri (typically
    the immutable archive bucket) and processes through the same parser core
    as bucket-walk mode. Source blob is NOT deleted on success — archive is
    forensic.

    This is the postmortem #2 fix: the 2,583 rows we'd want to retry from
    the pre-2026-05-04 cohort had their staging blobs deleted post-parse,
    so the bucket walk could never find them. Reading from archive_index
    + gcs_uri makes them reachable again.

    Task sharding: when running with --tasks N --parallelism N on Cloud Run,
    each task instance receives task_index ∈ [0, task_count). The query
    orders by gcs_uri so every task sees the SAME ordered list, then each
    takes its `rows[task_index::task_count]` stripe. Idempotent re-queries
    converge because the underlying ordering doesn't drift even as rows
    transition pending → parsed (a parsed row simply drops out of the
    pending set; remaining pending rows keep the same relative order).

    Returns (succeeded, failed).
    """
    # Dedupe by gcs_uri at SQL time. The same source_mrf_url can appear in
    # multiple archive_index rows (re-scrapes, scraper retries, the pre-fix
    # Dignity Health duplicate-archive cohort). When `update_archive_index_status`
    # flips a URL's parse_status, ALL archive_index rows for that URL flip —
    # but the in-memory result list still contains every original row.
    # Without dedup, we'd re-parse the same blob N times AND append duplicate
    # rows into hospital_charges (append-only, no on-write dedup). 2026-05-04
    # 16:46 incident: ~3x duplication of Saint Michaels Medical Center rows
    # before the runaway loop was caught.
    sql = f"""
    SELECT
      ANY_VALUE(source_mrf_url) AS source_mrf_url,
      gcs_uri,
      ANY_VALUE(hospital_npi) AS hospital_npi,
      ANY_VALUE(ccn) AS ccn,
      ANY_VALUE(mrf_last_modified_header) AS mrf_last_modified_header
    FROM `{ARCHIVE_INDEX_TABLE}`
    WHERE parse_status = 'pending'
      AND gcs_uri IS NOT NULL
      AND gcs_uri != ''
    GROUP BY gcs_uri
    ORDER BY gcs_uri
    """
    if limit:
        sql += f"\nLIMIT {int(limit)}"

    all_rows = list(bq.query(sql).result())
    rows = all_rows[task_index::task_count] if task_count > 1 else all_rows
    if task_count > 1:
        logger.info(
            "Task %d/%d — processing %d/%d distinct gcs_uris (stripe rows[%d::%d])",
            task_index, task_count, len(rows), len(all_rows), task_index, task_count,
        )
    else:
        logger.info("Loaded %d distinct gcs_uris from pending archive_index rows", len(rows))

    # In-memory belt-and-suspenders dedupe — defends against any race where
    # the same gcs_uri could re-appear after our SQL-side GROUP BY (e.g., if
    # a concurrent process re-inserted a pending row mid-loop).
    seen_uris: set[str] = set()
    buffer = _SuccessBuffer()

    succeeded = 0
    failed = 0
    for row in rows:
        gcs_uri = str(row["gcs_uri"])
        if gcs_uri in seen_uris:
            continue
        seen_uris.add(gcs_uri)
        mrf_url = str(row["source_mrf_url"] or "")
        try:
            blob = _blob_from_gcs_uri(gcs, gcs_uri)
            meta = {
                "mrf_url": mrf_url,
                "hospital_name": mrf_url or gcs_uri,
                "hospital_npi": str(row["hospital_npi"] or ""),
                "state": "",
                "last_modified": str(row["mrf_last_modified_header"] or ""),
            }
            ok = process_blob_with_meta(
                blob, meta, bq, staging_bucket,
                delete_source_on_success=False,
                success_buffer=buffer,
            )
            if ok:
                succeeded += 1
            else:
                failed += 1
        except Exception as exc:
            logger.error("[archive_index %s] Failed: %s", gcs_uri, exc, exc_info=True)
            failed += 1
            if mrf_url:
                update_archive_index_status(
                    bq, mrf_url, "failed",
                    error=f"archive_index_driver: {type(exc).__name__}: {exc}"[:1000],
                )

        if buffer.needs_flush():
            buffer.flush(bq)

    buffer.flush(bq)  # commit the final partial batch
    return succeeded, failed


def _load_terminal_mrf_urls(bq: bigquery.Client) -> set[str]:
    """Return the set of source MRF URLs already in a terminal parse state.

    The parser walks gs://mrf-staging/raw/ each run, but most blobs there
    are already classified ('failed' / 'skipped' / 'parsed' in
    mrf_archive_index). Re-downloading and re-sniffing them every run
    burns Cloud Run runtime for no output. This returns the skip-set so
    the main loop can short-circuit before any HTTP I/O.

    SF13 (Phase 8.5): on BQ failure, fall back to a GCS-cached snapshot
    (≤24h) before slow-processing the full bucket. Pre-SF13 a transient
    BQ outage at parser startup → empty skip-set → ~25K staging blobs
    all reprocessed instead of the ~1k pending ones → Cloud Run
    --task-timeout 4h blows + partial flush + re-run loop. Cost: ~5 MB
    Standard storage + 25 reads/writes per year ≈ $0.001/year
    (CLAUDE.md Rule 16).
    """
    query = f"""
        SELECT DISTINCT source_mrf_url
        FROM `{ARCHIVE_INDEX_TABLE}`
        WHERE parse_status IN ('failed', 'skipped', 'parsed')
          AND source_mrf_url IS NOT NULL
    """
    cache_bucket = os.environ.get("MRF_DISCOVERY_CACHE_BUCKET", "").strip() or None
    try:
        rows = list(bq.query(query).result())
    except Exception as exc:
        logger.warning(
            "Could not load terminal-state skip-set from %s: %s — falling back to GCS cache",
            ARCHIVE_INDEX_TABLE, exc,
        )
        if cache_bucket:
            cached = _load_skip_set_cache(cache_bucket)
            if cached is not None:
                logger.warning(
                    "Using cached skip-set (%d URLs). May be up to 24h stale; "
                    "the worst case is re-parsing a few recently-completed "
                    "blobs — survivable.",
                    len(cached),
                )
                return cached
        logger.warning("No cache available — proceeding without skip-set (full bucket walk)")
        return set()
    skip_set = {str(r["source_mrf_url"]) for r in rows}
    logger.info("Loaded skip-set: %d source MRF URLs already in terminal state", len(skip_set))
    # SF13 fallback: persist this run's snapshot for the next outage.
    # Best-effort — write failure must not fail the parser.
    if cache_bucket and skip_set:
        try:
            _save_skip_set_cache(cache_bucket, skip_set)
        except Exception as exc:  # noqa: BLE001 — cache is best-effort
            logger.warning("Skip-set cache write failed: %s", exc)
    return skip_set


def _skip_set_cache_path() -> str:
    return "parse_skip_set/latest.json"


def _save_skip_set_cache(bucket: str, urls: set[str]) -> None:
    """Persist the skip-set to GCS so a future outage can fall back. SF13."""
    blob = storage.Client().bucket(bucket).blob(_skip_set_cache_path())
    blob.upload_from_string(json.dumps(sorted(urls)), content_type="application/json")
    logger.info("Cached %d skip-set URLs to gs://%s/%s", len(urls), bucket, _skip_set_cache_path())


def _load_skip_set_cache(bucket: str) -> set[str] | None:
    """Load the most recent cached skip-set. None if not cached or expired. SF13."""
    try:
        blob = storage.Client().bucket(bucket).blob(_skip_set_cache_path())
        if not blob.exists():
            return None
        # Reject snapshots older than 24h — staleness beyond that risks
        # re-parsing too many recently-completed blobs.
        blob.reload()
        if blob.updated:
            age_seconds = (datetime.now(timezone.utc) - blob.updated).total_seconds()
            if age_seconds > 24 * 3600:
                logger.warning(
                    "Skip-set cache too stale (%.1f hours); ignoring",
                    age_seconds / 3600,
                )
                return None
        return set(json.loads(blob.download_as_text()))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Skip-set cache load failed: %s", exc)
        return None


def main() -> None:
    task_index = int(os.environ.get("CLOUD_RUN_TASK_INDEX", "0"))
    task_count = int(os.environ.get("CLOUD_RUN_TASK_COUNT", "1"))

    bq, gcs = build_clients()
    bucket = gcs.bucket(GCS_BUCKET)

    # PARSER_RETRY_PATTERN, if set, resets matching 'failed' rows back to
    # 'pending' BEFORE the run starts. Use SQL LIKE syntax. Examples:
    #   PARSER_RETRY_PATTERN='parsed with NULL NPI%'  → retry the post-cb9b420
    #                                                   reclassified cohort
    #   PARSER_RETRY_PATTERN='no NPI resolvable%'    → retry the strict-mode
    #                                                   reject cohort
    # Only meaningful when paired with PARSER_DRIVER=archive_index since
    # the bucket-walk mode can't reach blobs whose staging copy is gone.
    retry_pattern = os.environ.get("PARSER_RETRY_PATTERN", "").strip()
    if retry_pattern:
        n = reset_failed_to_pending(bq, retry_pattern)
        logger.info("Pre-run retry reset: %d rows", n)

    # SF1 (Phase 8.2): PARSER_RESET_SKIPPED='true' (or a SQL LIKE pattern)
    # flips 'skipped' rows back to 'pending'. Operators run this AFTER
    # deploying support for a previously-skipped format (CSV, XLSX, ZIP)
    # so the next archive_index-driven run re-evaluates the cohort.
    # Without this helper the historical 'skipped' rows stay permanently
    # skipped — see SF1 in docs/playbooks/bug-fix-campaign.md.
    reset_skipped = os.environ.get("PARSER_RESET_SKIPPED", "").strip()
    if reset_skipped:
        # 'true' / '1' resets all skipped rows; any other value is treated as
        # a SQL LIKE pattern matched against parse_error.
        pattern = None if reset_skipped.lower() in ("true", "1") else reset_skipped
        n = reset_skipped_to_pending(bq, pattern)
        logger.info("Pre-run skipped reset: %d rows (pattern=%r)", n, pattern)

    # PARSER_DRIVER selects how the parser sources work:
    #   bucket_walk    (default) — walk gs://mrf-staging/raw/ and skip rows
    #                              already in a terminal mrf_archive_index state.
    #                              Bytes-source = staging bucket only.
    #                              Source blob deleted on success.
    #   archive_index  — query `mrf_archive_index` for parse_status='pending',
    #                    open each row's gcs_uri (immutable archive bucket),
    #                    and process. Source blob is NOT deleted (archive is
    #                    forensic). Required for retrying historical 'failed'
    #                    cohorts whose staging copies were already deleted.
    driver = os.environ.get("PARSER_DRIVER", "bucket_walk").strip().lower()

    if driver == "archive_index":
        succeeded, failed = process_archive_index_pending(
            bq, gcs, bucket,
            task_index=task_index, task_count=task_count,
        )
        logger.info("Parse complete (archive_index driver, task %d/%d): %d succeeded, %d failed",
                    task_index, task_count, succeeded, failed)
        return

    all_blobs = list_raw_blobs(bucket)

    if not all_blobs:
        logger.info("No MRF files to parse — exiting.")
        sys.exit(0)

    blobs = _task_shard(all_blobs, task_index, task_count)
    if task_count > 1:
        logger.info(
            "Task %d/%d — processing %d/%d blobs",
            task_index, task_count, len(blobs), len(all_blobs),
        )

    # Pre-fetch the set of MRF URLs already in a terminal parse state.
    # Each blob's mrf_url comes from custom GCS metadata; checking the set
    # before download is what cuts a 49-hour run down to ~60 minutes when
    # most of the staging bucket has already been classified.
    skip_set = _load_terminal_mrf_urls(bq)

    succeeded = 0
    failed = 0
    skipped_terminal = 0
    buffer = _SuccessBuffer()
    for blob in blobs:
        # Cheap pre-flight: read blob metadata once. If its mrf_url is in
        # the skip-set, move on without download / sniff / index update.
        meta = _get_blob_metadata(bucket, blob)
        mrf_url = meta.get("mrf_url") or ""
        if mrf_url and mrf_url in skip_set:
            skipped_terminal += 1
            continue

        if process_blob(blob, bq, bucket, success_buffer=buffer):
            succeeded += 1
        else:
            failed += 1

        if buffer.needs_flush():
            buffer.flush(bq)

    buffer.flush(bq)  # commit the final partial batch
    logger.info(
        "Parse complete: %d succeeded, %d failed, %d already-terminal (skipped pre-flight)",
        succeeded, failed, skipped_terminal,
    )
    if failed > 0:
        logger.warning("%d hospitals failed to load — check logs above", failed)
        # Exit 0 anyway — partial success is acceptable for a weekly batch job.
        # Cloud Scheduler will retry on the next weekly run.


if __name__ == "__main__":
    main()
