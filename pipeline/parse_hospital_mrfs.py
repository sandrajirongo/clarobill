"""Parse hospital MRF files from GCS and load charges into BigQuery.

Cloud Run Job — triggered by Cloud Scheduler weekly, after the scraper job.

Reads all files under gs://mrf-staging/raw/, parses each MRF
according to CMS JSON schema v2.0.0, and loads the normalised charge rows
into BigQuery hospital_charges.

For each hospital processed:
  1. Extract NPI from GCS blob path (raw/{npi}/{timestamp}.ext)
  2. Stream-parse the JSON/CSV file using hospital_mrf_utils
  3. Write normalised rows as NDJSON to a GCS staging blob
  4. DELETE existing rows for this NPI from hospital_charges (idempotent)
  5. Run a BigQuery load job from the staging blob → hospital_charges
  6. Update hospital_directory.last_scraped for this NPI
  7. Delete the raw MRF blob (GCS lifecycle handles it anyway, but explicit
     deletion prevents double-processing if the scheduler overlaps)

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

# hospital_mrf_utils lives in the same package directory (pipeline/)
from hospital_mrf_utils import (
    ChargeRow,
    extract_mrf_date,
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

# BigQuery schema for hospital_charges
HOSPITAL_CHARGES_SCHEMA = [
    bigquery.SchemaField("hospital_npi", "STRING", mode="REQUIRED"),
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
    bigquery.SchemaField("effective_date", "DATE"),
    bigquery.SchemaField("scraped_at", "TIMESTAMP"),
]

CHARGES_TABLE = f"{GCP_PROJECT}.{BQ_DATASET}.hospital_charges"
DIRECTORY_TABLE = f"{GCP_PROJECT}.{BQ_DATASET}.hospital_directory"


def build_clients() -> tuple[bigquery.Client, storage.Client]:
    """Build BigQuery and GCS clients using Application Default Credentials."""
    return bigquery.Client(project=GCP_PROJECT), storage.Client(project=GCP_PROJECT)


def list_raw_blobs(bucket: storage.Bucket) -> list[storage.Blob]:
    """List all MRF blobs in the raw/ prefix, sorted by NPI then name."""
    blobs = list(bucket.list_blobs(prefix=RAW_PREFIX))
    blobs = [b for b in blobs if not b.name.endswith("/")]
    blobs.sort(key=lambda b: b.name)
    logger.info("Found %d raw MRF files to process", len(blobs))
    return blobs


def _extract_npi_from_path(blob_name: str) -> str | None:
    """Extract the NPI from a GCS path of the form raw/{npi}/{timestamp}.ext."""
    match = re.match(r"raw/(\d{10})/", blob_name)
    return match.group(1) if match else None


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


def delete_existing_charges(bq: bigquery.Client, hospital_npi: str) -> None:
    """Delete all existing charge rows for this hospital before re-loading.

    This makes the parser idempotent: re-running on the same MRF file
    replaces stale data rather than appending duplicates.
    """
    sql = f"""
        DELETE FROM `{CHARGES_TABLE}`
        WHERE hospital_npi = @npi
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("npi", "STRING", hospital_npi)]
    )
    bq.query(sql, job_config=job_config).result()


def load_charges_from_gcs(bq: bigquery.Client, staging_uri: str) -> bigquery.LoadJob:
    """Run a BigQuery load job from the staging NDJSON file into hospital_charges.

    Uses WRITE_APPEND so we can load charges for multiple hospitals in one run
    (each hospital deletes its own rows first — see delete_existing_charges).
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


def mark_last_scraped(bq: bigquery.Client, npi: str, scraped_at: str) -> None:
    """Update hospital_directory.last_scraped after successful charge load."""
    sql = f"""
        UPDATE `{DIRECTORY_TABLE}`
        SET last_scraped = @scraped_at
        WHERE npi = @npi
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("scraped_at", "TIMESTAMP", scraped_at),
            bigquery.ScalarQueryParameter("npi", "STRING", npi),
        ]
    )
    bq.query(sql, job_config=job_config).result()


def process_blob(
    blob: storage.Blob,
    bq: bigquery.Client,
    bucket: storage.Bucket,
) -> bool:
    """Parse one MRF blob and load its charges into BigQuery.

    Returns True on success, False on any error (logs details and continues
    to the next hospital so one bad MRF doesn't abort the entire run).
    """
    hospital_npi = _extract_npi_from_path(blob.name)
    if not hospital_npi:
        logger.error("Cannot extract NPI from blob path: %s — skipping", blob.name)
        return False

    logger.info("[%s] Processing %s", hospital_npi, blob.name)
    scraped_at = datetime.now(timezone.utc).isoformat()

    # We need the effective_date from the MRF root before streaming charges.
    # Load just the root metadata (first ~4 KB) to extract last_updated_on.
    effective_date = _read_mrf_date(blob)
    if not effective_date:
        # Fall back to today if the MRF doesn't publish a date.
        effective_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        logger.warning("[%s] MRF has no last_updated_on — using today %s", hospital_npi, effective_date)

    staging_blob_name = f"{STAGING_PREFIX}{hospital_npi}/{uuid.uuid4()}.ndjson"
    staging_uri = f"gs://{GCS_BUCKET}/{staging_blob_name}"

    try:
        with _open_mrf_blob(blob) as f:
            rows = stream_charges_v2(f, hospital_npi, effective_date, scraped_at)
            row_count = _write_ndjson_to_gcs(rows, bucket, staging_blob_name)

        if row_count == 0:
            logger.warning("[%s] No charge rows parsed — skipping load", hospital_npi)
            bucket.blob(staging_blob_name).delete()
            return False

        logger.info("[%s] Parsed %d charge rows", hospital_npi, row_count)

        delete_existing_charges(bq, hospital_npi)
        load_charges_from_gcs(bq, staging_uri)
        logger.info("[%s] Loaded %d rows to hospital_charges", hospital_npi, row_count)

        mark_last_scraped(bq, hospital_npi, scraped_at)

        # Delete raw MRF blob — prevents double-processing on next run.
        blob.delete()
        bucket.blob(staging_blob_name).delete()
        return True

    except Exception as exc:
        logger.error("[%s] Failed: %s", hospital_npi, exc, exc_info=True)
        # Best-effort cleanup of staging file
        try:
            bucket.blob(staging_blob_name).delete()
        except Exception:
            pass
        return False


def _read_mrf_date(blob: storage.Blob) -> str | None:
    """Read the first 8 KB of an MRF blob to extract last_updated_on.

    Uses a partial download rather than streaming the entire file since
    the date field is always in the root object (near the start).
    """
    import json as _json

    try:
        # Download first 8 KB — enough to contain the root metadata.
        header_bytes = blob.download_as_bytes(start=0, end=8192)
        if blob.name.endswith(".gz") or blob.name.endswith(".gzip"):
            header_bytes = gzip.decompress(header_bytes[:])
    except Exception:
        return None

    try:
        # Find the last_updated_on field via substring search to avoid
        # partial-JSON parse errors (the 8 KB slice is not complete JSON).
        import re as _re
        match = _re.search(rb'"last_updated_on"\s*:\s*"([^"]{4,20})"', header_bytes)
        if match:
            return match.group(1).decode("utf-8", errors="replace")[:10]
        match = _re.search(rb'"version_date"\s*:\s*"([^"]{4,20})"', header_bytes)
        if match:
            return match.group(1).decode("utf-8", errors="replace")[:10]
    except Exception:
        pass
    return None


def main() -> None:
    bq, gcs = build_clients()
    bucket = gcs.bucket(GCS_BUCKET)
    blobs = list_raw_blobs(bucket)

    if not blobs:
        logger.info("No MRF files to parse — exiting.")
        sys.exit(0)

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
