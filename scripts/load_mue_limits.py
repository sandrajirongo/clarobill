"""Load CMS NCCI Medically Unlikely Edit (MUE) limits into the database.

Supports two CMS file formats:

  MCR CSV format (Q2 2026+, .csv files):
    Row 0: multi-line copyright preamble (one CSV cell)
    Row 1: header — "HCPCS/\nCPT Code", "<ServiceType> MUE Values",
                    "MUE Adjudication Indicator", "MUE Rationale"
    Row 2+: data — "0001U", "1", "2 Date of Service Edit: Policy", "Code Descriptor"
    Adjudication indicator included — parse the leading digit.

  MCD tab-delimited format (Q1 2026, .txt files):
    Multi-line preamble until a header row starting with "HCPCS/CPT Code"
    Columns: HCPCS/CPT Code, <ServiceType> MUE Values, MUE Rationale
    No adjudication indicator column — stored as 0 (unknown); treated conservatively.

MUE Adjudication Indicators:
  0 = Unknown (MCD files)         → treat as hard denial (critical)
  1 = Claim Edit                  → sum same code+date across lines; must not exceed MUE
  2 = Date of Service Edit: Policy → each line must not exceed MUE (hard denial)
  3 = Date of Service Edit: Clinical → each line must not exceed MUE (overridable with docs)

Usage:
  # Load MCR practitioner MUE file (Medicare, Q2 2026)
  python scripts/load_mue_limits.py \
      --file data/ncci/MCR_MUE_PractitionerServices_Eff_04-01-2026.csv \
      --service-type practitioner --payer-type medicare

  # Load MCR outpatient hospital MUE file
  python scripts/load_mue_limits.py \
      --file data/ncci/MCR_MUE_OutpatientHospitalServices_Eff_04-01-2026.csv \
      --service-type outpatient --payer-type medicare

  # Load MCR DME supplier MUE file
  python scripts/load_mue_limits.py \
      --file data/ncci/MCR_MUE_DMESupplierServices_Eff_04-01-2026.csv \
      --service-type dme --payer-type medicare

  # Load MCD practitioner MUE file (Medicare national standard, Q1 2026)
  python scripts/load_mue_limits.py \
      --file data/ncci/MCD-MUE-PractitionerServices-Effective_01012026.txt \
      --service-type practitioner --payer-type medicare
"""

import argparse
import csv
import os
import sys
import uuid
from pathlib import Path

from supabase import create_client

BATCH_SIZE = 500
VALID_SERVICE_TYPES = ("practitioner", "outpatient", "dme")
VALID_PAYER_TYPES = ("medicare", "medicaid")


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


def load_mcr_csv(path: Path, service_type: str, payer_type: str) -> list[dict]:
    """Parse an MCR MUE CSV file (Q2 2026+ format with Adjudication Indicator)."""
    rows = []
    with path.open(newline="", encoding="latin-1") as f:
        reader = csv.reader(f)
        header_found = False
        for line_num, row in enumerate(reader, start=1):
            if not row:
                continue

            # Row 0 is the copyright preamble (one big cell); row 1 is the header.
            # Detect header by looking for a cell starting with "HCPCS" or "CPT Code".
            if not header_found:
                first = row[0].replace("\n", " ").strip().lower()
                if first.startswith("hcpcs") or first.startswith("cpt code"):
                    header_found = True
                continue  # skip preamble and header

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

            # Column 2 is the adjudication indicator; column 3 is the rationale.
            # Some files may have only 3 columns with rationale as col 2.
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
                "mue_value": mue_value,
                "adjudication_indicator": adj_indicator,
                "mue_rationale": mue_rationale,
            })
    return rows


def load_mcd_txt(path: Path, service_type: str, payer_type: str) -> list[dict]:
    """Parse an MCD MUE tab-delimited file (no Adjudication Indicator column).

    Adjudication indicator is stored as 0 (unknown) — the rules engine treats
    this conservatively (same as indicator 2: hard denial).
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
                "mue_value": mue_value,
                "adjudication_indicator": 0,  # MCD files do not include this field
                "mue_rationale": mue_rationale,
            })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Load CMS NCCI MUE limits into ClaroBill DB")
    parser.add_argument(
        "--file",
        type=Path,
        required=True,
        help="Path to CMS MUE file (.csv for MCR, .txt for MCD)",
    )
    parser.add_argument(
        "--service-type",
        choices=VALID_SERVICE_TYPES,
        default="practitioner",
        help="Bill service type the MUE limits apply to (default: practitioner)",
    )
    parser.add_argument(
        "--payer-type",
        choices=VALID_PAYER_TYPES,
        default="medicare",
        help="Insurance programme the MUE file was published for (default: medicare)",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help=(
            "Delete all existing rows for the given (service_type, payer_type) "
            "before inserting. Use when refreshing from a new quarterly file."
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

    suffix = args.file.suffix.lower()
    if suffix == ".csv":
        rows = load_mcr_csv(args.file, args.service_type, args.payer_type)
        fmt = "MCR CSV"
    elif suffix == ".txt":
        rows = load_mcd_txt(args.file, args.service_type, args.payer_type)
        fmt = "MCD tab-delimited"
    else:
        print(
            f"Error: Unrecognised file extension '{suffix}'. Expected .csv (MCR) or .txt (MCD).",
            file=sys.stderr,
        )
        sys.exit(1)

    client = create_client(supabase_url, supabase_key)

    print(
        f"Parsed {len(rows)} MUE limits from {args.file.name} "
        f"[{fmt}] (service_type={args.service_type}, payer_type={args.payer_type})"
    )

    if args.replace:
        print(f"  Deleting existing rows for service_type={args.service_type}, payer_type={args.payer_type}…")
        client.table("ncci_mue_limits").delete().match(
            {"service_type": args.service_type, "payer_type": args.payer_type}
        ).execute()
        print("  Deleted.")

    # Upsert in batches — re-runnable without creating duplicates.
    # Conflict key is (hcpcs_code, service_type, payer_type) — one limit per code per context.
    inserted = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        client.table("ncci_mue_limits").upsert(
            batch,
            on_conflict="hcpcs_code,service_type,payer_type",
        ).execute()
        inserted += len(batch)
        print(f"  Upserted {inserted}/{len(rows)} rows...")

    print(f"Done. {inserted} MUE limits loaded.")


if __name__ == "__main__":
    main()
