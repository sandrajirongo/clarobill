"""Scrape the Payerset hospital MRF directory and output a bootstrap-ready CSV.

Fetches https://docs.payerset.com/hospital-transparency/mrf-links-by-state,
parses the per-state tables (System Name, Hospital Name, File URL, Record Count),
and optionally resolves NPIs via the public NPPES registry API.

The output CSV has columns:
  npi, name, system_name, state, mrf_url, record_count, is_direct_download

Feed the output straight into bootstrap_hospital_directory.py:
  python scripts/scrape_payerset_directory.py --out hospitals.csv
  python scripts/bootstrap_hospital_directory.py --file hospitals.csv

--- NPI resolution ---

The Payerset page does not include NPIs. The filename prefix in direct-download
URLs is typically a 9-digit EIN or 6-digit CCN — not a 10-digit NPI.

With --resolve-npis the script queries the NPPES registry API:
  https://npiregistry.cms.hhs.gov/api/?organization_name=...&state=...

This adds ~1-2 seconds per hospital (rate-limited to 5 req/s). For ~5,000
hospitals expect 15-20 minutes total. Results are cached in --npi-cache so
you only pay this cost once.

Without --resolve-npis, npi is left blank for EIN/CCN entries and you can
resolve them later. Direct-download URLs with a 10-digit NPI prefix are
populated immediately — no API call needed.

--- Usage ---

  # Quick scrape, no NPI resolution:
  python scripts/scrape_payerset_directory.py --out data/cms/hospitals/hospitals_raw.csv

  # Full scrape with NPI resolution (slow but complete):
  python scripts/scrape_payerset_directory.py --out data/cms/hospitals/hospitals.csv \\
    --resolve-npis --npi-cache data/cms/hospitals/npi_cache.json

  # Single state for testing:
  python scripts/scrape_payerset_directory.py --out test.csv --state TX
"""

import argparse
import csv
import json
import logging
import re
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse, unquote

import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PAYERSET_URL = "https://docs.payerset.com/hospital-transparency/mrf-links-by-state"
NPPES_API = "https://npiregistry.cms.hhs.gov/api/"
NPPES_RATE_LIMIT = 0.2  # seconds between requests (5 req/s max)

REQUEST_HEADERS = {
    "User-Agent": "ClaroBill-Research/1.0 (price transparency; contact@clarobill.com)",
}

OUTPUT_COLUMNS = ["npi", "name", "system_name", "state", "mrf_url", "record_count", "is_direct_download"]


# ---------------------------------------------------------------------------
# HTML parser — extracts state tables from the Payerset docs page
# ---------------------------------------------------------------------------

class PayersetPageParser(HTMLParser):
    """Stateful HTML parser that walks the Payerset MRF links page.

    The page structure is:
      <h2>State Name</h2>
      <table>
        <thead><tr><th>System Name</th><th>Hospital Name</th><th>File URL</th><th>Record Count</th></tr></thead>
        <tbody>
          <tr><td>...</td><td>...</td><td><a href="...">Link</a></td><td>...</td></tr>
        </tbody>
      </table>

    State name is tracked from H2 headings. Each table row under a state
    heading is emitted as a dict.
    """

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict] = []
        self._current_state: str = ""
        self._in_table: bool = False
        self._in_thead: bool = False
        self._in_row: bool = False
        self._cell_index: int = 0
        self._current_cells: list[str] = []
        self._current_link: str = ""
        self._collecting: bool = False
        self._buffer: str = ""

    def handle_starttag(self, tag: str, attrs: list) -> None:
        attrs_dict = dict(attrs)
        if tag == "h2":
            self._collecting = True
            self._buffer = ""
        elif tag == "table":
            self._in_table = True
        elif tag == "thead":
            self._in_thead = True
        elif tag == "tr" and self._in_table and not self._in_thead:
            self._in_row = True
            self._current_cells = []
            self._current_link = ""
            self._cell_index = 0
        elif tag == "td" and self._in_row:
            self._collecting = True
            self._buffer = ""
        elif tag == "a" and self._in_row:
            self._current_link = attrs_dict.get("href", "")
        elif tag == "th":
            self._in_thead = True  # stay in header mode

    def handle_endtag(self, tag: str) -> None:
        if tag == "h2":
            self._current_state = self._buffer.strip()
            self._collecting = False
        elif tag == "table":
            self._in_table = False
            self._in_thead = False
        elif tag == "thead":
            self._in_thead = False
        elif tag == "td" and self._in_row:
            self._current_cells.append(self._buffer.strip())
            self._cell_index += 1
            self._collecting = False
            self._buffer = ""
        elif tag == "tr" and self._in_row:
            self._in_row = False
            if len(self._current_cells) >= 3:
                # Columns: System Name (0), Hospital Name (1), File URL (2), Record Count (3)
                system_name = self._current_cells[0]
                hospital_name = self._current_cells[1]
                mrf_url = self._current_link or self._current_cells[2]
                record_count = self._current_cells[3] if len(self._current_cells) > 3 else ""
                if hospital_name and mrf_url:
                    self.rows.append({
                        "system_name": system_name,
                        "name": hospital_name,
                        "state": _abbreviate_state(self._current_state),
                        "mrf_url": mrf_url,
                        "record_count": record_count.replace(",", ""),
                    })

    def handle_data(self, data: str) -> None:
        if self._collecting:
            self._buffer += data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# US state name → abbreviation mapping (covers all 50 states + DC)
_STATE_ABBR: dict[str, str] = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI",
    "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
    "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC",
}


def _abbreviate_state(name: str) -> str:
    """Convert a full state name to its 2-letter abbreviation, or return as-is."""
    return _STATE_ABBR.get(name.lower(), name.upper()[:2])


def _extract_provider_id(mrf_url: str) -> tuple[str | None, bool]:
    """Try to extract NPI from a direct-download MRF filename.

    CMS requires hospitals to prefix their filename with NPI, CCN, or EIN:
      {NPI|CCN|EIN}_{hospital-name}_standardcharges.{ext}

    NPI is exactly 10 digits — if the prefix is 10 digits, use it directly.
    CCN is 6 digits, EIN is 9 digits — these are NOT NPIs.

    Returns (npi_or_none, is_direct_download).
    """
    path = unquote(urlparse(mrf_url).path)
    filename = path.split("/")[-1]

    # Check if it's a direct file download (has a known extension)
    is_direct = any(
        filename.lower().endswith(ext)
        for ext in (".json", ".json.gz", ".csv", ".csv.gz", ".zip")
    )

    if not is_direct:
        return None, False

    # CMS naming convention: leading digits before first underscore or dot
    match = re.match(r"^(\d+)[_\-]", filename)
    if match:
        digits = match.group(1)
        if len(digits) == 10:
            return digits, True  # 10-digit prefix = NPI

    return None, is_direct


def _lookup_npi(hospital_name: str, state: str, session: requests.Session) -> str | None:
    """Query the NPPES registry API to resolve an NPI from hospital name + state.

    Uses the public NPI Registry API (no auth required). Returns the first
    matching NPI for an organizational provider in the given state, or None.

    Args:
        hospital_name: Hospital name as listed on the Payerset page.
        state: 2-letter state abbreviation.
        session: Requests session (shared to reuse TCP connections).

    Returns:
        10-digit NPI string, or None if not found.
    """
    params = {
        "organization_name": hospital_name,
        "state": state,
        "enumeration_type": "NBO",  # NBO = organizational providers
        "version": "2.1",
        "limit": 5,
    }
    try:
        resp = session.get(NPPES_API, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results") or []
        if results:
            return results[0].get("number")
    except Exception as exc:
        logger.debug("NPPES lookup failed for %r (%s): %s", hospital_name, state, exc)
    return None


# ---------------------------------------------------------------------------
# Main scrape logic
# ---------------------------------------------------------------------------

def scrape_payerset(session: requests.Session) -> list[dict]:
    """Fetch and parse the Payerset MRF directory page.

    Returns list of dicts with keys: system_name, name, state, mrf_url, record_count.
    """
    logger.info("Fetching %s", PAYERSET_URL)
    resp = session.get(PAYERSET_URL, timeout=30)
    resp.raise_for_status()

    parser = PayersetPageParser()
    parser.feed(resp.text)

    logger.info("Parsed %d hospital entries", len(parser.rows))
    return parser.rows


def enrich_with_npis(
    rows: list[dict],
    resolve_npis: bool,
    npi_cache_path: Path | None,
    filter_state: str | None,
    session: requests.Session,
) -> list[dict]:
    """Add NPI and is_direct_download fields to each row.

    First tries to extract NPI from the filename (free, immediate).
    Then optionally queries NPPES for rows without an NPI (slow, one API call each).

    Args:
        rows: Hospital rows from scrape_payerset().
        resolve_npis: If True, call NPPES API for hospitals without a filename NPI.
        npi_cache_path: Optional path to a JSON cache file to avoid re-querying NPPES.
        filter_state: If set, only process hospitals in this state abbreviation.
        session: Shared requests session.

    Returns:
        Enriched rows with npi (str|None) and is_direct_download (bool) added.
    """
    # Load NPI cache if available
    npi_cache: dict[str, str] = {}
    if npi_cache_path and npi_cache_path.exists():
        with npi_cache_path.open() as f:
            npi_cache = json.load(f)
        logger.info("Loaded %d cached NPIs", len(npi_cache))

    enriched = []
    npis_resolved = 0
    npis_missing = 0

    for row in rows:
        if filter_state and row["state"] != filter_state.upper():
            continue

        npi, is_direct = _extract_provider_id(row["mrf_url"])

        if npi is None and resolve_npis:
            cache_key = f"{row['name']}|{row['state']}"
            if cache_key in npi_cache:
                npi = npi_cache[cache_key]
            else:
                npi = _lookup_npi(row["name"], row["state"], session)
                npi_cache[cache_key] = npi or ""
                npis_resolved += 1
                time.sleep(NPPES_RATE_LIMIT)

        if npi is None:
            npis_missing += 1

        enriched.append({
            "npi": npi or "",
            "name": row["name"],
            "system_name": row["system_name"],
            "state": row["state"],
            "mrf_url": row["mrf_url"],
            "record_count": row["record_count"],
            "is_direct_download": "true" if is_direct else "false",
        })

    if resolve_npis and npi_cache_path:
        npi_cache_path.parent.mkdir(parents=True, exist_ok=True)
        with npi_cache_path.open("w") as f:
            json.dump(npi_cache, f, indent=2)
        logger.info("Saved NPI cache to %s", npi_cache_path)

    logger.info(
        "NPI summary: %d from filename, %d from NPPES, %d unresolved",
        sum(1 for r in enriched if r["npi"] and r["is_direct_download"] == "true"),
        npis_resolved,
        npis_missing,
    )
    return enriched


def write_csv(rows: list[dict], out_path: Path) -> None:
    """Write enriched rows to a CSV file."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    logger.info("Wrote %d rows to %s", len(rows), out_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape Payerset hospital MRF directory into a bootstrap-ready CSV."
    )
    parser.add_argument("--out", type=Path, required=True, help="Output CSV path")
    parser.add_argument(
        "--resolve-npis",
        action="store_true",
        help="Query NPPES API for hospitals without a filename NPI (slow)",
    )
    parser.add_argument(
        "--npi-cache",
        type=Path,
        default=None,
        help="JSON file to cache NPPES results (avoids re-querying on re-runs)",
    )
    parser.add_argument(
        "--state",
        default=None,
        help="Filter to a single state abbreviation (e.g. TX) — useful for testing",
    )
    args = parser.parse_args()

    with requests.Session() as session:
        session.headers.update(REQUEST_HEADERS)

        rows = scrape_payerset(session)
        if not rows:
            print("Error: no rows parsed from Payerset page.", file=sys.stderr)
            sys.exit(1)

        enriched = enrich_with_npis(
            rows,
            resolve_npis=args.resolve_npis,
            npi_cache_path=args.npi_cache,
            filter_state=args.state,
            session=session,
        )

    write_csv(enriched, args.out)

    # Summary
    total = len(enriched)
    with_npi = sum(1 for r in enriched if r["npi"])
    direct = sum(1 for r in enriched if r["is_direct_download"] == "true")
    print(f"\n  Total hospitals : {total}")
    print(f"  Direct download : {direct} ({direct * 100 // total}%)")
    print(f"  With NPI        : {with_npi} ({with_npi * 100 // total}%)")
    print(f"  Missing NPI     : {total - with_npi}")
    if total - with_npi > 0:
        print("  → Re-run with --resolve-npis to fill missing NPIs via NPPES API")


if __name__ == "__main__":
    main()
