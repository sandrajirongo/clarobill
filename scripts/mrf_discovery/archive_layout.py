"""GCS archive path scheme for hospital MRF files.

Pure functions, no I/O. The archiver (Phase 4) imports these to construct
object URIs; the parser imports them to deserialise sibling meta.json files
into a typed shape.

Layout:

    gs://mrf-archive-clarobill-prd/
      pricing-year={year}/
        {key}/                                  # hospital_npi if known else pra_facility_uuid
          {sha256_first16}.{ext}                # the raw MRF, immutable
          {sha256_first16}.meta.json            # provenance metadata

Example:

    gs://mrf-archive-clarobill-prd/pricing-year=2026/
      1234567890/
        a1b2c3d4e5f60718.csv
        a1b2c3d4e5f60718.meta.json

Why the project-ID suffix on the bucket name:
  GCS bucket names are globally unique across all of GCP, and the unsuffixed
  `mrf-archive` was already taken. We follow the same disambiguation convention
  GCP applies automatically to Cloud Build (`clarobill-prd_cloudbuild`) and
  Cloud Run sources (`run-sources-clarobill-prd-us-central1`). Suffix, not
  prefix — the project ID stays as a tail-disambiguator, not a primary identifier.

Why include sha256 in the filename:
  An archive object name uniquely identifies content. If a hospital re-publishes
  an unchanged file under a new "last modified" date, the sha256 stays the same
  and we don't double-store. If the content actually changed, we get a new
  object — both are preserved (versioning is also enabled at the bucket level
  as belt-and-suspenders).

Why a sibling meta.json instead of GCS object metadata:
  Object metadata is invisible without an extra HEAD per object. Storing
  provenance as a small (~1 KB) JSON sibling means a `gsutil ls` walk shows
  every fact about every archive without a single metadata fetch, and the
  parser can read it in one stream alongside the MRF itself.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

ARCHIVE_BUCKET = "mrf-archive-clarobill-prd"

VALID_EXTENSIONS = frozenset({"csv", "csv.gz", "json", "json.gz", "xlsx", "xml", "zip"})

# When matching extensions in a regex, longer alternatives must come first so
# the engine matches "csv.gz" before "csv" on a "...sha.csv.gz" path. Sorting
# by length descending guarantees this without having to maintain order by
# hand. Derived from VALID_EXTENSIONS so adding a new extension only requires
# updating one constant.
_EXT_ALTERNATION = "|".join(re.escape(e) for e in sorted(VALID_EXTENSIONS, key=len, reverse=True))

_KEY_RE = re.compile(r"^[A-Za-z0-9_\-]+$")
_SHA256_RE = re.compile(r"^[0-9a-f]{16,64}$")
_OBJECT_RE = re.compile(
    r"^pricing-year=(?P<year>\d{4})/"
    r"(?P<key>[A-Za-z0-9_\-]+)/"
    r"(?P<sha>[0-9a-f]{16,64})"
    rf"(?:\.meta\.json|\.(?P<ext>{_EXT_ALTERNATION}))$"
)


@dataclass(frozen=True)
class ArchiveMeta:
    """Provenance recorded alongside every archived MRF.

    Written as {sha256_first16}.meta.json sibling. Read by the parser to
    reconstruct who/what/when about a stored file without re-querying BigQuery.
    """

    source_url: str
    pricing_effective_year: int
    hospital_npi: str | None
    pra_facility_uuid: str | None
    ccn: str | None
    sha256: str
    file_size_bytes: int
    content_type: str | None
    mrf_last_modified_header: str | None
    mrf_etag_header: str | None
    scraped_at: str  # ISO 8601 UTC

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @staticmethod
    def from_json(text: str) -> "ArchiveMeta":
        d = json.loads(text)
        return ArchiveMeta(**d)


def _validate_key(key: str) -> None:
    if not key or not _KEY_RE.match(key):
        raise ValueError(
            f"Archive key must be alphanumeric/underscore/hyphen only, got {key!r}"
        )


def _validate_sha(sha: str) -> str:
    """Return the first-16 prefix used in object names."""
    if not _SHA256_RE.match(sha):
        raise ValueError(f"Expected hex sha256 (16-64 chars), got {sha!r}")
    return sha[:16]


def _validate_ext(ext: str) -> str:
    ext = ext.lstrip(".").lower()
    if ext not in VALID_EXTENSIONS:
        raise ValueError(f"Unsupported MRF extension {ext!r}; valid: {sorted(VALID_EXTENSIONS)}")
    return ext


def _validate_year(year: int) -> int:
    if not isinstance(year, int) or year < 2024 or year > 2034:
        raise ValueError(f"pricing_effective_year must be 2024..2034, got {year!r}")
    return year


def build_object_name(
    pricing_effective_year: int,
    key: str,
    sha256: str,
    extension: str,
) -> str:
    """Return the GCS object name (no gs:// prefix, no bucket).

    `key` is the hospital_npi when known, otherwise the pra_facility_uuid.
    The choice is made by the caller and recorded inside ArchiveMeta.
    """
    year = _validate_year(pricing_effective_year)
    _validate_key(key)
    sha_prefix = _validate_sha(sha256)
    ext = _validate_ext(extension)
    return f"pricing-year={year}/{key}/{sha_prefix}.{ext}"


def build_meta_object_name(
    pricing_effective_year: int,
    key: str,
    sha256: str,
) -> str:
    """Return the sibling meta.json object name."""
    year = _validate_year(pricing_effective_year)
    _validate_key(key)
    sha_prefix = _validate_sha(sha256)
    return f"pricing-year={year}/{key}/{sha_prefix}.meta.json"


def build_object_uri(
    pricing_effective_year: int,
    key: str,
    sha256: str,
    extension: str,
    bucket: str = ARCHIVE_BUCKET,
) -> str:
    """Return the full gs:// URI for the MRF object."""
    return f"gs://{bucket}/" + build_object_name(pricing_effective_year, key, sha256, extension)


def build_meta_uri(
    pricing_effective_year: int,
    key: str,
    sha256: str,
    bucket: str = ARCHIVE_BUCKET,
) -> str:
    """Return the full gs:// URI for the sibling meta.json object."""
    return f"gs://{bucket}/" + build_meta_object_name(pricing_effective_year, key, sha256)


def parse_object_uri(uri: str) -> dict[str, Any]:
    """Parse a gs:// archive URI back into its components.

    Returns a dict with keys: bucket, pricing_effective_year, key, sha256_prefix,
    extension (None for meta.json), is_meta (bool). Raises ValueError on a URI
    that does not match the archive layout.
    """
    if not uri.startswith("gs://"):
        raise ValueError(f"Not a gs:// URI: {uri!r}")
    rest = uri[len("gs://"):]
    bucket, _, object_name = rest.partition("/")
    if not object_name:
        raise ValueError(f"URI has no object name: {uri!r}")

    m = _OBJECT_RE.match(object_name)
    if not m:
        raise ValueError(f"URI does not match archive layout: {uri!r}")

    return {
        "bucket": bucket,
        "pricing_effective_year": int(m.group("year")),
        "key": m.group("key"),
        "sha256_prefix": m.group("sha"),
        "extension": m.group("ext"),
        "is_meta": m.group("ext") is None,
    }


def utcnow_iso() -> str:
    """ISO 8601 UTC timestamp suitable for ArchiveMeta.scraped_at."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
