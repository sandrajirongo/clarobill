"""Scrape hospital MRF files from hospital websites to GCS.

Cloud Run Job — triggered weekly by Cloud Scheduler.

Reads all hospitals with an mrf_url from BigQuery hospital_directory.
For each, sends a HEAD request to check the Last-Modified header.
Downloads the file to GCS only when it has changed since last scrape.

After the scrape run, batches all updates to hospital_directory.last_modified
via a BigQuery MERGE so the next run knows which files to skip.

GCS layout:
  mrf-staging/
    raw/{name_slug}/{scraped_at_utc_iso}{.ext}
    e.g. raw/johns-hopkins-hospital/2025-01-15T00:00:00Z.json.gz

The parser reads hospital context (name, mrf_url, state) from GCS blob
metadata rather than the path, since NPIs are not known until the MRF is
parsed.  The parser job (parse_hospital_mrfs.py) reads from this prefix.

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

# Phase 4 helpers — pulled from sibling files in pipeline/
import effective_year
import archive_writer
from hospital_mrf_utils import ACCEPTED_MRF_FORMATS, sniff_mrf_format

# SF5 (Phase 8.4): centralised DML helper. See parse_hospital_mrfs.py for context.
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "scripts" / "mrf_discovery"))
from bq_checkpoint import run_dml_with_count  # noqa: E402

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

GCP_PROJECT = os.environ.get("GCP_PROJECT_ID", "clarobill-prd")
BQ_DATASET = os.environ.get("BIGQUERY_DATASET", "hospital_prices")
GCS_BUCKET = os.environ.get("GCS_MRF_STAGING_BUCKET", "mrf-staging")
# Phase 4 archive bucket (immutable historical). Dual-write: every download
# lands in BOTH mrf-staging (legacy parser path, ephemeral) AND mrf-archive
# (year-partitioned, immutable). Parser reads from staging today; future
# parser revision reads from archive. Set as env var so tests can override.
GCS_ARCHIVE_BUCKET = os.environ.get("GCS_MRF_ARCHIVE_BUCKET", "clarobill-mrf-archive-uscentral")

# Concurrent download workers. Two prior calibrations:
#   2026-04-30 first run: 60 workers OOM'd at 4 GiB.
#   2026-04-30 retry: 20 workers OOM'd at 8 GiB on a 321 MiB Baylor MRF.
# Root cause of both: archive_writer.write_archive() buffered the full MRF
# in io.BytesIO before knowing the sha-based object name. A 321 MiB CSV
# × N workers grew unbounded with file size.
#
# 2026-05-01 architectural fix: archive_writer now stream-writes to a tmp
# GCS blob via blob.open("wb"), hashes in flight, then server-side renames
# to the final sha-based path. Per-worker peak memory = chunk_size × 2
# (~32 MiB) regardless of file size.
#
# With that fix, MAX_WORKERS=40 fits comfortably in 8 GiB:
#   40 workers × 32 MiB = ~1.3 GiB, leaves ~6 GiB for Python overhead +
#   ThreadPoolExecutor state + concurrent BigQuery clients.
# Throughput vs 20: 2x scrape rate, fleet completes in ~half the time.
MAX_WORKERS = 40

# GCS resumable upload chunk size (bytes). 16MB is a good balance — large
# enough for throughput, small enough to keep per-worker memory bounded.
GCS_UPLOAD_CHUNK_SIZE = 16 * 1024 * 1024

# Separate timeouts for HEAD checks vs file downloads.
# Hospital web servers are often slow — 30s HEAD timeouts cause many false
# skips. Downloads can take minutes for large (100-500 MB) MRF files.
HEAD_TIMEOUT = 60   # seconds — generous for slow hospital DNS + TLS handshake
GET_TIMEOUT  = 120  # seconds — large files need time to start streaming

# No file size limit — files stream from hospital servers directly to GCS in
# 16MB chunks so memory usage is constant regardless of file size.

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

    Returns list of dicts with keys: hospital_npi, ccn, hospital_name, state,
    mrf_url, last_modified.

    Phase 4: also pulls `ccn` so we can use it as the archive key when NPI is
    missing (mixed-key strategy from Phase 4 Q1). The parser will backfill NPI
    from MRF JSON metadata after the first successful parse.
    """
    query = f"""
        SELECT hospital_npi, ccn, hospital_name, state, mrf_url, last_modified
        FROM `{GCP_PROJECT}.{BQ_DATASET}.hospital_directory`
        WHERE mrf_url IS NOT NULL AND TRIM(mrf_url) != ''
        ORDER BY hospital_name
    """
    rows = list(bq.query(query).result())
    logger.info("Loaded %d hospitals with MRF URLs", len(rows))
    return [dict(row) for row in rows]


def _archive_key(hospital: dict[str, Any]) -> str | None:
    """Return the GCS archive key for a hospital — NPI if known, else CCN.

    Per Phase 4 Q1: mixed keys are acceptable. The parser later backfills
    NPI when it parses the MRF JSON root. archive_layout's path-builder
    accepts either format; downstream queries don't care which one was used.
    """
    npi = (hospital.get("hospital_npi") or "").strip()
    if npi and npi.isdigit() and len(npi) == 10:
        return npi
    ccn = (hospital.get("ccn") or "").strip()
    if ccn:
        return ccn
    return None


def _name_slug(name: str) -> str:
    """Return a GCS-safe path segment from a hospital name.

    Lowercases, replaces all non-alphanumeric runs with hyphens, trims leading
    and trailing hyphens, and caps at 60 characters so paths stay readable.
    Used for GCS blob paths since NPIs are not available at scrape time.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:60]


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
    label = hospital.get("hospital_name") or hospital.get("mrf_url", "?")
    url = hospital["mrf_url"]
    stored_lm = hospital.get("last_modified")

    try:
        resp = session.head(url, timeout=HEAD_TIMEOUT, allow_redirects=True)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("[%s] HEAD failed: %s", label, exc)
        return hospital, False, None, None

    new_lm = resp.headers.get("Last-Modified") or resp.headers.get("ETag")
    content_length = resp.headers.get("Content-Length")
    size = int(content_length) if content_length and content_length.isdigit() else None

    if size:
        logger.debug("[%s] File size: %d MB", label, size // (1024 * 1024))

    changed = (new_lm is None) or (new_lm != stored_lm)
    return hospital, changed, new_lm, size


class _PrependedStream(io.RawIOBase):
    """A read-only stream that yields `prefix` bytes first, then drains `rest`.

    Used to splice the 4 KB sniff buffer back onto the front of the response
    stream so GCS upload sees the unaltered bytes. We can't `seek(0)` on
    `requests` HTTP streams, and re-opening the connection would double-fetch
    every hospital. This wrapper solves it without buffering the full body.

    Forward-only: GCS resumable uploads call read()/readinto() sequentially,
    so seek/tell support is not needed (and would be misleading anyway since
    `rest` is a non-seekable network socket).
    """

    def __init__(self, prefix: bytes, rest) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self._prefix = io.BytesIO(prefix)
        self._rest = rest

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        if size == -1:
            return self._prefix.read() + self._rest.read()
        out = self._prefix.read(size)
        if len(out) < size:
            remainder = self._rest.read(size - len(out))
            out += remainder if isinstance(remainder, bytes) else bytes(remainder)
        return out

    def readinto(self, b) -> int:  # type: ignore[no-untyped-def]
        # GCS resumable upload uses readinto when available; fall back to
        # read() if `rest` doesn't expose readinto.
        n = self._prefix.readinto(b)
        if n < len(b):
            view = memoryview(b)[n:]
            try:
                more = self._rest.readinto(view)
            except AttributeError:
                chunk = self._rest.read(len(view))
                view[: len(chunk)] = chunk
                more = len(chunk)
            n += more or 0
        return n


def _download_to_gcs(
    session: requests.Session,
    bucket: storage.Bucket,
    hospital: dict[str, Any],
    scraped_at: str,
    last_modified: str | None = None,
) -> str | None:
    """Download a hospital's MRF file and upload it to GCS.

    Returns the GCS blob name on success, None on failure.

    The blob path uses the hospital name slug (NPIs are not reliably available
    at scrape time — the NPI is extracted from inside the MRF during parsing).
    Hospital context (name, mrf_url, state) is stored in GCS blob metadata so
    the parser can link rows back to hospital_directory.

    The response is always explicitly closed in a finally block so the
    underlying socket and its kernel receive buffer are released immediately
    after upload, regardless of success or failure.  Without this, failed
    uploads leave open sockets that accumulate and cause OOM.
    """
    name = hospital.get("hospital_name") or ""
    url = hospital["mrf_url"]
    label = name or url

    try:
        resp = session.get(url, timeout=GET_TIMEOUT, stream=True, allow_redirects=True)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("[%s] GET failed: %s", label, exc)
        return None

    content_type = resp.headers.get("Content-Type", "")
    content_encoding = resp.headers.get("Content-Encoding", "").lower()
    ext = _infer_extension(url, content_type)

    # Some hospital servers send plain .json files with Content-Encoding: gzip
    # (transport compression). The actual bytes on the wire are compressed, so
    # the URL path has no .gz suffix but the stored bytes are gzip.
    # Append .gz so the parser knows to decompress them.
    if "gzip" in content_encoding and not ext.endswith(".gz"):
        ext += ".gz"

    # Scrape-time content validation (postmortem #1). Read the first 4 KB
    # off the response, sniff the format, and reject HTML / PDF / unknown
    # formats *before* writing anything to GCS. Without this, every
    # scheduled scrape re-pollutes the archive with hospital landing pages,
    # marketing brochures, 404 HTML, and once a Facebook redirect chain.
    # The sniffed bytes are then prepended back onto the upload stream so
    # the on-the-wire content is preserved bit-for-bit.
    try:
        prefix = resp.raw.read(4096)
    except Exception as exc:
        logger.error("[%s] read prefix failed: %s", label, exc)
        return None
    fmt = sniff_mrf_format(prefix, content_type=content_type, url=url)
    if fmt not in ACCEPTED_MRF_FORMATS:
        logger.warning(
            "[%s] Rejecting non-MRF response: format=%s url=%s ct=%s",
            label, fmt, url, content_type,
        )
        return None
    upload_stream = _PrependedStream(prefix, resp.raw)

    # 2026-05-01 fix: include the hospital's archive key (NPI or CCN) in
    # the staging path so multi-facility hospital systems whose names
    # truncate to identical 60-char slugs don't collide. Saw this on the
    # 6xvh9 run with multiple Baylor Scott & White facilities all
    # uploading to the same `raw/baylor-scott-white-emergency-medical-
    # center-at-c/...` blob name and racing each other's generations.
    slug = _name_slug(name) if name else "unknown"
    key_suffix = _archive_key(hospital) or "nokey"
    blob_name = f"raw/{slug}-{key_suffix}/{scraped_at}{ext}"

    try:
        blob = bucket.blob(blob_name, chunk_size=GCS_UPLOAD_CHUNK_SIZE)
        # Store hospital context in blob metadata — parser reads these to link
        # rows to hospital_directory without needing NPI at scrape time.
        # Phase 4: also stamp `last_modified` so the parser can use it as a
        # second-source signal for pricing_effective_year (after the JSON
        # `last_updated_on` field, which is more authoritative).
        blob.metadata = {
            "hospital_name": name,
            "mrf_url": url,
            "state": hospital.get("state") or "",
            "hospital_npi": hospital.get("hospital_npi") or "",
            "last_modified": last_modified or "",
        }
        # decode_content=False: store the raw compressed bytes as received.
        # The Content-Length header reflects the compressed size — if we let
        # urllib3 decompress on the fly (decode_content=True), the GCS
        # resumable upload gets more bytes than the Content-Range header
        # declares, causing a 400 "Invalid request" from the GCS API.
        resp.raw.decode_content = False
        blob.upload_from_file(upload_stream)
        logger.info("[%s] Uploaded to gs://%s/%s", label, bucket.name, blob_name)
        return blob_name
    except Exception as exc:
        logger.error("[%s] GCS upload failed: %s", label, exc)
        return None
    finally:
        # Always release the socket — prevents kernel recv-buffer accumulation.
        resp.close()


def scrape_hospital(
    hospital: dict[str, Any],
    bucket: storage.Bucket,
    archive_bucket: storage.Bucket | None,
    scraped_at: str,
) -> dict[str, Any] | None:
    """Check and conditionally download one hospital's MRF file.

    Creates its own requests.Session so each worker thread has an independent
    connection pool — shared sessions cause urllib3 pool contention and
    leave stale buffers when connections are reused across threads.

    Phase 4: dual-writes to BOTH the legacy mrf-staging bucket (for the
    existing parser) AND the immutable clarobill-mrf-archive-uscentral bucket
    (year-partitioned, content-hashed). Returns archive metadata so the
    caller can also insert a row into mrf_archive_index.

    Returns either:
      - dict with {mrf_url, last_modified, archive_meta} on success
      - None on skip or failure

    archive_meta (when present) is a dict ready to insert into mrf_archive_index.
    archive_bucket may be None for tests; when None the archive write is skipped.
    """
    with requests.Session() as session:
        session.headers.update(REQUEST_HEADERS)
        hospital, should_download, new_lm, _ = _check_hospital(session, hospital)

        label = hospital.get("hospital_name") or hospital.get("mrf_url", "?")
        if not should_download:
            logger.debug("[%s] Unchanged, skipping", label)
            return None

        blob_name = _download_to_gcs(session, bucket, hospital, scraped_at, new_lm)
        if blob_name is None:
            return None

        # Phase 4 dual-write: also archive to the immutable bucket.
        # The legacy bucket already has the bytes; we re-download for the
        # archive write because the legacy upload streamed directly from
        # `resp.raw` and is no longer available. This doubles per-hospital
        # bandwidth but is the smallest-blast-radius way to ship dual-write
        # without rewriting the whole download path.
        archive_meta = None
        if archive_bucket is not None:
            try:
                archive_meta = _archive_from_legacy_blob(
                    bucket, archive_bucket, blob_name, hospital, new_lm,
                )
            except Exception as exc:
                # Archive failures must NOT kill the legacy path. The legacy
                # bucket has the file; the parser can still process it. We
                # just lose the immutable copy for this run, which is
                # recovered on next week's scrape.
                logger.warning("[%s] Archive write failed (legacy still OK): %s", label, exc)

        return {
            "mrf_url": hospital["mrf_url"],
            "last_modified": new_lm or "",
            "archive_meta": archive_meta,
        }


def _archive_from_legacy_blob(
    legacy_bucket: storage.Bucket,
    archive_bucket: storage.Bucket,
    legacy_blob_name: str,
    hospital: dict[str, Any],
    last_modified: str | None,
) -> dict[str, Any] | None:
    """Read the just-written legacy blob and re-write to archive bucket.

    Computes SHA256 inline, resolves pricing_effective_year, writes to the
    year/key/sha-keyed path, plus a sibling meta.json.

    Returns a dict ready to insert into mrf_archive_index, or None if the
    hospital lacks an archive key (no NPI and no CCN — rare but possible).
    """
    key = _archive_key(hospital)
    if not key:
        logger.debug("Skipping archive: no NPI or CCN for %s", hospital.get("hospital_name"))
        return None

    legacy_blob = legacy_bucket.blob(legacy_blob_name)
    legacy_blob.reload()  # populate metadata
    metadata = legacy_blob.metadata or {}

    # Determine pricing_effective_year. Without parsing the MRF JSON here,
    # we lean on Last-Modified header + calendar-year fallback. The parser
    # will refine the year when it actually opens the file.
    year, year_source = effective_year.resolve_year(
        json_last_updated_on=None,
        http_last_modified=last_modified,
    )

    # Infer extension from the legacy blob name (already correct from the
    # original download path).
    ext = _legacy_blob_to_extension(legacy_blob_name)

    # Stream the legacy bytes through the archive writer rather than loading
    # the whole blob into memory. 2026-04-30 OOM postmortem: a 111MB Sutter
    # MRF × 20+ concurrent workers × 2x buffering (download_as_bytes +
    # archive_writer's internal buffer) hit Cloud Run's memory ceiling.
    # legacy_blob.open("rb") streams; archive_writer still buffers internally
    # because it needs the SHA256 to construct the object name, but at least
    # we cut the per-worker peak in half.
    body_stream = legacy_blob.open("rb")

    result = archive_writer.write_archive(
        storage_client=archive_bucket.client,
        pricing_effective_year=year,
        key=key,
        extension=ext,
        source_url=metadata.get("mrf_url") or hospital.get("mrf_url", ""),
        content_type=legacy_blob.content_type,
        byte_stream=body_stream,
        last_modified=last_modified,
        bucket_name=archive_bucket.name,
    )

    return {
        "hospital_npi": hospital.get("hospital_npi"),
        "ccn": hospital.get("ccn"),
        "pricing_effective_year": year,
        "source_mrf_url": metadata.get("mrf_url") or hospital.get("mrf_url", ""),
        "gcs_uri": result.gcs_uri,
        "sha256": result.sha256,
        "file_size_bytes": result.file_size_bytes,
        "content_type": legacy_blob.content_type,
        "mrf_last_modified_header": last_modified,
        "mrf_etag_header": None,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "parse_status": "pending",
        "parse_error": None,
        "parsed_at": None,
        "_year_source": year_source,  # log-only, stripped before insert
    }


def _legacy_blob_to_extension(blob_name: str) -> str:
    """Extract the canonical extension (csv, json, json.gz, etc.) from a
    legacy GCS blob name like 'raw/foo-hospital/2026-04-29T00:00:00Z.json.gz'.
    Maps to archive_layout.VALID_EXTENSIONS.
    """
    name = blob_name.lower()
    # Match longest first so .json.gz wins over .json
    for ext in ("json.gz", "csv.gz", "json", "csv", "xlsx", "xml", "zip"):
        if name.endswith("." + ext):
            return ext
    return "json"  # default; should never happen given _infer_extension at download time


def update_last_modified(
    bq: bigquery.Client,
    updates: list[dict[str, Any]],
    task_index: int = 0,
) -> None:
    """Batch-update hospital_directory.last_modified for all scraped hospitals.

    Uses a staging table + MERGE to avoid individual row-level DML queries.
    Joins on mrf_url (always populated) rather than hospital_npi (often NULL
    until the MRF is parsed and the NPI is extracted from the file content).
    Updates only the last_modified column — last_scraped is set by the parser
    after it successfully loads the charges.

    task_index is appended to the staging table name so parallel task instances
    don't clobber each other's staging data during concurrent MERGE operations.

    Args:
        bq: Authenticated BigQuery client.
        updates: List of {mrf_url, last_modified} dicts.
        task_index: Cloud Run task index (0 for single-task runs).
    """
    if not updates:
        logger.info("No hospitals to update.")
        return

    # Deduplicate by mrf_url — multiple hospitals can share one URL (health
    # system MRFs covering several facilities). BigQuery MERGE requires at most
    # one source row per target row; duplicates cause a 400 BadRequest.
    deduped: dict[str, str] = {u["mrf_url"]: u["last_modified"] for u in updates}
    if len(deduped) < len(updates):
        logger.info(
            "Deduplicated %d updates → %d unique mrf_urls",
            len(updates),
            len(deduped),
        )

    staging_id = f"{GCP_PROJECT}.{BQ_DATASET}.scraper_lm_staging_{task_index}"
    ndjson = "\n".join(
        json.dumps({"mrf_url": url, "last_modified": lm})
        for url, lm in deduped.items()
    )

    load_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        schema=[
            bigquery.SchemaField("mrf_url", "STRING"),
            bigquery.SchemaField("last_modified", "STRING"),
        ],
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        create_disposition=bigquery.CreateDisposition.CREATE_IF_NEEDED,
    )
    bq.load_table_from_file(io.StringIO(ndjson), staging_id, job_config=load_config).result()

    merge_sql = f"""
        MERGE `{GCP_PROJECT}.{BQ_DATASET}.hospital_directory` T
        USING `{staging_id}` S
        ON T.mrf_url = S.mrf_url
        WHEN MATCHED THEN
            UPDATE SET last_modified = S.last_modified
    """
    # SF5 (Phase 8.4): verify the MERGE actually wrote rows.
    affected = run_dml_with_count(bq, merge_sql, label="hospital_directory.last_modified MERGE")
    bq.delete_table(staging_id, not_found_ok=True)
    logger.info(
        "Updated last_modified for %d unique mrf_urls (MERGE affected %d rows)",
        len(deduped), affected,
    )


def _task_shard(items: list, task_index: int, task_count: int) -> list:
    """Return the slice of items assigned to this Cloud Run task instance.

    Cloud Run Jobs injects CLOUD_RUN_TASK_INDEX (0-based) and
    CLOUD_RUN_TASK_COUNT when --tasks > 1. Slice pattern items[i::n] gives
    each task a roughly equal share with no gaps or overlaps.

    Example — 6 tasks, 7,200 hospitals: each task gets exactly 1,200.
    Callers pass task_index=0, task_count=1 for single-task runs (default).
    """
    return items[task_index::task_count]


def insert_archive_index_rows(
    bq: bigquery.Client,
    archive_metas: list[dict[str, Any]],
) -> None:
    """Append archived-MRF rows to mrf_archive_index via a LOAD JOB.

    Why a load job instead of streaming insert: streaming-inserted rows sit
    in BigQuery's streaming buffer for ~30 minutes before they become
    UPDATEable. The parser job runs immediately after the scraper and needs
    to UPDATE parse_status, which fails against streamed-but-not-yet-merged
    rows ("UPDATE or DELETE statement over table ... would affect rows in
    the streaming buffer"). Load jobs land directly in storage and become
    DML-eligible immediately.

    Drops the internal `_year_source` field (log-only) before insert.
    """
    if not archive_metas:
        return
    table_id = f"{GCP_PROJECT}.{BQ_DATASET}.mrf_archive_index"
    rows = []
    for meta in archive_metas:
        if meta is None:
            continue
        row = {k: v for k, v in meta.items() if not k.startswith("_")}
        rows.append(row)
    if not rows:
        return

    ndjson = "\n".join(json.dumps(r) for r in rows)
    load_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        ignore_unknown_values=True,
    )
    job = bq.load_table_from_file(
        io.StringIO(ndjson), table_id, job_config=load_config,
    )
    job.result()
    logger.info(
        "Loaded %d rows into mrf_archive_index (load job, not streaming)",
        len(rows),
    )


def main() -> None:
    task_index = int(os.environ.get("CLOUD_RUN_TASK_INDEX", "0"))
    task_count = int(os.environ.get("CLOUD_RUN_TASK_COUNT", "1"))

    bq, gcs = build_clients()
    bucket = gcs.bucket(GCS_BUCKET)
    archive_bucket = gcs.bucket(GCS_ARCHIVE_BUCKET) if GCS_ARCHIVE_BUCKET else None
    all_hospitals = load_hospitals(bq)

    if not all_hospitals:
        logger.info("No hospitals to scrape — exiting.")
        sys.exit(0)

    hospitals = _task_shard(all_hospitals, task_index, task_count)
    if task_count > 1:
        logger.info(
            "Task %d/%d — processing %d/%d hospitals",
            task_index, task_count, len(hospitals), len(all_hospitals),
        )

    scraped_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 2026-05-01 hardening: incremental flush every FLUSH_EVERY hospitals.
    # The 6xvh9 run (4h timeout) made it through 9,242 hospitals but lost
    # ALL the last_modified updates and ~half the archive_index rows because
    # the prior all-or-nothing write at end-of-run never executed before
    # SIGTERM. Mirror Stage 4's pattern (commit c8e6791) so a partial scrape
    # converges instead of restarting from scratch.
    FLUSH_EVERY = 500
    updates_buffer: list[dict[str, Any]] = []
    archive_metas_buffer: list[dict[str, Any]] = []
    total_downloaded = 0
    total_archived = 0
    total_lm_flushed = 0
    total_archive_flushed = 0

    def _flush_batch(reason: str) -> None:
        """Persist whatever is in the flush buffers, then clear them."""
        nonlocal total_lm_flushed, total_archive_flushed
        try:
            if updates_buffer:
                update_last_modified(bq, updates_buffer, task_index=task_index)
                total_lm_flushed += len(updates_buffer)
            if archive_metas_buffer:
                insert_archive_index_rows(bq, archive_metas_buffer)
                total_archive_flushed += len(archive_metas_buffer)
            logger.info(
                "Flushed batch (%s): +%d last_modified rows, +%d archive_index rows. "
                "Cumulative persisted so far: lm=%d, archive=%d",
                reason, len(updates_buffer), len(archive_metas_buffer),
                total_lm_flushed, total_archive_flushed,
            )
            updates_buffer.clear()
            archive_metas_buffer.clear()
        except Exception:
            # Never let a transient BQ error abort the scrape. Log full
            # traceback to stdout (Cloud Run captures reliably) and keep
            # the buffer for retry on the next flush.
            logger.exception(
                "Persist flush FAILED (%s) — keeping buffers for retry. "
                "buffer sizes: updates=%d archive_metas=%d",
                reason, len(updates_buffer), len(archive_metas_buffer),
            )

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(scrape_hospital, h, bucket, archive_bucket, scraped_at): (
                h.get("hospital_name") or h.get("mrf_url", "?")
            )
            for h in hospitals
        }
        completed = 0
        for future in as_completed(futures):
            label = futures[future]
            try:
                result = future.result()
                if result:
                    updates_buffer.append({k: v for k, v in result.items() if k != "archive_meta"})
                    total_downloaded += 1
                    if result.get("archive_meta"):
                        archive_metas_buffer.append(result["archive_meta"])
                        total_archived += 1
            except Exception as exc:
                logger.error("[%s] Unexpected error: %s", label, exc)
            completed += 1
            if completed % FLUSH_EVERY == 0:
                _flush_batch(reason=f"every-{FLUSH_EVERY} at completed={completed}")

    # Final flush — anything still in the buffers from the last partial batch.
    _flush_batch(reason="final")

    logger.info(
        "Scrape complete: %d/%d files downloaded, %d archived to %s",
        total_downloaded, len(hospitals), total_archived, GCS_ARCHIVE_BUCKET,
    )


if __name__ == "__main__":
    main()
