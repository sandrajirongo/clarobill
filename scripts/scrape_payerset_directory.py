"""Scrape the Payerset hospital MRF directory and output a bootstrap-ready CSV.

Fetches the GitBook Markdown endpoint for:
  https://docs.payerset.com/hospital-transparency/mrf-links-by-state

The page is Next.js client-rendered so requests cannot parse the HTML directly.
GitBook exposes a raw Markdown alternate at the same URL + ".md", which is
server-rendered and contains all the table data.

The output CSV has columns:
  npi, name, system_name, state, mrf_url, record_count, is_direct_download

Feed the output straight into bootstrap_hospital_directory.py:
  python3 scripts/scrape_payerset_directory.py --out hospitals.csv
  python3 scripts/bootstrap_hospital_directory.py --file hospitals.csv

--- NPI resolution ---

The Payerset page does not include NPIs. Filename prefixes are 9-digit EINs
or 6-digit CCNs — not 10-digit NPIs. The --resolve-npis flag queries the
free NPPES registry API (name + state lookup) to fill them in.

This takes ~1-2 seconds per hospital. For ~5,000 hospitals expect 2-3 hours
total. Use --npi-cache to save results so re-runs skip already-resolved NPIs.

Without --resolve-npis, npi is left blank and can be resolved later.

--- Usage ---

  # Quick scrape, no NPI resolution (seconds):
  python3 scripts/scrape_payerset_directory.py --out data/cms/hospitals/hospitals_raw.csv

  # Full scrape with NPI resolution (slow, cached):
  python3 scripts/scrape_payerset_directory.py \\
    --out data/cms/hospitals/hospitals.csv \\
    --resolve-npis \\
    --npi-cache data/cms/hospitals/npi_cache.json

  # Single state for testing:
  python3 scripts/scrape_payerset_directory.py --out /tmp/test.csv --state AL
"""

import argparse
import csv
import json
import logging
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse, unquote

import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# GitBook exposes raw Markdown at the .md alternate URL — use this instead of
# the HTML page, which requires JavaScript to render.
PAYERSET_MD_URL = "https://docs.payerset.com/hospital-transparency/mrf-links-by-state.md"
NPPES_API = "https://npiregistry.cms.hhs.gov/api/"
NPPES_RATE_LIMIT = 0.2  # seconds between requests (5 req/s max)

REQUEST_HEADERS = {
    "User-Agent": "ClaroBill-Research/1.0 (price transparency; contact@clarobill.com)",
}

OUTPUT_COLUMNS = ["npi", "name", "system_name", "state", "mrf_url", "record_count", "is_direct_download"]

# Matches a Markdown link: [any text](url)
_MD_LINK_RE = re.compile(r'\[([^\]]*)\]\(([^)]+)\)')

# Matches a Markdown table data row (not a header or separator line).
# Separator lines look like: | --- | --- | ... |
_TABLE_ROW_RE = re.compile(r'^\|(.+)\|$')
_TABLE_SEP_RE = re.compile(r'^\|[\s\-|]+\|$')

# US state name → 2-letter abbreviation
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
    return _STATE_ABBR.get(name.strip().lower(), name.strip().upper()[:2])


def parse_markdown(md_text: str) -> list[dict]:
    """Parse the Payerset Markdown page into a list of hospital dicts.

    The Markdown structure is:
      ## State Name
      | System Name | Hospital Name | File URL | Record Count |
      | --- | --- | --- | --- |
      | Ascension | St Vincents | [Link](https://...) | 420,150 |

    Walks line by line, tracking the current state from ## headings and
    extracting data rows from pipe-delimited tables.

    Args:
        md_text: Raw Markdown content of the Payerset page.

    Returns:
        List of dicts with keys: system_name, name, state, mrf_url, record_count.
    """
    rows: list[dict] = []
    current_state = ""

    for line in md_text.splitlines():
        line = line.strip()

        # ## Heading → new state section
        if line.startswith("## "):
            current_state = _abbreviate_state(line[3:].strip())
            continue

        # Skip non-table lines and separator rows (| --- | --- |)
        if not _TABLE_ROW_RE.match(line):
            continue
        if _TABLE_SEP_RE.match(line):
            continue

        # Split pipe-delimited columns, strip whitespace from each
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 3:
            continue

        # Skip the header row (first column is "System Name")
        if cols[0].lower() in ("system name", "system"):
            continue

        system_name = cols[0]
        hospital_name = cols[1]
        url_cell = cols[2]
        record_count = cols[3].replace(",", "").strip() if len(cols) > 3 else ""

        # Extract URL from Markdown link [Link](url) or use raw text if it's a plain URL
        link_match = _MD_LINK_RE.search(url_cell)
        mrf_url = link_match.group(2) if link_match else url_cell.strip()

        # Remove escaped backslashes GitBook inserts before & and = in query strings
        mrf_url = mrf_url.replace("\\&", "&").replace("\\=", "=")

        if hospital_name and mrf_url and current_state:
            rows.append({
                "system_name": system_name,
                "name": hospital_name,
                "state": current_state,
                "mrf_url": mrf_url,
                "record_count": record_count,
            })

    return rows


def scrape_payerset(session: requests.Session) -> list[dict]:
    """Fetch and parse the Payerset MRF directory Markdown page.

    Returns list of dicts with keys: system_name, name, state, mrf_url, record_count.
    """
    logger.info("Fetching %s", PAYERSET_MD_URL)
    resp = session.get(PAYERSET_MD_URL, timeout=30)
    resp.raise_for_status()
    rows = parse_markdown(resp.text)
    logger.info("Parsed %d hospital entries", len(rows))
    return rows


def _extract_npi_from_url(mrf_url: str) -> tuple[str | None, bool]:
    """Try to extract an NPI from a direct-download MRF filename.

    CMS naming convention: {NPI|EIN|CCN}_{hospital-name}_standardcharges.{ext}
      NPI = 10 digits
      EIN = 9 digits, sometimes formatted as XX-XXXXXXX
      CCN = 6 digits

    Only 10-digit prefixes are returned as NPIs. EINs and CCNs are ignored
    since they cannot be used directly as NPI keys.

    Returns (npi_or_none, is_direct_download).
    """
    path = unquote(urlparse(mrf_url).path)
    filename = path.split("/")[-1].lower()

    is_direct = any(filename.endswith(ext) for ext in (".json", ".json.gz", ".csv", ".csv.gz", ".zip"))

    if not is_direct:
        return None, False

    # Extract prefix before the first underscore (handles EIN with dashes: 83-1651180_...)
    prefix_match = re.match(r'^([0-9\-]+)_', filename)
    if prefix_match:
        digits = prefix_match.group(1).replace("-", "")
        if len(digits) == 10:
            return digits, True

    return None, is_direct


def _lookup_npi(hospital_name: str, state: str, session: requests.Session) -> str | None:
    """Query the NPPES registry API to resolve an NPI by hospital name + state.

    Uses the public NPI Registry API (no auth required). Returns the first
    matching NPI for an organizational provider, or None if not found.
    """
    params = {
        "organization_name": hospital_name,
        "state": state,
        "enumeration_type": "NBO",
        "version": "2.1",
        "limit": 5,
    }
    try:
        resp = session.get(NPPES_API, params=params, timeout=10)
        resp.raise_for_status()
        results = resp.json().get("results") or []
        if results:
            return results[0].get("number")
    except Exception as exc:
        logger.debug("NPPES lookup failed for %r (%s): %s", hospital_name, state, exc)
    return None


def enrich_with_npis(
    rows: list[dict],
    resolve_npis: bool,
    npi_cache_path: Path | None,
    filter_state: str | None,
    session: requests.Session,
) -> list[dict]:
    """Add npi and is_direct_download fields to each row.

    First tries to extract NPI from the filename (free, instant).
    Then optionally queries NPPES for rows still missing an NPI.
    """
    npi_cache: dict[str, str] = {}
    if npi_cache_path and npi_cache_path.exists():
        with npi_cache_path.open() as f:
            npi_cache = json.load(f)
        logger.info("Loaded %d cached NPIs", len(npi_cache))

    enriched = []
    npis_from_filename = 0
    npis_from_api = 0
    npis_missing = 0

    for row in rows:
        if filter_state and row["state"] != filter_state.upper():
            continue

        npi, is_direct = _extract_npi_from_url(row["mrf_url"])

        if npi:
            npis_from_filename += 1
        elif resolve_npis:
            cache_key = f"{row['name']}|{row['state']}"
            if cache_key in npi_cache:
                npi = npi_cache[cache_key] or None
            else:
                npi = _lookup_npi(row["name"], row["state"], session)
                npi_cache[cache_key] = npi or ""
                npis_from_api += 1
                time.sleep(NPPES_RATE_LIMIT)

        if not npi:
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
        "NPI summary: %d from filename, %d from NPPES API, %d unresolved",
        npis_from_filename, npis_from_api, npis_missing,
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
        help="Query NPPES API for hospitals without a filename NPI (slow — use --npi-cache)",
    )
    parser.add_argument(
        "--npi-cache",
        type=Path,
        default=None,
        help="JSON file to cache NPPES results across runs",
    )
    parser.add_argument(
        "--state",
        default=None,
        help="Filter to a single state (e.g. AL) — useful for testing",
    )
    args = parser.parse_args()

    with requests.Session() as session:
        session.headers.update(REQUEST_HEADERS)
        rows = scrape_payerset(session)

    if not rows:
        print("Error: no rows parsed from Payerset page.", file=sys.stderr)
        sys.exit(1)

    with requests.Session() as session:
        session.headers.update(REQUEST_HEADERS)
        enriched = enrich_with_npis(
            rows,
            resolve_npis=args.resolve_npis,
            npi_cache_path=args.npi_cache,
            filter_state=args.state,
            session=session,
        )

    if not enriched:
        print("Error: no rows after filtering.", file=sys.stderr)
        sys.exit(1)

    write_csv(enriched, args.out)

    total = len(enriched)
    with_npi = sum(1 for r in enriched if r["npi"])
    direct = sum(1 for r in enriched if r["is_direct_download"] == "true")
    print(f"\n  Total hospitals : {total}")
    print(f"  Direct download : {direct} ({direct * 100 // total}%)")
    print(f"  With NPI        : {with_npi} ({with_npi * 100 // total}%)")
    print(f"  Missing NPI     : {total - with_npi}")
    if total - with_npi > 0:
        print("  → Re-run with --resolve-npis --npi-cache npi_cache.json to fill missing NPIs")


if __name__ == "__main__":
    main()
