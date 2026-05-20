"""Streams hospital MRF files to the immutable GCS archive.

Wraps the GCS upload with three concerns the legacy scraper handled
inconsistently:

  1. Inline SHA256 — bytes are hashed as they flow through, so we know the
     content-hash without a second pass. This is the dedup key in
     mrf_archive_index AND the object name suffix.

  2. Sibling meta.json — every archived file gets a `{sha256}.meta.json`
     written next to it with provenance fields (source_url, scraped_at,
     content_type, file_size_bytes, etag, last_modified). The parser reads
     meta.json instead of needing to look up the archive_index row, which
     keeps the parser independent of BigQuery during the actual parse.

  3. Idempotency — if an object already exists at the same path (same year,
     same key, same sha256), we skip the upload. Saves bandwidth on weekly
     re-scrapes of unchanged hospital MRFs.

The archive bucket is `clarobill-mrf-archive-uscentral` (Standard storage class
as of 2026-05-03 — was Coldline, but the parser actively re-reads the
bucket so retrieval fees + Class B op rates were burning ~$100/day; see
docs/postmortem/2026-05-03-mrf-pipeline-postmortem.md). Versioning is
disabled. This module never deletes.

Path layout (delegated to scripts/mrf_discovery/archive_layout.py):
  pricing-year={year}/{key}/{sha256[:16]}.{ext}
  pricing-year={year}/{key}/{sha256[:16]}.meta.json

Where `key` is `hospital_npi` if known, else `ccn` (the mixed-key strategy
from Phase 4 Q1).
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

from google.cloud import storage

# Reuse the path-construction module from scripts/mrf_discovery/. Two
# environments to support — different file layouts:
#   Dev (run from repo root):
#     pipeline/archive_writer.py -> ../scripts/mrf_discovery/archive_layout.py
#     i.e. parent.parent / "scripts"
#   Container (pipeline/Dockerfile):
#     /app/archive_writer.py -> /app/scripts/mrf_discovery/archive_layout.py
#     i.e. parent / "scripts"
# Add whichever candidate path actually contains mrf_discovery/ to sys.path
# so the same import line works in both. The next environment variant just
# adds another candidate to the tuple.
_THIS = Path(__file__).resolve()
for _candidate in (
    _THIS.parent / "scripts",         # container layout (/app/scripts/)
    _THIS.parent.parent / "scripts",  # dev layout (<repo>/scripts/)
):
    if (_candidate / "mrf_discovery" / "archive_layout.py").exists():
        sys.path.insert(0, str(_candidate))
        break
else:
    raise ImportError(
        "Could not locate scripts/mrf_discovery/archive_layout.py from "
        f"{_THIS} — checked {[str(p) for p in (_THIS.parent / 'scripts', _THIS.parent.parent / 'scripts')]}"
    )
from mrf_discovery import archive_layout  # type: ignore[import-not-found]

logger = logging.getLogger(__name__)

DEFAULT_ARCHIVE_BUCKET = "clarobill-mrf-archive-uscentral"
UPLOAD_CHUNK_SIZE = 16 * 1024 * 1024  # 16 MiB; matches existing scraper


@dataclass(frozen=True)
class ArchiveResult:
    """Summary of one archive write."""

    gcs_uri: str          # gs://clarobill-mrf-archive-uscentral/pricing-year=Y/.../sha.csv
    meta_uri: str         # sibling meta.json
    sha256: str           # full hex digest
    file_size_bytes: int
    skipped_existing: bool  # True if we found the object already and didn't re-upload


def write_archive(
    storage_client: storage.Client,
    pricing_effective_year: int,
    key: str,                        # hospital_npi or ccn
    extension: str,                  # csv, json, json.gz, etc.
    source_url: str,
    content_type: str | None,
    byte_stream: BinaryIO,
    etag: str | None = None,
    last_modified: str | None = None,
    bucket_name: str = DEFAULT_ARCHIVE_BUCKET,
) -> ArchiveResult:
    """Stream `byte_stream` to GCS, computing SHA256 inline.

    Memory contract: per-worker peak memory is bounded by UPLOAD_CHUNK_SIZE
    (16 MiB) regardless of MRF file size. Approach:

      1. Stream byte_stream into a temporary GCS blob via BlobWriter,
         hashing inline. BlobWriter buffers one chunk at a time in its own
         internal BytesIO and retries failed chunks from that cache — no
         tmpfs, no seekable source required.
      2. After upload completes we know SHA256. Build the final
         content-addressed object name.
      3. Check idempotency: if the final blob already exists, delete the
         tmp blob and return — we already have this content archived.
      4. Server-side copy tmp blob → final path (metadata-only op, no
         data leaves GCS, no RAM). Delete tmp blob.

    Why this matters: a 321 MiB Baylor Scott & White MRF × 40 concurrent
    workers using tempfile.TemporaryFile() (which is in-memory tmpfs in
    Cloud Run) OOM'd an 8 GiB container. BlobWriter is the only approach
    that provides retry-safe uploads without tmpfs buffering.

    Idempotency: handles re-scrapes of unchanged MRFs and any worker-shard
    overlap — the tmp blob is always cleaned up regardless of outcome.

    Args:
        storage_client: shared GCS client (one per process is fine).
        pricing_effective_year: from `pipeline.effective_year.resolve_year`.
        key: hospital_npi if known, else ccn.
        extension: file extension (e.g. 'csv', 'json.gz') — must be in
            archive_layout.VALID_EXTENSIONS.
        source_url: original URL we downloaded from.
        content_type: HTTP Content-Type header value.
        byte_stream: file-like producing bytes. Will be fully consumed.
        etag: HTTP ETag (for change detection on next scrape).
        last_modified: HTTP Last-Modified header value.
        bucket_name: defaults to the production archive bucket.

    Returns:
        ArchiveResult with sha256, sizes, and the gs:// URIs.
    """
    bucket = storage_client.bucket(bucket_name)
    content_type_or_default = content_type or "application/octet-stream"

    # Step 1: stream byte_stream into a temporary GCS blob, hashing inline.
    # BlobWriter buffers one chunk in its own internal BytesIO and retries
    # failed chunks from that cache — no tmpfs required, no seekable source.
    hasher = hashlib.sha256()
    total_bytes = 0
    tmp_name = f"_tmp/{uuid.uuid4().hex}"
    tmp_blob = bucket.blob(tmp_name, chunk_size=UPLOAD_CHUNK_SIZE)

    try:
        with tmp_blob.open("wb", content_type=content_type_or_default) as gcs_out:
            while True:
                chunk = byte_stream.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                hasher.update(chunk)
                gcs_out.write(chunk)
                total_bytes += len(chunk)

        sha256 = hasher.hexdigest()

        # Step 2: build the final content-addressed object name.
        object_name = archive_layout.build_object_name(
            pricing_effective_year, key, sha256, extension,
        )
        meta_object_name = archive_layout.build_meta_object_name(
            pricing_effective_year, key, sha256,
        )
        gcs_uri = f"gs://{bucket_name}/{object_name}"
        meta_uri = f"gs://{bucket_name}/{meta_object_name}"

        data_blob = bucket.blob(object_name, chunk_size=UPLOAD_CHUNK_SIZE)
        meta_blob = bucket.blob(meta_object_name)

        # Step 3: idempotency — if the exact content is already archived, skip.
        if data_blob.exists():
            logger.info(
                "Archive object exists, skipping upload: %s (%d bytes)",
                gcs_uri, total_bytes,
            )
            return ArchiveResult(
                gcs_uri=gcs_uri, meta_uri=meta_uri, sha256=sha256,
                file_size_bytes=total_bytes, skipped_existing=True,
            )

        # Step 4: server-side copy tmp → final content-addressed path.
        # No data leaves GCS, no RAM. Then clean up the tmp blob.
        bucket.copy_blob(tmp_blob, bucket, object_name)

    finally:
        try:
            tmp_blob.delete()
        except Exception:
            pass

    # Build + upload sibling meta.json (small, single put)
    meta = archive_layout.ArchiveMeta(
        source_url=source_url,
        pricing_effective_year=pricing_effective_year,
        hospital_npi=key if _looks_like_npi(key) else None,
        pra_facility_uuid=None,  # not used in CMS-direct path; legacy field
        ccn=key if not _looks_like_npi(key) else None,
        sha256=sha256,
        file_size_bytes=total_bytes,
        content_type=content_type,
        mrf_last_modified_header=last_modified,
        mrf_etag_header=etag,
        scraped_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    meta_blob.upload_from_string(meta.to_json(), content_type="application/json")

    logger.info("Archived %s (%d bytes, sha256=%s...)", gcs_uri, total_bytes, sha256[:16])
    return ArchiveResult(
        gcs_uri=gcs_uri, meta_uri=meta_uri, sha256=sha256,
        file_size_bytes=total_bytes, skipped_existing=False,
    )


def _looks_like_npi(key: str) -> bool:
    """Heuristic: NPIs are exactly 10 digits; CCNs are 6 chars (often alphanumeric).

    Used for meta.json provenance only — never for routing. The mixed-key
    strategy (Phase 4 Q1) means callers pass whichever they have; this
    function just records which one it was.
    """
    return len(key) == 10 and key.isdigit()
