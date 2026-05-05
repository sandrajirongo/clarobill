"""Stage 1 of CMS-direct MRF discovery: seed the checkpoint table from CMS PI list.

Fetches the CMS Promoting Interoperability hospital list (dataset xubh-q36u) via
the public datastore API and inserts one row per hospital into
`mrf_discovery_checkpoint`.

  Source: https://data.cms.gov/provider-data/dataset/xubh-q36u
  API:    https://data.cms.gov/provider-data/api/1/datastore/query/xubh-q36u/0
  Fields: facility_id (CCN), facility_name, address, citytown, state, zip_code,
          telephone_number, hospital_type, hospital_ownership,
          hospital_overall_rating
  Refresh: quarterly
  Cost:   free

This stage does no Playwright, no rate-limited work, and no paid API calls. The
endpoint serves JSON directly. For ~5,400 hospitals at 500 per page = ~11
paginated requests. Total runtime ~30 seconds.

Output: one row per CCN in `mrf_discovery_checkpoint` with `cms_loaded_at` set.
Resumable: if the checkpoint already has rows for the given run_id with
cms_loaded_at, the existing run picks up at Stage 2 next time. To re-fetch with
a fresh run_id, generate a new run_id (the orchestrator does this; this script
takes whatever run_id you pass).

Usage:
    python scripts/mrf_discovery/stage1_cms_hospital_list.py \\
        --project clarobill-prd \\
        --run-id 20260428T130000Z_abc12345
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Iterator

import requests

# Allow running as a script
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from mrf_discovery import bq_checkpoint  # type: ignore[no-redef]
else:
    from . import bq_checkpoint

from google.cloud import bigquery

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CMS_PI_API = "https://data.cms.gov/provider-data/api/1/datastore/query/xubh-q36u/0"
USER_AGENT = (
    "ClaroBill-MRFDiscovery/1.0 "
    "(price transparency research; contact@clarobill.com)"
)
PAGE_SIZE = 500
REQUEST_TIMEOUT = 60
# H6 fix (2026-05-04): hard cap on the pagination loop so a misreported
# `count` field on the CMS API response (or a bug that causes the API to
# echo the same `next` cursor) can't run away into millions of requests.
# CMS Hospital General Information has ~6,000 rows; doubling that twice
# leaves comfortable headroom for unexpected growth without tolerating
# a runaway loop. Beyond MAX_PAGES * PAGE_SIZE rows, raise.
MAX_PAGES = 200


def fetch_all_hospitals(
    api_url: str = CMS_PI_API,
    page_size: int = PAGE_SIZE,
) -> list[dict]:
    """Page through the CMS PI dataset and return every row.

    The API supports format=json&limit=N&offset=N. The `count` field in the
    first response tells us the total; we iterate until we've fetched that
    many rows. A small inter-request sleep keeps us polite even though CMS
    publishes no documented rate limit.
    """
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}

    # First request: get total count + first page
    first_url = f"{api_url}?format=json&limit={page_size}&offset=0"
    logger.info("Fetching %s", first_url)
    resp = requests.get(first_url, headers=headers, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()
    total = int(payload.get("count", 0))
    rows: list[dict] = list(payload.get("results", []))
    logger.info("Total hospitals reported by CMS: %d (got %d on page 1)", total, len(rows))

    offset = page_size
    pages_fetched = 1  # the first page above counts
    while offset < total:
        if pages_fetched >= MAX_PAGES:
            # H6 fix: protects against a runaway pagination caused by a
            # misreported `count`. CMS has ~6,000 hospitals (12 pages at
            # PAGE_SIZE=500). Hitting 200 pages means something is wrong;
            # raise rather than blast millions of requests.
            raise RuntimeError(
                f"Stage 1 pagination exceeded MAX_PAGES={MAX_PAGES} "
                f"(reported total={total}, fetched_so_far={len(rows)}). "
                "Investigate CMS API response — likely a bad `count` field."
            )
        page_url = f"{api_url}?format=json&limit={page_size}&offset={offset}"
        logger.info("  page offset=%d", offset)
        page_resp = requests.get(page_url, headers=headers, timeout=REQUEST_TIMEOUT)
        page_resp.raise_for_status()
        page_rows = page_resp.json().get("results", [])
        if not page_rows:
            logger.warning("Empty page at offset=%d, stopping early", offset)
            break
        rows.extend(page_rows)
        offset += page_size
        pages_fetched += 1
        time.sleep(0.25)  # polite even though no documented rate limit

    logger.info("Fetched %d hospitals total", len(rows))
    return rows


def normalise_row(raw: dict) -> dict | None:
    """Convert a raw CMS PI row into a checkpoint-shaped dict.

    Returns None if the row is:
      - missing facility_id or facility_name
      - a federal facility (DoD/VA) — those have their own pricing rules and
        do not publish CMS Hospital Price Transparency MRFs

    Sandra's 2026-04-28 real run pulled in 32 DoD + 132 VA facilities. They
    are correctly identified by CMS but are out of scope for ClaroBill's
    audit engine, which targets civilian-billed bills against civilian-
    published chargemasters.
    """
    ccn = (raw.get("facility_id") or "").strip()
    name = (raw.get("facility_name") or "").strip()
    if not ccn or not name:
        return None

    hospital_type_raw = (raw.get("hospital_type") or "").strip()
    if hospital_type_raw.lower().startswith("acute care - "):
        # "Acute Care - Department of Defense" / "Acute Care - Veterans Administration"
        return None

    rating = _parse_int(raw.get("hospital_overall_rating"))

    return {
        "ccn": ccn,
        "hospital_name": name,
        "address": _clean_str(raw.get("address")),
        "city": _clean_str(raw.get("citytown")),
        "state": _clean_str(raw.get("state")),
        "zip_code": _clean_str(raw.get("zip_code")),
        "phone": _clean_str(raw.get("telephone_number")),
        "hospital_type": _clean_str(raw.get("hospital_type")),
        "hospital_ownership": _clean_str(raw.get("hospital_ownership")),
        "overall_rating": rating,
    }


def _clean_str(val) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s if s and s.lower() != "not available" else None


def _parse_int(val) -> int | None:
    if val is None:
        return None
    try:
        return int(str(val).strip())
    except (ValueError, TypeError):
        return None


def run(
    bq_client: bigquery.Client,
    project: str,
    run_id: str,
    dataset: str = bq_checkpoint.DEFAULT_DATASET,
    api_url: str = CMS_PI_API,
    dry_run: bool = False,
) -> dict[str, int]:
    """Fetch the CMS PI list, normalise rows, seed the checkpoint table.

    Returns {"cms_count": N, "seeded": M, "skipped_missing_required": K}.
    In dry-run mode, seeded is 0 and the checkpoint table is not touched.
    """
    raw_rows = fetch_all_hospitals(api_url=api_url)

    seed_rows: list[dict] = []
    skipped = 0
    for raw in raw_rows:
        normalised = normalise_row(raw)
        if normalised is None:
            skipped += 1
            continue
        seed_rows.append(normalised)

    if skipped:
        logger.warning("Skipped %d rows missing facility_id or facility_name", skipped)

    if dry_run:
        logger.info("[dry-run] would seed %d hospitals into checkpoint for run_id=%s", len(seed_rows), run_id)
        return {"cms_count": len(raw_rows), "seeded": 0, "skipped_missing_required": skipped}

    bq_checkpoint.ensure_checkpoint_table(bq_client, project, dataset)
    seeded = bq_checkpoint.seed_hospitals(bq_client, project, run_id, seed_rows, dataset=dataset)
    return {"cms_count": len(raw_rows), "seeded": seeded, "skipped_missing_required": skipped}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--project", default="clarobill-prd")
    parser.add_argument("--dataset", default=bq_checkpoint.DEFAULT_DATASET)
    parser.add_argument(
        "--run-id",
        help="Run ID to attach to checkpoint rows. If omitted, a fresh one is generated.",
    )
    parser.add_argument("--api-url", default=CMS_PI_API, help="Override the CMS PI API URL")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    run_id = args.run_id or bq_checkpoint.new_run_id()
    logger.info("Stage 1 starting: project=%s run_id=%s", args.project, run_id)

    client = bigquery.Client(project=args.project)
    summary = run(
        bq_client=client,
        project=args.project,
        run_id=run_id,
        dataset=args.dataset,
        api_url=args.api_url,
        dry_run=args.dry_run,
    )

    logger.info(
        "Stage 1 complete: run_id=%s cms_count=%d seeded=%d skipped=%d",
        run_id, summary["cms_count"], summary["seeded"], summary["skipped_missing_required"],
    )
    print(run_id)  # stdout for the orchestrator to capture
    return 0


if __name__ == "__main__":
    sys.exit(main())
