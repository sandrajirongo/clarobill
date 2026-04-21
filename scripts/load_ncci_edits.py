"""Load CMS NCCI Procedure-to-Procedure (PTP) edit pairs into the database.

Supports two file formats:

  MCD (tab-delimited, Q1 data, .txt files):
    Multi-line preamble before the header row. Header starts with "Col1\t".
    Columns: Col1, Col2, EffDt, DelDt, ModifierIndicator, PTP Edit Rationale

  MCR (tab-delimited, same format as MCD — no CSV MCR PTP files shipped by CMS):
    Same format; use --payer-type medicare to tag rows appropriately.

Usage:
  # Load MCD PTP Practitioner file as Medicare practitioner edits
  python scripts/load_ncci_edits.py \
      --file data/ncci/MCD-PTP-PractitionerServices-Effective_01012026.txt \
      --service-type practitioner --payer-type medicare

  # Load MCD PTP Outpatient file
  python scripts/load_ncci_edits.py \
      --file data/ncci/MCD-PTP-OutpatientHospitalServices-Effective_01012026.txt \
      --service-type outpatient --payer-type medicare

  # Load MCD PTP DME file
  python scripts/load_ncci_edits.py \
      --file data/ncci/MCD-PTP-DMEServices-Effective_01012026.txt \
      --service-type dme --payer-type medicare

  # Load sample data for dev/testing
  python scripts/load_ncci_edits.py --sample
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
VALID_SERVICE_TYPES = ("practitioner", "outpatient", "dme")
VALID_PAYER_TYPES = ("medicare", "medicaid")


def parse_cms_date(value: str) -> date | None:
    """Parse a CMS date string (YYYYMMDD). Returns None for the 'active' sentinel."""
    value = value.strip()
    if not value or value in ("20991231", "99991231"):
        return None
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        return None


def load_from_file(path: Path, service_type: str, payer_type: str) -> list[dict]:
    """Parse a CMS NCCI PTP tab-delimited file into dicts ready for DB insertion.

    Skips the preamble by reading until the header row (Col1 or "Column 1 Code").
    Both MCD .txt and any equivalent tab-delimited format are supported.
    """
    rows = []
    with path.open(newline="", encoding="latin-1") as f:
        reader = csv.reader(f, delimiter="\t")
        header_found = False
        for line_num, row in enumerate(reader, start=1):
            if not row:
                continue

            # Detect the header row. CMS ships two formats:
            #   Older: standalone header row where row[0] is exactly "Col1"
            #   2026+: header embedded inside a quoted preamble cell, so row[0]
            #          is a long description that contains "\nCol1\tCol2\t..." —
            #          check the full row text for that pattern.
            if not header_found:
                row_text = "\t".join(row).lower()
                if row_text.strip().startswith("col1") or "\ncol1\t" in row_text:
                    header_found = True
                continue  # skip everything up to and including the header

            if len(row) < 5:
                print(f"  Skipping malformed row {line_num}: {row}", file=sys.stderr)
                continue

            col1 = row[0].strip().zfill(5)
            col2 = row[1].strip().zfill(5)
            effective = parse_cms_date(row[2])
            deletion = parse_cms_date(row[3])

            # Modifier indicator may be quoted and have trailing label text
            try:
                modifier_indicator = int(row[4].strip().split()[0])
            except (ValueError, IndexError):
                modifier_indicator = 9

            if not effective:
                continue  # effective date is required

            rows.append({
                "id": str(uuid.uuid4()),
                "column_one_code": col1,
                "column_two_code": col2,
                "effective_date": effective.isoformat(),
                "deletion_date": deletion.isoformat() if deletion else None,
                "modifier_indicator": modifier_indicator,
                "service_type": service_type,
                "payer_type": payer_type,
            })
    return rows


def load_sample() -> list[dict]:
    """Returns a small sample of known NCCI pairs for dev/testing."""
    pairs = [
        ("99213", "36415", "20200101", None, 1),
        ("99214", "36415", "20200101", None, 1),
        ("27447", "27370", "20200101", None, 1),
        ("99291", "99213", "20200101", None, 0),
        ("99291", "99214", "20200101", None, 0),
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
            "service_type": "practitioner",
            "payer_type": "medicare",
        }
        for col1, col2, eff, del_date, mod in pairs
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Load CMS NCCI PTP edit pairs into ClaroBill DB")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", type=Path, help="Path to CMS NCCI PTP tab-delimited .txt file")
    group.add_argument("--sample", action="store_true", help="Load sample data for dev/testing")
    parser.add_argument(
        "--service-type",
        choices=VALID_SERVICE_TYPES,
        default="practitioner",
        help="Bill service type the edits apply to (default: practitioner)",
    )
    parser.add_argument(
        "--payer-type",
        choices=VALID_PAYER_TYPES,
        default="medicare",
        help="Insurance programme the NCCI file was published for (default: medicare)",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help=(
            "Delete all existing rows for the given (service_type, payer_type) "
            "before inserting. Use when refreshing from a new quarterly file so "
            "that pairs removed in the new release are not left in the database."
        ),
    )
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
        rows = load_from_file(args.file, args.service_type, args.payer_type)
        print(
            f"Parsed {len(rows)} NCCI PTP pairs from {args.file.name} "
            f"(service_type={args.service_type}, payer_type={args.payer_type})"
        )

    # When --replace is set, delete all existing rows for this (service_type, payer_type)
    # before inserting. The CMS PTP files are full snapshots of currently active edits,
    # so pairs absent from the new file should be removed, not kept from previous loads.
    if args.replace and not args.sample:
        print(f"  Deleting existing rows for service_type={args.service_type}, payer_type={args.payer_type}…")
        client.table("ncci_edit_pairs").delete().match(
            {"service_type": args.service_type, "payer_type": args.payer_type}
        ).execute()
        print("  Deleted.")

    seen: dict[tuple[str, str], int] = {}
    for i, row in enumerate(rows):
        seen[(row["column_one_code"], row["column_two_code"])] = i
    rows = [rows[i] for i in sorted(seen.values())]

    inserted = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        client.table("ncci_edit_pairs").upsert(
            batch,
            on_conflict="column_one_code,column_two_code,service_type,payer_type",
        ).execute()
        inserted += len(batch)
        print(f"  Upserted {inserted}/{len(rows)} rows...")

    print(f"Done. {inserted} NCCI PTP edit pairs loaded.")


if __name__ == "__main__":
    main()
