"""Scrape hospital MRF files from hospital websites to GCS.

Cloud Run Job — triggered weekly by Cloud Scheduler.

Reads all hospitals with an mrf_url from BigQuery hospital_directory.
For each, sends a HEAD request to check the Last-Modified header.
Downloads the file to GCS only when it has changed since last scrape.

After the scrape run, batches all updates to hospital_directory.last_modified
via a BigQuery MERGE so the next run knows which files to skip.

GCS layout:
  clarobill-mrf-staging/
    raw/{npi}/{scraped_at_utc_iso}{.ext}
    e.g. raw/1234567890/2025-01-15T00:00:00Z.json.gz

The parser job (parse_hospital_mrfs.py) reads from this prefix.

--- Running locally ---
  export GOOGLE_APPLICATION_CREDENTIALS=/path/to/pipeline-sa-key.json
  export GCP_PROJECT_ID=clarobill-prd
  python pipeline/scrape_hospital_mrfs.py

--- Cloud Run Job ---
  docker build -f pipeline/Dockerfile -t scraper pipeline/
  gcloud run jobs execute clarobill-mrf-scraper --region us-central1
"""

import gzip
import io
import json
import logging
import os
import re
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

import requests
from google.cloud import bigquery, storage

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

GCP_PROJECT = os.environ.get("GCP_PROJECT_ID", "clarobill-prd")
BQ_DATASET = os.environ.get("BIGQUERY_DATASET", "clarobill_hospital_prices")
GCS_BUCKET = os.environ.get("GCS_MRF_STAGING_BUCKET", "clarobill-mrf-staging")

# Concurrent download workers — stay polite to hospital web servers.
# Each hospital is a different origin so parallel downloads are fine.
MAX_WORKERS = 20

# HEAD/GET timeout in seconds — hospitals have slow web servers.
REQUEST_TIMEOUT = 30

# Maximum file size to download (500 MB). Files larger than this are logged
# and skipped — they likely need a streaming / chunked download path.
MAX_FILE_SIZE_BYTES = 500 * 1024 * 1024

REQUEST_HEADERS = {
    "User-Agent": "ClaroBill-PriceTransparency/1.0 (price transparency research; contact@clarobill.com)",
}


def build_clients() -> tuple[bigquery.Client, storage.Client]:
    """Build BigQuery and GCS clients using Application Default Credentials.

    On Cloud Run Jobs the runtime SA is used automatically.
    Locally, GOOGLE_APPLICATION_CREDENTIALS must point to a key file.
    """
    bq = bigquery.Client(project=GCP_PROJECT)
    gcs = storage.Client(project=GCP_PROJECT)
    return bq, gcs


def load_hospitals(bq: bigquery.Client) -> list[dict[str, Any]]:
    """Load all hospitals that have an MRF URL from BigQuery.

    Returns list of dicts with keys: npi, name, mrf_url, last_modified.
    """
    query = f"""
        SELECT npi, name, mrf_url, last_modified
        FROM `{GCP_PROJECT}.{BQ_DATASET}.hospital_directory`
        WHERE mrf_url IS NOT NULL AND TRIM(mrf_url) != ''
        ORDER BY npi
    """
    rows = list(bq.query(query).result())
    logger.info("Loaded %d hospitals with MRF URLs", len(rows))
    return [dict(row) for row in rows]


def _infer_extension(url: str, content_type: str | None) -> str:
    """Infer the file extension from URL path or Content-Type header.

    MRF files are JSON, JSON-gzip, or CSV. The URL path is the most reliable
    indicator; Content-Type falls back for URLs with no extension.
    """
    path = urllib.parse.urlparse(url).path.lower()
    if path.endswith(".json.gz") or path.endswith(".json.gzip"):
        return ".json.gz"
    if path.endswith(".csv.gz") or path.endswith(".csv.gzip"):
        return ".csv.gz"
    if path.endswith(".json"):
        return ".json"
    if path.endswith(".csv"):
        return ".csv"
    if path.endswith(".zip"):
        return ".zip"
    if content_type:
        ct = content_type.lower()
        if "gzip" in ct or "gz" in ct:
            return ".json.gz"
        if "csv" in ct:
            return ".csv"
    return ".json"


def _check_hospital(
    session: requests.Session,
    hospital: dict[str, Any],
) -> tuple[dict[str, Any], bool, str | None, int | None]:
    """HEAD-check a hospital's MRF URL to detect file changes.

    Returns (hospital, should_download, new_last_modified, content_length).
    should_download is True when Last-Modified has changed or was never recorded.
    """
    npi = hospital["npi"]
    url = hospital["mrf_url"]
    stored_lm = hospital.get("last_modified")

    try:
        resp = session.head(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("[%s] HEAD failed: %s", npi, exc)
        return hospital, False, None, None

    new_lm = resp.headers.get("Last-Modified") or resp.headers.get("ETag")
    content_length = resp.headers.get("Content-Length")
    size = int(content_length) if content_length and content_length.isdigit() else None

    if size and size > MAX_FILE_SIZE_BYTES:
        logger.warning(
            "[%s] File too large (%d MB), skipping",
            npi,
            size // (1024 * 1024),
        )
        return hospital, False, new_lm, size

    changed = (new_lm is None) or (new_lm != stored_lm)
    return hospital, changed, new_lm, size


def _download_to_gcs(
    session: requests.Session,
    bucket: storage.Bucket,
    hospital: dict[str, Any],
    scraped_at: str,
) -> str | None:
    """Download a hospital's MRF file and upload it to GCS.

    Returns the GCS blob name on success, None on failure.
    The blob name encodes the NPI and scrape timestamp so the parser
    can identify which hospital the file belongs to.
    """
    npi = hospital["npi"]
    url = hospital["mrf_url"]

    try:
        resp = session.get(url, timeout=REQUEST_TIMEOUT, stream=True, allow_redirects=True)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("[%s] GET failed: %s", npi, exc)
        return None

    content_type = resp.headers.get("Content-Type", "")
    ext = _infer_extension(url, content_type)
    blob_name = f"raw/{npi}/{scraped_at}{ext}"

    try:
        blob = bucket.blob(blob_name)
        blob.upload_from_file(resp.raw, rewind=True)
        logger.info("[%s] Uploaded to gs://%s/%s", npi, bucket.name, blob_name)
        return blob_name
    except Exception as exc:
        logger.error("[%s] GCS upload failed: %s", npi, exc)
        return None


def scrape_hospital(
    hospital: dict[str, Any],
    session: requests.Session,
    bucket: storage.Bucket,
    scraped_at: str,
) -> dict[str, Any] | None:
    """Check and conditionally download one hospital's MRF file.

    Returns an update dict {npi, last_modified} if the file was downloaded,
    or None if it was unchanged or an error occurred.
    """
    hospital, should_download, new_lm, _ = _check_hospital(session, hospital)

    if not should_download:
        logger.debug("[%s] Unchanged, skipping", hospital["npi"])
        return None

    blob_name = _download_to_gcs(session, bucket, hospital, scraped_at)
    if blob_name is None:
        return None

    return {"npi": hospital["npi"], "last_modified": new_lm or ""}


def update_last_modified(
    bq: bigquery.Client,
    updates: list[dict[str, Any]],
) -> None:
    """Batch-update hospital_directory.last_modified for all scraped hospitals.

    Uses a staging table + MERGE to avoid individual row-level DML queries.
    Updates only the last_modified column — last_scraped is set by the parser
    after it successfully loads the charges.

    Args:
        bq: Authenticated BigQuery client.
        updates: List of {npi, last_modified} dicts.
    """
    if not updates:
        logger.info("No hospitals to update.")
        return

    staging_id = f"{GCP_PROJECT}.{BQ_DATASET}.scraper_lm_staging"
    ndjson = "\n".join(json.dumps({"npi": u["npi"], "last_modified": u["last_modified"]}) for u in updates)

    load_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        schema=[
            bigquery.SchemaField("npi", "STRING"),
            bigquery.SchemaField("last_modified", "STRING"),
        ],
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        create_disposition=bigquery.CreateDisposition.CREATE_IF_NEEDED,
    )
    bq.load_table_from_file(io.StringIO(ndjson), staging_id, job_config=load_config).result()

    merge_sql = f"""
        MERGE `{GCP_PROJECT}.{BQ_DATASET}.hospital_directory` T
        USING `{staging_id}` S
        ON T.npi = S.npi
        WHEN MATCHED THEN
            UPDATE SET last_modified = S.last_modified
    """
    bq.query(merge_sql).result()
    bq.delete_table(staging_id, not_found_ok=True)
    logger.info("Updated last_modified for %d hospitals", len(updates))


def main() -> None:
    bq, gcs = build_clients()
    bucket = gcs.bucket(GCS_BUCKET)
    hospitals = load_hospitals(bq)

    if not hospitals:
        logger.info("No hospitals to scrape — exiting.")
        sys.exit(0)

    scraped_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    updates: list[dict[str, Any]] = []

    with requests.Session() as session:
        session.headers.update(REQUEST_HEADERS)

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {
                pool.submit(scrape_hospital, h, session, bucket, scraped_at): h["npi"]
                for h in hospitals
            }
            for future in as_completed(futures):
                npi = futures[future]
                try:
                    result = future.result()
                    if result:
                        updates.append(result)
                except Exception as exc:
                    logger.error("[%s] Unexpected error: %s", npi, exc)

    logger.info(
        "Scrape complete: %d/%d files downloaded",
        len(updates),
        len(hospitals),
    )
    update_last_modified(bq, updates)


if __name__ == "__main__":
    main()
