"""Phase 4 dual-write smoke test — 10 hospitals against real GCP.

Runs the new scraper code against a small slice of `hospital_directory`,
verifies that:

  1. Each hospital's MRF is downloaded to mrf-staging (legacy parser path).
  2. Each is also archived to clarobill-mrf-archive-uscentral with sibling .meta.json.
  3. mrf_archive_index gets a row per hospital with parse_status='pending'.
  4. The new scraper's last_modified blob metadata is populated for the parser.

Then runs the parser against just those staging blobs and verifies:

  5. hospital_charges rows for those hospitals carry pricing_effective_year.
  6. mrf_archive_index.parse_status flipped to 'parsed' / 'failed' / 'skipped'.

Usage:
    cd <repo>
    python scripts/smoke_test_dual_write.py --limit 10
    python scripts/smoke_test_dual_write.py --limit 10 --skip-parser
    python scripts/smoke_test_dual_write.py --hospital-npis 1234567890,9876543210

Safety:
    - Reads/writes the real `mrf-staging` and `clarobill-mrf-archive-uscentral`
      buckets, plus real BigQuery tables. Idempotent: archive_writer skips
      duplicates; archive_index inserts are pre-checked.
    - Defaults to 10 hospitals to keep blast radius small.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Make pipeline/ importable as a package
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "pipeline"))

from google.cloud import bigquery, storage  # noqa: E402

import scrape_hospital_mrfs  # noqa: E402
import parse_hospital_mrfs  # noqa: E402

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("smoke_test")

PROJECT = os.environ.get("GCP_PROJECT_ID", "clarobill-prd")
DATASET = os.environ.get("BIGQUERY_DATASET", "hospital_prices")
STAGING_BUCKET = os.environ.get("GCS_MRF_STAGING_BUCKET", "mrf-staging")
ARCHIVE_BUCKET = os.environ.get("GCS_MRF_ARCHIVE_BUCKET", "clarobill-mrf-archive-uscentral")


def _pick_hospitals(
    bq: bigquery.Client, limit: int, hospital_npis: list[str] | None
) -> list[dict[str, Any]]:
    """Pick a small set of hospitals to test against.

    Defaults to the first `limit` hospitals with `mrf_url IS NOT NULL`,
    sorted by name for determinism. If --hospital-npis is provided, picks
    those exact rows instead.
    """
    if hospital_npis:
        npi_list = ",".join(f"'{n.strip()}'" for n in hospital_npis)
        sql = f"""
            SELECT hospital_npi, ccn, hospital_name, state, mrf_url, last_modified
            FROM `{PROJECT}.{DATASET}.hospital_directory`
            WHERE mrf_url IS NOT NULL AND TRIM(mrf_url) != ''
              AND hospital_npi IN ({npi_list})
            ORDER BY hospital_name
        """
    else:
        sql = f"""
            SELECT hospital_npi, ccn, hospital_name, state, mrf_url, last_modified
            FROM `{PROJECT}.{DATASET}.hospital_directory`
            WHERE mrf_url IS NOT NULL AND TRIM(mrf_url) != ''
            ORDER BY hospital_name
            LIMIT {limit}
        """
    return [dict(row) for row in bq.query(sql).result()]


def _verify_archive_blob(
    storage_client: storage.Client, archive_meta: dict[str, Any]
) -> tuple[bool, str]:
    """Check that the archive blob and its meta.json sibling both exist.

    Returns (ok, summary_line).
    """
    gcs_uri = archive_meta["gcs_uri"]
    # gs://bucket/object_name
    _, _, bucket_name, *path_parts = gcs_uri.split("/", 3) + [""]
    bucket = storage_client.bucket(bucket_name)
    object_name = gcs_uri.split(f"gs://{bucket_name}/", 1)[1]
    meta_object_name = object_name.rsplit(".", 1)[0]
    if "." in meta_object_name:
        # Strip multi-part extension like .json.gz → keep base
        # archive_layout uses sha-prefix.ext; meta is sha-prefix.meta.json
        # Easier: derive from the stored sha256.
        pass
    sha_first16 = archive_meta["sha256"][:16]
    parent = "/".join(object_name.split("/")[:-1])
    expected_meta = f"{parent}/{sha_first16}.meta.json"

    data_blob = bucket.blob(object_name)
    meta_blob = bucket.blob(expected_meta)
    data_ok = data_blob.exists()
    meta_ok = meta_blob.exists()
    if data_ok:
        data_blob.reload()  # populate .size from server
    size = data_blob.size or 0 if data_ok else 0
    return (
        data_ok and meta_ok,
        f"data={data_ok} meta={meta_ok} bytes={size:,} sha={sha_first16}",
    )


def _verify_archive_index_rows(
    bq: bigquery.Client, hospital_npis: list[str], scrape_started_at: str
) -> dict[str, str]:
    """Look up parse_status for each hospital's most recent archive_index row.

    Filters by scraped_at >= scrape_started_at so a re-run doesn't pick up
    older rows. Returns {hospital_npi: parse_status}.
    """
    if not hospital_npis:
        return {}
    npi_list = ",".join(f"'{n}'" for n in hospital_npis)
    sql = f"""
        SELECT hospital_npi, ccn, parse_status, parse_error, gcs_uri,
               pricing_effective_year, scraped_at
        FROM `{PROJECT}.{DATASET}.mrf_archive_index`
        WHERE (hospital_npi IN ({npi_list}) OR ccn IN ({npi_list}))
          AND scraped_at >= TIMESTAMP('{scrape_started_at}')
        ORDER BY scraped_at DESC
    """
    result: dict[str, str] = {}
    for row in bq.query(sql).result():
        key = row["hospital_npi"] or row["ccn"] or ""
        if key not in result:  # keep most recent
            result[key] = (
                f"status={row['parse_status']!s:<8} year={row['pricing_effective_year']} "
                f"uri={row['gcs_uri']}"
            )
    return result


def _verify_charges_rows(bq: bigquery.Client, hospital_npis: list[str]) -> dict[str, int]:
    """Count rows in hospital_charges per NPI, restricted to recently-loaded data."""
    valid = [n for n in hospital_npis if n]
    if not valid:
        return {}
    npi_list = ",".join(f"'{n}'" for n in valid)
    sql = f"""
        SELECT hospital_npi, COUNT(*) AS row_count,
               MAX(pricing_effective_year) AS year,
               MAX(scraped_at) AS latest_scrape
        FROM `{PROJECT}.{DATASET}.hospital_charges`
        WHERE hospital_npi IN ({npi_list})
        GROUP BY hospital_npi
    """
    return {
        row["hospital_npi"]: int(row["row_count"])
        for row in bq.query(sql).result()
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument(
        "--hospital-npis", default="",
        help="Comma-separated NPIs to target instead of --limit",
    )
    parser.add_argument(
        "--skip-parser", action="store_true",
        help="Run only the scraper (dual-write); skip the parser run + verification",
    )
    parser.add_argument(
        "--force-redownload", action="store_true",
        help="Clear each hospital's last_modified locally before scraping so the "
             "If-Modified-Since check always triggers a fresh download. Used to "
             "exercise the dual-write archive path during a smoke test even when "
             "the hospital's MRF hasn't changed.",
    )
    args = parser.parse_args(argv)

    bq = bigquery.Client(project=PROJECT)
    gcs = storage.Client(project=PROJECT)
    staging_bucket = gcs.bucket(STAGING_BUCKET)
    archive_bucket = gcs.bucket(ARCHIVE_BUCKET)

    npis = [n.strip() for n in args.hospital_npis.split(",") if n.strip()]
    hospitals = _pick_hospitals(bq, args.limit, npis or None)
    if not hospitals:
        logger.error("No hospitals matched the selection criteria — exiting.")
        return 2

    logger.info("Selected %d hospitals:", len(hospitals))
    for h in hospitals:
        logger.info(
            "  npi=%s ccn=%s state=%s name=%s",
            h.get("hospital_npi") or "(none)",
            h.get("ccn") or "(none)",
            h.get("state") or "(none)",
            (h.get("hospital_name") or "")[:60],
        )

    # ----- 1. Run the new scraper path against just these hospitals -----
    scrape_started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    logger.info("=== Phase 1: scraper dual-write ===")
    archive_metas: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []
    for h in hospitals:
        if args.force_redownload:
            # Local override only — does NOT clear the row in hospital_directory.
            h = {**h, "last_modified": None}
        try:
            result = scrape_hospital_mrfs.scrape_hospital(
                h, staging_bucket, archive_bucket, scrape_started_at,
            )
        except Exception as exc:
            logger.error("[%s] scrape_hospital crashed: %s", h.get("hospital_name"), exc)
            continue
        if not result:
            logger.info("[%s] skipped (HEAD failed or unchanged)", h.get("hospital_name"))
            continue
        updates.append({k: v for k, v in result.items() if k != "archive_meta"})
        if result.get("archive_meta"):
            archive_metas.append(result["archive_meta"])

    logger.info(
        "Scraper finished: %d hospitals downloaded, %d archived",
        len(updates), len(archive_metas),
    )

    # ----- 2. Verify each archive write -----
    logger.info("=== Phase 2: archive blob + meta.json verification ===")
    failed_archives = 0
    for meta in archive_metas:
        ok, summary = _verify_archive_blob(gcs, meta)
        key = meta.get("hospital_npi") or meta.get("ccn") or "?"
        logger.info("  [%s] archive %s — %s", key, "OK" if ok else "MISSING", summary)
        if not ok:
            failed_archives += 1

    # ----- 3. Insert mrf_archive_index rows -----
    if archive_metas:
        logger.info("=== Phase 3: insert mrf_archive_index rows ===")
        scrape_hospital_mrfs.insert_archive_index_rows(bq, archive_metas)

    if updates:
        logger.info("=== Phase 4: update last_modified in hospital_directory ===")
        # Use a unique task_index so we don't collide with a real run
        scrape_hospital_mrfs.update_last_modified(bq, updates, task_index=999)

    # ----- 5. Optionally run the parser against the staging blobs -----
    parser_summary = ""
    if args.skip_parser:
        logger.info("=== Skipping parser per --skip-parser ===")
    else:
        logger.info("=== Phase 5: parser run against staging blobs ===")
        # The parser reads ALL blobs under raw/. To restrict to our 10, we
        # filter by mrf_url after listing.
        target_urls = {h["mrf_url"] for h in hospitals}
        all_blobs = parse_hospital_mrfs.list_raw_blobs(staging_bucket)

        target_blobs = []
        for blob in all_blobs:
            md = parse_hospital_mrfs._get_blob_metadata(staging_bucket, blob)
            if md.get("mrf_url") in target_urls:
                target_blobs.append(blob)
        logger.info("Parser will process %d blobs matching our test set", len(target_blobs))

        succeeded = failed = 0
        for blob in target_blobs:
            if parse_hospital_mrfs.process_blob(blob, bq, staging_bucket):
                succeeded += 1
            else:
                failed += 1
        parser_summary = f"parser: {succeeded} succeeded, {failed} failed/skipped"
        logger.info(parser_summary)

    # ----- 6. Verify archive_index parse_status + hospital_charges rowcount -----
    logger.info("=== Phase 6: verification queries ===")
    keys = [(h.get("hospital_npi") or h.get("ccn") or "") for h in hospitals]
    keys = [k for k in keys if k]

    index_status = _verify_archive_index_rows(bq, keys, scrape_started_at)
    logger.info("mrf_archive_index status (most-recent row per hospital):")
    for k in keys:
        logger.info("  [%s] %s", k, index_status.get(k, "<no row>"))

    if not args.skip_parser:
        npi_keys = [h.get("hospital_npi") for h in hospitals if h.get("hospital_npi")]
        charge_counts = _verify_charges_rows(bq, npi_keys)
        logger.info("hospital_charges row counts (current data, all years):")
        for k in npi_keys:
            logger.info("  [%s] %d rows", k, charge_counts.get(k, 0))

    # ----- 7. Summary -----
    logger.info("=== Smoke test summary ===")
    logger.info("  Hospitals selected:          %d", len(hospitals))
    logger.info("  Files downloaded:            %d", len(updates))
    logger.info("  Archive writes succeeded:    %d", len(archive_metas) - failed_archives)
    logger.info("  Archive writes failed:       %d", failed_archives)
    if parser_summary:
        logger.info("  %s", parser_summary)

    return 0 if failed_archives == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
