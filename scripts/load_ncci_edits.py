"""Load CMS NCCI Procedure-to-Procedure (PTP) edit pairs into the database.

Download the quarterly file from CMS:
  https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-procedure-to-procedure-edits

Select "NCCI PTP Edits" → download the ZIP → extract the CSV file.
The CSV filename looks like: "NCCI_PT_to_PT_XXQYYYY.csv"

Expected CSV columns (no header row in CMS file):
  col 1: Column 1 HCPCS code  (5-digit CPT/HCPCS)
  col 2: Column 2 HCPCS code  (5-digit CPT/HCPCS)
  col 3: Effective date        (YYYYMMDD)
  col 4: Deletion date         (YYYYMMDD or 20991231 = still active)
  col 5: Modifier indicator    (0 = no modifier; 1 = modifier may allow; 9 = N/A)

Usage:
  python scripts/load_ncci_edits.py --file /path/to/NCCI_PT_to_PT_XXQYYYY.csv
  python scripts/load_ncci_edits.py --sample   # loads a small sample for dev/testing
"""

import argparse
import csv
import os
import sys
import uuid
from datetime import date, datetime
from pathlib import Path

from supabase import create_client

BATCH_SIZE = 500
ACTIVE_DATE = date(2099, 12, 31)  # CMS sentinel value meaning "not yet deleted"


def parse_cms_date(value: str) -> date | None:
    """Parse a CMS date string (YYYYMMDD). Returns None for the 'active' sentinel."""
    value = value.strip()
    if not value or value in ("20991231", "99991231"):
        return None
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        return None


def load_from_file(path: Path) -> list[dict]:
    """Parse CMS NCCI CSV into dicts ready for DB insertion."""
    rows = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for line_num, row in enumerate(reader, start=1):
            # Skip any header row CMS may include
            if line_num == 1 and not row[0].strip().isdigit():
                continue
            if len(row) < 5:
                print(f"  Skipping malformed row {line_num}: {row}", file=sys.stderr)
                continue

            col1 = row[0].strip().zfill(5)
            col2 = row[1].strip().zfill(5)
            effective = parse_cms_date(row[2])
            deletion = parse_cms_date(row[3])
            try:
                modifier_indicator = int(row[4].strip())
            except ValueError:
                modifier_indicator = 9

            if not effective:
                continue  # Effective date is required

            rows.append({
                "id": str(uuid.uuid4()),
                "column_one_code": col1,
                "column_two_code": col2,
                "effective_date": effective.isoformat(),
                "deletion_date": deletion.isoformat() if deletion else None,
                "modifier_indicator": modifier_indicator,
            })
    return rows


def load_sample() -> list[dict]:
    """Returns a small sample of known NCCI pairs for dev/testing without the full file."""
    pairs = [
        # Office visit bundles routine venipuncture
        ("99213", "36415", "20200101", None, 1),
        ("99214", "36415", "20200101", None, 1),
        # Total knee replacement bundles knee injection
        ("27447", "27370", "20200101", None, 1),
        # Critical care bundles many E&M codes
        ("99291", "99213", "20200101", None, 0),
        ("99291", "99214", "20200101", None, 0),
        # Colonoscopy bundles biopsy
        ("45378", "45380", "20200101", None, 1),
    ]
    return [
        {
            "id": str(uuid.uuid4()),
            "column_one_code": col1,
            "column_two_code": col2,
            "effective_date": datetime.strptime(eff, "%Y%m%d").date().isoformat(),
            "deletion_date": del_date,
            "modifier_indicator": mod,
        }
        for col1, col2, eff, del_date, mod in pairs
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Load CMS NCCI edit pairs into MedScan DB")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", type=Path, help="Path to the CMS NCCI CSV file")
    group.add_argument("--sample", action="store_true", help="Load sample data for dev/testing")
    args = parser.parse_args()

    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        print("Error: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set.", file=sys.stderr)
        sys.exit(1)

    client = create_client(supabase_url, supabase_key)

    if args.sample:
        rows = load_sample()
        print(f"Loaded {len(rows)} sample NCCI pairs.")
    else:
        if not args.file.exists():
            print(f"Error: File not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        rows = load_from_file(args.file)
        print(f"Parsed {len(rows)} NCCI pairs from {args.file.name}")

    # Upsert in batches — re-runnable without duplicates
    inserted = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        client.table("ncci_edit_pairs").upsert(
            batch, on_conflict="column_one_code,column_two_code"
        ).execute()
        inserted += len(batch)
        print(f"  Upserted {inserted}/{len(rows)} rows...")

    print(f"Done. {inserted} NCCI edit pairs loaded.")


if __name__ == "__main__":
    main()
