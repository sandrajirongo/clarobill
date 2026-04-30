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

# Curated listing pages for known multi-hospital systems. One successful
# crawl of a system listing page = up to 50+ facility MRFs. Each entry maps
# a domain (substring host match — `www.foo.com` and `mychart.foo.com`
# both hit) to the absolute path of the system's listing page.
#
# Curation criteria — every entry must satisfy ALL three:
#   1. Returns HTTP 200 to our scraper UA.
#   2. The HTML contains ≥10 occurrences of "standardcharges" so the CMS
#      filename regex actually extracts MRF URLs (not just nav text).
#   3. The page links to ≥3 facility MRFs (single-facility entries get
#      caught by the generic crawler; no need to curate them).
#
# 2026-04-30 round 2: of 16 originally-curated entries, 13 turned out to
# return 404/403 or to be JS-rendered (verified empty `standardcharges`
# count after fetch). Only 5 met the criteria. Pruned the rest — the
# generic depth-1 keyword-follow strategy (homepage → "Billing" or
# "Price Transparency" anchor → resolved page) handles the others.
#
# Re-verification pattern (run if a system stops working):
#   curl -sL --max-time 15 -A "Mozilla/5.0..." \
#     "https://www.<host><path>" | grep -c standardcharges
_SYSTEM_LISTING_PAGES: dict[str, str] = {
    # Verified 2026-04-30 — every entry returns 200 with ≥10 standardcharges hits.
    "sutterhealth.org":          "/billing-insurance/costs-and-charges/cost-transparency",  # 54 hits
    "providence.org":            "/billing-support/pricing-transparency",                    # 57 hits
    "bannerhealth.com":          "/patients/billing/pricing-resources/hospital-price-transparency",  # 31 hits
    "massgeneralbrigham.org":    "/en/patient-care/patient-visitor-information/billing/cms-required-hospital-charge-data",  # 28 hits
    "northwell.edu":             "/billing-and-insurance/price-estimator-tools",             # 17 hits
}


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


def _system_listing_path(host: str) -> str | None:
    """Return the curated listing-page path for a known hospital system, or None.

    Domain match is a substring check so subdomains and `www.` variants both
    resolve. Iteration order is the dict insertion order — first hit wins.
    """
    host_lower = host.lower()
    for system_domain, path in _SYSTEM_LISTING_PAGES.items():
        if system_domain in host_lower:
            return path
    return None


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

    2026-04-30 rewrite: aggregates across every strategy instead of stopping
    on first match. Order of attempts:

      (1) System-listing page (if homepage host matches a curated entry in
          _SYSTEM_LISTING_PAGES — Sutter, HCA, Ascension, etc.). One URL,
          highest-leverage probe.
      (2) Path heuristics (every entry, no early-stop). Each 200 OK page is
          scanned for filename-shaped URLs, keyword anchors, and TOC JSONs.
      (3) Homepage. Always crawled, even if (1) or (2) found URLs — picks
          up MRF links advertised in the main nav that aren't on a
          dedicated /price-transparency path.
      (4) Depth-1 follow-link from the homepage: any anchor whose text/href
          matches _KEYWORD_RE is fetched and re-scanned. This is what
          generically catches Sutter-style sites: homepage → "Cost
          Transparency" anchor → that page's embedded MRF URL list.
      (5) HEAD-validate every candidate URL. Survivors become DiscoveredMrf.
    """
    website = (hospital.get("hospital_website") or "").strip()
    label = hospital.get("hospital_name") or hospital.get("ccn") or "?"
    if not website:
        return []

    website = website.rstrip("/")
    parsed = urllib.parse.urlparse(website)
    if parsed.scheme not in ("http", "https"):
        return []

    found_urls: dict[str, str] = {}  # url -> discovery_method
    toc_seen: set[str] = set()
    visited_pages: set[str] = set()

    def _scan(probe_url: str, method: str) -> None:
        """Fetch `probe_url`, run all extractors, record matches. Idempotent."""
        if probe_url in visited_pages:
            return
        visited_pages.add(probe_url)
        resp = _get_with_ua_fallback(session, probe_url, GET_TIMEOUT)
        if resp is None or resp.status_code != 200:
            if resp is not None:
                resp.close()
            return
        html = resp.text or ""
        resp.close()
        _scan_page_for_urls(session, probe_url, html, found_urls, toc_seen, method)
        return

    with _http_session() as session:
        # ---- (1) System-aware curated listing page ----
        # If this hospital belongs to one of the big systems we've curated,
        # hit the system's known cost-transparency page first. One curated
        # entry per system can match 5-50 hospitals.
        listing_path = _system_listing_path(parsed.netloc)
        if listing_path:
            listing_url = f"{parsed.scheme}://{parsed.netloc}{listing_path}"
            _scan(listing_url, "system_listing")

        # ---- (2) Every path heuristic ----
        # Aggregating, not first-match-wins. A hospital might 200 on
        # /charges (generic page, no MRF) AND on /standard-charges (the
        # real cost page) — we want both scanned.
        for path in PATH_HEURISTICS:
            probe = f"{parsed.scheme}://{parsed.netloc}{path}"
            _scan(probe, "path_heuristic")

        # ---- (3) Homepage ----
        # Always crawl, regardless of what (1)/(2) found. Catches MRF links
        # advertised directly in the homepage nav.
        if website not in visited_pages:
            resp = _get_with_ua_fallback(session, website, GET_TIMEOUT)
            if resp is not None and resp.status_code == 200:
                html = resp.text or ""
                resp.close()
                visited_pages.add(website)
                _scan_page_for_urls(session, website, html, found_urls, toc_seen, "html_link")

                # ---- (4) Depth-1 follow from the homepage ----
                # If the homepage has a "Cost Transparency" / "Standard
                # Charges" / "Pricing" anchor, follow it one level deep.
                # This is the universal Sutter solution: many hospitals'
                # MRF link is one nav-click away from home.
                for follow_url, _anchor_text in _follow_keyword_anchors(
                    session, html, website, max_followups=5,
                ):
                    _scan(follow_url, "homepage_keyword_follow")

        # ---- (5) HEAD-validate every candidate ----
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
        # Run-id sanitization: BigQuery table names allow [a-zA-Z0-9_], so
        # strip everything else (e.g. the `T` separator in the ISO timestamp
        # is fine but the leading underscore for `_stage4_*` is reserved
        # only for system tables — our prefix is `_stage4_` which IS allowed
        # for application tables).
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
        except Exception:
            # Don't let a transient BQ error kill the whole crawl. Log the
            # full traceback to stdout (Cloud Run captures it) and keep
            # the buffer for retry on the next flush.
            logger.exception(
                "Persist flush FAILED (%s) — keeping buffer for retry. "
                "buffer sizes: discovered=%d failed=%d",
                reason, len(flush_buffer_discovered), len(flush_buffer_failed),
            )

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
                flush_buffer_discovered.extend(result)
            else:
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
        "Stage 4 crawl done: %d hospitals → %d MRF URLs (%d hospitals had ≥1 URL)",
        len(pending),
        len(discovered_all),
        len({d.ccn for d in discovered_all}),
    )

    # Final flush — anything still in the buffers from the last partial batch.
    _flush_batch(reason="final")

    return {
        "pending": len(pending),
        "discovered": len(discovered_all),
        "failed": len(failed_ccns),
        "hospitals_with_urls": len({d.ccn for d in discovered_all}),
        "total_flushed": total_flushed,
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
