"""Load CMS Ambulance Fee Schedule ZIP-to-locality mappings into the database.

Source files: AFS ZIP5 fixed-width files (ZIP5_<period>_FINAL.txt)
Download: https://www.cms.gov/medicare/payment/ambulance-services/ambulance-fee-schedule

These files map every US ZIP code to its CMS ambulance MAC carrier/locality and
rural designation. The rural_indicator determines which rate column to use:
  ''  = urban    → use urban_rate  from cms_ambulance_rates
  'R' = rural    → use rural_rate  from cms_ambulance_rates
  'B' = super rural → use super_rural_rate from cms_ambulance_rates

File format: fixed-width ASCII, one record per ZIP code.

  Field               Bytes (1-indexed)   Length
  State               1–2                 2
  ZIP Code            3–7                 5
  Carrier             8–12                5
  Pricing Locality    13–14               2
  Rural Indicator     15                  1     blank, 'R', or 'B'
  Year/Quarter        76–80               5     YYYYQ (e.g. 20254 = 2025 Q4)

NOTE: The files are published with a DEC effective date and take effect Jan 1 of
the following year. Load them with --effective-from set to Jan 1 of the year the
rates apply:
  ZIP5_DEC2024_FINAL.txt → --effective-from 2025-01-01
  ZIP5_DEC2025_FINAL.txt → --effective-from 2026-01-01

The 2026 file (ZIP5_APR2026.txt) is effective Apr 1, 2026.

The script is re-runnable — it upserts on (zip5, effective_from).

Usage:
  python scripts/load_ambulance_zip_locality.py \\
    --file data/cms/ambulance-fee-schedule/2025/ZIP5_DEC2025_FINAL.txt \\
    --effective-from 2026-01-01
"""

import argparse
import os
import sys
import uuid
from datetime import date
from pathlib import Path

from supabase import create_client

BATCH_SIZE = 1000

# Fixed-width byte positions (0-indexed, matching Python slice notation)
_STATE_SLICE = slice(0, 2)
_ZIP5_SLICE = slice(2, 7)
_CARRIER_SLICE = slice(7, 12)
_LOCALITY_SLICE = slice(12, 14)
_RURAL_INDICATOR_SLICE = slice(14, 15)


def load_from_file(path: Path, effective_from: date) -> list[dict]:
    """Parse a ZIP5 fixed-width file into rows for cms_ambulance_zip_locality.

    Args:
        path: Path to the ZIP5 fixed-width file.
        effective_from: The date these mappings became effective (e.g. date(2026, 1, 1)).

    Returns:
        List of dicts ready for upsert.
    """
    effective_from_str = effective_from.isoformat()
    rows: list[dict] = []
    skipped = 0

    with path.open(encoding="latin-1") as f:
        for line in f:
            if len(line) < 15:
                # Skip lines too short to contain required fields
                skipped += 1
                continue

            state = line[_STATE_SLICE].strip()
            zip5 = line[_ZIP5_SLICE].strip()
            carrier = line[_CARRIER_SLICE].strip()
            locality = line[_LOCALITY_SLICE].strip()
            # Rural indicator: ' ' (blank) = urban, 'R' = rural, 'B' = super rural
            rural_indicator = line[_RURAL_INDICATOR_SLICE].strip()

            if not state or not zip5 or not carrier or not locality:
                skipped += 1
                continue

            rows.append({
                "id": str(uuid.uuid4()),
                "effective_from": effective_from_str,
                "state": state,
                "zip5": zip5,
                "carrier": carrier,
                "pricing_locality": locality,
                "rural_indicator": rural_indicator,  # '' when blank (urban)
            })

    print(
        f"  Parsed {len(rows)} ZIP locality rows "
        f"(skipped {skipped}, effective_from={effective_from_str})."
    )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load CMS Ambulance Fee Schedule ZIP-to-locality mappings."
    )
    parser.add_argument(
        "--file",
        type=Path,
        required=True,
        help="Path to the ZIP5 fixed-width file",
    )
    parser.add_argument(
        "--effective-from",
        type=date.fromisoformat,
        required=True,
        dest="effective_from",
        help=(
            "Effective date in YYYY-MM-DD format. DEC files take effect Jan 1 of the "
            "following year (e.g. ZIP5_DEC2025_FINAL.txt → 2026-01-01)."
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

    print(f"Loading ZIP locality data from {args.file.name} (effective_from={args.effective_from})...")
    rows = load_from_file(args.file, args.effective_from)

    total = len(rows)
    upserted = 0
    for i in range(0, total, BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        client.table("cms_ambulance_zip_locality").upsert(
            batch, on_conflict="zip5,effective_from"
        ).execute()
        upserted += len(batch)
        print(f"  Upserted {upserted}/{total} rows...")

    print(f"Done. {upserted} ZIP locality rows loaded for effective_from={args.effective_from}.")


if __name__ == "__main__":
    main()
