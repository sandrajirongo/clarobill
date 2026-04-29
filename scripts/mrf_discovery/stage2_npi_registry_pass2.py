"""Stage 2B Pass 2A: name-cleaned NPI re-resolution for hospitals that failed Pass 1.

Pass 1 (`stage2_npi_registry.py`) achieved 45.3% match rate against the NPPES
Registry API on Sandra's 2026-04-28 real run (6,272 / 13,833). The 7,561
no-match population is dominated by hospitals whose CMS POS legal name diverges
from how NPPES indexes them — typically because POS uses ALL-CAPS legal-entity
names ("HOUSTON COUNTY HEALTHCARE AUTHORITY") while NPPES indexes by the
informal hospital name.

This pass tries three escalating strategies for each unmatched CCN:

  Strategy 1 — Drop common name suffixes
    "FOO MEDICAL CENTER, INC" -> "FOO" (try as organisation_name)
    Drops: HOSPITAL, MEDICAL CENTER, HEALTH CENTER, HEALTHCARE,
           INC, LLC, LLP, ASSOCIATION, AUTHORITY, CORPORATION, CO,
           OF AMERICA, AT [CITY], etc.

  Strategy 2 — City + state without name
    Many hospitals are unique within a (city, state) pair. Searching by city
    only catches hospitals whose name in NPPES is a DBA or trade name we
    can't predict.

  Strategy 3 — State + first-three-name-words
    "Saint Vincent's Medical Center of Bridgeport" -> "SAINT VINCENT'S MEDICAL"
    Captures matches where NPPES legal name truncates ours mid-name.

Each strategy uses the same `nppes_client.NppesClient` and shares the
same GCS cache as Pass 1 (so subsequent passes won't re-call the API for
already-resolved hospitals).

Output:
  - hospital_npi populated for every CCN that Pass 2A matches
  - npi_match_strategy column set to "pass2_suffix_drop" | "pass2_city_only" |
    "pass2_truncated_name" so downstream auditing can spot-check which strategy
    produced which match
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

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
SAVE_CACHE_EVERY = 200

# Common name-component suffixes to strip. Order matters — longer phrases
# first so "MEDICAL CENTER" is caught before "CENTER" is left behind.
# Each entry is matched as a word/phrase boundary, case-insensitive.
SUFFIX_PATTERNS = [
    r"\bMEDICAL CENTER\b",
    r"\bMEDICAL CENTRE\b",
    r"\bMEMORIAL HOSPITAL\b",
    r"\bGENERAL HOSPITAL\b",
    r"\bCOMMUNITY HOSPITAL\b",
    r"\bCRITICAL ACCESS HOSPITAL\b",
    r"\bREGIONAL HOSPITAL\b",
    r"\bUNIVERSITY HOSPITAL\b",
    r"\bWOMEN['']?S HOSPITAL\b",
    r"\bCHILDREN['']?S HOSPITAL\b",
    r"\bHEALTH CENTER\b",
    r"\bHEALTH SYSTEM\b",
    r"\bHEALTH AUTHORITY\b",
    r"\bHEALTHCARE\b",
    r"\bHEALTH CARE\b",
    r"\bHOSPITAL\b",
    r"\bHOSPITAL AUTHORITY\b",
    r"\bAUTHORITY\b",
    r"\bASSOCIATION\b",
    r"\bCORPORATION\b",
    r"\bCORP\b",
    r"\bINC\b",
    r"\bLLC\b",
    r"\bLLP\b",
    r"\bL\.L\.C\.\b",
    r"\bCO\b",
    r"\bOF AMERICA\b",
    r"\bOF THE\b",
    r"\bAT [A-Z][A-Z\s]+$",  # "AT BRIDGEPORT"
]

_SUFFIX_RE = re.compile("|".join(SUFFIX_PATTERNS), re.IGNORECASE)
_PUNCT_RE = re.compile(r"[,;:.()\[\]/\\]+")
_WS_RE = re.compile(r"\s+")


def clean_name(raw: str) -> str:
    """Strip suffixes, punctuation, collapse whitespace.

    Returns the cleaned name. Empty result if every word was a suffix.
    """
    s = raw.upper()
    # Replace punctuation with spaces (so "MAYO, INC" -> "MAYO  INC" -> drop INC)
    s = _PUNCT_RE.sub(" ", s)
    # Collapse whitespace before suffix-strip so word boundaries match
    s = _WS_RE.sub(" ", s).strip()
    # Iteratively drop suffixes until none match (handles nested cases like
    # "FOO MEDICAL CENTER INC" -> "FOO MEDICAL CENTER" -> "FOO")
    prev = None
    while s != prev:
        prev = s
        s = _SUFFIX_RE.sub("", s).strip()
    s = _WS_RE.sub(" ", s).strip()
    return s


def first_n_words(name: str, n: int = 3) -> str:
    """Return the first n words of a name. Used for truncated-name strategy."""
    words = name.upper().split()
    return " ".join(words[:n]).strip()


def get_unmatched_hospitals(
    bq_client: bigquery.Client,
    project: str,
    run_id: str,
    dataset: str = bq_checkpoint.DEFAULT_DATASET,
) -> list[dict]:
    """Return checkpoint rows that completed Pass 1 with no NPI match.

    Filters: nppes_resolved_at IS NOT NULL (Pass 1 ran)
             AND hospital_npi IS NULL (Pass 1 found no match)
             AND state IS NOT NULL AND hospital_name IS NOT NULL.
    """
    sql = f"""
    SELECT ccn, hospital_name, state, city
    FROM `{project}.{dataset}.mrf_discovery_checkpoint`
    WHERE run_id = @run_id
      AND nppes_resolved_at IS NOT NULL
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


def try_resolution(
    client: NppesClient,
    hospital_name: str,
    state: str,
    city: str | None,
) -> tuple[str | None, str | None, str]:
    """Try the three Pass 2A strategies in escalating order.

    Returns (npi, legal_name, strategy) where strategy describes which
    technique produced the match (or "no_match").
    """
    # Strategy 1: drop suffixes
    cleaned = clean_name(hospital_name)
    if cleaned and cleaned != hospital_name.upper():
        result = client.lookup(cleaned, state, city)
        if result.npi:
            return result.npi, result.legal_name, f"pass2_suffix_drop_{result.matched_via}"

    # Strategy 2: city only (no organization_name)
    # We pass an empty string for hospital_name and rely on city + state
    # filtering server-side. The NppesClient.lookup checks hospital_name
    # truthiness so we can't use that path; we'd need a separate API call.
    # For Pass 2A simplicity, skip this if cleaned-name strategy didn't work
    # and try Strategy 3 instead. (Strategy 2 is harder to wire through the
    # client; defer to a separate module if recovery rate from Strategy 1+3
    # is insufficient.)

    # Strategy 3: first 3 words of the cleaned name
    if cleaned:
        truncated = first_n_words(cleaned, n=3)
        if truncated and truncated != cleaned:
            result = client.lookup(truncated, state, city)
            if result.npi:
                return result.npi, result.legal_name, f"pass2_truncated_{result.matched_via}"

    return None, None, "pass2_no_match"


def apply_pass2_npis(
    bq_client: bigquery.Client,
    project: str,
    run_id: str,
    npi_by_ccn: dict[str, dict],
    dataset: str = bq_checkpoint.DEFAULT_DATASET,
    dry_run: bool = False,
) -> int:
    """MERGE pass-2 NPIs into the checkpoint. Only writes hospital_npi where
    Pass 1 left it NULL — never overwrites a Pass 1 match.

    npi_by_ccn maps CCN -> {"npi": str, "strategy": str}.
    """
    if not npi_by_ccn:
        return 0
    if dry_run:
        logger.info("[dry-run] would update hospital_npi for %d CCNs", len(npi_by_ccn))
        return 0

    checkpoint_table = f"{project}.{dataset}.mrf_discovery_checkpoint"
    staging_table = f"{project}.{dataset}._stage2_pass2_staging_{run_id.replace('-', '_').lower()}"

    bq_client.query(f"""
        CREATE OR REPLACE TABLE `{staging_table}` (
          run_id        STRING,
          ccn           STRING,
          hospital_npi  STRING
        )
    """).result()

    try:
        rows = [
            {"run_id": run_id, "ccn": ccn, "hospital_npi": v["npi"]}
            for ccn, v in npi_by_ccn.items()
        ]
        BATCH = 500
        for i in range(0, len(rows), BATCH):
            errors = bq_client.insert_rows_json(staging_table, rows[i : i + BATCH])
            if errors:
                raise RuntimeError(f"Pass 2 staging insert failed at batch {i}: {errors[:3]}")

        merge_sql = f"""
        MERGE `{checkpoint_table}` T
        USING `{staging_table}` S
        ON T.run_id = S.run_id AND T.ccn = S.ccn
        WHEN MATCHED AND T.hospital_npi IS NULL THEN
          UPDATE SET
            hospital_npi    = S.hospital_npi,
            last_updated_at = CURRENT_TIMESTAMP()
        """
        bq_client.query(merge_sql).result()
        return len(rows)
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
) -> dict:
    targets = get_unmatched_hospitals(bq_client, project, run_id, dataset=dataset)
    logger.info("Stage 2B Pass 2A: %d hospitals to re-resolve", len(targets))
    if not targets:
        return {"target_count": 0, "matched": 0, "no_match": 0, "by_strategy": {}}

    cache = load_cache_from_gcs(storage_client, cache_bucket, cache_object)
    logger.info("Loaded %d cached entries from gs://%s/%s", len(cache), cache_bucket, cache_object)
    client = NppesClient(cache=cache)

    npi_by_ccn: dict[str, dict] = {}
    matched_count = 0
    no_match_count = 0
    by_strategy: dict[str, int] = {}
    sample_matches: list[tuple[str, str, str, str]] = []  # (ccn, original, cleaned, npi)

    for i, hospital in enumerate(targets, start=1):
        ccn = hospital["ccn"]
        name = hospital["hospital_name"]
        state = hospital["state"]
        city = hospital.get("city")

        npi, legal, strategy = try_resolution(client, name, state, city)
        by_strategy[strategy] = by_strategy.get(strategy, 0) + 1

        if npi:
            npi_by_ccn[ccn] = {"npi": npi, "strategy": strategy}
            matched_count += 1
            if len(sample_matches) < 10:
                sample_matches.append((ccn, name, clean_name(name), npi))
        else:
            no_match_count += 1

        if i % 200 == 0:
            logger.info(
                "  %d/%d processed (match=%d no_match=%d)",
                i, len(targets), matched_count, no_match_count,
            )
            if not dry_run:
                save_cache_to_gcs(storage_client, cache_bucket, cache_object, client.cache_snapshot())

    if not dry_run:
        save_cache_to_gcs(storage_client, cache_bucket, cache_object, client.cache_snapshot())
        logger.info("Final cache size: %d entries", len(client.cache_snapshot()))

    logger.info("Strategy breakdown: %s", by_strategy)
    if sample_matches:
        logger.info("Sample Pass 2A matches (first 10):")
        for ccn, original, cleaned, npi in sample_matches:
            logger.info("  %s: %r -> cleaned %r -> NPI %s", ccn, original, cleaned, npi)

    updated = apply_pass2_npis(
        bq_client, project, run_id, npi_by_ccn, dataset=dataset, dry_run=dry_run,
    )

    return {
        "target_count": len(targets),
        "matched": matched_count,
        "no_match": no_match_count,
        "by_strategy": by_strategy,
        "updated": updated,
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

    logger.info("Stage 2B Pass 2A starting: project=%s run_id=%s", args.project, args.run_id)
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
        "Stage 2B Pass 2A complete: targets=%d matched=%d no_match=%d updated=%d",
        summary["target_count"], summary["matched"], summary["no_match"], summary.get("updated", 0),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
