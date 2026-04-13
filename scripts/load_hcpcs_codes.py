"""Load CMS HCPCS Level II code descriptors into the database.

Source files: HCPCS Level II Annual/Quarterly Code Files — Contractor ANWEB format.
Download: https://www.cms.gov/medicare/coding-billing/healthcare-common-procedure-system

Each file is a 320-character fixed-width record file containing both procedure codes
(record ID 3/4) and modifier codes (record ID 7/8).  We load only procedure records.

Record layout (1-indexed positions from CMS documentation; Python slices are 0-indexed):
  pos  1–5   (0:5)    HCPCS code (5 chars)
  pos 11     (10:11)  Record identification code: 3=first procedure, 4=continuation,
                       7=first modifier, 8=continuation modifier
  pos 12–91  (11:91)  Long description (80 chars) — appended across continuation records
  pos 92–119 (91:119) Short description (28 chars) — only on first record (ID 3)
  pos 120–121 (119:121) Pricing indicator code (first of up to 4 occurrences):
                       00 = not separately priced by Part B
                       11 = RVU (physician fee schedule)
                       12 = anesthesia base units
                       13 = carrier-priced
                       31–39, 45–46 = DME categories
                       51 = drugs, 54 = vaccines
  pos 230    (229:230) Coverage code:
                       I = not payable by Medicare
                       M = non-covered by Medicare
                       S = non-covered by Medicare statute
                       C = carrier judgment
                       D = special coverage instructions apply
  pos 285–292 (284:292) Termination date (YYYYMMDD; blank = still active)
  pos 293    (292:293) Action code: A=added, B=both desc+admin changed, C=desc changed,
                       D=discontinued, F=admin changed, N=no change, P=payment changed,
                       R=reactivated, S=short desc changed, T=misc changed

Multi-line descriptions:
  A single HCPCS code may span multiple records.  The first record (ID 3) carries all
  administrative fields.  Subsequent records (ID 4) carry only additional description
  text in pos 12-91; all other fields are blank.  We concatenate these into a single
  long_description, separated by a space.

is_noc flag:
  Set True when "not otherwise" appears in the long description (covers both
  "not otherwise classified" and "not otherwise specified").

Usage:
  python3 scripts/load_hcpcs_codes.py \\
      --file data/hcpcs/2026/HCPC2026_APR_ANWEB.txt \\
      --effective-from 2026-04-01

  python3 scripts/load_hcpcs_codes.py \\
      --file data/hcpcs/2021/HCPC2021_JAN_CONTR_ANWEB.txt \\
      --effective-from 2021-01-01

Re-runnable — upserts on (effective_from, hcpc).
"""

import argparse
import os
import sys
import uuid
from datetime import date
from pathlib import Path

from supabase import create_client

BATCH_SIZE = 500

# Fixed-width field slices (0-indexed)
_HCPC_SLICE = slice(0, 5)
_REC_ID_SLICE = slice(10, 11)
_LONG_DESC_SLICE = slice(11, 91)
_SHORT_DESC_SLICE = slice(91, 119)
_PRICING_IND_SLICE = slice(119, 121)
_COVERAGE_CODE_SLICE = slice(229, 230)
_TERM_DATE_SLICE = slice(284, 292)
_ACTION_CODE_SLICE = slice(292, 293)


def _parse_date(raw: str) -> date | None:
    """Parse an 8-digit YYYYMMDD date string; return None for blank or zero values."""
    s = raw.strip()
    if not s or s == "00000000":
        return None
    try:
        return date(int(s[0:4]), int(s[4:6]), int(s[6:8]))
    except (ValueError, IndexError):
        return None


def load_from_file(path: Path, effective_from: date) -> list[dict]:
    """Parse a HCPCS ANWEB fixed-width file into rows for cms_hcpcs_codes.

    Processes only procedure records (record ID 3 and 4).  Multi-line descriptions
    are concatenated.  Modifier records (ID 7/8) are skipped entirely.

    Args:
        path:           Path to the fixed-width .txt file.
        effective_from: The quarterly release date (e.g. date(2026, 4, 1)).

    Returns:
        List of dicts ready for upsert into cms_hcpcs_codes.
    """
    effective_from_str = effective_from.isoformat()
    rows: list[dict] = []
    current: dict | None = None  # buffered procedure record being assembled

    def _flush(record: dict | None) -> None:
        if record is not None:
            record["long_description"] = record["long_description"].strip()
            record["is_noc"] = "not otherwise" in record["long_description"].lower()
            rows.append(record)

    with path.open(encoding="utf-8-sig", errors="replace") as f:
        for raw_line in f:
            # Pad to 320 chars to guard against truncated lines
            line = raw_line.rstrip("\n\r").ljust(320)

            rec_id = line[_REC_ID_SLICE]

            if rec_id == "3":
                _flush(current)
                hcpc = line[_HCPC_SLICE].strip()
                if not hcpc:
                    current = None
                    continue
                term_date = _parse_date(line[_TERM_DATE_SLICE])
                current = {
                    "id": str(uuid.uuid4()),
                    "effective_from": effective_from_str,
                    "hcpc": hcpc,
                    "long_description": line[_LONG_DESC_SLICE].rstrip(),
                    "short_description": line[_SHORT_DESC_SLICE].strip() or None,
                    "pricing_indicator": line[_PRICING_IND_SLICE].strip() or None,
                    "coverage_code": line[_COVERAGE_CODE_SLICE].strip() or None,
                    "termination_date": term_date.isoformat() if term_date else None,
                    "action_code": line[_ACTION_CODE_SLICE].strip() or None,
                    "is_noc": False,  # computed in _flush
                }

            elif rec_id == "4":
                # Continuation of the previous procedure record's long description
                if current is not None:
                    continuation = line[_LONG_DESC_SLICE].rstrip()
                    if continuation:
                        current["long_description"] += " " + continuation

            # rec_id 7/8 (modifier records) — skip

    _flush(current)  # flush the last buffered record

    print(f"  Parsed {len(rows)} HCPCS procedure code records (effective_from={effective_from_str}).")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load CMS HCPCS Level II code descriptors into the ClaroBill database."
    )
    parser.add_argument(
        "--file",
        type=Path,
        required=True,
        help="Path to the HCPCS ANWEB fixed-width .txt file.",
    )
    parser.add_argument(
        "--effective-from",
        type=date.fromisoformat,
        required=True,
        dest="effective_from",
        help="Quarterly release date in YYYY-MM-DD format (e.g. 2026-04-01).",
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

    print(f"Loading HCPCS codes from {args.file.name} (effective_from={args.effective_from})...")
    rows = load_from_file(args.file, args.effective_from)

    total = len(rows)
    upserted = 0
    for i in range(0, total, BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        client.table("cms_hcpcs_codes").upsert(
            batch, on_conflict="effective_from,hcpc"
        ).execute()
        upserted += len(batch)
        print(f"  Upserted {upserted}/{total} rows...")

    print(f"Done. {upserted} HCPCS code rows loaded for effective_from={args.effective_from}.")


if __name__ == "__main__":
    main()
