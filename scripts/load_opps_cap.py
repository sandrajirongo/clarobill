"""Load CMS OPPS cap rates into the database.

Source files: "OPPSCAP_<period>.csv" — Outpatient Prospective Payment System cap rates
Download from: https://www.cms.gov/medicare/payment/prospective-payment-systems/hospital-outpatient

Each row contains the Medicare payment cap for a HCPC code in a specific MAC locality.
The locality_code is constructed as CARRIER (5 chars) + LOCALITY (2 chars), matching
the format used by cms_county_locality and cms_localities.

PROCSTAT values in the source data:
  A = active (APC-priced)
  C = capped (OPPS payment is capped at this amount)

Usage:
  python scripts/load_opps_cap.py --file data/cms/opps/2026/OPPSCAP_Apr.csv --year 2026
  python scripts/load_opps_cap.py --file data/cms/opps/2025/OPPSCAP_APR.csv --year 2025
"""

import argparse
import csv
import os
import sys
import uuid
from pathlib import Path

from supabase import create_client

BATCH_SIZE = 500


def load_from_file(path: Path, year: int) -> list[dict]:
    """Parse an OPPSCAP CSV into rows ready for upsert into cms_opps_cap.

    Args:
        path: Path to the OPPSCAP CSV file.
        year: Calendar year to tag each row with.

    Returns:
        List of dicts ready for upsert.
    """
    rows: list[dict] = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            hcpc = row["HCPCS"].strip()
            carrier = row["CARRIER"].strip()
            locality = row["LOCALITY"].strip()

            if not hcpc or not carrier or not locality:
                continue

            locality_code = carrier + locality  # e.g. "0111205" = carrier 01112, locality 05

            facility_raw = row["FACILITY PRICE"].strip()
            # CMS headers have a typo: "NON-FACILTY PRICE" (missing an I)
            non_facility_raw = (row.get("NON-FACILTY PRICE") or row.get("NON-FACILITY PRICE", "")).strip()

            rows.append({
                "id": str(uuid.uuid4()),
                "year": year,
                "hcpc": hcpc,
                "modifier": row["MOD"].strip(),
                "proc_stat": row["PROCSTAT"].strip() or None,
                "locality_code": locality_code,
                "facility_price": float(facility_raw) if facility_raw else None,
                "non_facility_price": float(non_facility_raw) if non_facility_raw else None,
            })

    print(f"  Parsed {len(rows)} OPPS cap rows.")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load CMS OPPS cap rates into the ClaroBill database."
    )
    parser.add_argument("--file", type=Path, required=True, help="Path to the OPPSCAP CSV file")
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

    print(f"Loading OPPS cap rates from {args.file.name} (year={args.year})...")
    rows = load_from_file(args.file, args.year)

    # Clear only this year's rows before reload (safe to re-run)
    client.table("cms_opps_cap").delete().eq("year", args.year).execute()
    print(f"  Cleared existing year={args.year} rows.")

    inserted = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        client.table("cms_opps_cap").insert(batch).execute()
        inserted += len(batch)
        print(f"  Inserted {inserted}/{len(rows)} rows...")

    print(f"Done. {inserted} OPPS cap rows loaded for year={args.year}.")


if __name__ == "__main__":
    main()
