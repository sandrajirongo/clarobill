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

import gzip
import io
import json
import logging
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from typing import Iterator

from google.cloud import bigquery, storage

# Phase 4 helpers + sibling modules in pipeline/
import effective_year
from hospital_mrf_utils import (
    ChargeRow,
    extract_mrf_date,
    extract_npi_from_mrf_root,
    stream_charges_v2,
)

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

# Extensions we know how to parse today. CSV-format MRFs are valid CMS output
# but use vendor-specific column names — supporting them properly requires a
# separate column-mapping pass. For now we log + skip so a CSV file does not
# crash the parser, and we mark the archive_index row as 'skipped'.
# See docs/future_improvements/csv-mrf-parser.md for the planned approach.
_PARSEABLE_EXTENSIONS = (".json", ".json.gz", ".json.gzip")


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
    try:
        bq.query(sql, job_config=job_config).result()
    except Exception as exc:
        # archive_index updates are bookkeeping, not data — failure to update
        # must not fail the parse itself. Log and continue.
        logger.warning("archive_index status update failed for %s: %s", mrf_url, exc)


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
    bq.query(sql, job_config=job_config).result()


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
    bq.query(sql, job_config=job_config).result()
    logger.info("Backfilled hospital_npi=%s for mrf_url=%s", hospital_npi, mrf_url)


def _is_parseable_extension(blob_name: str) -> bool:
    """True if the parser knows how to handle this blob's format today.

    JSON / JSON-gzip are supported. CSV/XLSX/ZIP are skipped with a logged
    'skipped' status in mrf_archive_index — see _PARSEABLE_EXTENSIONS.
    """
    name = blob_name.lower()
    return any(name.endswith(ext) for ext in _PARSEABLE_EXTENSIONS)


def process_blob(
    blob: storage.Blob,
    bq: bigquery.Client,
    bucket: storage.Bucket,
) -> bool:
    """Parse one MRF blob and load its charges into BigQuery.

    Returns True on success, False on any error (logs details and continues
    to the next hospital so one bad MRF doesn't abort the entire run).

    Phase 4 changes:
      - Resolves pricing_effective_year via effective_year.resolve_year()
        from the MRF JSON last_updated_on (best), HTTP Last-Modified header
        carried in blob metadata (good), or current calendar year (fallback).
      - Append-only: no DELETE before LOAD. Downstream queries pick the most
        recent (scraped_at, pricing_effective_year) per (hospital_npi, code).
      - Updates mrf_archive_index.parse_status to 'parsed' / 'failed' /
        'skipped' so the archive bucket has authoritative parse provenance.
      - Skips non-JSON formats (CSV/XLSX/ZIP) cleanly without crashing.

    NPI strategy: the scraper stores the hospital_name/mrf_url/state in GCS
    blob metadata at download time. The NPI is not reliably available then
    (some discovery sources only have CCN). This function reads the MRF JSON
    root to extract the NPI, then backfills hospital_directory if it was NULL.
    """
    meta = _get_blob_metadata(bucket, blob)
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

    logger.info("[%s] Processing %s", label, blob.name)
    scraped_at = datetime.now(timezone.utc).isoformat()

    # Read MRF JSON last_updated_on AND scraper-stamped HTTP Last-Modified.
    # The scraper writes the latter into blob metadata as `last_modified`.
    # effective_year resolves both into a single year + source label.
    json_last_updated = _read_mrf_date(blob)
    http_last_modified = meta.get("last_modified") or None
    pricing_effective_year, year_source = effective_year.resolve_year(
        json_last_updated_on=json_last_updated,
        http_last_modified=http_last_modified,
    )
    logger.info(
        "[%s] pricing_effective_year=%d (source=%s)",
        label, pricing_effective_year, year_source,
    )

    # Provenance: every charge row carries the original MRF URL it came from
    # plus (when available) the gs:// URI of the immutable archive blob.
    # Lets us trace any anomalous row back to its source file.
    source_mrf_url = mrf_url
    # The staging blob has gs://mrf-staging/raw/... — the parser doesn't have
    # the archive URI handy unless we pass it through blob metadata. For now
    # we record None and rely on mrf_archive_index.source_mrf_url join to
    # recover the archive blob if needed.
    source_gcs_uri: str | None = None

    # Extract NPI from MRF JSON root — the most reliable source.
    # Fall back to the value the scraper stored in blob metadata (may be empty).
    hospital_npi = _read_mrf_npi(blob) or meta.get("hospital_npi") or ""
    if not hospital_npi:
        logger.warning(
            "[%s] NPI not found in MRF root or blob metadata — charges will have blank NPI",
            label,
        )

    staging_blob_name = f"{STAGING_PREFIX}{uuid.uuid4()}.ndjson"
    staging_uri = f"gs://{GCS_BUCKET}/{staging_blob_name}"

    try:
        with _open_mrf_blob(blob) as f:
            rows = stream_charges_v2(
                f, hospital_npi, pricing_effective_year, scraped_at,
                source_mrf_url=source_mrf_url, source_gcs_uri=source_gcs_uri,
            )
            row_count = _write_ndjson_to_gcs(rows, bucket, staging_blob_name)

        if row_count == 0:
            logger.warning("[%s] No charge rows parsed — skipping load", label)
            bucket.blob(staging_blob_name).delete()
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

        mark_last_scraped(bq, mrf_url, scraped_at)

        # Backfill NPI into hospital_directory if it was NULL (common on first scrape).
        if hospital_npi:
            update_hospital_npi(bq, mrf_url, hospital_npi)

        update_archive_index_status(bq, mrf_url, "parsed")

        # Delete raw MRF blob — prevents double-processing on next run.
        # The immutable archive bucket still has the file (Phase 4 dual-write).
        blob.delete()
        bucket.blob(staging_blob_name).delete()
        return True

    except Exception as exc:
        logger.error("[%s] Failed: %s", label, exc, exc_info=True)
        try:
            bucket.blob(staging_blob_name).delete()
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


def main() -> None:
    task_index = int(os.environ.get("CLOUD_RUN_TASK_INDEX", "0"))
    task_count = int(os.environ.get("CLOUD_RUN_TASK_COUNT", "1"))

    bq, gcs = build_clients()
    bucket = gcs.bucket(GCS_BUCKET)
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

    succeeded = 0
    failed = 0
    for blob in blobs:
        if process_blob(blob, bq, bucket):
            succeeded += 1
        else:
            failed += 1

    logger.info("Parse complete: %d succeeded, %d failed", succeeded, failed)
    if failed > 0:
        logger.warning("%d hospitals failed to load — check logs above", failed)
        # Exit 0 anyway — partial success is acceptable for a weekly batch job.
        # Cloud Scheduler will retry on the next weekly run.


if __name__ == "__main__":
    main()
