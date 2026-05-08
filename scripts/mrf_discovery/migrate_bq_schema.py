"""BigQuery schema migration for the CMS-direct MRF discovery pipeline.

This script is idempotent and reversible. It does six things:

  1. Renames the existing hospital_charges table to hospital_charges_legacy_stale.
     Existing rows have no pricing_effective_year, which means the rules engine
     would compare a 2026 bill to a chargemaster of unknown vintage. That is
     a correctness defect, not just stale data. The rename takes the table out
     of the rules-engine read path while preserving rows for forensics.

  2. Creates a fresh hospital_charges with pricing_effective_year as a NOT NULL
     column. Partitioned by pricing_effective_year (RANGE_BUCKET 2024-2034)
     and clustered by (hospital_npi, code) for the rules-engine join shape.

  3. Adds new columns to hospital_directory: ccn, address, zip_code, phone,
     hospital_website, mrf_pricing_effective_year, mrf_discovery_method,
     mrf_file_format, mrf_file_size_bytes, price_transparency_page_url. All
     NULLABLE so existing rows are unaffected.

  4. Creates mrf_archive_index. One row per archived MRF file in GCS. This is
     the canonical record of what we have stored, keyed by
     (hospital_npi, pricing_effective_year, sha256). The new scraper writes
     here; the new parser reads from here.

  5. Creates mrf_discovery_runs (annual summary, one row per discovery run).

  6. (--cleanup-pra-legacy) Drops PRA-themed tables and columns that were
     created by the original PRA-sourced design before we pivoted to CMS-direct.
     `pra_facility_index` and `pra_discovery_runs` are unused; the
     `pra_facility_uuid` and `last_pra_check` columns on hospital_directory
     are unused. See `docs/decisions/2026-04-28-cms-direct-mrf-discovery.md`
     for the pivot rationale.

Usage:

    # Inspect the planned changes only:
    python scripts/mrf_discovery/migrate_bq_schema.py --dry-run

    # Apply against the production project:
    python scripts/mrf_discovery/migrate_bq_schema.py --project clarobill-prd

    # Drop PRA-themed tables/columns left over from the abandoned PRA plan:
    python scripts/mrf_discovery/migrate_bq_schema.py --cleanup-pra-legacy

    # Roll back the rename (puts hospital_charges_legacy_stale back as
    # hospital_charges; only used in the unlikely case we need to abort
    # before parser cutover):
    python scripts/mrf_discovery/migrate_bq_schema.py --rollback-rename

The script logs each step. Re-running is safe: every CREATE/ALTER uses
IF NOT EXISTS, the rename is skipped if hospital_charges_legacy_stale
already exists, and the cleanup is idempotent.
"""

import argparse
import logging
import sys

from google.cloud import bigquery
from google.cloud.exceptions import NotFound

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_DATASET = "hospital_prices"


def _table_id(project: str, dataset: str, name: str) -> str:
    return f"{project}.{dataset}.{name}"


def _table_exists(client: bigquery.Client, table_id: str) -> bool:
    try:
        client.get_table(table_id)
        return True
    except NotFound:
        return False


def rename_hospital_charges_to_legacy(
    client: bigquery.Client,
    project: str,
    dataset: str,
    dry_run: bool,
) -> None:
    """Move the stale hospital_charges out of the rules-engine read path.

    The ALTER TABLE ... RENAME TO statement is a metadata-only operation
    (instant, free, preserves rows).
    """
    src = _table_id(project, dataset, "hospital_charges")
    dst = _table_id(project, dataset, "hospital_charges_legacy_stale")

    if _table_exists(client, dst):
        logger.info("Skip rename: %s already exists", dst)
        return

    if not _table_exists(client, src):
        logger.info("Skip rename: %s does not exist (fresh project)", src)
        return

    sql = f"ALTER TABLE `{src}` RENAME TO hospital_charges_legacy_stale"
    if dry_run:
        logger.info("[dry-run] %s", sql)
        return
    logger.info("Renaming %s -> hospital_charges_legacy_stale", src)
    client.query(sql).result()


def create_new_hospital_charges(
    client: bigquery.Client,
    project: str,
    dataset: str,
    dry_run: bool,
) -> None:
    """Create the effective-dated hospital_charges table.

    pricing_effective_year is REQUIRED so we cannot accidentally insert rows
    with unknown vintage. Partitioning on it means range queries by bill
    date stay fast as the table grows year over year.
    """
    table_id = _table_id(project, dataset, "hospital_charges")

    sql = f"""
    CREATE TABLE IF NOT EXISTS `{table_id}` (
      hospital_npi              STRING,
      code_type                 STRING,
      code                      STRING,
      description               STRING,
      gross_charge              FLOAT64,
      discounted_cash_price     FLOAT64,
      min_negotiated            FLOAT64,
      max_negotiated            FLOAT64,
      payer_name                STRING,
      plan_name                 STRING,
      negotiated_charge         FLOAT64,
      negotiated_type           STRING,
      setting                   STRING,
      pricing_effective_year    INT64 NOT NULL,
      source_mrf_url            STRING,
      source_gcs_uri            STRING,
      scraped_at                TIMESTAMP
    )
    PARTITION BY RANGE_BUCKET(pricing_effective_year, GENERATE_ARRAY(2024, 2034, 1))
    CLUSTER BY hospital_npi, code
    """
    if dry_run:
        logger.info("[dry-run] CREATE TABLE %s (effective-dated)", table_id)
        return
    logger.info("Creating %s", table_id)
    client.query(sql).result()


def recreate_hospital_directory_with_partition(
    client: bigquery.Client,
    project: str,
    dataset: str,
    dry_run: bool,
) -> None:
    """Recreate hospital_directory partitioned by DATE(last_website_validated_at).

    BQ cannot add a partition to an existing table via ALTER TABLE, so we use
    CTAS: create a new partitioned table from the existing data, add new
    identity columns (ein, website_discovery_method, last_website_validated_at),
    drop the old table, and rename. All existing rows are preserved.

    Idempotent: skips if last_website_validated_at already exists on the table.
    """
    table_id = _table_id(project, dataset, "hospital_directory")
    new_table_id = _table_id(project, dataset, "hospital_directory_new")

    if not _table_exists(client, table_id):
        logger.warning("hospital_directory does not exist; skipping recreate")
        return

    # Already done if the new column is present
    tbl = client.get_table(table_id)
    if any(f.name == "last_website_validated_at" for f in tbl.schema):
        logger.info("hospital_directory already partitioned; skipping")
        return

    # Clean up a previous interrupted run
    if _table_exists(client, new_table_id):
        logger.warning("hospital_directory_new exists from interrupted run; dropping")
        if not dry_run:
            client.query(f"DROP TABLE `{new_table_id}`").result()

    sql_ctas = f"""
    CREATE TABLE `{new_table_id}`
    PARTITION BY DATE(last_website_validated_at)
    CLUSTER BY ccn, hospital_npi
    OPTIONS(description="Hospital identity table. One row per US hospital. "
                        "Written by discovery Stages 1-3 only. Stage 4 does not write here. "
                        "Join to hospital_price_transparency on ccn for MRF file URLs.")
    AS
    SELECT
      *,
      CAST(NULL AS STRING)    AS ein,
      CAST(NULL AS STRING)    AS website_discovery_method,
      CAST(NULL AS TIMESTAMP) AS last_website_validated_at
    FROM `{table_id}`
    """

    if dry_run:
        logger.info("[dry-run] CTAS hospital_directory_new (partition + 3 new columns, %d rows)", client.get_table(table_id).num_rows)
        logger.info("[dry-run] DROP TABLE hospital_directory")
        logger.info("[dry-run] RENAME hospital_directory_new -> hospital_directory")
        logger.info("[dry-run] ALTER COLUMN descriptions (ein, website_discovery_method, last_website_validated_at)")
        return

    logger.info("CTAS: creating partitioned hospital_directory_new")
    client.query(sql_ctas).result()

    logger.info("Dropping old hospital_directory")
    client.query(f"DROP TABLE `{table_id}`").result()

    logger.info("Renaming hospital_directory_new -> hospital_directory")
    client.query(f"ALTER TABLE `{new_table_id}` RENAME TO hospital_directory").result()

    logger.info("Setting column descriptions on new columns")
    client.query(f"""
    ALTER TABLE `{table_id}`
      ALTER COLUMN ein
        SET OPTIONS(description="IRS Employer Identification Number. Nullable until IRS Form 990 loader is built."),
      ALTER COLUMN website_discovery_method
        SET OPTIONS(description="How the hospital website URL was found: tier1_direct, tier2_pattern, or tier3_google_places."),
      ALTER COLUMN last_website_validated_at
        SET OPTIONS(description="Timestamp of the most recent successful HTTP check of the hospital website URL. Drives the DATE partition.")
    """).result()


def create_mrf_archive_index(
    client: bigquery.Client,
    project: str,
    dataset: str,
    dry_run: bool,
) -> None:
    """Canonical index of every MRF file we have archived to GCS.

    The (hospital_npi, pricing_effective_year, sha256) tuple uniquely
    identifies a file. parse_status drives the parser's work queue. If a
    file is re-fetched later in the same year and the sha256 matches, we
    skip the download entirely.
    """
    table_id = _table_id(project, dataset, "mrf_archive_index")

    sql = f"""
    CREATE TABLE IF NOT EXISTS `{table_id}` (
      hospital_npi              STRING,
      ccn                       STRING,
      pricing_effective_year    INT64 NOT NULL,
      source_mrf_url            STRING NOT NULL,
      gcs_uri                   STRING NOT NULL,
      sha256                    STRING NOT NULL,
      file_size_bytes           INT64,
      content_type              STRING,
      mrf_last_modified_header  STRING,
      mrf_etag_header           STRING,
      scraped_at                TIMESTAMP NOT NULL,
      parse_status              STRING NOT NULL,  -- pending | parsed | failed | skipped
      parse_error               STRING,
      parsed_at                 TIMESTAMP
    )
    PARTITION BY RANGE_BUCKET(pricing_effective_year, GENERATE_ARRAY(2024, 2034, 1))
    CLUSTER BY hospital_npi, parse_status
    """
    if dry_run:
        logger.info("[dry-run] CREATE TABLE %s", table_id)
        return
    logger.info("Creating %s", table_id)
    client.query(sql).result()


def create_hospital_price_transparency(
    client: bigquery.Client,
    project: str,
    dataset: str,
    dry_run: bool,
) -> None:
    """Create the hospital_price_transparency table.

    Stage 4 MRF URL discovery output. One row per discovered price
    transparency file URL per hospital. Scraper reads from here.
    Stage 4 writes via MERGE on (ccn, mrf_url) -- never INSERT directly.
    """
    table_id = _table_id(project, dataset, "hospital_price_transparency")

    sql = f"""
    CREATE TABLE IF NOT EXISTS `{table_id}` (
      ccn                         STRING NOT NULL
        OPTIONS(description="CMS Certification Number. Primary join key to hospital_directory. 95.6% coverage across 56,116 US hospitals."),
      hospital_npi                STRING
        OPTIONS(description="National Provider Identifier. NULL at Stage 4 insert; backfilled by scraper from file content."),
      mrf_url                     STRING NOT NULL
        OPTIONS(description="Publicly accessible URL of the hospital price transparency file, as discovered by the Stage 4 crawler."),
      file_format                 STRING
        OPTIONS(description="True inner content format after gzip decompression: json, csv, xlsx, tsv, or zip. NULL at Stage 4 insert; set by scraper via sniff_mrf_format()."),
      price_transparency_page_url STRING
        OPTIONS(description="URL of the intermediate webpage where the MRF URL was found, if different from the hospital root site."),
      mrf_discovery_method        STRING
        OPTIONS(description="How the URL was found: pass1_cms_filename, pass2_keyword_anchor, pass3_data_ext, pass4_html_scan, or path_heuristic."),
      first_discovered_at         TIMESTAMP NOT NULL
        OPTIONS(description="Timestamp when Stage 4 first found this MRF URL."),
      last_validated_at           TIMESTAMP
        OPTIONS(description="Timestamp of the most recent HEAD request confirming this URL is still reachable."),
      last_scraped_at             TIMESTAMP
        OPTIONS(description="Timestamp of the most recent successful scraper download. Drives the DATE partition."),
      last_modified_header        STRING
        OPTIONS(description="HTTP Last-Modified header value from the most recent HEAD or GET request."),
      is_active                   BOOL DEFAULT TRUE
        OPTIONS(description="False if the most recent HEAD request returned 404 or the URL is otherwise unreachable.")
    )
    PARTITION BY DATE(last_scraped_at)
    CLUSTER BY ccn, hospital_npi
    OPTIONS(description="Stage 4 MRF URL discovery output. One row per discovered price transparency file URL per hospital. "
                        "Scraper reads from here. Stage 4 writes via MERGE on (ccn, mrf_url) -- never INSERT directly. "
                        "Join to hospital_directory on ccn for hospital identity.")
    """
    if dry_run:
        logger.info("[dry-run] CREATE TABLE %s", table_id)
        return
    logger.info("Creating %s", table_id)
    client.query(sql).result()


def create_mrf_discovery_runs(
    client: bigquery.Client,
    project: str,
    dataset: str,
    dry_run: bool,
) -> None:
    """One row per CMS-direct discovery run for coverage tracking over time."""
    table_id = _table_id(project, dataset, "mrf_discovery_runs")

    sql = f"""
    CREATE TABLE IF NOT EXISTS `{table_id}` (
      run_id                       STRING NOT NULL,
      run_started_at               TIMESTAMP NOT NULL,
      run_finished_at              TIMESTAMP,
      run_duration_seconds         INT64,
      total_hospitals_in_checkpoint INT64,
      hospitals_with_npi           INT64,
      hospitals_with_website       INT64,
      hospitals_crawled            INT64,
      hospitals_with_candidate_url INT64,
      hospitals_with_validated_url INT64,
      coverage_rate                FLOAT64,
      pricing_effective_year       INT64,
      notes                        STRING
    )
    """
    if dry_run:
        logger.info("[dry-run] CREATE TABLE %s", table_id)
        return
    logger.info("Creating %s", table_id)
    client.query(sql).result()


def cleanup_pra_legacy(
    client: bigquery.Client,
    project: str,
    dataset: str,
    dry_run: bool,
) -> None:
    """Drop tables and columns that were created during the abandoned PRA design.

    The PRA-sourced plan was attempted on 2026-04-27 and abandoned on 2026-04-28
    after Cloudflare silent-block prevented scraping. Some BQ artifacts
    survived the pivot:
      - Tables: `pra_facility_index`, `pra_discovery_runs` (never written to)
      - Columns: hospital_directory.pra_facility_uuid, hospital_directory.last_pra_check

    All four are unused by Plan A. This function drops them. Safe to re-run.

    See: docs/decisions/2026-04-28-cms-direct-mrf-discovery.md
    """
    pra_facility_index = _table_id(project, dataset, "pra_facility_index")
    pra_discovery_runs = _table_id(project, dataset, "pra_discovery_runs")
    directory = _table_id(project, dataset, "hospital_directory")

    statements = [
        ("DROP pra_facility_index", f"DROP TABLE IF EXISTS `{pra_facility_index}`"),
        ("DROP pra_discovery_runs", f"DROP TABLE IF EXISTS `{pra_discovery_runs}`"),
        (
            "DROP hospital_directory.pra_facility_uuid",
            f"ALTER TABLE `{directory}` DROP COLUMN IF EXISTS pra_facility_uuid",
        ),
        (
            "DROP hospital_directory.last_pra_check",
            f"ALTER TABLE `{directory}` DROP COLUMN IF EXISTS last_pra_check",
        ),
    ]

    for label, sql in statements:
        if dry_run:
            logger.info("[dry-run] %s", label)
        else:
            logger.info("%s", label)
            client.query(sql).result()


def rollback_rename(
    client: bigquery.Client,
    project: str,
    dataset: str,
    dry_run: bool,
) -> None:
    """Move hospital_charges_legacy_stale back to hospital_charges.

    Used only if we need to abort the migration before parser cutover and
    restore the original rules-engine read path. Refuses if a new
    hospital_charges already exists.
    """
    legacy = _table_id(project, dataset, "hospital_charges_legacy_stale")
    target = _table_id(project, dataset, "hospital_charges")

    if not _table_exists(client, legacy):
        logger.info("Nothing to roll back: %s does not exist", legacy)
        return

    if _table_exists(client, target):
        logger.error(
            "Refusing rollback: %s exists. Drop it manually first if you are "
            "certain the new effective-dated table has no production data.",
            target,
        )
        sys.exit(2)

    sql = f"ALTER TABLE `{legacy}` RENAME TO hospital_charges"
    if dry_run:
        logger.info("[dry-run] %s", sql)
        return
    logger.info("Renaming %s -> hospital_charges (rollback)", legacy)
    client.query(sql).result()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--project", default="clarobill-prd")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log all planned SQL without executing it",
    )
    parser.add_argument(
        "--rollback-rename",
        action="store_true",
        help="Restore hospital_charges_legacy_stale -> hospital_charges and exit",
    )
    parser.add_argument(
        "--cleanup-pra-legacy",
        action="store_true",
        help="Drop PRA-themed tables/columns left over from the abandoned PRA design",
    )
    args = parser.parse_args(argv)

    client = bigquery.Client(project=args.project)

    if args.rollback_rename:
        rollback_rename(client, args.project, args.dataset, args.dry_run)
        return 0

    if args.cleanup_pra_legacy:
        cleanup_pra_legacy(client, args.project, args.dataset, args.dry_run)
        return 0

    logger.info(
        "Migrating BigQuery schema for project=%s dataset=%s dry_run=%s",
        args.project, args.dataset, args.dry_run,
    )

    rename_hospital_charges_to_legacy(client, args.project, args.dataset, args.dry_run)
    create_new_hospital_charges(client, args.project, args.dataset, args.dry_run)
    recreate_hospital_directory_with_partition(client, args.project, args.dataset, args.dry_run)
    create_hospital_price_transparency(client, args.project, args.dataset, args.dry_run)
    create_mrf_archive_index(client, args.project, args.dataset, args.dry_run)
    create_mrf_discovery_runs(client, args.project, args.dataset, args.dry_run)

    logger.info("Migration complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
