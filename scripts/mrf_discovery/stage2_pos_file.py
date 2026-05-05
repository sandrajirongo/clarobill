"""Stage 2 substep A — CMS Provider of Services file loader.

The Provider of Services (POS) file is CMS's authoritative quarterly snapshot
of every Medicare-certified facility. We use it for two purposes:

  1. Add the ~1,500 specialty/critical-access/psychiatric hospitals that the
     star-rated PI list (Stage 1) does not include. These hospitals exist in
     the CMS census but lack a star rating and therefore are not in xubh-q36u.
  2. Enrich every existing checkpoint row with `bed_count`, `medicare_carrier_code`,
     and `hospital_ownership` corrections from the POS file's authoritative columns.

The POS file does NOT contain NPIs. NPI resolution happens in Stage 2B
(`stage2_npi_registry.py`) via per-hospital NPPES Registry API lookups.

Source
------
CMS dataset "Provider of Services File - Quality Improvement and Evaluation System"
  Stable API: https://data.cms.gov/data-api/v1/dataset/8ba0f9b4-9493-4aa0-9f82-44ea9468d1b5/data
  Refresh:   quarterly
  Cost:      free
  ~30,000 rows total; we filter to hospital provider categories only.

Provider categories we keep (PRVDR_CTGRY_CD):
  01  Short-Term Acute Care Hospital
  02  Long-Term Care Hospital
  04  Religious Non-Medical Health Care Institution
  06  Psychiatric Hospital
  07  Rehabilitation Hospital
  08  Children's Hospital
  14  Critical Access Hospital
  21  Distinct Part Psychiatric Unit
  22  Distinct Part Rehabilitation Unit

The full dataset includes nursing homes, hospices, ambulatory surgical centres,
etc. None of those publish CMS Hospital Price Transparency MRFs (different rule),
so we filter at parse time.

Output
------
For each kept POS row:
  - If CCN already in checkpoint: UPDATE bed_count, medicare_carrier_code,
    hospital_type where currently NULL. Stage 1's PI-list values are kept
    when present (better case formatting than POS's ALL CAPS). nppes_resolved_at
    stays NULL — that gate is owned by Stage 2B.
  - If CCN NOT in checkpoint: INSERT a new row with cms_loaded_at = NOW().

The substep is idempotent within a run: re-running it for the same run_id
makes no changes to rows that already have non-NULL bed_count from POS.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import requests
from google.cloud import bigquery

# Allow running as a script
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from mrf_discovery import bq_checkpoint  # type: ignore[no-redef]
else:
    from . import bq_checkpoint

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

POS_API = "https://data.cms.gov/data-api/v1/dataset/8ba0f9b4-9493-4aa0-9f82-44ea9468d1b5/data"
USER_AGENT = (
    "ClaroBill-MRFDiscovery/1.0 "
    "(price transparency research; contact@clarobill.com)"
)
PAGE_SIZE = 5000  # POS rows are wide (~470 cols) so smaller pages avoid timeouts
REQUEST_TIMEOUT = 90

# Provider categories that publish CMS Hospital Price Transparency MRFs.
# Source: 42 CFR 482 + 42 CFR 485.
#
# Distinct-part unit codes (21 psychiatric, 22 rehabilitation) are deliberately
# EXCLUDED. Their parent acute-care hospital's MRF covers them (same building,
# same chargemaster). Including them in Sandra's 2026-04-28 real run produced
# 15,324 distinct-part psych unit rows — 5x our actual hospital target —
# because every short-term acute care hospital with a psych wing has a
# separate CCN for that wing.
HOSPITAL_PRVDR_CTGRY_CDS = frozenset({"01", "02", "04", "06", "07", "08", "14"})

# US states + DC + territories. CMS POS occasionally tags cross-border or
# US-government-abroad facilities with country codes like 'CN' (Canada) or
# 'MX' (Mexico). Sandra's 2026-04-28 run pulled in 270 such rows. ClaroBill
# audits US bills against US chargemasters, so we filter to US-only.
US_STATE_CODES = frozenset({
    "AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL","IN",
    "IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH",
    "NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT",
    "VT","VA","WA","WV","WI","WY",
    # Territories that participate in CMS Medicare:
    "PR", "VI", "GU", "MP", "AS",
    # Military "states":
    "AA", "AE", "AP",
})


def fetch_all_pos_rows(api_url: str = POS_API) -> Iterator[dict]:
    """Yield every POS row, paginated by `offset` and `size` parameters.

    The API returns a JSON array on each page. Empty array signals end. We use
    a generator (not list) because the full dataset is ~30,000 rows × ~470 cols
    = ~150 MB in memory if we materialised it; streaming keeps the working set
    bounded.
    """
    # SF7 (Phase 8.4): hard cap on pagination to prevent runaway loops
    # if the upstream stops honoring `len(rows) < PAGE_SIZE` as the
    # termination signal (the H6 pattern alive in Stage 2A pre-fix).
    # POS file is ~30K rows / 5K per page = 6 pages; 100 is generous.
    MAX_PAGES = 100

    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    offset = 0
    page = 0
    total_yielded = 0

    while page < MAX_PAGES:
        url = f"{api_url}?offset={offset}&size={PAGE_SIZE}"
        page += 1
        logger.info("  POS page %d (offset=%d)", page, offset)
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        rows = resp.json()
        if not isinstance(rows, list) or not rows:
            break
        for row in rows:
            yield row
            total_yielded += 1
        if len(rows) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        time.sleep(0.25)  # polite
    else:
        logger.warning(
            "POS fetch hit MAX_PAGES=%d cap (offset=%d, yielded=%d). "
            "Investigate before re-running — upstream may be returning "
            "full pages indefinitely.",
            MAX_PAGES, offset, total_yielded,
        )

    logger.info("POS fetch complete: %d rows yielded across %d pages", total_yielded, page)


def is_hospital(row: dict) -> bool:
    """True if this POS row is a US hospital category we care about.

    Two filters:
      1. PRVDR_CTGRY_CD must be in HOSPITAL_PRVDR_CTGRY_CDS — excludes nursing
         homes, hospices, ambulatory surgical centres, ESRD, AND distinct-part
         psychiatric/rehab units.
      2. STATE_CD must be in US_STATE_CODES — excludes cross-border and
         US-government-abroad facilities (CN, MX, etc.) that occasionally
         appear in CMS POS.
    """
    if (row.get("PRVDR_CTGRY_CD") or "").strip() not in HOSPITAL_PRVDR_CTGRY_CDS:
        return False
    if (row.get("STATE_CD") or "").strip().upper() not in US_STATE_CODES:
        return False
    return True


def normalise_pos_row(raw: dict) -> dict | None:
    """Convert a raw POS row into a checkpoint-shaped dict.

    Returns None if the row lacks PRVDR_NUM (CCN) or FAC_NAME. We do NOT
    populate hospital_npi from this source — substep B does that via NPPES.
    """
    ccn = (raw.get("PRVDR_NUM") or "").strip()
    name = (raw.get("FAC_NAME") or "").strip()
    if not ccn or not name:
        return None

    return {
        "ccn": ccn,
        "hospital_name": name,
        "address": _clean(raw.get("ST_ADR")),
        "city": _clean(raw.get("CITY_NAME")),
        "state": _clean(raw.get("STATE_CD")),
        "zip_code": _clean(raw.get("ZIP_CD")),
        "phone": _clean(raw.get("PHNE_NUM")),
        "hospital_type": _category_label(raw.get("PRVDR_CTGRY_CD")),
        "bed_count": _parse_int(raw.get("BED_CNT")),
        "medicare_carrier_code": _clean(raw.get("INTRMDRY_CARR_CD")),
    }


def _clean(val) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def _parse_int(val) -> int | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


_CATEGORY_LABELS = {
    "01": "Short-term Acute Care Hospital",
    "02": "Long-term Care Hospital",
    "04": "Religious Non-Medical Health Care Institution",
    "06": "Psychiatric Hospital",
    "07": "Rehabilitation Hospital",
    "08": "Children's Hospital",
    "14": "Critical Access Hospital",
    # Codes 21 (Distinct Part Psychiatric Unit) and 22 (Distinct Part
    # Rehabilitation Unit) are deliberately omitted from the filter set
    # above; their labels are not needed.
}


def _category_label(cd) -> str | None:
    if cd is None:
        return None
    return _CATEGORY_LABELS.get(str(cd).strip())


def apply_to_checkpoint(
    bq_client: bigquery.Client,
    project: str,
    run_id: str,
    pos_rows: list[dict],
    dataset: str = bq_checkpoint.DEFAULT_DATASET,
    dry_run: bool = False,
) -> dict[str, int]:
    """Merge POS rows into the inflight checkpoint table.

    Two-phase update:
      1. UPSERT POS rows into a staging table keyed by (run_id, ccn).
      2. MERGE into mrf_discovery_checkpoint:
         - WHEN MATCHED on ccn: UPDATE bed_count and medicare_carrier_code only
           where currently NULL (don't clobber Stage 1 PI-list values).
         - WHEN NOT MATCHED: INSERT a fresh row with cms_loaded_at = NOW()
           (these are the ~1,500 hospitals not in the PI list).

    Returns counts: matched, inserted, total_processed.
    """
    if not pos_rows:
        return {"matched": 0, "inserted": 0, "total_processed": 0}

    checkpoint_table = f"{project}.{dataset}.mrf_discovery_checkpoint"
    staging_table = f"{project}.{dataset}._stage2_pos_staging_{run_id.replace('-', '_').lower()}"
    now_iso = datetime.now(timezone.utc).isoformat()

    # Add run_id and timestamps to every staging row
    staging_rows = [
        {
            "run_id": run_id,
            "last_updated_at": now_iso,
            **row,
        }
        for row in pos_rows
    ]

    if dry_run:
        logger.info("[dry-run] would stage %d POS rows + MERGE into checkpoint", len(staging_rows))
        return {"matched": 0, "inserted": 0, "total_processed": len(staging_rows)}

    # Create staging table, insert rows, MERGE, drop staging table.
    # CREATE OR REPLACE handles the case where a prior run crashed mid-insert
    # and left an orphan staging table behind.
    logger.info("Creating staging table %s", staging_table)
    bq_client.query(f"""
        CREATE OR REPLACE TABLE `{staging_table}` (
          run_id                  STRING,
          ccn                     STRING,
          hospital_name           STRING,
          address                 STRING,
          city                    STRING,
          state                   STRING,
          zip_code                STRING,
          phone                   STRING,
          hospital_type           STRING,
          bed_count               INT64,
          medicare_carrier_code   STRING,
          last_updated_at         TIMESTAMP
        )
    """).result()

    # BigQuery streaming insert has practical limits around 10MB per request.
    # The full POS dataset is ~30,000 rows × ~12 columns of strings/ints, which
    # easily exceeds that — Sandra hit a 600s timeout pushing all 29,583 rows
    # in one HTTP body on 2026-04-28. We batch into chunks small enough that
    # each request completes in a few seconds.
    BATCH = 500
    logger.info("Loading %d POS rows into staging (batches of %d)", len(staging_rows), BATCH)
    try:
        for i in range(0, len(staging_rows), BATCH):
            chunk = staging_rows[i : i + BATCH]
            errors = bq_client.insert_rows_json(staging_table, chunk)
            if errors:
                raise RuntimeError(f"Staging insert failed at batch starting {i}: {errors[:3]}")
            if (i // BATCH) % 10 == 0:
                logger.info("  inserted %d / %d rows", min(i + BATCH, len(staging_rows)), len(staging_rows))
    except Exception:
        bq_client.query(f"DROP TABLE IF EXISTS `{staging_table}`").result()
        raise

    try:
        # MERGE: update bed_count and medicare_carrier_code on existing rows
        # where they're currently NULL; insert brand-new rows for CCNs not in
        # the checkpoint at all. Hospital_name and address are NOT updated on
        # match because Stage 1's PI-list values are likely cleaner formatting
        # (POS uses ALL CAPS, PI list uses Title Case).
        merge_sql = f"""
        MERGE `{checkpoint_table}` T
        USING `{staging_table}` S
        ON T.run_id = S.run_id AND T.ccn = S.ccn
        WHEN MATCHED THEN
          UPDATE SET
            bed_count             = COALESCE(T.bed_count, S.bed_count),
            medicare_carrier_code = COALESCE(T.medicare_carrier_code, S.medicare_carrier_code),
            hospital_type         = COALESCE(T.hospital_type, S.hospital_type),
            last_updated_at       = S.last_updated_at
        WHEN NOT MATCHED THEN
          INSERT (run_id, ccn, hospital_name, address, city, state, zip_code,
                  phone, hospital_type, bed_count, medicare_carrier_code,
                  cms_loaded_at, last_updated_at, consecutive_failures)
          VALUES (S.run_id, S.ccn, S.hospital_name, S.address, S.city, S.state,
                  S.zip_code, S.phone, S.hospital_type, S.bed_count,
                  S.medicare_carrier_code, S.last_updated_at, S.last_updated_at, 0)
        """
        logger.info("Executing MERGE")
        merge_job = bq_client.query(merge_sql)
        merge_job.result()

        # Count matched vs inserted via num_dml_affected_rows is not split by
        # type — we use a follow-up query to tell them apart.
        post_count_sql = f"""
        SELECT
          COUNTIF(bq_committed_at IS NULL AND cms_loaded_at = TIMESTAMP(@now)) AS just_inserted,
          (SELECT COUNT(*) FROM `{checkpoint_table}` WHERE run_id = @run_id) AS total_in_checkpoint
        FROM `{checkpoint_table}`
        WHERE run_id = @run_id
        """
        count_job = bq_client.query(
            post_count_sql,
            job_config=bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("run_id", "STRING", run_id),
                bigquery.ScalarQueryParameter("now", "TIMESTAMP", now_iso),
            ]),
        )
        count_row = next(iter(count_job.result()))
        just_inserted = int(count_row["just_inserted"] or 0)
        total = int(count_row["total_in_checkpoint"] or 0)
        matched = len(staging_rows) - just_inserted

        logger.info(
            "MERGE result: matched=%d, inserted=%d, total_in_checkpoint=%d",
            matched, just_inserted, total,
        )
        return {
            "matched": matched,
            "inserted": just_inserted,
            "total_processed": len(staging_rows),
        }
    finally:
        logger.info("Dropping staging table %s", staging_table)
        bq_client.query(f"DROP TABLE IF EXISTS `{staging_table}`").result()


def run(
    bq_client: bigquery.Client,
    project: str,
    run_id: str,
    dataset: str = bq_checkpoint.DEFAULT_DATASET,
    api_url: str = POS_API,
    dry_run: bool = False,
) -> dict[str, int]:
    """Fetch POS file, filter to hospitals, MERGE into checkpoint.

    Returns counts: pos_total, pos_hospital, pos_skipped_missing_required,
    matched, inserted.
    """
    pos_total = 0
    pos_hospital = 0
    pos_skipped = 0
    seed_rows: list[dict] = []

    logger.info("Streaming POS file from %s", api_url)
    for raw in fetch_all_pos_rows(api_url):
        pos_total += 1
        if not is_hospital(raw):
            continue
        normalised = normalise_pos_row(raw)
        if normalised is None:
            pos_skipped += 1
            continue
        pos_hospital += 1
        seed_rows.append(normalised)

    logger.info(
        "POS scan: total=%d hospitals=%d skipped_missing=%d",
        pos_total, pos_hospital, pos_skipped,
    )

    merge_summary = apply_to_checkpoint(
        bq_client, project, run_id, seed_rows, dataset=dataset, dry_run=dry_run,
    )

    return {
        "pos_total": pos_total,
        "pos_hospital": pos_hospital,
        "pos_skipped_missing_required": pos_skipped,
        **merge_summary,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--project", default="clarobill-prd")
    parser.add_argument("--dataset", default=bq_checkpoint.DEFAULT_DATASET)
    parser.add_argument(
        "--run-id",
        required=True,
        help="Run ID from Stage 1 (e.g. 20260428T135630Z_e37a012d)",
    )
    parser.add_argument("--api-url", default=POS_API)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    logger.info("Stage 2A starting: project=%s run_id=%s", args.project, args.run_id)
    client = bigquery.Client(project=args.project)
    summary = run(
        bq_client=client,
        project=args.project,
        run_id=args.run_id,
        dataset=args.dataset,
        api_url=args.api_url,
        dry_run=args.dry_run,
    )

    logger.info(
        "Stage 2A complete: pos_total=%d pos_hospital=%d matched=%d inserted=%d",
        summary["pos_total"], summary["pos_hospital"],
        summary["matched"], summary["inserted"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
