"""Load CMS Physician Fee Schedule data into the database.

Supports two file formats for the indicators file:

  API format (pfs.data.cms.gov, filename: indicators<date>.csv)
    Single lowercase header row; year embedded in each data row.
    Usage:
      python scripts/load_cms_pfs.py \\
        --indicators indicators2026-03-18-2026.csv \\
        --localities localities2026-01-01-2026.csv \\
        --effective-from 2026-01-01

  PPRRVU format (direct CMS download, filename: PPRRVU<YY>*.csv)
    Three preamble rows + two-row merged header; year/date NOT in the file.
    --effective-from is required.
    Usage:
      python scripts/load_cms_pfs.py \\
        --indicators PPRRVU25_APR.csv \\
        --localities localities2025.csv \\
        --effective-from 2025-04-01

--effective-from is the CMS release date: Jan 1, Apr 1, Jul 1, or Oct 1.
For the 2024 JANR correction, use the date the correction became effective.
Format is auto-detected from the indicators file header.

The localities file is always in API format (lowercase header row with year column).
GPCI values do not change mid-year, so localities only need to be loaded once per year.

Together they allow computing locality-adjusted Medicare rates:
  rate = (rvu_work * gpci_work + pe_rvu * gpci_pe + rvu_mp * gpci_mp) * conv_fact

For the national rate, use locality code '0000000' where all GPCIs = 1.0, giving:
  national_rate = nfac_total_rvu * conv_fact

The script is re-runnable — it upserts on the unique constraints.
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


def _is_pprrvu_format(path: Path) -> bool:
    """Return True if the indicators file is in PPRRVU (direct CMS download) format.

    PPRRVU files have a multi-row preamble followed by a header row starting with
    'HCPCS'. API-format files (pfs.data.cms.gov) start directly with 'hcpc'.
    """
    with path.open(encoding="latin-1") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            # API-format files start directly with lowercase 'hcpc,'
            # PPRRVU files start with a copyright/title preamble row
            return not stripped.startswith("hcpc,")
    return False


def load_indicators_pprrvu(path: Path, effective_from: date) -> list[dict]:
    """Parse a PPRRVU-format indicators file (direct CMS download) into db rows.

    PPRRVU files use a three-row merged header (rows 8-10) and do not embed the
    effective date — it must be supplied via effective_from. Column positions 0-14
    are stable across all years (2020+). The CONV FACTOR column shifts by one in
    2026 due to an added PRIC IND column, so it is located dynamically.

    Args:
        path: Path to the PPRRVU indicators CSV file.
        effective_from: The date this release became effective (e.g. date(2025, 4, 1)).

    Returns:
        List of dicts ready for upsert into cms_pfs_indicators.
    """
    # CMS PPRRVU files are nominally ASCII but occasionally contain Latin-1
    # characters in description fields (e.g. non-breaking space, accented letters).
    # latin-1 handles all single-byte values without error.
    with path.open(newline="", encoding="latin-1") as f:
        all_rows = list(csv.reader(f))

    # Find the header row — it starts with "HCPCS"
    header_idx = next(i for i, row in enumerate(all_rows) if row and row[0].strip() == "HCPCS")
    header = [h.strip() for h in all_rows[header_idx]]

    # FACTOR appears once in the header row (the CONV FACTOR column)
    conv_col = next(i for i, h in enumerate(header) if h == "FACTOR")

    effective_from_str = effective_from.isoformat()
    year = effective_from.year

    rows = []
    for raw in all_rows[header_idx + 1:]:
        if not raw or not raw[0].strip():
            continue
        rows.append({
            "id": str(uuid.uuid4()),
            "year": year,
            "effective_from": effective_from_str,
            "hcpc": raw[0].strip(),
            "modifier": raw[1].strip() or None,
            "sdesc": raw[2].strip() or None,
            "proc_stat": raw[3].strip() or None,
            "rvu_work": _float(raw[5]),
            "nfac_pe_rvu": _float(raw[6]),
            "fac_pe_rvu": _float(raw[8]),
            "rvu_mp": _float(raw[10]),
            "nfac_total_rvu": _float(raw[11]),
            "fac_total_rvu": _float(raw[12]),
            "conv_fact": _float(raw[conv_col]),
            "pctc": raw[13].strip() or None,
            "global_days": raw[14].strip() or None,
        })

    print(f"  Parsed {len(rows)} indicator rows (PPRRVU format, effective_from={effective_from_str}).")
    return rows


def load_indicators(path: Path, effective_from: date) -> list[dict]:
    """Parse the CMS PFS indicators CSV (API format) into rows for cms_pfs_indicators.

    API-format files (pfs.data.cms.gov) have a single lowercase header row and
    embed the year in each data row. When a code appears twice with different
    conv_fact values, the lower (non-QPP) rate is kept — it is the conservative
    baseline that any Medicare provider receives, making it the better benchmark
    for overcharge detection.

    Args:
        path: Path to the API-format indicators CSV file.
        effective_from: The date this release became effective.

    Returns:
        List of dicts ready for upsert into cms_pfs_indicators.
    """
    seen: dict[tuple, dict] = {}  # (effective_from, hcpc, modifier) → row
    effective_from_str = effective_from.isoformat()

    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            hcpc = row["hcpc"].strip()
            modifier = row["modifier"].strip() or None
            year = int(row["year"].strip())

            key = (effective_from_str, hcpc, modifier or "")
            record = {
                "id": str(uuid.uuid4()),
                "year": year,
                "effective_from": effective_from_str,
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
                # Keep the lower (non-QPP) rate as the conservative benchmark
                "conv_fact": _float(row["conv_fact"]),
                "pctc": row["pctc"].strip() or None,
                "global_days": row["global"].strip() or None,
            }

            existing = seen.get(key)
            if existing is None or record["conv_fact"] < existing["conv_fact"]:
                # Preserve the uuid from an existing entry to keep upserts stable
                if existing is not None:
                    record["id"] = existing["id"]
                seen[key] = record

    rows = list(seen.values())
    print(f"  Parsed {len(rows)} unique indicator rows (API format, effective_from={effective_from_str}).")
    return rows


def _parse_cms_year(raw: str) -> int:
    """Parse a CMS year field that may use internal notation.

    Standard API files use 4-digit years (e.g. "2024").
    Some mid-year locality files use a 3-digit + letter format (e.g. "224B", "225A")
    where the numeric prefix is the last 3 digits of the year.
    "224" → 2024, "225" → 2025, etc.
    """
    digits = "".join(c for c in raw.strip() if c.isdigit())
    n = int(digits)
    if n >= 1000:
        return n  # already a full year
    # CMS 3-digit prefix: 220 → 2020, 224 → 2024, etc.
    return 1800 + n


def load_localities(path: Path) -> list[dict]:
    """Parse the CMS PFS localities CSV into rows for cms_localities.

    GPCI values do not change mid-year, so localities are loaded once per year
    and keyed by year only. The year is embedded in the file's data rows.
    Some mid-year files use CMS internal year notation (e.g. "224B" for 2024).

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
                "year": _parse_cms_year(row["year"]),
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


def upsert_batches(
    client,
    table: str,
    rows: list[dict],
    conflict_cols: str | None = None,
) -> None:
    """Insert rows in batches, skipping rows that violate unique constraints.

    For cms_pfs_indicators, modifier is nullable so ON CONFLICT (col, ..., modifier) is
    not valid — PostgreSQL requires non-null columns in explicit conflict targets.
    The partial unique indexes (WHERE modifier IS NULL / IS NOT NULL) handle uniqueness
    at the DB level; ignore_duplicates=True emits ON CONFLICT DO NOTHING which works
    with all unique constraints/indexes including partial ones.
    """
    total = len(rows)
    inserted = 0
    for i in range(0, total, BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        if conflict_cols:
            client.table(table).upsert(batch, on_conflict=conflict_cols).execute()
        else:
            client.table(table).upsert(batch, ignore_duplicates=True).execute()
        inserted += len(batch)
        print(f"  Upserted {inserted}/{total} rows into {table}...")
    print(f"  Done — {inserted} rows loaded into {table}.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load CMS PFS indicators and localities into the ClaroBill database."
    )
    parser.add_argument(
        "--indicators",
        type=Path,
        required=True,
        help="Path to the CMS PFS indicators CSV (API format or PPRRVU format)",
    )
    parser.add_argument(
        "--localities",
        type=Path,
        required=False,
        default=None,
        help=(
            "Path to the CMS PFS localities CSV. Optional — omit when loading "
            "a mid-year PPRRVU release if localities were already loaded for that year."
        ),
    )
    parser.add_argument(
        "--effective-from",
        type=date.fromisoformat,
        required=True,
        dest="effective_from",
        help="Release effective date in YYYY-MM-DD format (e.g. 2025-04-01)",
    )
    args = parser.parse_args()

    if not args.indicators.exists():
        print(f"Error: indicators file not found: {args.indicators}", file=sys.stderr)
        sys.exit(1)
    if args.localities is not None and not args.localities.exists():
        print(f"Error: localities file not found: {args.localities}", file=sys.stderr)
        sys.exit(1)

    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        print("Error: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set.", file=sys.stderr)
        sys.exit(1)

    client = create_client(supabase_url, supabase_key)

    print(f"Loading indicators from {args.indicators.name} (effective_from={args.effective_from})...")
    if _is_pprrvu_format(args.indicators):
        indicators = load_indicators_pprrvu(args.indicators, args.effective_from)
    else:
        indicators = load_indicators(args.indicators, args.effective_from)
    # No explicit conflict_cols — modifier is nullable so partial unique indexes handle
    # deduplication via ON CONFLICT DO NOTHING. In-file duplicates are already removed
    # by the key-based dedup inside load_indicators / load_indicators_pprrvu.
    upsert_batches(client, "cms_pfs_indicators", indicators)

    if args.localities is not None:
        print(f"\nLoading localities from {args.localities.name}...")
        localities = load_localities(args.localities)
        upsert_batches(client, "cms_localities", localities, "year,locality_code")
        print(f"  Localities: {len(localities)}")

    print("\nAll CMS PFS data loaded successfully.")
    active_count = sum(1 for r in indicators if r.get("proc_stat") in ACTIVE_PROC_STATS)
    print(f"  Active (proc_stat=A) codes: {active_count} / {len(indicators)}")


if __name__ == "__main__":
    main()
