"""Load CMS anesthesia base units per CPT code into the database.

Source files:
  CY 2018: cms1676f_cy_2018_anesthesia_base_units.txt  (valid for 2018-2021)
  CY 2022: Section 508 compliant version of CY_2022_Anesthesia_Base_Units_110921.txt  (valid 2022+)

File format: ASCII, tab-delimited, 3-row multi-line header then one row per CPT code.

Usage:
  python scripts/load_anesthesia_base_units.py \\
    --file data/cms/anesthesia-base-units/2018/cms1676f_cy_2018_anesthesia_base_units.txt \\
    --effective-year 2018

  python scripts/load_anesthesia_base_units.py \\
    --file "data/cms/anesthesia-base-units/2022/Section 508 compliant version of CY_2022_Anesthesia_Base_Units_110921.txt" \\
    --effective-year 2022
"""

import argparse
import os
import sys
import uuid
from pathlib import Path

from supabase import create_client

BATCH_SIZE = 500


def load_from_file(path: Path, effective_year: int) -> list[dict]:
    """Parse a CMS anesthesia base units file.

    The file has a 3-line multi-line header before data rows:
      Line 1: CODE\\t<year>
      Line 2: \\tBASE
      Line 3: \\tUNIT
      Line 4+: <cpt_code>\\t<base_units>

    CPT 01999 (unlisted procedure, base_units=0) is excluded — its reimbursement
    is carrier-determined and has no meaningful benchmark for outlier detection.
    """
    rows: list[dict] = []
    skipped_zero = 0

    with path.open(encoding="utf-8-sig") as f:
        lines = f.readlines()

    # Skip the 3-line header
    data_lines = lines[3:]

    for line in data_lines:
        line = line.strip()
        if not line:
            continue

        parts = line.split("\t")
        if len(parts) < 2:
            continue

        cpt_code = parts[0].strip()
        try:
            base_units = int(parts[1].strip())
        except ValueError:
            print(f"  Skipping {cpt_code}: non-integer base unit value '{parts[1].strip()}'", file=sys.stderr)
            continue

        if base_units == 0:
            # CPT 01999 (unlisted procedure) — no publishable benchmark
            skipped_zero += 1
            continue

        rows.append({
            "id": str(uuid.uuid4()),
            "cpt_code": cpt_code,
            "base_units": base_units,
            "effective_year": effective_year,
        })

    print(f"  Parsed {len(rows)} codes ({skipped_zero} zero-unit codes excluded).")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load CMS anesthesia base units into the MedScan database."
    )
    parser.add_argument("--file", type=Path, required=True, help="Path to the base units file")
    parser.add_argument(
        "--effective-year",
        type=int,
        required=True,
        metavar="YYYY",
        help="First calendar year these base units apply to (e.g. 2018 or 2022)",
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

    print(f"Loading anesthesia base units from {args.file.name} (effective_year={args.effective_year})...")
    rows = load_from_file(args.file, args.effective_year)

    inserted = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        client.table("cms_anesthesia_base_units").upsert(
            batch, on_conflict="cpt_code,effective_year"
        ).execute()
        inserted += len(batch)

    print(f"Done. {inserted} base unit rows loaded for effective_year={args.effective_year}.")


if __name__ == "__main__":
    main()
