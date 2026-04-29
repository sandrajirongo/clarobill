"""Resolves `pricing_effective_year` for an MRF file.

Three-source fallback (per Phase 4 design Q3 + Sandra's append-only +
MAX(scraped_at) decision):

  1. MRF JSON `last_updated_on` field — CMS v2.0.0 schema includes this
     at the document root. Highest-quality source: the hospital itself
     stamped the file with the year it applies to.

  2. HTTP `Last-Modified` header — fallback if the JSON doesn't have
     last_updated_on or is malformed enough that we can't extract it.

  3. Current calendar year — final fallback. Logged as a warning so
     operators know which files we couldn't date-resolve.

The same fallback applies to non-JSON formats (CSV, XLSX) — for those, the
JSON step is skipped (no last_updated_on field exists) and we go straight
to HTTP Last-Modified, then current year.

Why this matters
----------------
The rules engine joins bills to charges by `pricing_effective_year`. If we
get the year wrong, a 2024 bill could get compared against 2026 rates —
exactly the false-positive defect the whole effective-dating effort was
designed to prevent. This module is the single point where year is
decided; the answer flows into every downstream row.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Match a 4-digit year between 2020 and 2099. Bounds chosen because:
#   - Below 2020: definitely a typo or placeholder; CMS price transparency
#     rule didn't exist before 2021.
#   - Above 2099: same reason, plus simple plausibility.
_YEAR_RE = re.compile(r"\b(20[2-9]\d)\b")


def resolve_year(
    json_last_updated_on: Optional[str],
    http_last_modified: Optional[str],
    fallback_year: Optional[int] = None,
) -> tuple[int, str]:
    """Return (year, source) where source describes which input produced it.

    Args:
        json_last_updated_on: The `last_updated_on` value from MRF JSON root,
            usually shaped like "2026-01-15" or "01/15/2026". May be None.
        http_last_modified: Raw HTTP Last-Modified header value, e.g.
            "Wed, 15 Jan 2026 10:00:00 GMT". May be None.
        fallback_year: Used only if both sources fail. Defaults to current
            UTC year. Allows tests to lock the fallback for determinism.

    Returns:
        (year, source) — source is one of:
            "json_last_updated_on" | "http_last_modified" |
            "fallback_calendar_year"
    """
    # Source 1: MRF JSON last_updated_on
    if json_last_updated_on:
        year = _extract_year(json_last_updated_on)
        if year is not None:
            return year, "json_last_updated_on"

    # Source 2: HTTP Last-Modified
    if http_last_modified:
        year = _parse_http_year(http_last_modified)
        if year is not None:
            return year, "http_last_modified"

    # Source 3: fallback
    fb = fallback_year if fallback_year is not None else datetime.now(timezone.utc).year
    logger.warning(
        "Could not resolve pricing_effective_year from JSON or HTTP headers; "
        "falling back to calendar year %d", fb,
    )
    return fb, "fallback_calendar_year"


def _extract_year(value: str) -> Optional[int]:
    """Extract a 4-digit year (2020-2099) from a string.

    Handles common date formats found in MRF files:
      - ISO 8601: "2026-01-15", "2026-01-15T00:00:00Z"
      - US: "01/15/2026", "1-15-26" (rejected — 2-digit year too ambiguous)
      - Year-only: "2026"
      - Embedded: "Effective 2026-01-15"
    """
    if not value or not isinstance(value, str):
        return None
    match = _YEAR_RE.search(value)
    if not match:
        return None
    return int(match.group(1))


def _parse_http_year(header_value: str) -> Optional[int]:
    """Parse HTTP Last-Modified per RFC 7231."""
    if not header_value:
        return None
    try:
        dt = parsedate_to_datetime(header_value)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    year = dt.year
    if 2020 <= year <= 2099:
        return year
    return None
