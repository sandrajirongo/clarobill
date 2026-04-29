"""One-time backfill: tag hospital_charges_legacy_stale with pricing_effective_year=2025.

Sandra's decision (2026-04-29 Phase 4 Q2): the legacy table predates the
introduction of pricing_effective_year. The data was scraped throughout
2025-early-2026 from MRFs hospitals published during 2025. Tagging every
legacy row as `pricing_effective_year = 2025` makes the data queryable as
2025-vintage data instead of "unknown vintage" — which the rules engine
can use as a fallback if no 2026 data exists for a given hospital.

This script is idempotent. Re-running is a no-op (the WHERE clause filters
out rows that already have the column populated).

The legacy table doesn't have pricing_effective_year as a column today —
the original schema migration only added it to the new hospital_charges.
This script:
  1. Adds the column to hospital_charges_legacy_stale (NULLABLE, not the
     NOT NULL we used for the new table — preserves "we know we don't
     know" for any future case)
  2. UPDATEs every existing row with pricing_effective_year = 2025
  3. Logs the row count for confirmation

Usage:
    python scripts/mrf_discovery/backfill_legacy_effective_year.py --dry-run
    python scripts/mrf_discovery/backfill_legacy_effective_year.py --project clarobill-prd
"""

from __future__ import annotations

import argparse
import logging
import sys

from google.cloud import bigquery

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_DATASET = "hospital_prices"
LEGACY_VINTAGE_YEAR = 2025  # Sandra's call: data scraped in 2025-early-2026 from 2025 MRFs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--project", default="clarobill-prd")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    client = bigquery.Client(project=args.project)
    table_id = f"{args.project}.{args.dataset}.hospital_charges_legacy_stale"

    # Step 1: ensure column exists (idempotent)
    add_col_sql = f"""
    ALTER TABLE `{table_id}`
    ADD COLUMN IF NOT EXISTS pricing_effective_year INT64
    """
    if args.dry_run:
        logger.info("[dry-run] %s", add_col_sql.strip())
    else:
        logger.info("Adding pricing_effective_year column (idempotent)...")
        client.query(add_col_sql).result()

    # Step 2: count rows that need backfill
    count_sql = f"""
    SELECT
      COUNTIF(pricing_effective_year IS NULL) AS needs_backfill,
      COUNTIF(pricing_effective_year = {LEGACY_VINTAGE_YEAR}) AS already_tagged,
      COUNT(*) AS total
    FROM `{table_id}`
    """
    if not args.dry_run:
        result = next(iter(client.query(count_sql).result()))
        needs = int(result["needs_backfill"] or 0)
        tagged = int(result["already_tagged"] or 0)
        total = int(result["total"] or 0)
        logger.info(
            "Legacy table: total=%d, already tagged year=%d (%d), needs backfill=%d",
            total, LEGACY_VINTAGE_YEAR, tagged, needs,
        )
        if needs == 0:
            logger.info("Nothing to backfill. Done.")
            return 0

    # Step 3: backfill
    update_sql = f"""
    UPDATE `{table_id}`
    SET pricing_effective_year = {LEGACY_VINTAGE_YEAR}
    WHERE pricing_effective_year IS NULL
    """
    if args.dry_run:
        logger.info("[dry-run] %s", update_sql.strip())
        return 0

    logger.info("Backfilling pricing_effective_year=%d on legacy rows...", LEGACY_VINTAGE_YEAR)
    job = client.query(update_sql)
    job.result()
    logger.info(
        "Backfill complete: %d rows updated (DML stats: %s)",
        job.num_dml_affected_rows or 0,
        {k: getattr(job, k, None) for k in ("num_dml_affected_rows",)},
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
