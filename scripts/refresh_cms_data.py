"""Automated CMS reference data refresh.

Downloads and reloads the latest Medicare fee schedule and NCCI edit pairs
from CMS. Designed to be run as a scheduled job:

  - Fee schedule:  annually in January (CMS releases in November, effective Jan 1)
  - NCCI edits:    quarterly (Jan 1, Apr 1, Jul 1, Oct 1)

Schedule this via cron, Railway Cron Jobs, or a CI/CD scheduled workflow:

  # Run quarterly on the 2nd of Jan, Apr, Jul, Oct at 06:00 UTC
  0 6 2 1,4,7,10 * python scripts/refresh_cms_data.py

CMS download URLs (update these when CMS publishes new files):

  Fee schedule:
    https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files
    Download the current year's pricing file ZIP, extract, convert to CSV format:
      hcpcs_code, modifier, locality_code, facility_rate, non_facility_rate, year

  NCCI PTP edits:
    https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-procedure-to-procedure-edits
    Download the current quarter's ZIP, extract the CSV.

Usage:
  # Dry run — shows what would be loaded without touching the DB
  python scripts/refresh_cms_data.py --dry-run

  # Load sample data (for dev/CI — no real CMS files needed)
  python scripts/refresh_cms_data.py --sample --year 2025

  # Load real CMS files
  python scripts/refresh_cms_data.py \\
    --fee-schedule /path/to/fee_schedule.csv \\
    --ncci /path/to/NCCI_PT_to_PT.csv \\
    --year 2025
"""

import argparse
import os
import subprocess
import sys
from datetime import date
from pathlib import Path


def current_cms_year() -> int:
    """Returns the year whose fee schedule is currently in effect."""
    today = date.today()
    # CMS fee schedule is effective January 1 each year
    return today.year


def run_script(script: str, args: list[str]) -> bool:
    """Run a data loading script as a subprocess. Returns True on success."""
    cmd = [sys.executable, script, *args]
    print(f"\n→ Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0:
        print(f"  FAILED (exit code {result.returncode})", file=sys.stderr)
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh CMS Medicare reference data")
    parser.add_argument("--year", type=int, default=current_cms_year(),
                        help="Year to load (default: current year)")
    parser.add_argument("--fee-schedule", type=Path,
                        help="Path to fee schedule CSV file")
    parser.add_argument("--ncci", type=Path,
                        help="Path to NCCI PTP edit pairs CSV file")
    parser.add_argument("--sample", action="store_true",
                        help="Load sample data instead of real CMS files (dev/CI only)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be run without executing")
    args = parser.parse_args()

    scripts_dir = Path(__file__).parent
    fee_schedule_script = str(scripts_dir / "load_fee_schedule.py")
    ncci_script = str(scripts_dir / "load_ncci_edits.py")

    # Validate env vars are present before starting
    required = ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing and not args.dry_run:
        print(f"Error: missing environment variables: {', '.join(missing)}", file=sys.stderr)
        print("Export them or source your .env file before running.", file=sys.stderr)
        sys.exit(1)

    # Build the argument lists for each sub-script
    if args.sample:
        fee_args = ["--sample", "--year", str(args.year)]
        ncci_args = ["--sample"]
    else:
        if not args.fee_schedule or not args.ncci:
            print("Error: --fee-schedule and --ncci are required unless using --sample or --dry-run.",
                  file=sys.stderr)
            sys.exit(1)
        fee_args = ["--file", str(args.fee_schedule), "--year", str(args.year)]
        ncci_args = ["--file", str(args.ncci)]

    print(f"CMS data refresh — year {args.year}")
    print(f"  Fee schedule: {'sample' if args.sample else args.fee_schedule}")
    print(f"  NCCI edits:   {'sample' if args.sample else args.ncci}")

    if args.dry_run:
        print("\nDry run — no changes made.")
        print(f"  Would run: python {fee_schedule_script} {' '.join(fee_args)}")
        print(f"  Would run: python {ncci_script} {' '.join(ncci_args)}")
        return

    success = True
    success &= run_script(fee_schedule_script, fee_args)
    success &= run_script(ncci_script, ncci_args)

    if success:
        print(f"\nCMS data refresh complete for year {args.year}.")
    else:
        print("\nRefresh completed with errors — check output above.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
