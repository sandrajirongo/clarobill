"""Load CMS county-to-locality mapping into the database.

Source files: "<YY>LOCCO.csv" — Counties Included in CY YYYY Localities
Download from: https://www.cms.gov/medicare/payment/fee-schedules/physician

The file maps US counties → CMS MAC locality codes. Each locality code is a
7-character string (contractor 5-char + locality_number 2-char) that joins
directly to cms_localities.locality_code for GPCI-adjusted rate lookups.

The CSV has a fill-forward pattern: contractor, locality_number, and state
are only set on the first row of each new locality group and must be carried
forward for subsequent rows.

County patterns handled:
  - "ALL COUNTIES" / "ALL COUNTY EQUIVALENTS"  → is_statewide = true
  - "ALL OTHER COUNTIES"                        → is_rest_of_state = true
  - Everything else                             → one row per county, comma/slash/semicolon-split

Note: the 2020 file uses "Carrier Number" instead of
"Medicare Adminstrative Contractor" for the first column — handled automatically.

Usage:
  python scripts/load_county_locality.py --file data/cms/county-locality/2026/26LOCCO.csv --year 2026
  python scripts/load_county_locality.py --file data/cms/county-locality/2025/25LOCCO.csv --year 2025
"""

import argparse
import csv
import os
import re
import sys
import uuid
from pathlib import Path

from supabase import create_client

BATCH_SIZE = 500

# Both column name variants used by CMS across years
_CONTRACTOR_COLUMNS = {"medicare adminstrative contractor", "carrier number"}


def _clean_county_name(raw: str) -> str:
    """Normalise a county name: uppercase, strip whitespace and the " CNTY" suffix."""
    name = raw.strip().upper()
    for suffix in (" CNTY", " COUNTY"):
        if name.endswith(suffix):
            name = name[: -len(suffix)].strip()
    # Strip jurisdiction qualifiers like "FALLS CHURCH CITY IN VIRGINIA"
    if " IN " in name:
        name = name[: name.index(" IN ")].strip()
    return name


def _parse_counties(raw_counties: str) -> tuple[list[str], bool, bool]:
    """Parse the counties column into (county_names, is_statewide, is_rest_of_state)."""
    normalised = raw_counties.strip().upper()

    if normalised in ("ALL COUNTIES", "ALL COUNTY EQUIVALENTS"):
        return [], True, False

    if "ALL OTHER COUNTIES" in normalised:
        return [], False, True

    # Replace " AND " with comma so it splits cleanly (handles "...X AND Y" at end of lists)
    text = re.sub(r"\bAND\b", ",", normalised)

    parts = re.split(r"[,;/]", text)
    county_names = [_clean_county_name(p) for p in parts if p.strip()]
    return county_names, False, False


def load_from_file(path: Path, year: int) -> list[dict]:
    """Parse a LOCCO CSV into rows ready for insert into cms_county_locality.

    Handles both column name variants:
      - "Medicare Adminstrative Contractor" (2021+)
      - "Carrier Number" (2020 and earlier)
    """
    with path.open(newline="", encoding="utf-8-sig") as f:
        lines = f.readlines()

    # Find the header row — starts with "Medicare" (2021+) or "Carrier" (2020)
    header_idx = None
    for i, line in enumerate(lines):
        stripped = line.strip().lower()
        if stripped.startswith("medicare") or stripped.startswith("carrier"):
            header_idx = i
            break

    if header_idx is None:
        print("Error: could not find header row in file.", file=sys.stderr)
        sys.exit(1)

    reader = csv.DictReader(lines[header_idx:])

    # Identify the contractor column name used in this file
    fieldnames_lower = {f.strip().lower(): f for f in (reader.fieldnames or [])}
    contractor_col = next(
        (fieldnames_lower[k] for k in _CONTRACTOR_COLUMNS if k in fieldnames_lower),
        None,
    )
    if contractor_col is None:
        print(
            f"Error: could not find contractor column. Columns: {list(fieldnames_lower.keys())}",
            file=sys.stderr,
        )
        sys.exit(1)

    rows: list[dict] = []
    current_contractor = ""
    current_locality_number = ""
    current_state = ""
    current_locality_name = ""

    for row in reader:
        contractor = row.get(contractor_col, "").strip()
        locality_number = row.get("Locality Number", "").strip()
        state = row.get("State ", "").strip()
        locality_name = row.get("Fee Schedule Area ", "").strip()
        counties_raw = row.get("Counties", "").strip()

        # Skip blank separator rows
        if not contractor and not locality_number and not state and not counties_raw:
            continue

        # Fill-forward: carry values from the previous data row
        if contractor:
            current_contractor = contractor
        if locality_number:
            current_locality_number = locality_number
        if state:
            current_state = state.upper()
        if locality_name:
            current_locality_name = locality_name

        if not current_contractor or not current_locality_number or not current_state:
            continue

        if not counties_raw:
            continue

        locality_code = current_contractor + current_locality_number.zfill(2)
        county_names, is_statewide, is_rest_of_state = _parse_counties(counties_raw)

        if is_statewide or is_rest_of_state:
            rows.append({
                "id": str(uuid.uuid4()),
                "year": year,
                "state": current_state,
                "locality_code": locality_code,
                "locality_name": current_locality_name,
                "county_name": None,
                "is_statewide": is_statewide,
                "is_rest_of_state": is_rest_of_state,
            })
        else:
            for county in county_names:
                if not county:
                    continue
                rows.append({
                    "id": str(uuid.uuid4()),
                    "year": year,
                    "state": current_state,
                    "locality_code": locality_code,
                    "locality_name": current_locality_name,
                    "county_name": county,
                    "is_statewide": False,
                    "is_rest_of_state": False,
                })

    print(f"  Parsed {len(rows)} county-locality rows.")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load CMS county-to-locality mapping into the ClaroBill database."
    )
    parser.add_argument("--file", type=Path, required=True, help="Path to the LOCCO CSV file")
    parser.add_argument("--year", type=int, required=True, help="Calendar year (e.g. 2026)")
    args = parser.parse_args()

    if not args.file.exists():
        print(f"Error: file not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        print("Error: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set.", file=sys.stderr)
        sys.exit(1)

    client = create_client(supabase_url, supabase_key)

    print(f"Loading county-locality mapping from {args.file.name} (year={args.year})...")
    rows = load_from_file(args.file, args.year)

    # Clear only this year's rows before reload (safe to re-run)
    client.table("cms_county_locality").delete().eq("year", args.year).execute()
    print(f"  Cleared existing year={args.year} rows.")

    inserted = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        client.table("cms_county_locality").insert(batch).execute()
        inserted += len(batch)
        print(f"  Inserted {inserted}/{len(rows)} rows...")

    print(f"Done. {inserted} county-locality rows loaded for year={args.year}.")


if __name__ == "__main__":
    main()
