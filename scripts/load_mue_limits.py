"""Load CMS NCCI Medically Unlikely Edit (MUE) limits into the database.

Supports two CMS file formats:

  MCR CSV format (.csv files):
    Row 0: multi-line copyright preamble (one CSV cell)
    Row 1: header — "HCPCS/\\nCPT Code", "<ServiceType> MUE Values",
                    "MUE Adjudication Indicator", "MUE Rationale"
    Row 2+: data — "0001U", "1", "2 Date of Service Edit: Policy", "Code Descriptor"
    Adjudication indicator included — parse the leading digit.

  MCD tab-delimited format (.txt / .TXT files):
    Multi-line preamble until a header row starting with "HCPCS/CPT Code"
    Columns: HCPCS/CPT Code, <ServiceType> MUE Values, MUE Rationale
    No adjudication indicator column — stored as 0 (unknown); treated conservatively.

Effective date:
  Auto-detected from the filename if --effective-date is not provided:
    MCR pattern: *_Eff_MM-DD-YYYY* → YYYY-MM-DD
    MCD pattern: *_Effective_MMDDYYYY* or *-Effective-MMDDYYYY* → YYYY-MM-DD

  Revisions (_R1, -REPLACEMENT, _D) for the same quarter share the same
  effective date. Load them after the base file — upsert will overwrite
  with the corrected values.

MUE Adjudication Indicators:
  0 = Unknown (MCD files)              → treat as hard denial (critical)
  1 = Claim Edit                       → sum same code+date across lines
  2 = Date of Service Edit: Policy     → per-line hard denial (critical)
  3 = Date of Service Edit: Clinical   → per-line, overridable (warning)

Usage:
  # Single file — effective date auto-detected from filename
  python scripts/load_mue_limits.py \\
      --file data/ncci/2026/mcr/MCR_MUE_PractitionerServices_Eff_04-01-2026.csv \\
      --service-type practitioner --payer-type medicare

  # Override effective date explicitly
  python scripts/load_mue_limits.py \\
      --file data/ncci/2026/mcd/MCD-MUE-DMEServices-Effective_01012026.txt \\
      --service-type dme --payer-type medicaid \\
      --effective-date 2026-01-01

  # Replace only this quarter's data (delete existing rows with same
  # service_type + payer_type + effective_date before inserting)
  python scripts/load_mue_limits.py \\
      --file data/ncci/2026/mcr/MCR_MUE_PractitionerServices_Eff_04-01-2026.csv \\
      --service-type practitioner --payer-type medicare --replace
"""

import argparse
import csv
import os
import re
import sys
import time
import uuid
from datetime import date, datetime
from pathlib import Path

from postgrest.exceptions import APIError
from supabase import create_client

BATCH_SIZE = 2000
_RETRY_DELAYS = (10, 30, 60)


def _upsert_with_retry(client, table: str, batch: list[dict], on_conflict: str) -> None:
    """Upsert a batch, retrying up to 3 times on transient 502/503/504 errors."""
    for attempt, delay in enumerate((*_RETRY_DELAYS, None), start=1):
        try:
            client.table(table).upsert(batch, on_conflict=on_conflict).execute()
            return
        except APIError as exc:
            code = exc.args[0].get("code") if exc.args else None
            is_transient = str(code) in ("502", "503", "504")
            if not is_transient or delay is None:
                raise
            print(f"  Transient {code} on attempt {attempt}, retrying in {delay}s…", file=sys.stderr)
            time.sleep(delay)
VALID_SERVICE_TYPES = ("practitioner", "outpatient", "dme")
VALID_PAYER_TYPES = ("medicare", "medicaid")

# MCR filename: *_Eff_MM-DD-YYYY* (e.g. _Eff_04-01-2026, _Eff_07-01-2020-REPLACEMENT)
_MCR_DATE_RE = re.compile(r"_Eff_(\d{2})-(\d{2})-(\d{4})", re.IGNORECASE)
# MCD filename: *_Effective_MMDDYYYY* or *-Effective-MMDDYYYY* (e.g. _Effective_01012026)
_MCD_DATE_RE = re.compile(r"[_-]Effective[_-](\d{2})(\d{2})(\d{4})", re.IGNORECASE)


def parse_effective_date_from_filename(path: Path) -> date | None:
    """Extract the CMS effective date from a MUE filename.

    Returns None if neither pattern matches — caller must provide --effective-date.
    """
    name = path.name
    m = _MCR_DATE_RE.search(name)
    if m:
        month, day, year = m.group(1), m.group(2), m.group(3)
        return datetime.strptime(f"{year}-{month}-{day}", "%Y-%m-%d").date()
    m = _MCD_DATE_RE.search(name)
    if m:
        month, day, year = m.group(1), m.group(2), m.group(3)
        return datetime.strptime(f"{year}-{month}-{day}", "%Y-%m-%d").date()
    return None


def _parse_adj_indicator(value: str) -> int:
    """Extract the leading integer from an adjudication indicator string.

    Input examples:
      "2 Date of Service Edit: Policy"  → 2
      "3 Date of Service Edit: Clinical" → 3
      "1"                                → 1
    Returns 0 if the value cannot be parsed.
    """
    try:
        return int(value.strip().split()[0])
    except (ValueError, IndexError):
        return 0


def load_mcr_csv(path: Path, service_type: str, payer_type: str, effective_date: date) -> list[dict]:
    """Parse an MCR MUE CSV file (format with Adjudication Indicator)."""
    rows = []
    with path.open(newline="", encoding="latin-1") as f:
        reader = csv.reader(f)
        header_found = False
        for line_num, row in enumerate(reader, start=1):
            if not row:
                continue
            if not header_found:
                first = row[0].replace("\n", " ").strip().lower()
                if first.startswith("hcpcs") or first.startswith("cpt code"):
                    header_found = True
                continue
            if len(row) < 3:
                print(f"  Skipping malformed row {line_num}: {row}", file=sys.stderr)
                continue
            hcpcs_code = row[0].strip()
            if not hcpcs_code:
                continue
            try:
                mue_value = int(row[1].strip())
            except ValueError:
                print(f"  Skipping row {line_num} — invalid MUE value: {row[1]!r}", file=sys.stderr)
                continue
            if len(row) >= 4:
                adj_indicator = _parse_adj_indicator(row[2])
                mue_rationale = row[3].strip()
            else:
                adj_indicator = _parse_adj_indicator(row[2])
                mue_rationale = ""
            rows.append({
                "id": str(uuid.uuid4()),
                "hcpcs_code": hcpcs_code,
                "service_type": service_type,
                "payer_type": payer_type,
                "effective_date": effective_date.isoformat(),
                "mue_value": mue_value,
                "adjudication_indicator": adj_indicator,
                "mue_rationale": mue_rationale,
            })
    return rows


def load_mcd_txt(path: Path, service_type: str, payer_type: str, effective_date: date) -> list[dict]:
    """Parse an MCD MUE tab-delimited file (no Adjudication Indicator column).

    Adjudication indicator stored as 0 (unknown) — rules engine treats this
    conservatively (same as indicator 2: hard denial).
    """
    rows = []
    with path.open(newline="", encoding="latin-1") as f:
        reader = csv.reader(f, delimiter="\t")
        header_found = False
        for line_num, row in enumerate(reader, start=1):
            if not row:
                continue
            if not header_found:
                first = row[0].strip().lower()
                if first.startswith("hcpcs") or first.startswith("cpt code"):
                    header_found = True
                continue
            if len(row) < 2:
                print(f"  Skipping malformed row {line_num}: {row}", file=sys.stderr)
                continue
            hcpcs_code = row[0].strip()
            if not hcpcs_code:
                continue
            try:
                mue_value = int(row[1].strip())
            except ValueError:
                print(f"  Skipping row {line_num} — invalid MUE value: {row[1]!r}", file=sys.stderr)
                continue
            mue_rationale = row[2].strip() if len(row) >= 3 else ""
            rows.append({
                "id": str(uuid.uuid4()),
                "hcpcs_code": hcpcs_code,
                "service_type": service_type,
                "payer_type": payer_type,
                "effective_date": effective_date.isoformat(),
                "mue_value": mue_value,
                "adjudication_indicator": 0,
                "mue_rationale": mue_rationale,
            })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Load CMS NCCI MUE limits into ClaroBill DB")
    parser.add_argument("--file", type=Path, required=True, help="Path to CMS MUE file (.csv for MCR, .txt/.TXT for MCD)")
    parser.add_argument("--service-type", choices=VALID_SERVICE_TYPES, default="practitioner")
    parser.add_argument("--payer-type", choices=VALID_PAYER_TYPES, default="medicare")
    parser.add_argument(
        "--effective-date",
        help="Override the CMS effective date (YYYY-MM-DD). Auto-detected from filename if omitted.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help=(
            "Delete existing rows for (service_type, payer_type, effective_date) "
            "before inserting. Use when re-loading a corrected quarterly file."
        ),
    )
    args = parser.parse_args()

    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        print("Error: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set.", file=sys.stderr)
        sys.exit(1)

    if not args.file.exists():
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    if args.effective_date:
        try:
            effective_date = datetime.strptime(args.effective_date, "%Y-%m-%d").date()
        except ValueError:
            print(f"Error: --effective-date must be YYYY-MM-DD, got: {args.effective_date!r}", file=sys.stderr)
            sys.exit(1)
    else:
        effective_date = parse_effective_date_from_filename(args.file)
        if effective_date is None:
            print(
                f"Error: Could not auto-detect effective date from filename '{args.file.name}'. "
                "Pass --effective-date YYYY-MM-DD explicitly.",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"  Detected effective_date={effective_date} from filename.")

    suffix = args.file.suffix.lower()
    if suffix == ".csv":
        rows = load_mcr_csv(args.file, args.service_type, args.payer_type, effective_date)
        fmt = "MCR CSV"
    elif suffix in (".txt", ".txt"):
        rows = load_mcd_txt(args.file, args.service_type, args.payer_type, effective_date)
        fmt = "MCD tab-delimited"
    else:
        print(f"Error: Unrecognised extension '{suffix}'. Expected .csv (MCR) or .txt (MCD).", file=sys.stderr)
        sys.exit(1)

    client = create_client(supabase_url, supabase_key)

    if args.replace:
        print(
            f"  Deleting existing rows for service_type={args.service_type}, "
            f"payer_type={args.payer_type}, effective_date={effective_date}…"
        )
        client.table("ncci_mue_limits").delete().match({
            "service_type": args.service_type,
            "payer_type": args.payer_type,
            "effective_date": effective_date.isoformat(),
        }).execute()
        print("  Deleted.")

    # Deduplicate on the DB conflict key before upserting. Some CMS files list
    # the same HCPCS code more than once (e.g. once with a note, once without).
    # PostgreSQL raises error 21000 if the same conflict key appears twice in a
    # single upsert command. Keep the last occurrence — it tends to be the more
    # specific or corrected entry.
    seen: dict[str, int] = {}
    for i, row in enumerate(rows):
        seen[row["hcpcs_code"]] = i
    rows = [rows[i] for i in sorted(seen.values())]

    print(
        f"Parsed {len(rows)} MUE limits from {args.file.name} "
        f"[{fmt}] (service_type={args.service_type}, payer_type={args.payer_type}, "
        f"effective_date={effective_date})"
    )

    inserted = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i: i + BATCH_SIZE]
        _upsert_with_retry(
            client, "ncci_mue_limits", batch,
            "hcpcs_code,service_type,payer_type,effective_date",
        )
        inserted += len(batch)
        print(f"  Upserted {inserted}/{len(rows)} rows…")

    print(f"Done. {inserted} MUE limits loaded.")


if __name__ == "__main__":
    main()
