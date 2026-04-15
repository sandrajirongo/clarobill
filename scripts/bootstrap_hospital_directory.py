"""Seed the BigQuery hospital_directory table from a CMS hospital list CSV.

This is a one-time (re-runnable) script that populates hospital_directory
with NPI, name, location, and MRF URL from a pre-downloaded CMS file.

--- Where to get the source data ---

Recommended: CMS "Promoting Interoperability" Hospital List
  Download: https://data.cms.gov/provider-data/dataset/xubh-q36u
  API endpoint: https://data.cms.gov/provider-data/api/1/datastore/query/xubh-q36u/0?format=csv
  Note: This file uses CCN (not NPI). Cross-reference with NPPES to get NPIs.

Alternatively: NPPES Data Dissemination (monthly full replacement)
  Download: https://download.cms.gov/nppes/NPI_Files.html
  Filter to: Entity_Type_Code = 2, Provider_Business_Practice_Location_Address_State != blank
  Taxonomy hint: codes starting with 28 (acute care), 26 (residential), 27 (nursing)

Simplest option: any CSV with columns npi, name, state, city, mrf_url.
  The --*-col flags let you remap column headers to the expected names.

--- Usage ---

  # With default column names (npi, name, state, city, mrf_url):
  python scripts/bootstrap_hospital_directory.py \\
    --file data/cms/hospitals/hospitals_2024.csv \\
    --project clarobill-prd

  # Remapping column names from a different CSV format:
  python scripts/bootstrap_hospital_directory.py \\
    --file hospitals.csv \\
    --npi-col "NPI" --name-col "Facility Name" \\
    --state-col "State" --city-col "City/Town" \\
    --mrf-url-col "MRF URL" \\
    --project clarobill-prd

  # Dry run (parse and count rows without writing to BigQuery):
  python scripts/bootstrap_hospital_directory.py \\
    --file hospitals.csv --dry-run

--- Authentication ---

Uses Application Default Credentials. Before running locally:
  gcloud auth application-default login
The authenticated account needs BigQuery Data Editor on hospital_prices.
"""

import argparse
import csv
import io
import json
import logging
import sys
import uuid
from pathlib import Path

from google.cloud import bigquery

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 500

HOSPITAL_DIRECTORY_SCHEMA = [
    bigquery.SchemaField("npi", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("name", "STRING"),
    bigquery.SchemaField("state", "STRING"),
    bigquery.SchemaField("city", "STRING"),
    bigquery.SchemaField("mrf_url", "STRING"),
    bigquery.SchemaField("last_scraped", "TIMESTAMP"),
    bigquery.SchemaField("last_modified", "STRING"),
    bigquery.SchemaField("schema_version", "STRING"),
]


def parse_csv(
    path: Path,
    npi_col: str,
    name_col: str,
    state_col: str,
    city_col: str,
    mrf_url_col: str,
) -> list[dict]:
    """Parse a hospital CSV into dicts ready for BigQuery insertion.

    Rows with a missing or non-10-digit NPI are skipped with a warning.

    Args:
        path: Path to the input CSV file.
        npi_col: Column header for the NPI field.
        name_col: Column header for the hospital name.
        state_col: Column header for the 2-letter state code.
        city_col: Column header for the city.
        mrf_url_col: Column header for the MRF URL (may be empty).

    Returns:
        List of dicts with normalised keys matching hospital_directory schema.
    """
    rows: list[dict] = []
    skipped = 0

    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        for line_num, row in enumerate(reader, start=2):
            npi = row.get(npi_col, "").strip()
            if not npi or not npi.isdigit() or len(npi) != 10:
                logger.warning("Line %d: skipping invalid NPI %r", line_num, npi)
                skipped += 1
                continue

            mrf_url = row.get(mrf_url_col, "").strip() or None

            rows.append({
                "npi": npi,
                "name": row.get(name_col, "").strip() or None,
                "state": row.get(state_col, "").strip().upper() or None,
                "city": row.get(city_col, "").strip() or None,
                "mrf_url": mrf_url,
                "last_scraped": None,
                "last_modified": None,
                "schema_version": None,
            })

    logger.info("Parsed %d hospital rows (%d skipped)", len(rows), skipped)
    return rows


def upsert_hospitals(
    client: bigquery.Client,
    project: str,
    dataset: str,
    hospitals: list[dict],
) -> None:
    """Merge hospitals into hospital_directory, preserving existing MRF URLs.

    Uses a load-to-staging + MERGE pattern:
    1. Loads all rows to a temp staging table.
    2. MERGEs into hospital_directory: INSERT new NPIs, UPDATE existing names/locations.
    3. Existing mrf_url and scrape metadata are preserved — bootstrap does not
       overwrite URLs that the scraper has already validated.

    Args:
        client: Authenticated BigQuery client.
        project: GCP project ID (e.g. "clarobill-prd").
        dataset: BigQuery dataset name (e.g. "hospital_prices").
        hospitals: List of hospital dicts from parse_csv().
    """
    staging_table_id = f"{project}.{dataset}.hospital_directory_bootstrap_staging"

    logger.info("Loading %d rows to staging table...", len(hospitals))
    ndjson = "\n".join(json.dumps(h) for h in hospitals)
    load_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        schema=HOSPITAL_DIRECTORY_SCHEMA,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        create_disposition=bigquery.CreateDisposition.CREATE_IF_NEEDED,
    )
    job = client.load_table_from_file(
        io.StringIO(ndjson),
        staging_table_id,
        job_config=load_config,
    )
    job.result()
    logger.info("Staging table loaded.")

    merge_sql = f"""
        MERGE `{project}.{dataset}.hospital_directory` T
        USING `{staging_table_id}` S
        ON T.npi = S.npi
        WHEN NOT MATCHED THEN
            INSERT (npi, name, state, city, mrf_url, last_scraped, last_modified, schema_version)
            VALUES (S.npi, S.name, S.state, S.city, S.mrf_url, NULL, NULL, NULL)
        WHEN MATCHED THEN
            UPDATE SET
                name = COALESCE(S.name, T.name),
                state = COALESCE(S.state, T.state),
                city = COALESCE(S.city, T.city),
                -- Preserve the scraper-validated MRF URL; only overwrite if we have a new one.
                mrf_url = COALESCE(T.mrf_url, S.mrf_url)
    """
    logger.info("Merging into hospital_directory...")
    client.query(merge_sql).result()
    logger.info("Merge complete.")

    logger.info("Dropping staging table...")
    client.delete_table(staging_table_id, not_found_ok=True)
    logger.info("Done.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed BigQuery hospital_directory from a CMS hospital list CSV."
    )
    parser.add_argument("--file", type=Path, required=True, help="Path to the hospital CSV file")
    parser.add_argument("--project", default="clarobill-prd", help="GCP project ID")
    parser.add_argument("--dataset", default="hospital_prices", help="BigQuery dataset")
    parser.add_argument("--npi-col", default="npi", help="CSV column for NPI")
    parser.add_argument("--name-col", default="name", help="CSV column for hospital name")
    parser.add_argument("--state-col", default="state", help="CSV column for state")
    parser.add_argument("--city-col", default="city", help="CSV column for city")
    parser.add_argument("--mrf-url-col", default="mrf_url", help="CSV column for MRF URL")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and count rows without writing to BigQuery",
    )
    args = parser.parse_args()

    if not args.file.exists():
        print(f"Error: file not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    hospitals = parse_csv(
        args.file,
        npi_col=args.npi_col,
        name_col=args.name_col,
        state_col=args.state_col,
        city_col=args.city_col,
        mrf_url_col=args.mrf_url_col,
    )

    if not hospitals:
        print("Error: no valid hospital rows found in CSV.", file=sys.stderr)
        sys.exit(1)

    mrf_count = sum(1 for h in hospitals if h.get("mrf_url"))
    print(f"  Parsed: {len(hospitals)} hospitals, {mrf_count} with MRF URL")

    if args.dry_run:
        print("Dry run — no changes written.")
        return

    client = bigquery.Client(project=args.project)
    upsert_hospitals(client, args.project, args.dataset, hospitals)
    print(f"\nBootstrap complete — {len(hospitals)} hospitals loaded into hospital_directory.")


if __name__ == "__main__":
    main()
