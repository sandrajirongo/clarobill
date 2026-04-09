"""Load CMS locality-adjusted anesthesia conversion factors into the database.

Source file: "Anesthesia CY 2026 locality adjusted CF with update factor 20NOV25_508.csv"
Download from: https://www.cms.gov/medicare/payment/fee-schedules/physician

Expected CSV columns (row 5 is the header after 4 metadata rows):
  Contractor, Locality, Locality Name,
  Qualifying APM National Anes CF (...),
  Non-Qualifying APM National Anes CF (...)

Usage:
  python scripts/load_anesthesia_cf.py \\
    --file "Anesthesia CY 2026 locality adjusted CF with update factor 20NOV25_508.csv" \\
    --year 2026
"""

import argparse
import csv
import os
import sys
import uuid
from pathlib import Path

from supabase import create_client

BATCH_SIZE = 500

# National CFs from the 2026 file header — used as fallback when a locality isn't found
NATIONAL_NON_QUALIFYING_CF = 20.4975
NATIONAL_QUALIFYING_CF = 20.5998
NATIONAL_LOCALITY_NUMBER = "NATL"


def load_from_file(path: Path, year: int) -> list[dict]:
    """Parse the CMS anesthesia CF CSV.

    The file has 4 metadata header rows before the actual column header on row 5.
    Rows with empty contractor or locality are skipped.

    Args:
        path: Path to the anesthesia CF CSV file.
        year: The year this schedule applies to.

    Returns:
        List of dicts ready for upsert into cms_anesthesia_cf.
    """
    rows = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        lines = f.readlines()

    # Find the actual header row — it's the first line that starts with "Contractor"
    header_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith("Contractor"):
            header_idx = i
            break

    if header_idx is None:
        print("Error: could not find header row in file.", file=sys.stderr)
        sys.exit(1)

    reader = csv.DictReader(lines[header_idx:])
    for row in reader:
        contractor = row.get("Contractor", "").strip()
        locality = row.get("Locality", "").strip()
        name = row.get("Locality Name", "").strip()

        if not contractor or not locality or not name:
            continue

        # Column names contain the national CF value in parentheses — match by prefix
        qual_cf = non_qual_cf = None
        for key, val in row.items():
            key_clean = key.strip()
            if key_clean.startswith("Qualifying APM"):
                try:
                    qual_cf = float(val.strip())
                except (ValueError, AttributeError):
                    pass
            elif key_clean.startswith("Non-Qualifying APM"):
                try:
                    non_qual_cf = float(val.strip())
                except (ValueError, AttributeError):
                    pass

        if qual_cf is None or non_qual_cf is None:
            print(f"  Skipping {name}: could not parse CF values", file=sys.stderr)
            continue

        rows.append({
            "id": str(uuid.uuid4()),
            "year": year,
            "contractor": contractor,
            "locality_number": locality,
            "locality_name": name,
            "qualifying_cf": qual_cf,
            "non_qualifying_cf": non_qual_cf,
        })

    # Add a synthetic NATIONAL row using the base CFs from the file header.
    # This is used as the default when a bill's locality cannot be determined.
    rows.append({
        "id": str(uuid.uuid4()),
        "year": year,
        "contractor": "NATL",
        "locality_number": NATIONAL_LOCALITY_NUMBER,
        "locality_name": "NATIONAL",
        "qualifying_cf": NATIONAL_QUALIFYING_CF,
        "non_qualifying_cf": NATIONAL_NON_QUALIFYING_CF,
    })

    print(f"  Parsed {len(rows)} rows ({len(rows) - 1} localities + 1 national).")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load CMS anesthesia conversion factors into the Clarobill database."
    )
    parser.add_argument(
        "--file",
        type=Path,
        required=True,
        help="Path to the CMS anesthesia CF CSV file",
    )
    parser.add_argument(
        "--year",
        type=int,
        required=True,
        help="Year the schedule applies to (e.g. 2026)",
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

    print(f"Loading anesthesia CFs from {args.file.name}...")
    rows = load_from_file(args.file, args.year)

    inserted = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        client.table("cms_anesthesia_cf").upsert(
            batch, on_conflict="year,contractor,locality_number"
        ).execute()
        inserted += len(batch)
        print(f"  Upserted {inserted}/{len(rows)} rows...")

    print(f"Done. {inserted} anesthesia CF rows loaded for year {args.year}.")


if __name__ == "__main__":
    main()
