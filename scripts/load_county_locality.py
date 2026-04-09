"""Load CMS county-to-locality mapping into the database.

Source file: "26LOCCO.csv" — Counties Included in CY 2026 Localities
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

Usage:
  python scripts/load_county_locality.py \\
    --file 26LOCCO.csv
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
    """Parse the counties column into (county_names, is_statewide, is_rest_of_state).

    Returns:
        county_names:    Individual county names (empty for statewide/rest-of-state rows).
        is_statewide:    True when the row represents ALL COUNTIES in the state.
        is_rest_of_state: True when the row represents ALL OTHER COUNTIES (fallback).
    """
    normalised = raw_counties.strip().upper()

    if normalised in ("ALL COUNTIES", "ALL COUNTY EQUIVALENTS"):
        return [], True, False

    if "ALL OTHER COUNTIES" in normalised or normalised == "ALL COUNTY EQUIVALENTS":
        return [], False, True

    # Replace " AND " with comma so it splits cleanly (handles "...X AND Y" at end of lists)
    text = re.sub(r"\bAND\b", ",", normalised)

    # Split on comma, slash, or semicolon
    parts = re.split(r"[,;/]", text)
    county_names = [_clean_county_name(p) for p in parts if p.strip()]
    return county_names, False, False


def load_from_file(path: Path) -> list[dict]:
    """Parse 26LOCCO.csv into rows ready for upsert into cms_county_locality.

    The CSV has:
      - 3 header/metadata rows before the data header on row 4 (0-indexed: row 3)
      - Data rows with fill-forward for contractor, locality_number, and state
      - Blank separator rows between state groups (all 6 columns empty)
    """
    with path.open(newline="", encoding="utf-8-sig") as f:
        lines = f.readlines()

    # Find the actual header row — it starts with "Medicare"
    header_idx = None
    for i, line in enumerate(lines):
        if line.strip().lower().startswith("medicare"):
            header_idx = i
            break

    if header_idx is None:
        print("Error: could not find header row in file.", file=sys.stderr)
        sys.exit(1)

    reader = csv.DictReader(lines[header_idx:])

    rows: list[dict] = []
    current_contractor = ""
    current_locality_number = ""
    current_state = ""
    current_locality_name = ""

    for row in reader:
        contractor = row.get("Medicare Adminstrative Contractor", "").strip()
        locality_number = row.get("Locality Number", "").strip()
        state = row.get("State ", "").strip()
        locality_name = row.get("Fee Schedule Area ", "").strip()
        counties_raw = row.get("Counties", "").strip()

        # Skip blank separator rows
        if not contractor and not locality_number and not state and not counties_raw:
            continue

        # Fill-forward: carry contractor/locality/state from the previous data row
        if contractor:
            current_contractor = contractor
        if locality_number:
            current_locality_number = locality_number
        if state:
            current_state = state.upper()
        if locality_name:
            current_locality_name = locality_name

        # Skip rows that still lack a resolved locality (shouldn't happen in clean data)
        if not current_contractor or not current_locality_number or not current_state:
            continue

        if not counties_raw:
            continue

        # Locality code = contractor (5-char) + locality_number (2-char), zero-padded
        locality_code = current_contractor + current_locality_number.zfill(2)

        county_names, is_statewide, is_rest_of_state = _parse_counties(counties_raw)

        if is_statewide or is_rest_of_state:
            rows.append({
                "id": str(uuid.uuid4()),
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
        description="Load CMS county-to-locality mapping into the MedScan database."
    )
    parser.add_argument(
        "--file",
        type=Path,
        required=True,
        help="Path to 26LOCCO.csv",
    )
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

    print(f"Loading county-locality mapping from {args.file.name}...")
    rows = load_from_file(args.file)

    # Clear existing rows before reload (idempotent full replacement)
    client.table("cms_county_locality").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
    print("  Cleared existing rows.")

    inserted = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        client.table("cms_county_locality").insert(batch).execute()
        inserted += len(batch)
        print(f"  Inserted {inserted}/{len(rows)} rows...")

    print(f"Done. {inserted} county-locality rows loaded.")


if __name__ == "__main__":
    main()
