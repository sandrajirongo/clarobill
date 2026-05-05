"""Stage 4 — Extract MRF download URLs from each hospital's website.

For each hospital with `hospital_website` set on `mrf_discovery_checkpoint`
but `validated_mrf_urls IS NULL`, this stage crawls the website using a
generic depth-2 heuristic and extracts CMS-shaped MRF URLs.

Pipeline per hospital:

  1. Crawl homepage + every PATH_HEURISTICS path (one GET each).
  2. From every fetched HTML page, follow up to MAX_FOLLOWUPS_PER_PAGE
     anchor links whose text/href matches `_KEYWORD_RE`. Recursively up
     to MAX_FOLLOW_DEPTH levels deep. Same-host only.
  3. URL extraction on every HTML response (filename regex + anchor scan
     for direct file links + TOC JSON expansion for system-wide indexes).
  4. STRICT validation: a URL is a valid MRF candidate ONLY if its path
     looks like an MRF file (CMS filename pattern OR real MRF extension)
     AND the server returns a non-HTML Content-Type. HTML responses are
     never classified as MRFs even if Content-Type is technically OK,
     because they're landing pages by definition.
  5. Persist:
       a. checkpoint.validated_mrf_urls = JSON array of URLs
       b. checkpoint.mrf_discovery_method = "homepage" | "path_heuristic"
          | "depth_follow" | "toc_expansion"
       c. checkpoint.mrf_validated_at + crawl_complete_at = NOW()
       d. MERGE into hospital_directory so the scraper picks them up

2026-05-04 rewrite removed the previous `_SYSTEM_LISTING_PAGES` hardcoded
dictionary (Sutter, Providence, Banner, MGB, Northwell). The depth-2
generic follow does the same job universally — the homepage links to a
landing page, the landing page links to the MRF files, depth-2 reaches
both. Hardcoded entries don't scale and gave a false sense of coverage:
the original Sutter entry produced 5 landing-page URLs that were all
classified as "validated MRF URLs" because the validation gate was too
permissive. Both gaps are closed in this rewrite.

Concurrency control
-------------------
`MAX_WORKERS` (60) bounds total parallelism. Per-host concurrency is
additionally capped at PER_HOST_MAX_CONCURRENT so 30+ Sutter hospitals
sharing `sutterhealth.org` don't stampede a single origin.

Resumability
------------
Skips any hospital whose `validated_mrf_urls` is already populated. To
re-process the cohort affected by the pre-2026-05-04 bug, run with
`--force-recrawl-broken` — that clears validated_mrf_urls for any row
whose JSON array doesn't contain a CMS-pattern URL.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import socket
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests
from google.cloud import bigquery


# S4 fix (2026-05-04): transient crawl errors must not permanently mark a
# hospital as "no MRF found". A timeout, dropped connection, or 5xx blip
# during the crawl tells us nothing about whether the hospital actually has
# a price-transparency file — only that this attempt didn't reach it. Pre-fix,
# every exception type was caught the same way and the hospital was added to
# failed_ccns, terminating future re-attempts. Defining this set explicitly
# at module scope so the catch-site below can re-classify cleanly.
_TRANSIENT_CRAWL_EXCEPTIONS: tuple[type[BaseException], ...] = (
    requests.Timeout,
    requests.ConnectionError,
    socket.timeout,
    ConnectionResetError,
)


def _assert_flush_complete(
    pending_discovered: int,
    pending_failed: int,
    flush_failures: list[tuple[str, str]],
) -> None:
    """Raise RuntimeError if Stage 4 finished with un-persisted rows or a
    failed final flush. Pulled out as a module-level function so it's
    independently testable (S3 fix, 2026-05-04).

    Pre-fix, _flush_batch swallowed every BQ error and Stage 4 reported
    success with total_flushed potentially zero. Cloud Run exited 0 → no
    alert → next quarterly run repeated the entire crawl. Now: anything
    that prevented rows from landing forces a non-zero exit so Sentry +
    Cloud Run alerts fire.
    """
    if pending_discovered or pending_failed:
        raise RuntimeError(
            f"Stage 4 finished with {pending_discovered} discovered + "
            f"{pending_failed} failed rows still un-persisted. "
            f"Flush failures recorded: {flush_failures}. "
            "Investigate BQ access / schema and re-run."
        )
    if flush_failures and flush_failures[-1][0] == "final":
        # Buffers are empty but the final flush itself failed — only happens
        # via an unusual code path where rows cleared without a successful
        # persist. Defensive raise so the operator can audit.
        raise RuntimeError(
            f"Stage 4 final flush failed: {flush_failures[-1][1]}. "
            f"All recorded failures: {flush_failures}."
        )
    # SF10 (Phase 8.4): intermediate flush failures (non-final) that were
    # eventually drained by the next periodic flush still indicate BQ
    # instability that should be triaged. Pre-SF10 the operator saw
    # `flush_failures: 3` in the summary stdout but the run exited 0
    # with no alert. Now: emit a WARN log line so Cloud Logging filters
    # can configure an alert. Keeps the run successful (data did make
    # it in eventually) but surfaces the signal.
    if flush_failures:
        logger.warning(
            "Stage 4 finished with %d intermediate flush failure(s) (non-final). "
            "Buffers eventually drained, but BQ instability should be triaged. "
            "Failures: %s",
            len(flush_failures), flush_failures,
        )

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from mrf_discovery import bq_checkpoint  # type: ignore[no-redef]
else:
    from . import bq_checkpoint

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

USER_AGENT = (
    "ClaroBill-MRFDiscovery/1.0 "
    "(price transparency research; contact@clarobill.com)"
)
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)

HEAD_TIMEOUT = 10
GET_TIMEOUT = 20
MAX_REDIRECTS = 3
MAX_WORKERS = 60
# S5 fix (2026-05-04): a single 500MB hospital response — binary file
# misadvertised as HTML, infinite-redirect loop, misconfigured streaming
# server — would OOM the worker because requests.get() without stream=True
# loads the entire body into memory before any size check can fire. The cap
# below is applied via stream=True + iter_content; anything beyond MAX_BODY_BYTES
# is silently truncated and treated as if the page wasn't useful. 5 MiB
# comfortably accommodates the largest hospital homepages (~2 MB peak observed)
# and the largest legitimate price-transparency JSON TOCs (HCA/Sutter ~3 MB).
MAX_BODY_BYTES = 5 * 1024 * 1024

# Depth-2 generic follow: from any fetched HTML page we follow up to N
# anchor links whose text/href matches `_KEYWORD_RE`. Bounds:
MAX_FOLLOW_DEPTH = 2
MAX_FOLLOWUPS_PER_PAGE = 5

# Per-host concurrency cap. Two reasons:
#   1. Hospital systems (Sutter ~30 facilities, HCA ~180, etc.) all live on
#      the same domain. Without a cap, 60 workers can fan out to the same
#      origin simultaneously and trigger rate-limiting / 429s.
#   2. Some sites are slow under concurrent load — limiting per-host keeps
#      individual response times sane and lets the global thread pool
#      saturate other hospitals' domains.
PER_HOST_MAX_CONCURRENT = 2

# CMS-mandated and CMS-suggested price-transparency landing pages.
# Updated 2026-04-30 after the first production run found 32% hit rate.
# Strategy change: probes are NO LONGER first-match-wins. We visit every
# matching path, aggregate every MRF URL extracted, and ALSO crawl the
# homepage. The widened list below includes paths harvested from real
# misses in the 2026-04-29 run (e.g. Sutter Health uses
# `/billing-insurance/costs-and-charges/cost-transparency`).
PATH_HEURISTICS: tuple[str, ...] = (
    # Original 17 (high-frequency CMS-suggested)
    "/price-transparency",
    "/standard-charges",
    "/billing/standard-charges",
    "/billing/price-transparency",
    "/patients/price-transparency",
    "/patients/billing/standard-charges",
    "/patients/financial-services/standard-charges",
    "/about/price-transparency",
    "/about/billing/standard-charges",
    "/financial-services/price-transparency",
    "/financial-services/standard-charges",
    "/transparency",
    "/charges",
    "/pricing",
    "/standardcharges",
    "/hospital-charges",
    "/financial-assistance/standard-charges",
    # Added 2026-04-30 from observed real-world variants
    "/billing-insurance/costs-and-charges/cost-transparency",  # Sutter
    "/billing-insurance/costs-and-charges",
    "/cost-transparency",
    "/costs-and-charges",
    "/about-us/billing-and-insurance/standard-charges",
    "/about-us/financial-information",
    "/about-us/price-transparency",
    "/financial-information/standard-charges",
    "/financial-information/price-transparency",
    "/billing-and-insurance/price-transparency",
    "/billing-and-insurance/standard-charges",
    "/patient-resources/billing/standard-charges",
    "/patient-services/billing-insurance",
    "/insurance-and-billing/cost-transparency",
    "/cost-estimator",
    "/shoppable-services",
    "/estimate-of-charges",
    "/patients-visitors/billing/standard-charges",
    # 2026-04-30 round 2: harvested from real-world misses (knoxville,
    # intermountain, ascension, commonspirit, banner, providence, etc.)
    "/billing",
    "/billing-information",
    "/billing-information-policies",
    "/for-patients/billing",
    "/for-patients/billing/hospital-price-estimates",
    "/patient-resources/price-transparency",
    "/billing-support/pricing-transparency",
)

# CMS rule 45 CFR 180.50 mandates a filename pattern of the form
# `{ein}_{hospital_name}_standardcharges.{csv,json,xml}` where EIN is
# 9 digits. Some hospitals use NPI (10 digits) or other 6-12-digit codes.
_CMS_FILENAME_RE = re.compile(
    r"\d{6,12}[_\-].+?[_\-]?standard[_\- ]?charges\.(?:csv|json|xml|xlsx)"
    r"(?:\.gz|\.gzip|\.zip)?",
    re.IGNORECASE,
)

# Generic anchor-text patterns that indicate a price-transparency MRF link.
# Widened 2026-04-30 with real-world variants observed across systems
# (Sutter calls their tool "Cost Estimator" and the page "Cost Transparency";
# many hospitals use "shoppable services" or "hospital charges" without the
# CMS-canonical "standard charges" phrasing).
_KEYWORD_RE = re.compile(
    r"(machine[\s\-]?readable[\s\-]?file"
    r"|standard[\s\-]?charges"
    r"|price[\s\-]?transparency"
    r"|chargemaster"
    r"|cost[\s\-]?transparency"
    r"|costs?[\s\-]?and[\s\-]?charges"
    r"|cost[\s\-]?estimator"
    r"|shoppable[\s\-]?services"
    r"|hospital[\s\-]?charges"
    r"|estimate[\s\-]?of[\s\-]?charges"
    r"|patient[\s\-]?pricing"
    r"|pricing[\s\-]?information"
    r"|view[\s\-]?(?:our[\s\-]?)?charges"
    r"|fee[\s\-]?schedule"
    r"|financial[\s\-]?information"
    # 2026-04-30 round 2: bare "billing" is the most common nav-link text
    # used by community hospitals to gate to their price-transparency page
    # (e.g. knoxvillehospital.org → /billing-information-policies/). Bare
    # "billing" matches a lot of false-positive anchors (footer "Pay Your
    # Bill" links etc.) but the depth-1 follow strategy gracefully degrades
    # — false-positive follows just don't yield MRF URLs and we move on.
    # The cost is HEAD requests; the benefit is reaching the long-tail
    # hospitals where "Billing" is the only nav term.
    r"|billing"
    r"|pay[\s\-]?(?:my[\s\-]?)?bill"
    r"|patient[\s\-]?(?:billing|services|resources|financial)"
    r")",
    re.IGNORECASE,
)

# Table-of-Contents JSON URL pattern (CMS allows hospital systems to publish
# one TOC linking to multiple facility MRFs).
_TOC_FILENAME_RE = re.compile(
    r"(standard[_\- ]?charges[_\- ]?toc|toc[_\- ]?standard[_\- ]?charges)\.json"
    r"(?:\.gz|\.gzip)?",
    re.IGNORECASE,
)

# 2026-05-04: the previous `_SYSTEM_LISTING_PAGES` hardcoded dict has been
# deleted. Hardcoding system→path mappings is brittle (paths break when
# systems rebrand their pricing pages), incomplete (only 5 systems out of
# the ~hundreds that exist), and it gives a false sense of coverage when
# the heuristic crawler should be doing this generically anyway.
#
# Replacement strategy: depth-2 generic follow.
#   - Crawl the homepage + every PATH_HEURISTICS path.
#   - From every fetched HTML page, follow up to MAX_FOLLOWUPS_PER_PAGE
#     anchor links whose text/href matches `_KEYWORD_RE`. Track depth so
#     a homepage → cost-transparency landing → MRF-files page chain works.
#   - Tighten validation so HTML responses are NEVER classified as MRFs;
#     the actual MRF files are extracted from those landing pages by
#     `_extract_links_from_html` and HEAD-validated separately.


# Acceptable Content-Type prefixes for HEAD validation — covers all the
# common MRF formats (CSV, JSON, gzipped, XLSX, generic octet-stream that
# many CDNs serve unhelpfully).
#
# 2026-05-04 INCIDENT FIX: text/html is NOT an acceptable MRF Content-Type.
# The previous "we accept and let parser decide" comment was the root cause
# of the Sutter Stage 4 miss: 5 landing pages with text/html responses passed
# validation as "MRF URLs" and got MERGEd into hospital_directory.mrf_url, so
# every Sutter hospital's mrf_url pointed at a billing-info marketing page
# instead of the real /files/Project/SutterHealth/.../standardcharges.csv
# files. By the time the parser saw them they were already terminal.
#
# An MRF URL is a FILE. Anything served as text/html is by definition not
# the file we're looking for — even if the page happens to contain links to
# the actual files (those are extracted by _extract_links_from_html and
# validated separately). The landing page itself is never the MRF.
_OK_CONTENT_TYPES = (
    "text/csv",
    "text/plain",
    "application/json",
    "application/octet-stream",
    "application/gzip",
    "application/x-gzip",
    "application/zip",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/xml",
    "text/xml",
)


@dataclass(frozen=True)
class DiscoveredMrf:
    """One validated MRF URL belonging to a hospital."""

    ccn: str
    hospital_npi: str | None
    hospital_name: str
    state: str | None
    mrf_url: str
    discovery_method: str  # 'path_heuristic' | 'html_link' | 'toc_expansion'
    file_format: str       # 'csv' | 'json' | 'xml' | 'xlsx' | 'unknown'
    content_type: str | None
    file_size_bytes: int | None


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _http_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "*/*"})
    return s


# Process-wide per-host semaphores. Lazy-created on first hit per host so we
# don't enumerate every possible host upfront. Threadsafe via threading.Lock.
import threading as _threading
_PER_HOST_SEMAPHORES: dict[str, _threading.Semaphore] = {}
_PER_HOST_LOCK = _threading.Lock()


def _per_host_semaphore(host: str) -> _threading.Semaphore:
    """Return the shared concurrency-cap semaphore for `host`.

    Creates one Semaphore(PER_HOST_MAX_CONCURRENT) per unique host. All
    workers across the thread pool share the same semaphore for a given
    host so hospital-system fan-outs (Sutter, HCA) can't stampede a single
    origin.
    """
    h = host.lower()
    sem = _PER_HOST_SEMAPHORES.get(h)
    if sem is not None:
        return sem
    with _PER_HOST_LOCK:
        sem = _PER_HOST_SEMAPHORES.get(h)
        if sem is None:
            sem = _threading.Semaphore(PER_HOST_MAX_CONCURRENT)
            _PER_HOST_SEMAPHORES[h] = sem
        return sem


def _host_of(url: str) -> str:
    """Lowercase host portion of a URL, for per-host rate-limiting bucket key."""
    try:
        return urllib.parse.urlparse(url).netloc.lower()
    except (ValueError, TypeError):
        return ""


def _read_capped(resp: requests.Response, max_bytes: int = MAX_BODY_BYTES) -> str | None:
    """Read the body up to max_bytes, decoded as text. Returns None when capped.

    Used by `_get_with_ua_fallback` so callers never see a payload larger than
    the cap. Refuses up-front if Content-Length declares an oversize response;
    falls back to chunked iter_content otherwise (some servers omit the header
    or stream-truncate at unbounded length).
    """
    cl = resp.headers.get("Content-Length")
    if cl and cl.isdigit() and int(cl) > max_bytes:
        return None
    encoding = resp.encoding or resp.apparent_encoding or "utf-8"
    chunks: list[bytes] = []
    total = 0
    try:
        for chunk in resp.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                return None
            chunks.append(chunk)
    except requests.RequestException:
        return None
    try:
        return b"".join(chunks).decode(encoding, errors="replace")
    except (UnicodeDecodeError, LookupError):
        return b"".join(chunks).decode("utf-8", errors="replace")


def _get_with_ua_fallback(
    session: requests.Session, url: str, timeout: int
) -> tuple[requests.Response | None, str | None]:
    """GET with descriptive UA; on 403/406/429 retry with a browser UA.

    Wraps every network call in a per-host semaphore (PER_HOST_MAX_CONCURRENT)
    so that hospital-system fan-outs (Sutter, HCA, Providence) don't stampede
    a single origin.

    S5 fix (2026-05-04): the response body is read via stream=True + chunked
    iter_content, capped at MAX_BODY_BYTES. Pre-fix, the bare `session.get()`
    loaded the entire body into memory before any size check could fire — a
    single 500MB response (binary misadvertised as HTML, redirect loop,
    misconfigured streaming server) would OOM the worker. With 60 workers,
    three pathological responses ate the Cloud Run container.

    Returns (response, body_text_or_none). body is None when the response
    was oversize, the network errored mid-stream, or the request itself
    failed. Caller checks resp.status_code and decides what to do with body.
    """
    sem = _per_host_semaphore(_host_of(url))
    with sem:
        try:
            resp = session.get(
                url, timeout=timeout, allow_redirects=True, stream=True,
            )
            if resp.status_code in (403, 406, 429):
                resp.close()
                resp = session.get(
                    url, timeout=timeout, allow_redirects=True, stream=True,
                    headers={"User-Agent": BROWSER_UA},
                )
            body = _read_capped(resp)
            resp.close()
            return resp, body
        except requests.RequestException:
            return None, None


def _head_with_ua_fallback(
    session: requests.Session, url: str
) -> tuple[int | None, str | None, int | None]:
    """HEAD probe with UA fallback. Returns (status, content_type, content_length).

    Per-host concurrency capped via _per_host_semaphore.
    """
    sem = _per_host_semaphore(_host_of(url))
    with sem:
        try:
            resp = session.head(url, timeout=HEAD_TIMEOUT, allow_redirects=True)
            if resp.status_code in (403, 406, 429):
                resp = session.head(
                    url, timeout=HEAD_TIMEOUT, allow_redirects=True,
                    headers={"User-Agent": BROWSER_UA},
                )
            ct = resp.headers.get("Content-Type")
            cl = resp.headers.get("Content-Length")
            size = int(cl) if cl and cl.isdigit() else None
            return resp.status_code, ct, size
        except requests.RequestException:
            return None, None, None


# ---------------------------------------------------------------------------
# URL extraction strategies
# ---------------------------------------------------------------------------


def _resolve_url(base: str, link: str) -> str | None:
    """Return absolute URL from a base + link, dropping fragments. None if invalid."""
    try:
        joined = urllib.parse.urljoin(base, link)
        parsed = urllib.parse.urlparse(joined)
        if parsed.scheme not in ("http", "https"):
            return None
        # Drop fragment + lowercase host
        return urllib.parse.urlunparse(parsed._replace(fragment=""))
    except (ValueError, TypeError):
        return None


def _extract_links_from_html(html: str, base_url: str) -> set[str]:
    """Find every CMS-shaped MRF link in raw HTML.

    Two-pass extraction:
      1. Filename regex against full document — finds direct links even when
         not in <a> tags.
      2. Anchor-keyword scan — finds <a href=X>...</a> where the link text
         matches `_KEYWORD_RE` ("standard charges" etc.).

    Returns absolute URLs.
    """
    found: set[str] = set()

    # Pass 1: filename-shaped links anywhere in the HTML.
    for match in _CMS_FILENAME_RE.finditer(html):
        # Walk back from the match position to find the surrounding href/url.
        start = match.start()
        # Look backwards up to 500 chars for `href="..."` or `url(...)`.
        prefix = html[max(0, start - 500):start]
        href_match = re.search(
            r'(?:href|src|url)\s*[=\(]\s*["\']?([^"\')\s>]+)$',
            prefix,
        )
        if href_match:
            link = href_match.group(1) + match.group(0)
            absolute = _resolve_url(base_url, link)
            if absolute:
                found.add(absolute)
        else:
            # Fallback: the match itself might already be a relative path
            # like `/files/123_hospital_standardcharges.csv`.
            absolute = _resolve_url(base_url, match.group(0))
            if absolute:
                found.add(absolute)

    # Pass 2: anchor tags whose target IS a real MRF file.
    # 2026-05-04 incident fix: previously this pass also accepted anchors
    # whose URL merely had _KEYWORD_RE keyword text (e.g. "/cost-transparency"
    # in the path). That caused Sutter's 5 landing-page URLs — which look
    # nothing like MRF files — to be classified as "validated MRF URLs".
    # The new rule: anchor-keyword pass emits ONLY URLs that look like real
    # MRF files (extension match OR CMS filename pattern). Landing pages
    # whose path matches keywords are NOT MRF candidates themselves; they
    # are crawl candidates handled by `_follow_keyword_anchors` separately.
    for anchor_match in re.finditer(
        r'<a\s+[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        html, re.IGNORECASE | re.DOTALL,
    ):
        href, anchor_text = anchor_match.group(1), anchor_match.group(2)
        # Strip HTML tags from the anchor text.
        clean_text = re.sub(r"<[^>]+>", "", anchor_text)
        if not _KEYWORD_RE.search(clean_text) and not _KEYWORD_RE.search(href):
            continue
        absolute = _resolve_url(base_url, href)
        if not absolute:
            continue
        # STRICT: anchor-keyword candidates only count if the URL itself
        # looks like an MRF file. URLs like `/billing/cost-transparency`
        # don't qualify even if the anchor text says "Cost Transparency".
        if (_CMS_FILENAME_RE.search(absolute)
                or absolute.lower().split("?", 1)[0].endswith((
                    ".csv", ".json", ".xml", ".xlsx",
                    ".csv.gz", ".json.gz", ".zip", ".xml.gz", ".gzip",
                ))):
            found.add(absolute)

    return found


def _find_toc_url(html: str, base_url: str) -> str | None:
    """Find a hospital-system Table-of-Contents JSON URL in the HTML."""
    for match in _TOC_FILENAME_RE.finditer(html):
        start = match.start()
        prefix = html[max(0, start - 500):start]
        href_match = re.search(
            r'(?:href|src|url)\s*[=\(]\s*["\']?([^"\')\s>]+)$',
            prefix,
        )
        link = (href_match.group(1) + match.group(0)) if href_match else match.group(0)
        absolute = _resolve_url(base_url, link)
        if absolute:
            return absolute
    return None


def _expand_toc(session: requests.Session, toc_url: str) -> list[str]:
    """Fetch a TOC JSON and extract every facility MRF URL inside it.

    The CMS TOC schema isn't strictly defined; common shapes are:
      { "files": [{"url": "...", "filename": "..."}, ...] }
      { "reporting_entity_name": "...", "in_network_files": [{"location": "..."}] }
      [ {"url": "..."}, {"url": "..."} ]

    We accept any of these by walking the JSON tree and collecting any
    string value under a key named url/location/href/file_url.
    """
    resp, body = _get_with_ua_fallback(session, toc_url, GET_TIMEOUT)
    if resp is None or resp.status_code != 200 or body is None:
        return []
    try:
        data = json.loads(body)
    except (ValueError, json.JSONDecodeError):
        return []

    urls: list[str] = []
    _URL_KEYS = ("url", "location", "href", "file_url", "mrf_url")

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if k.lower() in _URL_KEYS and isinstance(v, str):
                    absolute = _resolve_url(toc_url, v)
                    if absolute:
                        urls.append(absolute)
                else:
                    walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    # Dedup while preserving order.
    seen: set[str] = set()
    result = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            result.append(u)
    return result


# ---------------------------------------------------------------------------
# Per-hospital crawler
# ---------------------------------------------------------------------------


def _file_format_from_url(url: str) -> str:
    lower = url.lower()
    if lower.endswith(".csv") or lower.endswith(".csv.gz"):
        return "csv"
    if lower.endswith(".json") or lower.endswith(".json.gz"):
        return "json"
    if lower.endswith(".xml") or lower.endswith(".xml.gz"):
        return "xml"
    if lower.endswith(".xlsx"):
        return "xlsx"
    if lower.endswith(".zip"):
        return "zip"
    return "unknown"


def _validate_mrf_url(
    session: requests.Session, url: str
) -> tuple[bool, str | None, int | None]:
    """HEAD-check a candidate MRF URL.

    A URL is a valid MRF candidate ONLY if BOTH:
      1. URL shape says it's an MRF file (CMS filename pattern OR a real
         MRF extension on the path component).
      2. Server returns 200 + a non-HTML Content-Type (or no Content-Type
         at all — some CDNs omit it; we trust the URL shape in that case).

    The HTML rejection is the 2026-05-04 incident fix: previously HTML
    responses were accepted "and let the parser decide", which let 5
    Sutter landing pages get classified as MRF URLs and MERGEd into
    hospital_directory.

    Returns (ok, content_type, size_bytes).
    """
    # Gate 1: URL must look like an MRF file. This filters out landing pages
    # before we even make a network call.
    url_path_lower = url.lower().split("?", 1)[0]
    looks_like_file = (
        _CMS_FILENAME_RE.search(url_path_lower) is not None
        or url_path_lower.endswith((
            ".csv", ".json", ".xml", ".xlsx",
            ".csv.gz", ".json.gz", ".zip", ".xml.gz", ".gzip",
        ))
    )
    if not looks_like_file:
        return False, None, None

    # Gate 2: HEAD probe — 200 + non-HTML Content-Type.
    status, ct, size = _head_with_ua_fallback(session, url)
    if status is None or status >= 400:
        return False, ct, size

    # Reject HTML responses outright. If a server insists on serving an MRF
    # file as text/html (we've seen it on a few CDNs that auto-detect by
    # extension only) we'd rather miss it than admit landing pages.
    if ct and ct.lower().startswith(("text/html", "application/xhtml")):
        return False, ct, size

    if ct is None:
        # No Content-Type — trust the URL extension.
        return True, ct, size

    ct_lower = ct.lower()
    for ok_ct in _OK_CONTENT_TYPES:
        if ct_lower.startswith(ok_ct):
            return True, ct, size
    # Unknown CT — accept only because Gate 1 already verified the URL
    # extension. The scraper's content-sniff guard provides a final check.
    return True, ct, size


def _scan_page_for_urls(
    session: requests.Session,
    base_url: str,
    html: str,
    found_urls: dict[str, str],
    toc_seen: set[str],
    discovery_method: str,
) -> None:
    """Run all extraction strategies against one fetched page.

    Mutates `found_urls` in place. Each newly-discovered URL is tagged with
    the supplied `discovery_method` so we can attribute hit-rate by source
    (path_heuristic, html_link, toc_expansion, system_listing,
    homepage_keyword_follow). Existing entries are not overwritten — first
    method wins, which keeps system_listing winning over later html_link
    finds for the same URL.
    """
    # Direct filename match on the URL itself (sometimes the path heuristic
    # IS the MRF URL).
    if _CMS_FILENAME_RE.search(base_url):
        found_urls.setdefault(base_url, discovery_method)

    # HTML link extraction (CMS filename regex + keyword anchor).
    for link in _extract_links_from_html(html, base_url):
        found_urls.setdefault(link, discovery_method)

    # Hospital-system Table-of-Contents JSON expansion.
    toc = _find_toc_url(html, base_url)
    if toc and toc not in toc_seen:
        toc_seen.add(toc)
        for facility_url in _expand_toc(session, toc):
            found_urls.setdefault(facility_url, "toc_expansion")


def _follow_keyword_anchors(
    session: requests.Session, html: str, base_url: str, max_followups: int = 5,
) -> list[tuple[str, str]]:
    """Find anchors whose text/href matches `_KEYWORD_RE` and return their
    absolute URLs. Caller decides whether to fetch.

    Returns a list of (absolute_url, anchor_text). De-duplicated. Capped at
    `max_followups` entries to bound the depth-1 fan-out per page (Sutter
    has dozens of nav anchors; we don't need all of them — typically the
    first 3-5 unique destinations are enough to find the cost-transparency
    page).
    """
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for match in re.finditer(
        r'<a\s+[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        html, re.IGNORECASE | re.DOTALL,
    ):
        href, anchor_text = match.group(1), match.group(2)
        clean_text = re.sub(r"<[^>]+>", "", anchor_text).strip()
        if not _KEYWORD_RE.search(clean_text) and not _KEYWORD_RE.search(href):
            continue
        absolute = _resolve_url(base_url, href)
        if not absolute or absolute in seen:
            continue
        # Skip direct file links (those are MRF candidates already extracted
        # by _scan_page_for_urls — no point fetching them as HTML).
        if absolute.lower().endswith((".csv", ".json", ".xml", ".xlsx",
                                      ".csv.gz", ".json.gz", ".zip")):
            continue
        seen.add(absolute)
        out.append((absolute, clean_text))
        if len(out) >= max_followups:
            break
    return out


def _crawl_hospital(hospital: dict[str, Any]) -> list[DiscoveredMrf]:
    """Discover MRF URLs for one hospital. Returns 0-or-more DiscoveredMrf rows.

    2026-05-04 rewrite: removed all hardcoded system→path mappings. Pure
    heuristic discovery, depth-2 generic follow:

      (1) Homepage + every PATH_HEURISTICS path (one GET each, scan HTML).
      (2) From every fetched HTML page, follow up to MAX_FOLLOWUPS_PER_PAGE
          anchors whose text/href matches _KEYWORD_RE. Recursively up to
          MAX_FOLLOW_DEPTH levels deep. Same-host only.
      (3) HEAD-validate every candidate URL. Validation is strict — URL
          must look like an MRF file AND server must return non-HTML.

    The depth-2 follow is what unblocks Sutter-style sites: the homepage
    links to a "Cost Transparency" landing page (depth 1) which links to
    the actual /-/media/Project/.../standardcharges.csv files (depth 2).
    """
    website = (hospital.get("hospital_website") or "").strip()
    label = hospital.get("hospital_name") or hospital.get("ccn") or "?"
    if not website:
        return []

    website = website.rstrip("/")
    parsed = urllib.parse.urlparse(website)
    if parsed.scheme not in ("http", "https"):
        return []
    base_host = parsed.netloc.lower()

    found_urls: dict[str, str] = {}  # url -> discovery_method
    toc_seen: set[str] = set()
    visited_pages: set[str] = set()

    def _scan(probe_url: str, method: str, depth: int) -> None:
        """Fetch `probe_url`, run extractors, recurse depth-N follow.

        Same-host only — never follows cross-domain links. Bounded by
        `visited_pages` (no loops) and `MAX_FOLLOW_DEPTH`.
        """
        if probe_url in visited_pages:
            return
        if _host_of(probe_url) != base_host:
            # Stay on the hospital's own domain. CDN links that resolve
            # off-host (e.g. `cdn.somecdn.com/.../charges.csv`) are still
            # valid MRF candidates and are picked up by the URL extractor;
            # what we don't want is to crawl off-host LANDING pages.
            return
        visited_pages.add(probe_url)
        resp, body = _get_with_ua_fallback(session, probe_url, GET_TIMEOUT)
        if resp is None or resp.status_code != 200 or body is None:
            return
        html = body
        _scan_page_for_urls(session, probe_url, html, found_urls, toc_seen, method)

        if depth < MAX_FOLLOW_DEPTH:
            for follow_url, _anchor_text in _follow_keyword_anchors(
                session, html, probe_url, max_followups=MAX_FOLLOWUPS_PER_PAGE,
            ):
                _scan(follow_url, "depth_follow", depth + 1)

    with _http_session() as session:
        # ---- (1) Homepage ----
        _scan(website, "homepage", depth=0)

        # ---- (2) Path heuristics (every entry, aggregating) ----
        # A hospital might 200 on /charges (generic page, no MRF) AND on
        # /standard-charges (the real cost page) — scan both.
        for path in PATH_HEURISTICS:
            probe = f"{parsed.scheme}://{parsed.netloc}{path}"
            _scan(probe, "path_heuristic", depth=0)

        # ---- (3) HEAD-validate every candidate ----
        validated: list[DiscoveredMrf] = []
        for url, method in found_urls.items():
            ok, ct, size = _validate_mrf_url(session, url)
            if not ok:
                continue
            validated.append(DiscoveredMrf(
                ccn=hospital.get("ccn") or "",
                hospital_npi=hospital.get("hospital_npi"),
                hospital_name=hospital.get("hospital_name") or "",
                state=hospital.get("state"),
                mrf_url=url,
                discovery_method=method,
                file_format=_file_format_from_url(url),
                content_type=ct,
                file_size_bytes=size,
            ))

    if validated:
        logger.info(
            "[%s] %d MRF URL(s) discovered (methods: %s)",
            label, len(validated),
            ",".join(sorted({d.discovery_method for d in validated})),
        )
    else:
        logger.debug("[%s] no MRF URL found", label)
    return validated


# ---------------------------------------------------------------------------
# Persistence — write to checkpoint AND merge into hospital_directory
# ---------------------------------------------------------------------------


def _persist_results(  # noqa: C901
    bq: bigquery.Client,
    project: str,
    dataset: str,
    discovered: list[DiscoveredMrf],
    failed_ccns: list[str],
    run_id: str,
) -> None:
    """Update mrf_discovery_checkpoint and MERGE into hospital_directory.

    Round 2 hardening: every BigQuery operation logs progress markers so
    a partial failure points at the specific step that died. Caller is
    responsible for catching exceptions and deciding retry policy.

    Successful hospitals get:
      checkpoint.validated_mrf_urls = JSON array of URLs (string)
      checkpoint.mrf_discovery_method = the most authoritative method
      checkpoint.mrf_file_format = first URL's format
      checkpoint.mrf_validated_at = NOW()
      checkpoint.crawl_complete_at = NOW()

    Failed hospitals (no MRF found) get:
      checkpoint.error_stage = 'stage4_no_mrf_found'
      checkpoint.crawl_complete_at = NOW() (so we don't retry every run)

    Discovered URLs are then MERGEd into hospital_directory so the scraper
    picks them up on its next run. One row per (hospital, mrf_url) pair —
    a hospital with N URLs (e.g. system TOC fan-out) gets N rows.
    """
    checkpoint_table = f"{project}.{dataset}.mrf_discovery_checkpoint"
    directory_table = f"{project}.{dataset}.hospital_directory"

    # ---- 1. Per-hospital checkpoint update ----
    by_ccn: dict[str, list[DiscoveredMrf]] = {}
    for d in discovered:
        if d.ccn:
            by_ccn.setdefault(d.ccn, []).append(d)

    rows_to_update: list[dict[str, Any]] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for ccn, urls in by_ccn.items():
        # Most authoritative method preference: html_link > toc_expansion > path_heuristic.
        method_priority = {"html_link": 0, "toc_expansion": 1, "path_heuristic": 2}
        primary_method = sorted(
            (u.discovery_method for u in urls),
            key=lambda m: method_priority.get(m, 99),
        )[0]
        rows_to_update.append({
            "ccn": ccn,
            "validated_mrf_urls": json.dumps([u.mrf_url for u in urls]),
            "mrf_discovery_method": primary_method,
            "mrf_file_format": urls[0].file_format,
            "mrf_validated_at": now_iso,
            "crawl_complete_at": now_iso,
            "error_stage": None,
        })

    for ccn in failed_ccns:
        rows_to_update.append({
            "ccn": ccn,
            "validated_mrf_urls": None,
            "mrf_discovery_method": None,
            "mrf_file_format": None,
            "mrf_validated_at": None,
            "crawl_complete_at": now_iso,
            "error_stage": "stage4_no_mrf_found",
        })

    # Use a load job + MERGE for streaming-buffer safety (same approach as
    # Phase 4 archive_index).
    if rows_to_update:
        logger.info(
            "_persist_results: starting checkpoint update (%d rows)",
            len(rows_to_update),
        )
        # Run-id sanitization: BigQuery table names allow [a-zA-Z0-9_].
        # H5 fix (2026-05-04): the table name no longer starts with an
        # underscore. BQ allows leading underscores in DML CREATE statements
        # but treats `_*` as anonymous/temporary in default listings, so
        # debugging a stuck staging table required `bq ls --all`. Naming it
        # `stage4_staging_*` keeps the table visible in the standard listings
        # while still being scoped per-run via the run_id suffix.
        # BQ table renames are a free metadata operation
        # (https://cloud.google.com/bigquery/docs/managing-tables#renametable).
        staging_table = f"{project}.{dataset}.stage4_staging_{run_id.replace('-', '_')}"
        load_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            schema=[
                bigquery.SchemaField("ccn", "STRING"),
                bigquery.SchemaField("validated_mrf_urls", "STRING"),
                bigquery.SchemaField("mrf_discovery_method", "STRING"),
                bigquery.SchemaField("mrf_file_format", "STRING"),
                bigquery.SchemaField("mrf_validated_at", "TIMESTAMP"),
                bigquery.SchemaField("crawl_complete_at", "TIMESTAMP"),
                bigquery.SchemaField("error_stage", "STRING"),
            ],
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            create_disposition=bigquery.CreateDisposition.CREATE_IF_NEEDED,
        )
        ndjson = "\n".join(json.dumps(r) for r in rows_to_update)
        import io
        bq.load_table_from_file(
            io.StringIO(ndjson), staging_table, job_config=load_config,
        ).result()

        merge_sql = f"""
            MERGE `{checkpoint_table}` T
            USING `{staging_table}` S
            ON T.ccn = S.ccn AND T.run_id = @run_id
            WHEN MATCHED THEN UPDATE SET
              validated_mrf_urls = S.validated_mrf_urls,
              mrf_discovery_method = S.mrf_discovery_method,
              mrf_file_format = S.mrf_file_format,
              mrf_validated_at = S.mrf_validated_at,
              crawl_complete_at = S.crawl_complete_at,
              error_stage = S.error_stage,
              last_updated_at = CURRENT_TIMESTAMP()
        """
        # M13: assert + log affected row count via bq_checkpoint helper.
        bq_checkpoint.run_dml_with_count(
            bq, merge_sql,
            job_config=bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("run_id", "STRING", run_id),
            ]),
            label="Stage 4 checkpoint MERGE",
            logger=logger,
        )
        bq.delete_table(staging_table, not_found_ok=True)
        logger.info(
            "_persist_results: checkpoint MERGE done (rows=%d success=%d failed=%d)",
            len(rows_to_update), len(by_ccn), len(failed_ccns),
        )

    # ---- 2. MERGE discovered URLs into hospital_directory ----
    if not discovered:
        logger.info("_persist_results: no discovered URLs — skipping hospital_directory merge")
        return
    logger.info("_persist_results: starting hospital_directory MERGE (%d URLs)", len(discovered))

    directory_rows = [
        {
            "hospital_npi": d.hospital_npi,
            "ccn": d.ccn,
            "hospital_name": d.hospital_name,
            "state": d.state,
            "mrf_url": d.mrf_url,
            "last_modified": None,  # first scrape will populate this
        }
        for d in discovered
    ]
    staging_dir_table = f"{project}.{dataset}._stage4_dir_staging_{run_id.replace('-', '_')}"
    dir_load_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        schema=[
            bigquery.SchemaField("hospital_npi", "STRING"),
            bigquery.SchemaField("ccn", "STRING"),
            bigquery.SchemaField("hospital_name", "STRING"),
            bigquery.SchemaField("state", "STRING"),
            bigquery.SchemaField("mrf_url", "STRING"),
            bigquery.SchemaField("last_modified", "STRING"),
        ],
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        create_disposition=bigquery.CreateDisposition.CREATE_IF_NEEDED,
    )
    import io
    dir_ndjson = "\n".join(json.dumps(r) for r in directory_rows)
    bq.load_table_from_file(
        io.StringIO(dir_ndjson), staging_dir_table, job_config=dir_load_config,
    ).result()

    # MERGE: insert if (ccn, mrf_url) is new; update mrf_url stays as-is.
    # We key on (ccn, mrf_url) instead of just ccn because hospital systems
    # may have N URLs per CCN (TOC fan-out). Existing rows with the same
    # (ccn, mrf_url) are no-ops; new combinations get inserted.
    dir_merge_sql = f"""
        MERGE `{directory_table}` T
        USING `{staging_dir_table}` S
        ON COALESCE(T.ccn, '') = COALESCE(S.ccn, '')
           AND T.mrf_url = S.mrf_url
        WHEN NOT MATCHED THEN
          INSERT (hospital_npi, ccn, hospital_name, state, mrf_url, last_modified)
          VALUES (S.hospital_npi, S.ccn, S.hospital_name, S.state, S.mrf_url, S.last_modified)
        WHEN MATCHED AND T.hospital_npi IS NULL AND S.hospital_npi IS NOT NULL THEN
          UPDATE SET hospital_npi = S.hospital_npi
    """
    # M13: assert + log affected row count.
    bq_checkpoint.run_dml_with_count(
        bq, dir_merge_sql,
        label="Stage 4 hospital_directory MERGE",
        logger=logger,
    )
    bq.delete_table(staging_dir_table, not_found_ok=True)
    logger.info(
        "MERGEd %d (hospital, mrf_url) pairs into hospital_directory",
        len(directory_rows),
    )


# ---------------------------------------------------------------------------
# Stage entry-point
# ---------------------------------------------------------------------------


def _query_pending(
    bq: bigquery.Client, project: str, dataset: str, run_id: str,
) -> list[dict[str, Any]]:
    """Pull every hospital that has a website but no validated_mrf_urls yet.

    Idempotent re-runs: this query returns the empty set after a successful
    run because every processed hospital has either validated_mrf_urls
    populated OR error_stage='stage4_no_mrf_found'.
    """
    sql = f"""
        SELECT ccn, hospital_npi, hospital_name, state, hospital_website
        FROM `{project}.{dataset}.mrf_discovery_checkpoint`
        WHERE run_id = @run_id
          AND hospital_website IS NOT NULL
          AND TRIM(hospital_website) != ''
          AND validated_mrf_urls IS NULL
          AND (error_stage IS NULL OR error_stage = 'stage4_no_mrf_found')
        ORDER BY ccn
    """
    return [
        dict(row)
        for row in bq.query(
            sql,
            job_config=bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("run_id", "STRING", run_id),
            ]),
        ).result()
    ]


def reset_broken_validated_urls(
    bq: bigquery.Client, project: str, dataset: str, run_id: str,
) -> int:
    """Clear validated_mrf_urls for rows whose URLs don't look like real MRFs.

    Targets the cohort caused by the pre-2026-05-04 Stage 4 bug where
    landing pages (Sutter Health is the canonical example: 5 sub-pages of
    `/billing-insurance/costs-and-charges/` got recorded as "validated MRF
    URLs"). The fix: any checkpoint row whose validated_mrf_urls JSON
    array contains ZERO entries matching the CMS filename pattern
    `\\d{6,12}_..._standardcharges.{csv,json,xml}` is reset to pending so
    the rewritten Stage 4 (depth-2 generic follow + strict validation) can
    re-discover the real URLs.

    Returns the number of rows reset.
    """
    sql = f"""
        UPDATE `{project}.{dataset}.mrf_discovery_checkpoint`
        SET validated_mrf_urls = NULL,
            mrf_discovery_method = NULL,
            mrf_file_format = NULL,
            mrf_validated_at = NULL,
            crawl_complete_at = NULL,
            error_stage = NULL
        WHERE run_id = @run_id
          AND validated_mrf_urls IS NOT NULL
          AND NOT REGEXP_CONTAINS(
            validated_mrf_urls,
            r'\\d{{6,12}}[_\\-].+?[_\\-]?standard[_\\- ]?charges'
          )
    """
    job = bq.query(
        sql,
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("run_id", "STRING", run_id),
        ]),
    )
    job.result()
    n = int(job.num_dml_affected_rows or 0)
    logger.info("reset_broken_validated_urls: cleared %d checkpoint rows for re-crawl", n)
    return n


def run(
    bq: bigquery.Client,
    project: str,
    run_id: str,
    dataset: str = bq_checkpoint.DEFAULT_DATASET,
    max_hospitals: int | None = None,
    workers: int = MAX_WORKERS,
    flush_every: int = 1000,
) -> dict[str, int]:
    """Run Stage 4 across all pending hospitals. Returns a stats dict.

    2026-04-30 round 2 hardening: the crawler flushes partial results to
    BigQuery every `flush_every` hospitals so a mid-run crash only loses
    the last batch. The previous "all-or-nothing" persistence pattern lost
    5,700 hospitals' worth of crawl work when the container died during
    the final _persist_results call (execution w6wmc). Periodic flushes
    convert that failure mode into a survivable resume.

    Tracebacks from _persist_results are now caught and logged via
    logger.exception so Cloud Logging captures them — the previous failure
    showed only an empty `{}` ERROR entry because the unhandled exception
    went to stderr which Cloud Run didn't ship before container shutdown.
    """
    pending = _query_pending(bq, project, dataset, run_id)
    if max_hospitals is not None:
        pending = pending[:max_hospitals]
    if not pending:
        logger.info("Stage 4: no pending hospitals — nothing to do.")
        return {"pending": 0, "discovered": 0, "failed": 0}

    logger.info(
        "Stage 4: crawling %d hospitals with %d workers (flushing every %d)",
        len(pending), workers, flush_every,
    )

    discovered_all: list[DiscoveredMrf] = []
    failed_ccns: list[str] = []
    flush_buffer_discovered: list[DiscoveredMrf] = []
    flush_buffer_failed: list[str] = []
    total_flushed = 0
    # S3 fix (2026-05-04): track every flush failure so the run summary at
    # the end can raise if any persists never landed. Pre-fix, _flush_batch
    # caught + logged every Exception and kept buffering for retry; if the
    # final flush also failed the run still reported "Stage 4 complete"
    # with total_flushed understated. Cloud Run alerts didn't fire because
    # the exit code was 0. Now: any non-empty flush_failures at end-of-run
    # raises RuntimeError → exit 1 → Cloud Run alert.
    flush_failures: list[tuple[str, str]] = []  # [(reason, exception_class_name), ...]

    def _flush_batch(reason: str) -> None:
        """Persist whatever's in the flush buffers, then clear them."""
        nonlocal total_flushed
        if not flush_buffer_discovered and not flush_buffer_failed:
            return
        try:
            _persist_results(
                bq, project, dataset,
                flush_buffer_discovered, flush_buffer_failed, run_id,
            )
            total_flushed += len(flush_buffer_discovered) + len(flush_buffer_failed)
            logger.info(
                "Flushed batch (%s): %d discovered + %d failed = %d total persisted so far",
                reason, len(flush_buffer_discovered), len(flush_buffer_failed),
                total_flushed,
            )
            flush_buffer_discovered.clear()
            flush_buffer_failed.clear()
        except Exception as exc:
            # Don't let a transient BQ error kill the whole crawl mid-loop.
            # Log the full traceback (Cloud Run captures it) and keep the
            # buffer for retry on the next flush. The end-of-run summary
            # raises if any failure was recorded — converting silent
            # success-with-zero-rows-persisted into a non-zero exit.
            logger.exception(
                "Persist flush FAILED (%s) — keeping buffer for retry. "
                "buffer sizes: discovered=%d failed=%d",
                reason, len(flush_buffer_discovered), len(flush_buffer_failed),
            )
            flush_failures.append((reason, type(exc).__name__))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_crawl_hospital, h): h for h in pending}
        completed = 0
        transient_crashes = 0
        permanent_crashes = 0
        for fut in as_completed(futures):
            hospital = futures[fut]
            ccn = hospital.get("ccn") or ""
            result: list[DiscoveredMrf] = []
            crashed_transient = False
            try:
                result = fut.result()
            except _TRANSIENT_CRAWL_EXCEPTIONS:
                # S4 fix: transient — log full traceback, leave the
                # hospital's checkpoint row unchanged so the next run
                # picks it back up. NOT added to failed_ccns.
                logger.exception(
                    "[%s] transient crawler error — leaving hospital unmarked for retry next run",
                    ccn,
                )
                crashed_transient = True
                transient_crashes += 1
            except Exception:
                # Permanent — log full traceback (logger.exception, not warning,
                # so the trace appears in Cloud Logging) and route to failed_ccns
                # via the empty-result path below.
                logger.exception("[%s] crawler crashed (permanent failure)", ccn)
                permanent_crashes += 1
            if result:
                discovered_all.extend(result)
                flush_buffer_discovered.extend(result)
            elif not crashed_transient:
                # Empty result OR permanent crash — mark failed so future runs
                # don't repeat the same crawl. Transient crashes skip this so
                # the hospital is retried next quarterly run.
                failed_ccns.append(ccn)
                flush_buffer_failed.append(ccn)
            completed += 1
            if completed % 500 == 0:
                logger.info(
                    "Stage 4 progress: %d/%d (%d discovered URLs so far)",
                    completed, len(pending), len(discovered_all),
                )
            if completed % flush_every == 0:
                _flush_batch(reason=f"every-{flush_every} at completed={completed}")

    logger.info(
        "Stage 4 crawl done: %d hospitals → %d MRF URLs "
        "(%d hospitals had ≥1 URL, %d permanent crashes, %d transient crashes left for retry)",
        len(pending),
        len(discovered_all),
        len({d.ccn for d in discovered_all}),
        permanent_crashes,
        transient_crashes,
    )

    # Final flush — anything still in the buffers from the last partial batch.
    _flush_batch(reason="final")

    # S3 fix: surface any persist failures via non-zero exit.
    _assert_flush_complete(
        len(flush_buffer_discovered),
        len(flush_buffer_failed),
        flush_failures,
    )

    return {
        "pending": len(pending),
        "discovered": len(discovered_all),
        "failed": len(failed_ccns),
        "hospitals_with_urls": len({d.ccn for d in discovered_all}),
        "total_flushed": total_flushed,
        "flush_failures": len(flush_failures),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--project", default="clarobill-prd")
    parser.add_argument("--dataset", default=bq_checkpoint.DEFAULT_DATASET)
    parser.add_argument("--run-id", required=True,
                        help="Discovery run ID — must match Stage 1's run_id")
    parser.add_argument("--max-hospitals", type=int, default=None,
                        help="Process only first N hospitals (testing)")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS)
    parser.add_argument(
        "--force-recrawl-broken",
        action="store_true",
        help=(
            "Before crawling, clear validated_mrf_urls for any checkpoint "
            "row whose URLs don't match the CMS filename pattern "
            "(\\d{6,12}_..._standardcharges...). Used to recover from the "
            "pre-2026-05-04 Stage 4 bug that classified landing pages as "
            "MRF URLs (Sutter, Providence, Banner, etc.). Idempotent."
        ),
    )
    args = parser.parse_args(argv)

    bq = bigquery.Client(project=args.project)

    if args.force_recrawl_broken:
        n = reset_broken_validated_urls(bq, args.project, args.dataset, args.run_id)
        logger.info("Pre-run reset: %d rows flipped back to pending", n)

    stats = run(
        bq, args.project, args.run_id,
        dataset=args.dataset,
        max_hospitals=args.max_hospitals,
        workers=args.workers,
    )
    logger.info("Stage 4 stats: %s", stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
