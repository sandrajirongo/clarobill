"""Load CMS Ambulance Fee Schedule (AFS) rates into the database.

Source files: AFS Public Use Files (PUF) — one file per year/period.
Download: https://www.cms.gov/medicare/payment/ambulance-services/ambulance-fee-schedule

Each file contains pre-computed locality-adjusted rates for ambulance HCPCS codes
A0425–A0436. Rates are published annually (typically effective January 1).

Two delimiters are used across years (column order varies independently):

  Tab-separated:   2020, 2021, 2022, 2023, 2026
  Comma-separated: 2024, 2025

Column order also varies but DictReader resolves fields by name, so it is handled
automatically regardless of delimiter.

Both formats have the same 10 columns (different order):
  CONTRACTOR/CARRIER, LOCALITY, HCPCS, RVU, GPCI,
  BASE RATE,
  URBAN BASE RATE / URBAN MILEAGE,
  RURAL BASE RATE / RURAL MILEAGE,
  RURAL BASE RATE / LOWEST QUARTILE   (super-rural; "n/a" for some codes),
  RURAL GROUND MILES 1-17*            (A0425 super-rural per-mile; "n/a" for others)

Rate fields contain dollar signs and commas (e.g. "$3,861.62"). They are stripped
before parsing. "n/a" values are stored as NULL.

Special handling for A0425 (ground mileage) super_rural_rate:
  The "RURAL BASE RATE / LOWEST QUARTILE" column is "n/a" for A0425, but the
  "RURAL GROUND MILES 1-17*" column has the elevated super-rural per-mile rate.
  We store that as super_rural_rate for A0425, giving the rules engine a meaningful
  benchmark for super-rural ground transport mileage.

Usage:
  python scripts/load_ambulance_rates.py \\
    --file data/cms/ambulance-fee-schedule/2026/508-compliant-version-of-AFS2026_PUF_ext.txt \\
    --effective-from 2026-01-01

  python scripts/load_ambulance_rates.py \\
    --file data/cms/ambulance-fee-schedule/2025/508-compliant-version-AFS2025_PUF_ext.csv \\
    --effective-from 2025-01-01

The script is re-runnable — it upserts on (effective_from, carrier, locality, hcpc).
"""

import argparse
import csv
import os
import sys
import uuid
from datetime import date
from pathlib import Path

from supabase import create_client

BATCH_SIZE = 500


def _parse_rate(value: str) -> float | None:
    """Strip dollar signs and commas from a CMS rate field and parse as float.

    Returns None for "n/a" or empty values.
    """
    stripped = value.strip().replace("$", "").replace(",", "").replace('"', "")
    if not stripped or stripped.lower() == "n/a":
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


def _detect_delimiter(path: Path) -> str:
    """Return the field delimiter used by an AFS PUF file: tab or comma.

    All years use one of these two delimiters. Tab is determined by the presence
    of a tab character in the header row — commas appear in field values too
    (dollar amounts like "$3,861.62"), so tab is the safer signal to check.

    Year breakdown:
      Tab (\\t): 2020, 2021, 2022, 2023, 2026
      Comma:     2024, 2025
    Column order varies independently of the delimiter — DictReader handles
    both orderings by name, so delimiter is the only thing we need to detect.
    """
    with path.open(encoding="utf-8-sig") as f:
        first_line = f.readline()
    return "\t" if "\t" in first_line else ","


def _parse_row(row: dict) -> dict | None:
    """Convert a DictReader row into a db-ready dict.

    Returns None if the row is missing required fields.
    """
    carrier = row.get("CONTRACTOR/CARRIER", "").strip()
    locality = row.get("LOCALITY", "").strip()
    hcpc = row.get("HCPCS", "").strip()

    if not carrier or not locality or not hcpc:
        return None

    # The "RURAL GROUND MILES 1-17*" column name may have a trailing asterisk
    # or differ slightly between years — match by prefix.
    rural_miles_key = next(
        (k for k in row if k.strip().startswith("RURAL GROUND MILES")), None
    )

    urban_rate = _parse_rate(row.get("URBAN BASE RATE / URBAN MILEAGE", ""))
    rural_rate = _parse_rate(row.get("RURAL BASE RATE / RURAL MILEAGE", ""))
    quartile_rate = _parse_rate(row.get("RURAL BASE RATE / LOWEST QUARTILE", ""))
    rural_miles_rate = _parse_rate(row[rural_miles_key]) if rural_miles_key else None

    # A0425 (ground mileage): lowest quartile col is n/a; use the rural miles rate instead.
    # All other codes: lowest quartile IS the super-rural rate.
    if hcpc == "A0425":
        super_rural_rate = rural_miles_rate
    else:
        super_rural_rate = quartile_rate

    return {
        "id": str(uuid.uuid4()),
        "carrier": carrier,
        "locality": locality,
        "hcpc": hcpc,
        "rvu": _parse_rate(row.get("RVU", "")),
        "gpci": _parse_rate(row.get("GPCI", "")),
        "base_rate": _parse_rate(row.get("BASE RATE", "")),
        "urban_rate": urban_rate,
        "rural_rate": rural_rate,
        "super_rural_rate": super_rural_rate,
    }


def load_from_file(path: Path, effective_from: date) -> list[dict]:
    """Parse an AFS PUF file into rows ready for upsert into cms_ambulance_rates.

    Args:
        path: Path to the AFS PUF file (TSV old format or CSV new format).
        effective_from: The date this release became effective (e.g. date(2026, 1, 1)).

    Returns:
        List of dicts ready for upsert.
    """
    effective_from_str = effective_from.isoformat()
    delimiter = _detect_delimiter(path)
    fmt = "TSV" if delimiter == "\t" else "CSV"

    rows: list[dict] = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        for raw in reader:
            # Strip whitespace from all keys and values to handle format variations
            cleaned = {k.strip(): v for k, v in raw.items()}
            record = _parse_row(cleaned)
            if record is None:
                continue
            record["effective_from"] = effective_from_str
            rows.append(record)

    print(f"  Parsed {len(rows)} ambulance rate rows ({fmt}, effective_from={effective_from_str}).")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load CMS Ambulance Fee Schedule rates into the ClaroBill database."
    )
    parser.add_argument(
        "--file",
        type=Path,
        required=True,
        help="Path to the AFS PUF file (.txt or .csv)",
    )
    parser.add_argument(
        "--effective-from",
        type=date.fromisoformat,
        required=True,
        dest="effective_from",
        help="Release effective date in YYYY-MM-DD format (e.g. 2026-01-01)",
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

    print(f"Loading ambulance rates from {args.file.name} (effective_from={args.effective_from})...")
    rows = load_from_file(args.file, args.effective_from)

    total = len(rows)
    upserted = 0
    for i in range(0, total, BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        client.table("cms_ambulance_rates").upsert(
            batch, on_conflict="effective_from,carrier,locality,hcpc"
        ).execute()
        upserted += len(batch)
        print(f"  Upserted {upserted}/{total} rows...")

    print(f"Done. {upserted} ambulance rate rows loaded for effective_from={args.effective_from}.")


if __name__ == "__main__":
    main()
