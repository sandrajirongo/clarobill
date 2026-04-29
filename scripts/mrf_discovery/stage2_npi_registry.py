"""Stage 2B: per-hospital NPPES Registry API lookup.

Resolves CCN -> NPI for every checkpoint row by querying NPPES's public
Registry API (https://npiregistry.cms.hhs.gov/api/) with name + state.
See `nppes_client.py` for client details and `docs/decisions/2026-04-28-mrf-discovery-build-insights.md`
for why we use the API and not the bulk download.

Fetches ~14,000 NPIs at ~5 req/s ≈ 47 minutes first run, near-instant on
re-runs (GCS-backed cache hits all already-resolved hospitals).

Run order
---------
Runs AFTER Stage 2A (POS file) has produced its final list of checkpoint
rows. Stage 2C (Wikidata) and Stage 3 (website discovery) can run before or
after this — there is no NPI-to-website dependency. The orchestrator runs:

    Stage 1  (CMS PI)
    Stage 2A (POS file)
    Stage 2B (this — NPI Registry API)
    Stage 2C (Wikidata)
    Stage 3+ (website discovery, crawler, etc.)

Output
------
Updates `mrf_discovery_checkpoint`:
  - hospital_npi             <- resolved NPI (or NULL if no match)
  - nppes_resolved_at        <- NOW() for every processed CCN

The website_source column is NOT touched here — websites come from Wikidata
(Stage 2C) or Stage 3.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from google.cloud import bigquery, storage

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from mrf_discovery import bq_checkpoint  # type: ignore[no-redef]
    from mrf_discovery.nppes_client import (  # type: ignore[no-redef]
        NppesClient,
        load_cache_from_gcs,
        save_cache_to_gcs,
    )
else:
    from . import bq_checkpoint
    from .nppes_client import NppesClient, load_cache_from_gcs, save_cache_to_gcs

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CACHE_BUCKET = "mrf-staging"
CACHE_OBJECT = "nppes-api-cache.json"
SAVE_CACHE_EVERY = 200  # rows; balance cache durability vs GCS write cost


def get_unresolved_hospitals(
    bq_client: bigquery.Client,
    project: str,
    run_id: str,
    dataset: str = bq_checkpoint.DEFAULT_DATASET,
) -> list[dict]:
    """Return checkpoint rows that still need NPI resolution.

    Filters to rows where hospital_npi IS NULL AND state IS NOT NULL.

    - hospital_npi IS NULL — picks up rows that haven't been resolved yet.
    - state IS NOT NULL — the NPPES Registry API rejects requests without a
      state parameter. Skipping these rows avoids 100% no-match outcomes
      that would otherwise poison the cache. Rare in practice (CMS PI rows
      always have state) but possible for POS rows with empty STATE_CD.
    """
    sql = f"""
    SELECT ccn, hospital_name, state, city
    FROM `{project}.{dataset}.mrf_discovery_checkpoint`
    WHERE run_id = @run_id
      AND hospital_npi IS NULL
      AND state IS NOT NULL
      AND hospital_name IS NOT NULL
    ORDER BY ccn
    """
    job = bq_client.query(
        sql,
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("run_id", "STRING", run_id),
        ]),
    )
    return [dict(row) for row in job.result()]


def apply_npis(
    bq_client: bigquery.Client,
    project: str,
    run_id: str,
    npi_by_ccn: dict[str, str],
    all_target_ccns: list[str],
    dataset: str = bq_checkpoint.DEFAULT_DATASET,
    dry_run: bool = False,
) -> dict[str, int]:
    """Stage NPIs, MERGE into checkpoint, mark all targets nppes_resolved_at.

    Two effects in one MERGE:
      - For target CCNs with a resolved NPI: write hospital_npi.
      - For all target CCNs (matched or not): set nppes_resolved_at = NOW().
    """
    if not all_target_ccns:
        return {"matched": 0, "no_match": 0, "total_processed": 0}

    checkpoint_table = f"{project}.{dataset}.mrf_discovery_checkpoint"
    staging_table = f"{project}.{dataset}._stage2_npi_staging_{run_id.replace('-', '_').lower()}"
    now_iso = datetime.now(timezone.utc).isoformat()

    staging_rows = [
        {
            "run_id": run_id,
            "ccn": ccn,
            "hospital_npi": npi_by_ccn.get(ccn),
            "nppes_resolved_at": now_iso,
        }
        for ccn in all_target_ccns
    ]

    matched = sum(1 for r in staging_rows if r["hospital_npi"])
    no_match = len(staging_rows) - matched

    if dry_run:
        logger.info(
            "[dry-run] would stage %d rows (%d with NPI, %d no match) and MERGE",
            len(staging_rows), matched, no_match,
        )
        return {"matched": matched, "no_match": no_match, "total_processed": len(staging_rows)}

    bq_client.query(f"""
        CREATE OR REPLACE TABLE `{staging_table}` (
          run_id              STRING,
          ccn                 STRING,
          hospital_npi        STRING,
          nppes_resolved_at   TIMESTAMP
        )
    """).result()

    try:
        BATCH = 500
        for i in range(0, len(staging_rows), BATCH):
            chunk = staging_rows[i : i + BATCH]
            errors = bq_client.insert_rows_json(staging_table, chunk)
            if errors:
                raise RuntimeError(f"NPI staging insert failed at batch {i}: {errors[:3]}")

        merge_sql = f"""
        MERGE `{checkpoint_table}` T
        USING `{staging_table}` S
        ON T.run_id = S.run_id AND T.ccn = S.ccn
        WHEN MATCHED THEN
          UPDATE SET
            hospital_npi      = COALESCE(T.hospital_npi, S.hospital_npi),
            nppes_resolved_at = S.nppes_resolved_at,
            last_updated_at   = S.nppes_resolved_at
        """
        bq_client.query(merge_sql).result()
        return {
            "matched": matched,
            "no_match": no_match,
            "total_processed": len(staging_rows),
        }
    finally:
        bq_client.query(f"DROP TABLE IF EXISTS `{staging_table}`").result()


def run(
    bq_client: bigquery.Client,
    storage_client: storage.Client,
    project: str,
    run_id: str,
    dataset: str = bq_checkpoint.DEFAULT_DATASET,
    cache_bucket: str = CACHE_BUCKET,
    cache_object: str = CACHE_OBJECT,
    dry_run: bool = False,
) -> dict[str, int]:
    targets = get_unresolved_hospitals(bq_client, project, run_id, dataset=dataset)
    logger.info("Stage 2B (API): %d hospitals need NPI resolution", len(targets))
    if not targets:
        return {"target_count": 0, "matched": 0, "no_match": 0, "from_cache": 0, "from_api": 0}

    cache = load_cache_from_gcs(storage_client, cache_bucket, cache_object)
    logger.info("Loaded %d cached entries from gs://%s/%s", len(cache), cache_bucket, cache_object)
    client = NppesClient(cache=cache)

    npi_by_ccn: dict[str, str] = {}
    from_cache = 0
    from_api = 0
    matched_count = 0
    no_match_count = 0
    via_counts: dict[str, int] = {}

    for i, hospital in enumerate(targets, start=1):
        ccn = hospital["ccn"]
        name = hospital["hospital_name"]
        state = hospital["state"]
        city = hospital.get("city")

        # Was this a cache hit before the call? Compare cache snapshot before
        # vs after the lookup to know.
        key = NppesClient.cache_key(name, state, city)
        was_cached = key in cache

        result = client.lookup(name, state, city)

        if was_cached:
            from_cache += 1
        else:
            from_api += 1

        if result.npi:
            npi_by_ccn[ccn] = result.npi
            matched_count += 1
        else:
            no_match_count += 1

        via_counts[result.matched_via] = via_counts.get(result.matched_via, 0) + 1

        if i % 200 == 0:
            logger.info(
                "  %d/%d processed (cache=%d api=%d match=%d no_match=%d)",
                i, len(targets), from_cache, from_api, matched_count, no_match_count,
            )
            if not dry_run:
                save_cache_to_gcs(storage_client, cache_bucket, cache_object, client.cache_snapshot())

    # Final cache flush
    if not dry_run:
        save_cache_to_gcs(storage_client, cache_bucket, cache_object, client.cache_snapshot())
        logger.info("Final cache size: %d entries", len(client.cache_snapshot()))

    logger.info("Match outcomes: %s", via_counts)

    apply_summary = apply_npis(
        bq_client, project, run_id, npi_by_ccn, [t["ccn"] for t in targets],
        dataset=dataset, dry_run=dry_run,
    )

    return {
        "target_count": len(targets),
        "from_cache": from_cache,
        "from_api": from_api,
        "via_counts": via_counts,
        **apply_summary,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--project", default="clarobill-prd")
    parser.add_argument("--dataset", default=bq_checkpoint.DEFAULT_DATASET)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--cache-bucket", default=CACHE_BUCKET)
    parser.add_argument("--cache-object", default=CACHE_OBJECT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    logger.info("Stage 2B (API) starting: project=%s run_id=%s", args.project, args.run_id)
    bq_client = bigquery.Client(project=args.project)
    storage_client = storage.Client(project=args.project)
    summary = run(
        bq_client=bq_client,
        storage_client=storage_client,
        project=args.project,
        run_id=args.run_id,
        dataset=args.dataset,
        cache_bucket=args.cache_bucket,
        cache_object=args.cache_object,
        dry_run=args.dry_run,
    )
    logger.info(
        "Stage 2B (API) complete: targets=%d matched=%d no_match=%d (cache=%d api=%d)",
        summary["target_count"], summary["matched"], summary["no_match"],
        summary["from_cache"], summary["from_api"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
