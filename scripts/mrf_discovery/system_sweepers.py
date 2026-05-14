"""System-level MRF sweepers for Stage 4.

Addresses two failure modes in the generic per-hospital crawl:

  1. Same-domain rate-limiting: large systems (Sutter Health, Ascension, etc.)
     share a single domain across 30-130 hospitals. Stage 4 hits the same
     transparency page N times concurrently and gets 429-rate-limited.
     Fix: sweep the domain ONCE, then assign URLs to hospitals by the
     hospital name embedded in each CMS-pattern filename.

  2. Off-domain hosting: Tenet Health files are at mrfs.hyvehealthcare.com,
     not on individual hospital websites. The per-hospital same-host crawl
     never reaches that domain.
     Fix: fetch the Hyve manifest page, parse the JS const-files array,
     construct direct download URLs.

  3. JS-rendered regional pages (Kaiser, CommonSpirit): MRF links only appear
     after JavaScript execution. Requires Playwright.
     Fix: sweep_kaiser_playwright / sweep_commonspirit_playwright — called from
     stage4_extract_mrf_urls.run() when a Playwright browser is available.

Usage from stage4_extract_mrf_urls.run():

    from mrf_discovery import system_sweepers
    results, resolved = system_sweepers.run(session, pending, PATH_HEURISTICS)
    if playwright_browser:
        for fn in (system_sweepers.sweep_kaiser_playwright,
                   system_sweepers.sweep_commonspirit_playwright):
            r, res = fn(playwright_browser, pending)
            results.extend(r); resolved |= res
"""

from __future__ import annotations

import difflib
import logging
import re
import urllib.parse
from dataclasses import dataclass
from typing import Any

import requests

logger = logging.getLogger(__name__)

SAME_DOMAIN_SWEEP_THRESHOLD = 3
HYVE_TENET_URL = "https://mrfs.hyvehealthcare.com/TenetHealth/"
KAISER_REGIONS = (
    "northern-california",
    "southern-california",
    "colorado",
    "georgia",
    "hawaii",
    "washington",
)
COMMONSPIRIT_PRICE_TRANSPARENCY_URL = (
    "https://www.commonspirit.org/patient-resources/price-transparency"
)

_CMS_FILENAME_RE = re.compile(
    r"\d{6,12}[_\-].+?[_\-]?standard[_\- ]?charges\.(?:csv|json|xml|xlsx)"
    r"(?:\.gz|\.gzip|\.zip)?",
    re.IGNORECASE,
)
_NAME_NOISE_RE = re.compile(r"[^a-z0-9 ]")
_MULTI_SPACE_RE = re.compile(r"\s+")
_KEYWORD_RE = re.compile(
    r"(standard[_\- ]?charges?|price[_\- ]?transparency|machine[_\- ]?readable"
    r"|hospital[_\- ]?charges?|chargemaster|shoppable|negotiated[_\- ]?rates?)",
    re.IGNORECASE,
)

_USER_AGENT = (
    "ClaroBill-MRFDiscovery/1.0 (price transparency research; contact@clarobill.com)"
)
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)
_HEAD_TIMEOUT = 10
_GET_TIMEOUT = 20
_MAX_BODY = 10 * 1024 * 1024
_NAME_MATCH_THRESHOLD = 0.65


@dataclass(frozen=True)
class SweepResult:
    """One validated MRF URL resolved to a specific hospital CCN."""

    ccn: str
    hospital_npi: str | None
    hospital_name: str
    state: str | None
    mrf_url: str
    discovery_method: str
    file_format: str


# ---------------------------------------------------------------------------
# Name normalization + fuzzy matching
# ---------------------------------------------------------------------------


def normalize_hospital_name(name: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace for fuzzy matching."""
    s = _NAME_NOISE_RE.sub(" ", name.lower())
    return _MULTI_SPACE_RE.sub(" ", s).strip()


def extract_name_from_cms_filename(url: str) -> str | None:
    """Return normalized hospital name from a CMS-pattern filename URL.

    CMS convention: {EIN}[_-]{name}_standardcharges.{ext}
    Some hospitals also embed NPI: {EIN}-{NPI}_{name}_standardcharges.{ext}
    """
    path = url.split("?")[0].rsplit("/", 1)[-1]
    m = re.match(
        r"\d{6,12}[_\-](?:\d{10}[_\-])?(.+?)[_\-]standardcharges",
        path,
        re.IGNORECASE,
    )
    if not m:
        return None
    raw = m.group(1).replace("-", " ").replace("_", " ").replace(".", " ")
    return normalize_hospital_name(raw)


def _best_match(
    target: str,
    candidates: list[tuple[str, dict[str, Any]]],
) -> dict[str, Any] | None:
    """Return the hospital dict whose normalized name best matches target."""
    best_score = 0.0
    best: dict[str, Any] | None = None
    for norm, hospital in candidates:
        score = difflib.SequenceMatcher(None, target, norm).ratio()
        if score > best_score:
            best_score, best = score, hospital
    return best if best_score >= _NAME_MATCH_THRESHOLD else None


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _file_format(url: str) -> str:
    path = url.lower().split("?")[0]
    for ext, fmt in (
        (".json.gz", "json"), (".json", "json"),
        (".csv.gz", "csv"), (".csv", "csv"),
        (".xlsx", "xlsx"), (".xml", "xml"), (".zip", "zip"),
    ):
        if path.endswith(ext):
            return fmt
    return "unknown"


def _resolve(base: str, href: str) -> str:
    return urllib.parse.urljoin(base, href)


def _get_html(session: requests.Session, url: str) -> str | None:
    """Fetch URL, return decoded body (capped at _MAX_BODY), or None on error."""
    for ua in (_USER_AGENT, _BROWSER_UA):
        try:
            r = session.get(
                url, timeout=_GET_TIMEOUT, allow_redirects=True,
                headers={"User-Agent": ua}, stream=True,
            )
            if r.status_code != 200:
                continue
            chunks: list[bytes] = []
            total = 0
            for chunk in r.iter_content(chunk_size=65_536):
                total += len(chunk)
                if total > _MAX_BODY:
                    break
                chunks.append(chunk)
            return b"".join(chunks).decode("utf-8", errors="replace")
        except requests.RequestException:
            continue
    return None


def _head_ok(session: requests.Session, url: str) -> bool:
    """Return True if url responds 2xx with a non-HTML content-type."""
    for ua in (_USER_AGENT, _BROWSER_UA):
        try:
            r = session.head(
                url, timeout=_HEAD_TIMEOUT, allow_redirects=True,
                headers={"User-Agent": ua},
            )
            if r.status_code < 400:
                ct = r.headers.get("content-type", "")
                return not ct.lower().startswith(("text/html", "application/xhtml"))
        except requests.RequestException:
            continue
    return False


def _http_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Accept": "*/*"})
    return s


# ---------------------------------------------------------------------------
# URL extraction
# ---------------------------------------------------------------------------


def _extract_cms_urls(html: str, base_url: str) -> list[str]:
    """Extract absolute CMS-pattern MRF URLs from HTML or JS source.

    Pass 1: CMS filename regex scan across raw text (catches JS arrays,
            data-attributes, and inline href values simultaneously).
    Pass 2: <a href> anchor scan (explicit link elements).
    """
    found: dict[str, None] = {}

    for m in _CMS_FILENAME_RE.finditer(html):
        sq = html.rfind("'", 0, m.start())
        dq = html.rfind('"', 0, m.start())
        q_start = max(sq, dq)
        if q_start >= 0:
            q_char = html[q_start]
            q_end = html.find(q_char, m.end())
            if q_end > q_start:
                found[_resolve(base_url, html[q_start + 1: q_end])] = None

    for m in re.finditer(r'href=["\']([^"\'>\s]+)["\']', html, re.IGNORECASE):
        href = m.group(1)
        if _CMS_FILENAME_RE.search(href):
            found[_resolve(base_url, href)] = None

    return list(found)


# ---------------------------------------------------------------------------
# URL → CCN assignment
# ---------------------------------------------------------------------------


def assign_urls_to_hospitals(
    url_name_pairs: list[tuple[str, str]],
    hospitals: list[dict[str, Any]],
    discovery_method: str,
    session: requests.Session,
) -> list[SweepResult]:
    """Match extracted MRF URLs to hospital CCNs via fuzzy name matching.

    url_name_pairs: list of (mrf_url, extracted_hospital_name_normalized).
    hospitals: checkpoint rows for the domain/system being swept.
    Returns one SweepResult per matched + HEAD-validated URL.
    """
    candidates = [
        (normalize_hospital_name(h.get("hospital_name") or ""), h)
        for h in hospitals
        if h.get("hospital_name")
    ]
    assigned: dict[str, list[str]] = {}
    assigned_hospital: dict[str, dict[str, Any]] = {}

    for url, name in url_name_pairs:
        hospital = _best_match(name, candidates)
        if not hospital:
            logger.debug("sweep[%s]: no name match for %r (%s)", discovery_method, name, url)
            continue
        ccn = hospital.get("ccn") or ""
        if ccn:
            assigned.setdefault(ccn, []).append(url)
            assigned_hospital[ccn] = hospital

    results: list[SweepResult] = []
    for ccn, urls in assigned.items():
        hosp = assigned_hospital[ccn]
        validated = [u for u in urls if _head_ok(session, u)]
        if not validated:
            continue
        logger.info(
            "sweep[%s]: %s → %d URL(s) (ccn=%s)",
            discovery_method, hosp.get("hospital_name"), len(validated), ccn,
        )
        for url in validated:
            results.append(SweepResult(
                ccn=ccn,
                hospital_npi=hosp.get("hospital_npi"),
                hospital_name=hosp.get("hospital_name") or "",
                state=hosp.get("state"),
                mrf_url=url,
                discovery_method=discovery_method,
                file_format=_file_format(url),
            ))
    return results


# ---------------------------------------------------------------------------
# Tenet / Hyve sweeper
# ---------------------------------------------------------------------------


def sweep_tenet_hyve(
    session: requests.Session,
    hospitals: list[dict[str, Any]],
) -> tuple[list[SweepResult], set[str]]:
    """Extract Tenet Health MRF URLs from mrfs.hyvehealthcare.com/TenetHealth/.

    The Hyve page encodes its file list in a JS `const files = [...]` array.
    Each filename follows the CMS pattern, so we regex-extract the array,
    construct direct download URLs, and fuzzy-match to checkpoint hospitals.
    """
    html = _get_html(session, HYVE_TENET_URL)
    if not html:
        logger.warning("sweep_tenet_hyve: failed to fetch %s", HYVE_TENET_URL)
        return [], set()

    filenames = re.findall(r'"([^"]+_standardcharges\.(?:json|csv))"', html)
    if not filenames:
        logger.warning("sweep_tenet_hyve: no files found in JS array at %s", HYVE_TENET_URL)
        return [], set()

    url_name_pairs: list[tuple[str, str]] = []
    for fname in filenames:
        url = f"{HYVE_TENET_URL.rstrip('/')}/{fname}"
        name = extract_name_from_cms_filename(url)
        if name:
            url_name_pairs.append((url, name))

    logger.info(
        "sweep_tenet_hyve: %d candidate URLs, matching against %d hospitals",
        len(url_name_pairs), len(hospitals),
    )
    results = assign_urls_to_hospitals(url_name_pairs, hospitals, "tenet_hyve", session)
    return results, {r.ccn for r in results}


# ---------------------------------------------------------------------------
# Domain-dedup sweeper (same-domain rate-limit prevention)
# ---------------------------------------------------------------------------


def _sweep_domain_once(
    session: requests.Session,
    domain: str,
    base_url: str,
    hospitals: list[dict[str, Any]],
    path_heuristics: tuple[str, ...],
) -> tuple[list[SweepResult], set[str]]:
    """Fetch a domain's transparency paths ONCE and assign URLs to hospitals.

    Prevents the per-hospital crawl from hitting e.g.
    sutterhealth.org/billing-insurance/costs-and-charges/cost-transparency
    39 times concurrently, which triggers 429 rate-limiting after the first
    few requests. One fetch gets all facility URLs; name-matching distributes
    them to the right checkpoint rows.
    """
    parsed = urllib.parse.urlparse(base_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    all_urls: dict[str, None] = {}

    for path in path_heuristics:
        html = _get_html(session, root + path)
        if html:
            for url in _extract_cms_urls(html, root + path):
                all_urls[url] = None

    if not all_urls:
        return [], set()

    url_name_pairs = [
        (url, name)
        for url in all_urls
        if (name := extract_name_from_cms_filename(url)) is not None
    ]
    if not url_name_pairs:
        return [], set()

    logger.info(
        "_sweep_domain_once: %s — %d candidate URLs for %d hospitals",
        domain, len(url_name_pairs), len(hospitals),
    )
    results = assign_urls_to_hospitals(url_name_pairs, hospitals, "domain_dedup", session)
    resolved = {r.ccn for r in results}
    if resolved:
        logger.info(
            "_sweep_domain_once: %s resolved %d / %d hospitals",
            domain, len(resolved), len(hospitals),
        )
    return results, resolved


def run_domain_dedup_sweeps(
    session: requests.Session,
    hospitals: list[dict[str, Any]],
    path_heuristics: tuple[str, ...],
    threshold: int = SAME_DOMAIN_SWEEP_THRESHOLD,
) -> tuple[list[SweepResult], set[str]]:
    """Group hospitals by domain; sweep domains with ≥ threshold hospitals once.

    Returns (discovered, resolved_ccns).
    """
    by_domain: dict[str, list[dict[str, Any]]] = {}
    for h in hospitals:
        website = h.get("hospital_website") or ""
        try:
            host = urllib.parse.urlparse(website).netloc.lower()
        except (ValueError, TypeError):
            continue
        if host:
            by_domain.setdefault(host, []).append(h)

    all_results: list[SweepResult] = []
    all_resolved: set[str] = set()

    for domain, domain_hospitals in by_domain.items():
        if len(domain_hospitals) < threshold:
            continue
        sample = domain_hospitals[0].get("hospital_website") or ""
        results, resolved = _sweep_domain_once(
            session, domain, sample, domain_hospitals, path_heuristics,
        )
        all_results.extend(results)
        all_resolved |= resolved

    return all_results, all_resolved


# ---------------------------------------------------------------------------
# Kaiser Playwright sweeper
# ---------------------------------------------------------------------------


def sweep_kaiser_playwright(
    browser: Any,
    hospitals: list[dict[str, Any]],
) -> tuple[list[SweepResult], set[str]]:
    """Fetch Kaiser regional machine-readable pages via Playwright.

    Kaiser publishes one MRF-listing page per region. Each page is JS-rendered
    so requests-based crawl returns an empty shell. Playwright waits for network
    idle and extracts direct file links from the rendered DOM.
    """
    with _http_session() as session:
        url_name_pairs: list[tuple[str, str]] = []
        for region in KAISER_REGIONS:
            url = f"https://healthy.kaiserpermanente.org/{region}/front-door/machine-readable"
            pairs = _pw_extract_cms_urls(browser, url)
            url_name_pairs.extend(pairs)
            logger.info("sweep_kaiser_playwright: %s → %d URLs", region, len(pairs))

        logger.info(
            "sweep_kaiser_playwright: %d total candidate URLs for %d hospitals",
            len(url_name_pairs), len(hospitals),
        )
        results = assign_urls_to_hospitals(url_name_pairs, hospitals, "kaiser_playwright", session)
        return results, {r.ccn for r in results}


# ---------------------------------------------------------------------------
# CommonSpirit Playwright sweeper
# ---------------------------------------------------------------------------


def sweep_commonspirit_playwright(
    browser: Any,
    hospitals: list[dict[str, Any]],
) -> tuple[list[SweepResult], set[str]]:
    """Fetch CommonSpirit state price-transparency pages via Playwright.

    CommonSpirit uses a JS-rendered state dropdown. Playwright renders the page
    fully and extracts all CMS-pattern URLs from the rendered DOM, including
    links in collapsed accordion sections (their href values are in the DOM even
    when the accordion is visually closed).
    """
    with _http_session() as session:
        url_name_pairs = _pw_extract_cms_urls(browser, COMMONSPIRIT_PRICE_TRANSPARENCY_URL)
        logger.info(
            "sweep_commonspirit_playwright: %d candidate URLs for %d hospitals",
            len(url_name_pairs), len(hospitals),
        )
        results = assign_urls_to_hospitals(
            url_name_pairs, hospitals, "commonspirit_playwright", session,
        )
        return results, {r.ccn for r in results}


# ---------------------------------------------------------------------------
# Shared Playwright page-extraction helper
# ---------------------------------------------------------------------------


def _pw_extract_cms_urls(browser: Any, url: str) -> list[tuple[str, str]]:
    """Navigate to url in a fresh Playwright context, return (url, name) pairs.

    Extracts CMS-pattern file URLs from the fully-rendered DOM. Returns an
    empty list if Playwright is unavailable or if navigation fails.
    """
    try:
        ctx = browser.new_context(
            user_agent=_BROWSER_UA,
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        try:
            page = ctx.new_page()
            try:
                page.goto(url, wait_until="networkidle", timeout=30_000)
                html = page.content()
            finally:
                page.close()
        finally:
            ctx.close()
    except Exception:
        logger.exception("_pw_extract_cms_urls: Playwright error for %s", url)
        return []

    pairs: list[tuple[str, str]] = []
    for candidate in _extract_cms_urls(html, url):
        name = extract_name_from_cms_filename(candidate)
        if name:
            pairs.append((candidate, name))
    return pairs


# ---------------------------------------------------------------------------
# Top-level entry point (non-Playwright sweeps)
# ---------------------------------------------------------------------------


def run(
    session: requests.Session,
    hospitals: list[dict[str, Any]],
    path_heuristics: tuple[str, ...],
) -> tuple[list[SweepResult], set[str]]:
    """Run all non-Playwright system sweeps before the per-hospital crawl.

    Returns (discovered, resolved_ccns). Caller removes resolved_ccns from
    the per-hospital crawl queue to avoid redundant work and rate-limiting.

    Playwright sweeps (Kaiser, CommonSpirit) are NOT run here — they require
    a browser instance created in stage4_extract_mrf_urls.run() and are called
    directly from there.
    """
    all_results: list[SweepResult] = []
    all_resolved: set[str] = set()

    tenet_results, tenet_resolved = sweep_tenet_hyve(session, hospitals)
    all_results.extend(tenet_results)
    all_resolved |= tenet_resolved

    remaining = [h for h in hospitals if h.get("ccn") not in all_resolved]
    dedup_results, dedup_resolved = run_domain_dedup_sweeps(
        session, remaining, path_heuristics,
    )
    all_results.extend(dedup_results)
    all_resolved |= dedup_resolved

    logger.info(
        "system_sweepers.run: %d URLs discovered, %d hospitals resolved pre-crawl",
        len(all_results), len(all_resolved),
    )
    return all_results, all_resolved
