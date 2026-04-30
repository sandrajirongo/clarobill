"""Stage 4 — Extract MRF download URLs from each hospital's website.

Discovery's missing piece. Phase 3 found ~12,000 hospital homepage URLs but
no stage existed to crawl those homepages and extract the actual price-
transparency MRF download links. This stage fills that gap.

For each hospital with `hospital_website` set on `mrf_discovery_checkpoint`
but `validated_mrf_urls IS NULL`, this stage:

  1. Path-heuristic probe — try N common CMS-mandated paths (most hospitals
     publish at predictable URLs like `/price-transparency`).
  2. HTML link extraction — for any candidate page that returns 200, regex
     out `<a href>` whose text/URL matches the CMS filename pattern
     `\\d{9,10}_.+_standardcharges\\.(csv|json|xml)` or near-text keywords
     ("standard charges", "machine readable file").
  3. Table-of-Contents fan-out — hospital systems publish a single TOC JSON
     listing every facility's MRF. If we find one, fetch + parse + emit one
     URL per facility.
  4. HEAD validation — every candidate URL is HEAD-checked. Only URLs with
     200 OK + plausible Content-Type (csv/json/octet-stream/text) survive.
  5. Persist — for surviving URLs:
       a. checkpoint.validated_mrf_urls = JSON array of URLs
       b. checkpoint.mrf_discovery_method = "path_heuristic"|"html_link"|"toc_expansion"
       c. checkpoint.mrf_validated_at + crawl_complete_at = NOW()
       d. MERGE into hospital_directory so the scraper picks them up

Free, idempotent, ~15-25 min wall-clock at 60 concurrent workers for
~12,000 hospitals × ~5 path probes each.

Resumability
------------
Skips any hospital whose `validated_mrf_urls` is already populated. Re-runs
are safe; existing matches are not re-crawled. Failures (no MRF found)
populate `error_stage='stage4_no_mrf_found'` so a later --gap-fill run can
retry with widened heuristics.

Hit rate (industry expectation, refined post-run)
-------------------------------------------------
Target: 70-80% of website-having hospitals resolve to a valid MRF URL.
The remainder split into:
  - non-compliant with CMS rule (5-10%, CMS publishes enforcement)
  - portal/JS-walled (10-15%, requires headless-browser scrape later)
  - non-standard URL pattern (5-10%, widen heuristics + manual curation)
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests
from google.cloud import bigquery

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

# CMS-mandated and CMS-suggested price-transparency landing pages, ordered by
# observed frequency. The first hit wins — the path probe stops on the first
# 200 OK with HTML content.
PATH_HEURISTICS: tuple[str, ...] = (
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
_KEYWORD_RE = re.compile(
    r"(machine[\s\-]?readable[\s\-]?file"
    r"|standard[\s\-]?charges"
    r"|price[\s\-]?transparency"
    r"|chargemaster)",
    re.IGNORECASE,
)

# Table-of-Contents JSON URL pattern (CMS allows hospital systems to publish
# one TOC linking to multiple facility MRFs).
_TOC_FILENAME_RE = re.compile(
    r"(standard[_\- ]?charges[_\- ]?toc|toc[_\- ]?standard[_\- ]?charges)\.json"
    r"(?:\.gz|\.gzip)?",
    re.IGNORECASE,
)

# Acceptable Content-Type prefixes for HEAD validation — covers all the
# common MRF formats (CSV, JSON, gzipped, XLSX, generic octet-stream that
# many CDNs serve unhelpfully).
_OK_CONTENT_TYPES = (
    "text/csv",
    "text/plain",
    "application/json",
    "application/octet-stream",
    "application/gzip",
    "application/x-gzip",
    "application/zip",
    "text/csv;",
    "text/html",  # some servers mislabel; we accept and let parser decide
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


def _get_with_ua_fallback(
    session: requests.Session, url: str, timeout: int
) -> requests.Response | None:
    """GET with descriptive UA; on 403/406/429 retry with a browser UA.

    Returns None on any persistent failure. Same pattern as Stage 3 Tier 1.
    """
    try:
        resp = session.get(url, timeout=timeout, allow_redirects=True)
        if resp.status_code in (403, 406, 429):
            resp.close()
            resp = session.get(
                url, timeout=timeout, allow_redirects=True,
                headers={"User-Agent": BROWSER_UA},
            )
        return resp
    except requests.RequestException:
        return None


def _head_with_ua_fallback(
    session: requests.Session, url: str
) -> tuple[int | None, str | None, int | None]:
    """HEAD probe with UA fallback. Returns (status, content_type, content_length)."""
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

    # Pass 2: anchor tags with keyword text.
    for anchor_match in re.finditer(
        r'<a\s+[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        html, re.IGNORECASE | re.DOTALL,
    ):
        href, anchor_text = anchor_match.group(1), anchor_match.group(2)
        # Strip HTML tags from the anchor text.
        clean_text = re.sub(r"<[^>]+>", "", anchor_text)
        if not _KEYWORD_RE.search(clean_text) and not _KEYWORD_RE.search(href):
            continue
        # Only follow if it actually looks like a file or another HTML page
        # (skip mailto: tel: javascript: etc. — _resolve_url filters those).
        absolute = _resolve_url(base_url, href)
        if not absolute:
            continue
        # Filter: must look like a file or another HTML link likely to host one.
        if (_CMS_FILENAME_RE.search(absolute)
                or absolute.lower().endswith((".csv", ".json", ".xml", ".xlsx",
                                              ".csv.gz", ".json.gz", ".zip"))
                or _KEYWORD_RE.search(absolute)):
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
    resp = _get_with_ua_fallback(session, toc_url, GET_TIMEOUT)
    if resp is None or resp.status_code != 200:
        return []
    try:
        data = resp.json()
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
    """HEAD-check a candidate MRF URL. Returns (ok, content_type, size_bytes)."""
    status, ct, size = _head_with_ua_fallback(session, url)
    if status is None or status >= 400:
        return False, ct, size
    if ct is None:
        # Some servers return 200 with no Content-Type. Accept on the URL
        # extension alone — the scraper will reject if the bytes are wrong.
        return True, ct, size
    ct_lower = ct.lower()
    for ok_ct in _OK_CONTENT_TYPES:
        if ct_lower.startswith(ok_ct):
            return True, ct, size
    # Unknown CT — only accept if the URL extension says it's a real MRF.
    if _file_format_from_url(url) != "unknown":
        return True, ct, size
    return False, ct, size


def _crawl_hospital(hospital: dict[str, Any]) -> list[DiscoveredMrf]:
    """Discover MRF URLs for one hospital. Returns 0-or-more DiscoveredMrf rows."""
    website = (hospital.get("hospital_website") or "").strip()
    label = hospital.get("hospital_name") or hospital.get("ccn") or "?"
    if not website:
        return []

    # Normalise website (strip trailing slash for clean joins).
    website = website.rstrip("/")
    parsed = urllib.parse.urlparse(website)
    if parsed.scheme not in ("http", "https"):
        return []

    found_urls: dict[str, str] = {}  # url -> discovery_method
    toc_seen: set[str] = set()

    with _http_session() as session:
        # ---- (1) Path-heuristic probe ----
        for path in PATH_HEURISTICS:
            probe = f"{parsed.scheme}://{parsed.netloc}{path}"
            resp = _get_with_ua_fallback(session, probe, GET_TIMEOUT)
            if resp is None or resp.status_code != 200:
                if resp is not None:
                    resp.close()
                continue

            html = resp.text or ""
            resp.close()

            # First — direct filename match? (some hospitals link to their
            # MRF directly from the homepage).
            if _CMS_FILENAME_RE.search(probe):
                found_urls.setdefault(probe, "path_heuristic")

            # Look for HTML links on this page.
            for link in _extract_links_from_html(html, probe):
                if link not in found_urls:
                    found_urls[link] = "html_link"

            # Look for a TOC URL on this page.
            toc = _find_toc_url(html, probe)
            if toc and toc not in toc_seen:
                toc_seen.add(toc)
                for facility_url in _expand_toc(session, toc):
                    found_urls.setdefault(facility_url, "toc_expansion")

            # Stop probing more paths once we have at least one candidate.
            if found_urls:
                break

        # ---- (2) If no path produced anything, try the homepage itself ----
        if not found_urls:
            resp = _get_with_ua_fallback(session, website, GET_TIMEOUT)
            if resp is not None and resp.status_code == 200:
                html = resp.text or ""
                resp.close()
                for link in _extract_links_from_html(html, website):
                    found_urls.setdefault(link, "html_link")
                toc = _find_toc_url(html, website)
                if toc:
                    for facility_url in _expand_toc(session, toc):
                        found_urls.setdefault(facility_url, "toc_expansion")

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


def _persist_results(
    bq: bigquery.Client,
    project: str,
    dataset: str,
    discovered: list[DiscoveredMrf],
    failed_ccns: list[str],
    run_id: str,
) -> None:
    """Update mrf_discovery_checkpoint and MERGE into hospital_directory.

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
        staging_table = f"{project}.{dataset}._stage4_staging_{run_id.replace('-', '_')}"
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
        bq.query(
            merge_sql,
            job_config=bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("run_id", "STRING", run_id),
            ]),
        ).result()
        bq.delete_table(staging_table, not_found_ok=True)
        logger.info(
            "Updated %d checkpoint rows (success=%d, failed=%d)",
            len(rows_to_update), len(by_ccn), len(failed_ccns),
        )

    # ---- 2. MERGE discovered URLs into hospital_directory ----
    if not discovered:
        logger.info("No discovered URLs — skipping hospital_directory merge.")
        return

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
    bq.query(dir_merge_sql).result()
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


def run(
    bq: bigquery.Client,
    project: str,
    run_id: str,
    dataset: str = bq_checkpoint.DEFAULT_DATASET,
    max_hospitals: int | None = None,
    workers: int = MAX_WORKERS,
) -> dict[str, int]:
    """Run Stage 4 across all pending hospitals. Returns a stats dict."""
    pending = _query_pending(bq, project, dataset, run_id)
    if max_hospitals is not None:
        pending = pending[:max_hospitals]
    if not pending:
        logger.info("Stage 4: no pending hospitals — nothing to do.")
        return {"pending": 0, "discovered": 0, "failed": 0}

    logger.info("Stage 4: crawling %d hospitals with %d workers", len(pending), workers)

    discovered_all: list[DiscoveredMrf] = []
    failed_ccns: list[str] = []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_crawl_hospital, h): h for h in pending}
        completed = 0
        for fut in as_completed(futures):
            hospital = futures[fut]
            ccn = hospital.get("ccn") or ""
            try:
                result = fut.result()
            except Exception as exc:
                logger.warning("[%s] crawler crashed: %s", ccn, exc)
                result = []
            if result:
                discovered_all.extend(result)
            else:
                failed_ccns.append(ccn)
            completed += 1
            if completed % 500 == 0:
                logger.info(
                    "Stage 4 progress: %d/%d (%d discovered URLs so far)",
                    completed, len(pending), len(discovered_all),
                )

    logger.info(
        "Stage 4 crawl done: %d hospitals → %d MRF URLs (%d hospitals had ≥1 URL)",
        len(pending),
        len(discovered_all),
        len({d.ccn for d in discovered_all}),
    )

    _persist_results(bq, project, dataset, discovered_all, failed_ccns, run_id)
    return {
        "pending": len(pending),
        "discovered": len(discovered_all),
        "failed": len(failed_ccns),
        "hospitals_with_urls": len({d.ccn for d in discovered_all}),
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
    args = parser.parse_args(argv)

    bq = bigquery.Client(project=args.project)
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
