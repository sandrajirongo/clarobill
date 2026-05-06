"""Stage 6 — Merge discovery checkpoint MRF URLs into hospital_directory.

Expands the JSON array in mrf_discovery_checkpoint.validated_mrf_urls into
individual rows and MERGEs them into hospital_directory, which is the table
the scraper reads to know which MRF files to download.

Match key: (ccn, mrf_url). This is the correct composite key because:
  - A hospital (identified by CCN) may publish multiple MRF files.
  - The scraper and archive_index de-duplicate by URL, so inserting the same
    URL twice would be a no-op at the scraper level, but MERGE prevents it.

Effects:
  - Existing hospital_directory rows matched by (ccn, mrf_url): backfill
    hospital_npi and hospital_website from checkpoint if currently NULL.
  - New (ccn, mrf_url) pairs not in hospital_directory: INSERT new rows.
  - Existing Payerset rows with different URLs for the same CCN: untouched
    (the scraper will attempt all URLs and retire ones that 404).

Idempotent: safe to re-run. A second run produces 0 inserts and 0 updates
because all matched rows are already populated.

Run order:
  Runs after Stage 4 (extract_mrf_urls) has written validated_mrf_urls.
  Run again after any future Stage 4 top-up that adds more URLs.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from google.cloud import bigquery

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from mrf_discovery import bq_checkpoint  # type: ignore[no-redef]
else:
    from . import bq_checkpoint

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def count_pending(
    bq_client: bigquery.Client,
    project: str,
    run_id: str,
    dataset: str,
) -> int:
    row = next(bq_client.query(f"""
        SELECT COUNT(*) AS cnt
        FROM `{project}.{dataset}.mrf_discovery_checkpoint`,
        UNNEST(JSON_VALUE_ARRAY(validated_mrf_urls)) AS mrf_url
        WHERE run_id = @run_id
          AND validated_mrf_urls IS NOT NULL
          AND validated_mrf_urls NOT IN ('[]', '')
    """, job_config=bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("run_id", "STRING", run_id),
    ])).result())
    return int(row["cnt"])


def run(
    bq_client: bigquery.Client,
    project: str,
    run_id: str,
    dataset: str = bq_checkpoint.DEFAULT_DATASET,
    dry_run: bool = False,
) -> dict[str, int]:
    pending = count_pending(bq_client, project, run_id, dataset)
    logger.info("Stage 6: %d (hospital, mrf_url) pairs to merge", pending)
    if not pending:
        return {"pending": 0, "inserted": 0, "updated": 0}

    checkpoint = f"{project}.{dataset}.mrf_discovery_checkpoint"
    directory = f"{project}.{dataset}.hospital_directory"

    merge_sql = f"""
    MERGE `{directory}` T
    USING (
      SELECT
        c.ccn,
        c.hospital_npi,
        c.hospital_name,
        c.state,
        c.city,
        c.hospital_website,
        c.website_source AS mrf_discovery_method,
        TRIM(mrf_url) AS mrf_url
      FROM `{checkpoint}` c,
      UNNEST(JSON_VALUE_ARRAY(c.validated_mrf_urls)) AS mrf_url
      WHERE c.run_id = @run_id
        AND c.validated_mrf_urls IS NOT NULL
        AND c.validated_mrf_urls NOT IN ('[]', '')
        AND TRIM(mrf_url) != ''
      QUALIFY ROW_NUMBER() OVER (
        PARTITION BY c.ccn, TRIM(mrf_url)
        ORDER BY c.mrf_validated_at DESC
      ) = 1
    ) S
    ON T.ccn IS NOT NULL AND T.ccn = S.ccn AND T.mrf_url = S.mrf_url
    WHEN MATCHED AND (T.hospital_npi IS NULL OR T.hospital_website IS NULL) THEN
      UPDATE SET
        hospital_npi      = COALESCE(T.hospital_npi, S.hospital_npi),
        hospital_website  = COALESCE(T.hospital_website, S.hospital_website),
        mrf_discovery_method = S.mrf_discovery_method
    WHEN NOT MATCHED BY TARGET THEN
      INSERT (ccn, hospital_npi, hospital_name, state, city,
              mrf_url, hospital_website, mrf_discovery_method)
      VALUES (S.ccn, S.hospital_npi, S.hospital_name, S.state, S.city,
              S.mrf_url, S.hospital_website, S.mrf_discovery_method)
    """  # noqa: S608

    if dry_run:
        logger.info("[dry-run] would MERGE %d source rows into %s", pending, directory)
        logger.info("[dry-run] SQL:\n%s", merge_sql)
        return {"pending": pending, "inserted": 0, "updated": 0}

    job = bq_client.query(
        merge_sql,
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("run_id", "STRING", run_id),
        ]),
    )
    job.result()

    stats = job.dml_stats
    inserted = stats.inserted_row_count if stats else 0
    updated = stats.updated_row_count if stats else 0
    logger.info(
        "Stage 6 complete: inserted=%d updated=%d (of %d source pairs)",
        inserted, updated, pending,
    )
    return {"pending": pending, "inserted": inserted, "updated": updated}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--project", default="clarobill-prd")
    parser.add_argument("--dataset", default=bq_checkpoint.DEFAULT_DATASET)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    logger.info(
        "Stage 6 (merge to directory) starting: project=%s run_id=%s dry_run=%s",
        args.project, args.run_id, args.dry_run,
    )
    bq_client = bigquery.Client(project=args.project)
    summary = run(
        bq_client=bq_client,
        project=args.project,
        run_id=args.run_id,
        dataset=args.dataset,
        dry_run=args.dry_run,
    )
    logger.info("Summary: %s", summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
