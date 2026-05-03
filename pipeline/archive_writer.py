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

The archive bucket is `mrf-archive-clarobill-prd` (Standard storage class
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

DEFAULT_ARCHIVE_BUCKET = "mrf-archive-clarobill-prd"
UPLOAD_CHUNK_SIZE = 16 * 1024 * 1024  # 16 MiB; matches existing scraper


@dataclass(frozen=True)
class ArchiveResult:
    """Summary of one archive write."""

    gcs_uri: str          # gs://mrf-archive-clarobill-prd/pricing-year=Y/.../sha.csv
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

    Memory contract (2026-05-01 rewrite):
      Per-worker peak memory is bounded by UPLOAD_CHUNK_SIZE (16 MiB)
      regardless of MRF size. We do this with a tee-write pattern:

        byte_stream  →  GCS resumable upload at a tmp path (streaming)
                     →  SHA256 hasher (incremental update)

      Then a server-side copy renames the tmp blob to the final
      sha-based name, and the tmp is deleted. No GCS-side data transfer
      twice; copy is metadata-only.

    Why this matters: a 321 MiB Baylor Scott & White MRF × 20 concurrent
    workers × 2x prior buffering (download_as_bytes + io.BytesIO) blew an
    8 GiB Cloud Run container at the first big-file convergence. The
    earlier inline-buffer comment "MRF files average ~5 MB, max ~500 MB"
    was wrong on the upper bound — Baylor's MRF is 321 MiB; some hospital
    systems publish 1+ GiB JSON. Stream-write is the only architecture
    that survives without an explicit per-file size check.

    Idempotency: after we know the SHA, we check whether the final blob
    already exists. If yes, skip the rename and delete the tmp blob —
    we already have this exact content archived. This handles re-scrapes
    of unchanged MRFs and worker-shard overlap.

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
    import uuid

    bucket = storage_client.bucket(bucket_name)

    # Step 1: stream `byte_stream` to a temp blob, hashing in flight.
    # The temp prefix `_tmp/` is outside the pricing-year=YYYY/ namespace
    # so the structured-search queries downstream never see it.
    tmp_object_name = f"_tmp/{uuid.uuid4()}.{extension}"
    tmp_blob = bucket.blob(tmp_object_name, chunk_size=UPLOAD_CHUNK_SIZE)

    hasher = hashlib.sha256()
    total_bytes = 0

    # blob.open("wb") returns a writer that streams chunks to GCS via a
    # single resumable upload session. Each write is buffered up to
    # chunk_size, then sent and the buffer reset. Per-worker peak memory:
    # ~chunk_size (the writer's internal buffer) + chunk_size (our read
    # buffer) = ~32 MiB, bounded.
    content_type_or_default = content_type or "application/octet-stream"
    with tmp_blob.open("wb", content_type=content_type_or_default) as gcs_writer:
        while True:
            chunk = byte_stream.read(UPLOAD_CHUNK_SIZE)
            if not chunk:
                break
            hasher.update(chunk)
            gcs_writer.write(chunk)
            total_bytes += len(chunk)
    sha256 = hasher.hexdigest()

    # Step 2: now that we know the sha, build the final object name.
    object_name = archive_layout.build_object_name(
        pricing_effective_year, key, sha256, extension,
    )
    meta_object_name = archive_layout.build_meta_object_name(
        pricing_effective_year, key, sha256,
    )
    gcs_uri = f"gs://{bucket_name}/{object_name}"
    meta_uri = f"gs://{bucket_name}/{meta_object_name}"

    data_blob = bucket.blob(object_name)
    meta_blob = bucket.blob(meta_object_name)

    # Step 3: idempotency check. If the final blob exists already, this
    # exact content was archived previously — skip the rename, delete the
    # tmp upload, and return. Saves the server-side copy cost and keeps
    # the bucket free of redundant tmp objects.
    if data_blob.exists():
        logger.info(
            "Archive object exists, skipping rename: %s (%d bytes)",
            gcs_uri, total_bytes,
        )
        try:
            tmp_blob.delete()
        except Exception as exc:
            logger.warning("Failed to delete tmp blob %s: %s", tmp_object_name, exc)
        return ArchiveResult(
            gcs_uri=gcs_uri, meta_uri=meta_uri, sha256=sha256,
            file_size_bytes=total_bytes, skipped_existing=True,
        )

    # Step 4: server-side copy tmp → final (metadata-only operation, no
    # data transfer), then delete the tmp blob.
    bucket.copy_blob(tmp_blob, bucket, new_name=object_name)
    try:
        tmp_blob.delete()
    except Exception as exc:
        # Failure to delete the tmp doesn't break the archive — the data
        # is correctly at the final path. A bucket lifecycle rule on
        # _tmp/* (age >= 1 day) catches stragglers.
        logger.warning("Failed to delete tmp blob %s after copy: %s", tmp_object_name, exc)

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
