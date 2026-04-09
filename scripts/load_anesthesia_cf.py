"""Load CMS locality-adjusted anesthesia conversion factors into the database.

Handles all file formats published by CMS from 2020 onwards:

  2020-2022  ASCII / tab-delimited  — single CF column
  2023-2025  UTF-16LE / tab-delimited — single CF column
  2026+      UTF-8 / CSV            — separate qualifying + non-qualifying CF columns

For years with a mid-year CF update (e.g. 2024), run the loader twice with
different --effective-from dates:

  python scripts/load_anesthesia_cf.py \\
    --file "...Jan 1-March 8.txt" --year 2024 --effective-from 2024-01-01

  python scripts/load_anesthesia_cf.py \\
    --file "...March 9-December 31.txt" --year 2024 --effective-from 2024-03-09

For all other years:

  python scripts/load_anesthesia_cf.py \\
    --file "...Sheet 1.txt" --year 2025 --effective-from 2025-01-01

Download source: https://www.cms.gov/medicare/payment/fee-schedules/physician
"""

import argparse
import csv
import os
import re
import sys
import uuid
from datetime import date
from pathlib import Path

from supabase import create_client

BATCH_SIZE = 500

# Synthetic national row keys — used as the default when a bill's locality is unknown.
NATIONAL_CONTRACTOR = "NATL"
NATIONAL_LOCALITY_NUMBER = "NATL"
NATIONAL_LOCALITY_NAME = "NATIONAL"


def _detect_encoding(path: Path) -> str:
    """Detect file encoding by checking for a UTF-16 BOM."""
    with path.open("rb") as f:
        bom = f.read(2)
    if bom in (b"\xff\xfe", b"\xfe\xff"):
        return "utf-16"        # Python auto-detects LE vs BE from the BOM
    return "utf-8-sig"         # Handles plain ASCII and UTF-8 with/without BOM


def _read_lines(path: Path) -> list[str]:
    encoding = _detect_encoding(path)
    with path.open(encoding=encoding, newline="") as f:
        return f.readlines()


def _find_header_idx(lines: list[str]) -> int:
    """Find the index of the column header row (starts with 'Contractor')."""
    for i, line in enumerate(lines):
        if line.strip().lower().startswith("contractor"):
            return i
    raise ValueError("Could not locate header row — expected a line starting with 'Contractor'")


def _extract_national_cf_from_header(column_name: str) -> float | None:
    """Parse the national CF value embedded in a column name.

    CMS column names look like: "National Anes CF of 21.1249"
    or "Non-Qualifying APM National Anes CF (...) of 20.49754"
    """
    match = re.search(r"(\d+\.\d+)\s*$", column_name.strip())
    if match:
        return float(match.group(1))
    # Also handle formats like "National Anes CF of 20.4349" where value is mid-string
    match = re.search(r"of\s+(\d+\.\d+)", column_name, re.IGNORECASE)
    return float(match.group(1)) if match else None


def load_from_file(path: Path, year: int, effective_from: date) -> list[dict]:
    """Parse a CMS anesthesia CF file into rows for upsert into cms_anesthesia_cf.

    Handles:
    - ASCII tab-delimited (2020-2022)
    - UTF-16LE tab-delimited (2023-2025), including 2025's quoted multiline header
    - CSV comma-delimited (2026+) with dual qualifying/non-qualifying CF columns
    """
    lines = _read_lines(path)
    header_idx = _find_header_idx(lines)

    delimiter = "," if path.suffix.lower() == ".csv" else "\t"
    reader = csv.DictReader(lines[header_idx:], delimiter=delimiter)

    # Identify CF columns from the header by substring matching (case-insensitive)
    fieldnames = reader.fieldnames or []
    non_qual_col: str | None = None
    qual_col: str | None = None
    national_non_qual_cf: float | None = None
    national_qual_cf: float | None = None

    for col in fieldnames:
        col_lower = col.strip().lower()
        if "non-qualifying" in col_lower or "non qualifying" in col_lower:
            non_qual_col = col
            national_non_qual_cf = _extract_national_cf_from_header(col)
        elif "qualifying" in col_lower:
            # Qualifying APM column (2026+); must come after the non-qualifying check
            qual_col = col
            national_qual_cf = _extract_national_cf_from_header(col)
        elif "national anes cf" in col_lower:
            # Pre-2026 single CF column — treat as non-qualifying
            non_qual_col = col
            national_non_qual_cf = _extract_national_cf_from_header(col)

    if non_qual_col is None:
        print(
            f"Error: could not identify a CF column in {path.name}.\n"
            f"  Columns found: {fieldnames}",
            file=sys.stderr,
        )
        sys.exit(1)

    rows: list[dict] = []

    for row in reader:
        contractor = row.get("Contractor", "").strip().rstrip("*")
        locality = row.get("Locality", "").strip()
        name = row.get("Locality Name", "").strip()

        if not contractor or not locality or not name:
            continue

        try:
            non_qual_cf = float(str(row[non_qual_col]).strip())
        except (ValueError, KeyError):
            print(f"  Skipping {name}: could not parse non-qualifying CF", file=sys.stderr)
            continue

        # For pre-2026 files there is no separate qualifying CF column.
        # Store the same value in both columns — the distinction didn't exist yet.
        if qual_col and qual_col in row:
            try:
                qual_cf = float(str(row[qual_col]).strip())
            except (ValueError, KeyError):
                qual_cf = non_qual_cf
        else:
            qual_cf = non_qual_cf

        rows.append({
            "id": str(uuid.uuid4()),
            "year": year,
            "effective_from": effective_from.isoformat(),
            "contractor": contractor,
            "locality_number": locality.zfill(2),
            "locality_name": name,
            "qualifying_cf": qual_cf,
            "non_qualifying_cf": non_qual_cf,
        })

    if national_non_qual_cf is None:
        print(
            f"Warning: could not extract national CF from column name '{non_qual_col}'. "
            "Skipping synthetic NATIONAL row.",
            file=sys.stderr,
        )
    else:
        # Synthetic national row — used as default when a bill's locality is unknown.
        rows.append({
            "id": str(uuid.uuid4()),
            "year": year,
            "effective_from": effective_from.isoformat(),
            "contractor": NATIONAL_CONTRACTOR,
            "locality_number": NATIONAL_LOCALITY_NUMBER,
            "locality_name": NATIONAL_LOCALITY_NAME,
            "qualifying_cf": national_qual_cf if national_qual_cf is not None else national_non_qual_cf,
            "non_qualifying_cf": national_non_qual_cf,
        })

    print(f"  Parsed {len(rows)} rows ({len(rows) - 1} localities + 1 national).")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load CMS anesthesia conversion factors into the MedScan database."
    )
    parser.add_argument("--file", type=Path, required=True, help="Path to the CF file")
    parser.add_argument("--year", type=int, required=True, help="Calendar year (e.g. 2025)")
    parser.add_argument(
        "--effective-from",
        type=date.fromisoformat,
        required=True,
        metavar="YYYY-MM-DD",
        help=(
            "Date from which these CF values apply. "
            "Use YYYY-01-01 for standard full-year files. "
            "For mid-year updates (e.g. 2024 March correction), use the actual effective date."
        ),
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

    print(f"Loading anesthesia CFs from {args.file.name} (year={args.year}, effective_from={args.effective_from})...")
    rows = load_from_file(args.file, args.year, args.effective_from)

    inserted = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        client.table("cms_anesthesia_cf").upsert(
            batch, on_conflict="year,contractor,locality_number,effective_from"
        ).execute()
        inserted += len(batch)
        print(f"  Upserted {inserted}/{len(rows)} rows...")

    print(f"Done. {inserted} anesthesia CF rows loaded for year={args.year} effective_from={args.effective_from}.")


if __name__ == "__main__":
    main()
