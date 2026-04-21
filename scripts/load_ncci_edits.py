"""Load CMS NCCI Procedure-to-Procedure (PTP) edit pairs into the database.

Supports two CMS file formats:

  MCD (Medicaid, tab-delimited .txt):
    Multi-line preamble before a header row starting with "Col1".
    6 columns: Col1, Col2, EffDt, DelDt, ModifierIndicator, PTP Edit Rationale
    Deletion date sentinels: 20991231, 99991231 (= still active)
    Files: MCD-PTP-*.txt

  MCR (Medicare, tab-delimited .txt/.TXT):
    Multi-line preamble before a header row starting with "Column 1".
    7 columns: Col1, Col2, Pre1996Indicator, EffDt, DelDt, ModifierIndicator, Rationale
    Deletion date sentinel: * (= still active)
    Files: ccioph-v*-f*.txt (outpatient), ccipra-v*-f*.txt (practitioner)

Usage:
  python scripts/load_ncci_edits.py \\
      --file data/ncci/2026/mcd/MCD-PTP-PractitionerServices-Effective_01012026.txt \\
      --service-type practitioner --payer-type medicaid

  python scripts/load_ncci_edits.py \\
      --file data/ncci/2026/mcr/ccioph-v321r0-f1.txt \\
      --service-type outpatient --payer-type medicare

  python scripts/load_ncci_edits.py --sample
"""

import argparse
import csv
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path

import httpx
from postgrest.exceptions import APIError
from supabase import create_client, ClientOptions

BATCH_SIZE = 1000
_RETRY_DELAYS = (30, 60, 120, 180)  # seconds between attempts on transient 5xx

VALID_SERVICE_TYPES = ("practitioner", "outpatient", "dme")
VALID_PAYER_TYPES = ("medicare", "medicaid")


def _upsert_with_retry(client, fn_name: str, batch: list[dict]) -> None:
    """Call a server-side upsert RPC, retrying on transient errors.

    The RPC runs with statement_timeout=300s, bypassing the 30s PostgREST limit.
    """
    for attempt, delay in enumerate((*_RETRY_DELAYS, None), start=1):
        try:
            client.rpc(fn_name, {"p_rows": batch}).execute()
            return
        except APIError as exc:
            arg0 = exc.args[0] if exc.args else {}
            code = arg0.get("code") if isinstance(arg0, dict) else None
            is_transient = str(code) in ("502", "503", "504")
            if not is_transient or delay is None:
                raise
            print(f"  Transient {code} on attempt {attempt}, retrying in {delay}s…", file=sys.stderr)
            time.sleep(delay)
        except (
            httpx.RemoteProtocolError, httpx.ConnectError,
            httpx.ReadError, httpx.ReadTimeout,
            httpx.WriteError, httpx.TimeoutException,
        ) as exc:
            if delay is None:
                raise
            print(f"  Network error on attempt {attempt} ({type(exc).__name__}: {exc}), retrying in {delay}s…", file=sys.stderr)
            time.sleep(delay)


def parse_cms_date(value: str) -> date | None:
    """Parse a CMS date string (YYYYMMDD). Returns None for any 'still active' sentinel.

    Handles MCD sentinels (20991231, 99991231) and MCR sentinel (*).
    """
    value = value.strip()
    if not value or value in ("20991231", "99991231", "*"):
        return None
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        return None


def load_from_file(path: Path, service_type: str, payer_type: str) -> list[dict]:
    """Parse a CMS NCCI PTP tab-delimited file into dicts ready for DB insertion.

    Handles both file formats automatically:
      MCD (6 columns): Col1, Col2, EffDt, DelDt, Modifier, Rationale
        Header starts with "Col1"
      MCR (7 columns): Col1, Col2, Pre1996, EffDt, DelDt, Modifier, Rationale
        Header starts with "Column 1"
        The extra Pre1996 column (index 2) is empty or "*" — not a date.
    """
    rows = []
    with path.open(newline="", encoding="latin-1") as f:
        reader = csv.reader(f, delimiter="\t")
        header_found = False
        for line_num, row in enumerate(reader, start=1):
            if not row:
                continue

            if not header_found:
                row_text = "\t".join(row).lower()
                if (row_text.strip().startswith("col1")
                        or row_text.strip().startswith("column 1")
                        or "\ncol1\t" in row_text):
                    header_found = True
                continue  # skip everything up to and including the header

            if len(row) < 5:
                print(f"  Skipping malformed row {line_num}: {row}", file=sys.stderr)
                continue

            col1 = row[0].strip().zfill(5)
            col2 = row[1].strip().zfill(5)

            # MCR files have a 7-column layout where row[2] is a pre-1996 indicator
            # ("*" or empty), not a date. MCD files have 6 columns where row[2] IS
            # the effective date. Detect by checking whether row[2] is a date.
            if len(row) >= 7 and not row[2].strip().isdigit():
                # MCR format — shift date/modifier columns right by 1
                effective = parse_cms_date(row[3])
                deletion = parse_cms_date(row[4])
                modifier_col = row[5]
            else:
                # MCD format
                effective = parse_cms_date(row[2])
                deletion = parse_cms_date(row[3])
                modifier_col = row[4]

            try:
                modifier_indicator = int(modifier_col.strip().split()[0])
            except (ValueError, IndexError):
                modifier_indicator = 9

            if not effective:
                continue  # effective date is required

            rows.append({
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

    client = create_client(supabase_url, supabase_key, options=ClientOptions(
        postgrest_client_timeout=360,
    ))

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
    # Uses the delete_ncci_pairs() RPC (statement_timeout=300s) because a direct DELETE
    # on 2M+ rows exceeds the 30s PostgREST timeout.
    if args.replace and not args.sample:
        print(f"  Deleting existing rows for service_type={args.service_type}, payer_type={args.payer_type}…")
        result = client.rpc("delete_ncci_pairs", {
            "p_service_type": args.service_type,
            "p_payer_type": args.payer_type,
        }).execute()
        deleted = result.data if isinstance(result.data, int) else 0
        print(f"  Deleted {deleted} rows.")

    # Deduplicate on the DB conflict key. CMS PTP files contain ~298k duplicate
    # (col1, col2) pairs — PostgreSQL raises error 21000 if the same conflict key
    # appears twice in one upsert command. Keep the last occurrence.
    seen: dict[tuple[str, str], int] = {}
    for i, row in enumerate(rows):
        seen[(row["column_one_code"], row["column_two_code"])] = i
    rows = [rows[i] for i in sorted(seen.values())]

    inserted = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        _upsert_with_retry(client, "upsert_ncci_pairs_batch", batch)
        inserted += len(batch)
        print(f"  Upserted {inserted}/{len(rows)} rows...")
        time.sleep(0.3)

    print(f"Done. {inserted} NCCI PTP edit pairs loaded.")


if __name__ == "__main__":
    main()
