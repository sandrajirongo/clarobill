"""Load CMS Physician Fee Schedule data into the database.

Downloads two files from https://pfs.data.cms.gov/:
  - Indicators file  (e.g. indicators2026-03-18-2026.csv)
  - Localities file  (e.g. localities2026-01-01-2026.csv)

The indicators file contains RVU components and the conversion factor for each
HCPC code. The localities file contains GPCI multipliers per MAC locality.

Together they allow computing locality-adjusted Medicare rates:
  rate = (rvu_work * gpci_work + pe_rvu * gpci_pe + rvu_mp * gpci_mp) * conv_fact

For the national rate, use locality code '0000000' where all GPCIs = 1.0, giving:
  national_rate = nfac_total_rvu * conv_fact

Usage:
  python scripts/load_cms_pfs.py \\
    --indicators /path/to/indicators2026-03-18-2026.csv \\
    --localities /path/to/localities2026-01-01-2026.csv

The script is re-runnable — it upserts on the unique constraints.
"""

import argparse
import csv
import os
import sys
import uuid
from pathlib import Path

from supabase import create_client

BATCH_SIZE = 500

# proc_stat values that are actively priced via the RVU formula.
# All others (I=inactive, B=bundled, J=anesthesia, etc.) are excluded from
# price outlier detection since they are not independently payable.
ACTIVE_PROC_STATS = {"A"}


def _float(value: str, default: float = 0.0) -> float:
    """Parse a CSV float value, returning default on empty or invalid input."""
    stripped = value.strip()
    if not stripped:
        return default
    try:
        return float(stripped)
    except ValueError:
        return default


def load_indicators(path: Path) -> list[dict]:
    """Parse the CMS PFS indicators CSV into rows for cms_pfs_indicators.

    Deduplicates by (year, hcpc, modifier) — when a code appears twice (CMS
    sometimes emits rows for both standard and anesthesia conversion factors),
    the row with the higher conv_fact is kept, which corresponds to the standard
    physician fee schedule rate (2026: $33.5675 vs $33.4009 for anesthesia).

    Args:
        path: Path to the indicators CSV file from pfs.data.cms.gov.

    Returns:
        List of dicts ready for upsert into cms_pfs_indicators.
    """
    seen: dict[tuple, dict] = {}  # (year, hcpc, modifier) → row

    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            hcpc = row["hcpc"].strip()
            modifier = row["modifier"].strip()
            year = int(row["year"].strip())

            key = (year, hcpc, modifier)
            record = {
                "id": str(uuid.uuid4()),
                "year": year,
                "hcpc": hcpc,
                "modifier": modifier,
                "sdesc": row["sdesc"].strip() or None,
                "proc_stat": row["proc_stat"].strip() or None,
                "rvu_work": _float(row["rvu_work"]),
                # full_nfac_pe = full (non-transitional) non-facility PE RVU
                "nfac_pe_rvu": _float(row["full_nfac_pe"]),
                "fac_pe_rvu": _float(row["full_fac_pe"]),
                "rvu_mp": _float(row["rvu_mp"]),
                "nfac_total_rvu": _float(row["full_nfac_total"]),
                "fac_total_rvu": _float(row["full_fac_total"]),
                "conv_fact": _float(row["conv_fact"]),
                "pctc": row["pctc"].strip() or None,
                "global_days": row["global"].strip() or None,
            }

            existing = seen.get(key)
            if existing is None or record["conv_fact"] > existing["conv_fact"]:
                # Preserve the uuid from an existing entry to keep upserts stable
                if existing is not None:
                    record["id"] = existing["id"]
                seen[key] = record

    rows = list(seen.values())
    print(f"  Parsed {len(rows)} unique indicator rows.")
    return rows


def load_localities(path: Path) -> list[dict]:
    """Parse the CMS PFS localities CSV into rows for cms_localities.

    Args:
        path: Path to the localities CSV file from pfs.data.cms.gov.

    Returns:
        List of dicts ready for upsert into cms_localities.
    """
    rows = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                "id": str(uuid.uuid4()),
                "year": int(row["year"].strip()),
                "locality_code": row["locality"].strip(),
                "locality_description": row["loc_description"].strip(),
                "mac": row["mac"].strip() or None,
                "mac_description": row["mac_description"].strip() or None,
                "gpci_work": _float(row["gpci_work"]),
                "gpci_pe": _float(row["gpci_pe"]),
                "gpci_mp": _float(row["gpci_mp"]),
            })
    print(f"  Parsed {len(rows)} locality rows.")
    return rows


def upsert_batches(client, table: str, rows: list[dict], conflict_cols: str) -> None:
    """Upsert rows in batches, printing progress."""
    total = len(rows)
    inserted = 0
    for i in range(0, total, BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        client.table(table).upsert(batch, on_conflict=conflict_cols).execute()
        inserted += len(batch)
        print(f"  Upserted {inserted}/{total} rows into {table}...")
    print(f"  Done — {inserted} rows loaded into {table}.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load CMS PFS indicators and localities into the Clarobill database."
    )
    parser.add_argument(
        "--indicators",
        type=Path,
        required=True,
        help="Path to the CMS PFS indicators CSV (e.g. indicators2026-03-18-2026.csv)",
    )
    parser.add_argument(
        "--localities",
        type=Path,
        required=True,
        help="Path to the CMS PFS localities CSV (e.g. localities2026-01-01-2026.csv)",
    )
    args = parser.parse_args()

    for label, path in [("indicators", args.indicators), ("localities", args.localities)]:
        if not path.exists():
            print(f"Error: {label} file not found: {path}", file=sys.stderr)
            sys.exit(1)

    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        print("Error: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set.", file=sys.stderr)
        sys.exit(1)

    client = create_client(supabase_url, supabase_key)

    print(f"Loading indicators from {args.indicators.name}...")
    indicators = load_indicators(args.indicators)
    upsert_batches(client, "cms_pfs_indicators", indicators, "year,hcpc,modifier")

    print(f"\nLoading localities from {args.localities.name}...")
    localities = load_localities(args.localities)
    upsert_batches(client, "cms_localities", localities, "year,locality_code")

    print("\nAll CMS PFS data loaded successfully.")
    active_count = sum(1 for r in indicators if r.get("proc_stat") in ACTIVE_PROC_STATS)
    print(f"  Active (proc_stat=A) codes: {active_count} / {len(indicators)}")
    print(f"  Localities: {len(localities)}")


if __name__ == "__main__":
    main()
