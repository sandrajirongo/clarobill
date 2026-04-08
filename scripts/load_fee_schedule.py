"""Load CMS Medicare Physician Fee Schedule into the database.

Download the annual pricing file from CMS:
  https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files

1. Click the current year's "Physician Fee Schedule" ZIP file
2. Extract the ZIP — look for a file named like "PPRRVU25.txt" (tab-delimited)
3. Also download the "Addendum B" file which has the national payment amounts

Alternatively, CMS provides a simplified pricing file through their look-up tool
export. This script accepts a CSV in this format (with header row):

  hcpcs_code, modifier, locality_code, facility_rate, non_facility_rate, year

You can produce this CSV by exporting from the CMS Physician Fee Schedule
Look-Up Tool: https://www.cms.gov/medicare/payment/fee-schedules/physician/lookup-tool

OR use the --sample flag to load a small set of common codes for dev/testing.

Usage:
  python scripts/load_fee_schedule.py --file /path/to/fee_schedule.csv --year 2025
  python scripts/load_fee_schedule.py --sample --year 2025
"""

import argparse
import csv
import os
import sys
import uuid
from pathlib import Path

from supabase import create_client

BATCH_SIZE = 500

# National locality code used when the file doesn't include locality
NATIONAL_LOCALITY = "0000"

# Common CPT codes used in sample data — realistic office and lab rates
SAMPLE_RATES = [
    ("99201", "0000", 46.62, 46.62),
    ("99202", "0000", 74.25, 74.25),
    ("99203", "0000", 111.97, 111.97),
    ("99204", "0000", 167.56, 167.56),
    ("99205", "0000", 211.33, 211.33),
    ("99211", "0000", 24.67, 24.67),
    ("99212", "0000", 55.15, 55.15),
    ("99213", "0000", 92.78, 92.78),
    ("99214", "0000", 135.59, 135.59),
    ("99215", "0000", 180.50, 180.50),
    ("85025", "0000", 11.32, 11.32),   # Complete blood count
    ("85027", "0000", 9.85, 9.85),     # CBC without differential
    ("36415", "0000", 3.20, 3.20),     # Routine venipuncture
    ("80053", "0000", 15.44, 15.44),   # Comprehensive metabolic panel
    ("80061", "0000", 20.17, 20.17),   # Lipid panel
    ("93000", "0000", 19.78, 19.78),   # Electrocardiogram
    ("71046", "0000", 43.21, 43.21),   # Chest X-ray, 2 views
    ("27447", "0000", 1289.54, 1289.54),  # Total knee replacement
    ("27370", "0000", 102.33, 102.33),    # Injection into knee
    ("99291", "0000", 271.44, 271.44),    # Critical care, first hour
]


def load_from_file(path: Path, year: int) -> list[dict]:
    """Parse a simplified CSV fee schedule file into dicts for DB insertion."""
    rows = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for line_num, row in enumerate(reader, start=2):
            hcpcs = row.get("hcpcs_code", "").strip().zfill(5)
            locality = row.get("locality_code", NATIONAL_LOCALITY).strip()
            if not hcpcs:
                print(f"  Skipping row {line_num}: missing hcpcs_code", file=sys.stderr)
                continue
            try:
                facility_rate = float(row.get("facility_rate", "0").replace(",", ""))
                non_facility_rate = float(row.get("non_facility_rate", "0").replace(",", ""))
            except ValueError:
                print(f"  Skipping row {line_num}: invalid rate values for {hcpcs}", file=sys.stderr)
                continue

            rows.append({
                "id": str(uuid.uuid4()),
                "cpt_code": hcpcs,
                "locality_code": locality,
                "facility_rate": facility_rate,
                "non_facility_rate": non_facility_rate,
                "year": year,
                "_modifier": row.get("modifier", "").strip(),
            })

    # Deduplicate by (cpt_code, locality_code, year) — the DB unique constraint.
    # Prefer the base code row (empty modifier) over modifier variants since we
    # want the standard rate for outlier detection, not a modified rate.
    seen: dict[tuple, dict] = {}
    for row in rows:
        key = (row["cpt_code"], row["locality_code"], row["year"])
        existing = seen.get(key)
        if existing is None or (existing["_modifier"] != "" and row["_modifier"] == ""):
            seen[key] = row

    deduped = []
    for row in seen.values():
        row.pop("_modifier")
        deduped.append(row)

    print(f"  Deduplicated {len(rows)} rows → {len(deduped)} unique codes.")
    return deduped


def load_sample(year: int) -> list[dict]:
    """Returns national rates for common CPT codes for dev/testing."""
    return [
        {
            "id": str(uuid.uuid4()),
            "cpt_code": cpt,
            "locality_code": locality,
            "facility_rate": facility,
            "non_facility_rate": non_facility,
            "year": year,
        }
        for cpt, locality, facility, non_facility in SAMPLE_RATES
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Load CMS Medicare fee schedule into Clarobill DB")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", type=Path, help="Path to the fee schedule CSV file")
    group.add_argument("--sample", action="store_true", help="Load sample rates for dev/testing")
    parser.add_argument(
        "--year", type=int, required=True, help="Year the fee schedule applies to (e.g. 2025)"
    )
    args = parser.parse_args()

    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        print("Error: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set.", file=sys.stderr)
        sys.exit(1)

    client = create_client(supabase_url, supabase_key)

    if args.sample:
        rows = load_sample(args.year)
        print(f"Loaded {len(rows)} sample rates for year {args.year}.")
    else:
        if not args.file.exists():
            print(f"Error: File not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        rows = load_from_file(args.file, args.year)
        print(f"Parsed {len(rows)} fee schedule rows from {args.file.name}")

    # Upsert in batches — re-runnable; updates rates if the schedule is corrected mid-year
    inserted = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        client.table("medicare_fee_schedule").upsert(
            batch, on_conflict="cpt_code,locality_code,year"
        ).execute()
        inserted += len(batch)
        print(f"  Upserted {inserted}/{len(rows)} rows...")

    print(f"Done. {inserted} fee schedule rows loaded for year {args.year}.")


if __name__ == "__main__":
    main()
