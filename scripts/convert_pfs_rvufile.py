"""Convert CMS PPRRVU file to the format expected by load_fee_schedule.py.

The PPRRVU file has a 9-line multi-row header and duplicate column names
(AMOUNT appears 3 times, PAYMENT appears twice). We read rows as plain lists
and access columns by index to avoid DictReader's duplicate-key merging.

Usage:
  python scripts/convert_pfs_rvufile.py --file /path/to/PPRRVU2026_Apr_nonQPP.csv --year 2026
  # Outputs: /tmp/PPRRVU2026_converted.csv
"""

import argparse
import csv
import sys
from pathlib import Path

# Lines to skip before the actual column header row
HEADER_LINES = 9


def convert(input_path: Path, year: int) -> Path:
    output_path = input_path.parent / (input_path.stem + "_converted.csv")

    with input_path.open(newline="", encoding="utf-8-sig") as f_in:
        for _ in range(HEADER_LINES):
            f_in.readline()

        reader = csv.reader(f_in, delimiter=",")
        header = [f.strip() for f in next(reader)]

        if not header:
            print("Error: could not read column headers.", file=sys.stderr)
            sys.exit(1)

        hcpcs_idx = next((i for i, f in enumerate(header) if f.upper() == "HCPCS"), None)
        mod_idx = next((i for i, f in enumerate(header) if f.upper() == "MOD"), None)

        if hcpcs_idx is None:
            print(f"Error: HCPCS column not found. Columns: {header}", file=sys.stderr)
            sys.exit(1)

        # The last 3 PAYMENT/AMOUNT columns are (in order):
        #   NON-FACILITY PAYMENT AMOUNT, FACILITY PAYMENT AMOUNT, OPPS PAYMENT AMOUNT
        payment_indices = [i for i, f in enumerate(header) if f.upper() in ("PAYMENT", "AMOUNT")]
        if len(payment_indices) < 2:
            print(
                f"Error: expected at least 2 PAYMENT/AMOUNT columns, found {len(payment_indices)}.\n"
                f"Columns: {header}",
                file=sys.stderr,
            )
            sys.exit(1)

        non_fac_idx = payment_indices[-3] if len(payment_indices) >= 3 else payment_indices[-2]
        fac_idx = payment_indices[-2]

        print(f"HCPCS col: {hcpcs_idx}, MOD col: {mod_idx}")
        print(f"Non-facility payment col: {non_fac_idx}")
        print(f"Facility payment col:     {fac_idx}")

        written = 0
        skipped = 0

        with output_path.open("w", newline="", encoding="utf-8") as f_out:
            writer = csv.DictWriter(
                f_out,
                fieldnames=["hcpcs_code", "modifier", "locality_code", "facility_rate", "non_facility_rate", "year"],
            )
            writer.writeheader()

            for row in reader:
                if len(row) <= max(hcpcs_idx, fac_idx, non_fac_idx):
                    skipped += 1
                    continue

                hcpcs = row[hcpcs_idx].strip()
                mod = row[mod_idx].strip() if mod_idx is not None else ""

                if not hcpcs:
                    skipped += 1
                    continue

                try:
                    non_fac = float((row[non_fac_idx] or "0").replace(",", ""))
                    fac = float((row[fac_idx] or "0").replace(",", ""))
                except ValueError:
                    skipped += 1
                    continue

                writer.writerow({
                    "hcpcs_code": hcpcs.zfill(5),
                    "modifier": mod,
                    "locality_code": "0000",
                    "facility_rate": fac,
                    "non_facility_rate": non_fac,
                    "year": year,
                })
                written += 1

    print(f"\nDone. {written} rows written to {output_path}")
    print(f"Skipped {skipped} rows (blank HCPCS, short rows, or invalid rates).")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert CMS PPRRVU file for Clarobill import")
    parser.add_argument("--file", type=Path, required=True, help="Path to PPRRVU CSV file")
    parser.add_argument("--year", type=int, required=True, help="Fee schedule year (e.g. 2026)")
    args = parser.parse_args()

    if not args.file.exists():
        print(f"Error: file not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    output = convert(args.file, args.year)
    print(f"\nNext step — load into Supabase:")
    print(
        f"  SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... "
        f"python scripts/load_fee_schedule.py --file {output} --year {args.year}"
    )


if __name__ == "__main__":
    main()
