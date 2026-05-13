"""Stage 3 Tier 3 — Google Places API website discovery (PAID).

This is the only paid stage in the entire ClaroBill data pipeline. Every
design decision is documented at:
    docs/decisions/2026-04-28-google-places-cost-design.md

Run modes
---------
    --cost-preview          Project the run cost without making any API call
    --max-places-cost N     Hard ceiling in USD (default 450)
    --limit N               Process at most N hospitals (for testing)
    --target-ccn CCN        Process only this single CCN (for the $0.03 live test)

The script:
  1. Loads the Places API key from GCP Secret Manager (NOT env var)
     unless GOOGLE_PLACES_API_KEY is set (local dev only)
  2. Loads the GCS-backed cache
  3. Queries the checkpoint for hospitals needing Tier 3
  4. Applies pre-call validators (Layer 5 in the cost design)
  5. If --cost-preview: prints projected cost and exits
  6. Otherwise: per hospital, calls PlacesClient.lookup, writes results
     to checkpoint, persists cache every 200 hospitals
  7. On BudgetExceeded: halts cleanly, marks remaining hospitals with
     error_stage='stage3_tier3_budget_exhausted'
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from google.cloud import bigquery, storage

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from mrf_discovery import bq_checkpoint  # type: ignore[no-redef]
    from mrf_discovery.places_client import (  # type: ignore[no-redef]
        BudgetExceeded,
        COST_PER_PLACE_DETAILS,
        COST_PER_TEXT_SEARCH,
        CostMeter,
        MAX_VERIFY_CANDIDATES,
        PlacesClient,
        is_lookupable,
    )
else:
    from . import bq_checkpoint
    from .places_client import (
        BudgetExceeded,
        COST_PER_PLACE_DETAILS,
        COST_PER_TEXT_SEARCH,
        CostMeter,
        MAX_VERIFY_CANDIDATES,
        PlacesClient,
        is_lookupable,
    )

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CACHE_BUCKET = "mrf-staging"
CACHE_OBJECT = "places-api-cache.json"
ARCHIVE_BUCKET = "clarobill-mrf-archive-uscentral"
ARCHIVE_OBJECT_TEMPLATE = "places-api-cache-snapshots/{year}.json"

DEFAULT_BUDGET = 450.0
SECRET_NAME = "google-places-api-key"

# Cost preview heuristic: estimated rates of each outcome type AMONG
# API-CALLED HOSPITALS (cache hits incur no cost and aren't included).
#
# Calibrated 2026-04-29 from the 500-hospital smoke test:
#   300 API calls broken into:
#     181 single_result        (60.3%)
#     116 ambiguous_*          (38.7%) — averaged 3 details each
#       3 no_result            (1.0%)
#
# The original 0.85 / 0.13 values were proxied from NPPES match outcomes
# (where ambiguity is rarer); the real Places API distribution is meaningfully
# more ambiguous because Google's hospital index returns 2-3 candidates more
# often when names overlap (e.g. "Memorial Hospital" in any major city).
#
# Sum MUST stay <= 1.0 — these are mutually-exclusive outcome categories.
# We err slightly on the side of OVER-projecting (sum slightly < 1) so the
# preview never under-warns about budget.
EXPECTED_SINGLE_RESULT_RATE = 0.60
EXPECTED_AMBIGUOUS_RATE = 0.39


import re as _re_module

# Google API keys have a fixed shape: "AIzaSy" + 33 alphanumeric/underscore/hyphen chars.
# Sourced from Google's API key documentation. We extract this pattern from
# whatever the secret returned to defend against:
#   - Trailing whitespace / newlines from gcloud cli wrapping
#   - Shell-substitution-induced contamination (gcloud bootstrap output,
#     pip install logs, etc. — observed live on 2026-04-28)
_GOOGLE_API_KEY_RE = _re_module.compile(r"AIza[0-9A-Za-z_\-]{35}")


def _extract_clean_api_key(raw: str) -> str:
    """Extract a Google API key from possibly-contaminated input.

    Sandra's 2026-04-28 incident: the secret stored in Secret Manager contained
    gcloud's bootstrap output (pip install logs etc.) followed by the actual
    API key on the last line. The contaminated string was passed verbatim as
    the `X-Goog-Api-Key` header, which `requests` rejected ("Invalid leading
    whitespace, reserved character(s), or return character(s) in header
    value").

    This function:
      1. Searches for the canonical Google API key pattern (AIzaSy + 33 chars)
      2. Returns the FIRST match, or raises ValueError if none found
      3. Never logs the key value (even on error — we redact)

    Even when the secret is clean, this is a defensive no-op: a clean key
    matches the regex and is returned as-is.
    """
    if not raw:
        raise ValueError("Empty API key value loaded from secret")
    match = _GOOGLE_API_KEY_RE.search(raw)
    if not match:
        # Critically: do NOT include `raw` in the error message — it may
        # contain sensitive data interleaved with the key. We log only that
        # extraction failed and the LENGTH of what we received (signal of
        # contamination without leaking the contents).
        raise ValueError(
            f"No valid Google API key found in loaded secret "
            f"(payload was {len(raw)} bytes; expected exactly 39 for a clean key)"
        )
    return match.group(0)


def load_api_key(project: str) -> str:
    """Load Places API key from Secret Manager.

    Falls back to env var GOOGLE_PLACES_API_KEY for local dev. Production
    Cloud Run jobs should always read from Secret Manager.

    Defensive: applies `_extract_clean_api_key` to the loaded value so a
    contaminated secret (e.g. from a shell-substitution mishap during
    provisioning) doesn't crash the run. The key is NEVER logged in any
    branch of this function.
    """
    env_key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if env_key:
        logger.warning(
            "Using GOOGLE_PLACES_API_KEY from env (local-dev fallback). "
            "Production runs should read from Secret Manager."
        )
        return _extract_clean_api_key(env_key)

    try:
        from google.cloud import secretmanager
    except ImportError:
        logger.error(
            "google-cloud-secret-manager not installed. Either install it "
            "(pip install google-cloud-secret-manager) or set GOOGLE_PLACES_API_KEY "
            "as an env var for local dev."
        )
        raise

    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project}/secrets/{SECRET_NAME}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    raw = response.payload.data.decode("UTF-8")
    return _extract_clean_api_key(raw)


def load_cache_from_gcs(
    storage_client: storage.Client, bucket: str = CACHE_BUCKET, obj: str = CACHE_OBJECT,
) -> dict[str, dict]:
    blob = storage_client.bucket(bucket).blob(obj)
    if not blob.exists():
        return {}
    text = blob.download_as_text()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Places cache at gs://%s/%s is malformed; starting fresh", bucket, obj)
        return {}


def save_cache_to_gcs(
    storage_client: storage.Client, cache: dict[str, dict],
    bucket: str = CACHE_BUCKET, obj: str = CACHE_OBJECT,
) -> None:
    storage_client.bucket(bucket).blob(obj).upload_from_string(
        json.dumps(cache, sort_keys=True, separators=(",", ":")),
        content_type="application/json",
    )


def snapshot_cache_to_archive(
    storage_client: storage.Client, cache: dict[str, dict], year: int | None = None,
) -> str:
    """Write an immutable year-stamped snapshot of the cache to the archive bucket."""
    year = year or datetime.now(timezone.utc).year
    object_name = ARCHIVE_OBJECT_TEMPLATE.format(year=year)
    storage_client.bucket(ARCHIVE_BUCKET).blob(object_name).upload_from_string(
        json.dumps(cache, sort_keys=True, separators=(",", ":")),
        content_type="application/json",
    )
    return f"gs://{ARCHIVE_BUCKET}/{object_name}"


def get_pending_hospitals(
    bq_client: bigquery.Client,
    project: str,
    run_id: str,
    dataset: str = bq_checkpoint.DEFAULT_DATASET,
    limit: int | None = None,
    target_ccn: str | None = None,
) -> list[dict]:
    """Hospitals needing Tier 3 — Stage 2 done, no website found in Tiers 1+2."""
    where_clauses = [
        "run_id = @run_id",
        "nppes_resolved_at IS NOT NULL",
        "hospital_website IS NULL",
        "website_found_at IS NULL",
    ]
    params = [bigquery.ScalarQueryParameter("run_id", "STRING", run_id)]
    if target_ccn:
        where_clauses.append("ccn = @ccn")
        params.append(bigquery.ScalarQueryParameter("ccn", "STRING", target_ccn))

    limit_clause = f"LIMIT {int(limit)}" if limit else ""
    sql = f"""
    SELECT ccn, hospital_name, state, city
    FROM `{project}.{dataset}.mrf_discovery_checkpoint`
    WHERE {" AND ".join(where_clauses)}
    ORDER BY ccn
    {limit_clause}
    """
    job = bq_client.query(
        sql, job_config=bigquery.QueryJobConfig(query_parameters=params),
    )
    return [dict(row) for row in job.result()]


def cost_preview(targets: list[dict]) -> dict:
    """Project the cost of a Tier 3 run without making any API call.

    Layer 6 of the cost design. Filters out lookupable hospitals, projects
    text-search calls, then projects details calls assuming single-vs-ambiguous
    distribution.
    """
    lookupable = [t for t in targets if is_lookupable(
        t.get("hospital_name"), t.get("state"), t.get("city"))]
    rejected = len(targets) - len(lookupable)

    n = len(lookupable)
    text_search_cost = n * COST_PER_TEXT_SEARCH

    # Estimate Details calls:
    # - EXPECTED_SINGLE_RESULT_RATE × n have 1 details call each
    # - EXPECTED_AMBIGUOUS_RATE × n have up to MAX_VERIFY_CANDIDATES details each
    # - The rest (no_result) have 0 details calls
    single_count = int(n * EXPECTED_SINGLE_RESULT_RATE)
    ambig_count = int(n * EXPECTED_AMBIGUOUS_RATE)
    details_cost = (single_count * COST_PER_PLACE_DETAILS
                    + ambig_count * MAX_VERIFY_CANDIDATES * COST_PER_PLACE_DETAILS)

    total = text_search_cost + details_cost
    return {
        "targets_total": len(targets),
        "rejected_pre_call": rejected,
        "lookupable": n,
        "expected_text_search_calls": n,
        "expected_details_calls_single": single_count,
        "expected_details_calls_ambiguous": ambig_count * MAX_VERIFY_CANDIDATES,
        "projected_text_search_cost": text_search_cost,
        "projected_details_cost": details_cost,
        "projected_total_usd": total,
    }


def apply_results(
    bq_client: bigquery.Client,
    project: str,
    run_id: str,
    matched: dict[str, dict],
    definitive_negatives: list[str] | None = None,
    dataset: str = bq_checkpoint.DEFAULT_DATASET,
    dry_run: bool = False,
) -> int:
    """MERGE Places results into the checkpoint.

    Two effects in one MERGE:

      1. For CCNs with a resolved website (`matched`): write hospital_website
         + website_source='google_places' + website_found_at=NOW().

      2. For CCNs with definitive Tier 3 negatives (`no_result` or
         `ambiguous_no_verify`): set website_found_at=NOW() WITHOUT writing
         a website. This marks the row as "we tried, Google has no answer"
         so re-runs don't keep re-counting them as pending Tier 3 input.
         Sandra spotted this on 2026-04-29: the cost-preview projected $63
         for 1,294 hospitals that were ALL definitive negatives from the
         prior run, because places_client cached the negatives but the
         checkpoint row's website_found_at stayed NULL.

    Returns the number of rows updated (matched + definitive_negatives).
    """
    definitive_negatives = list(definitive_negatives or [])

    if not matched and not definitive_negatives:
        return 0
    if dry_run:
        logger.info(
            "[dry-run] would update %d matched + %d definitive-negative rows",
            len(matched), len(definitive_negatives),
        )
        return 0

    checkpoint_table = f"{project}.{dataset}.mrf_discovery_checkpoint"
    staging_table = f"{project}.{dataset}._stage3_tier3_staging_{run_id.replace('-', '_').lower()}"
    now_iso = datetime.now(timezone.utc).isoformat()

    bq_client.query(f"""
        CREATE OR REPLACE TABLE `{staging_table}` (
          run_id            STRING,
          ccn               STRING,
          hospital_website  STRING,
          website_found_at  TIMESTAMP,
          is_negative       BOOL
        )
    """).result()

    try:
        rows: list[dict] = []
        for ccn, v in matched.items():
            if v.get("website"):
                rows.append({
                    "run_id": run_id, "ccn": ccn,
                    "hospital_website": v["website"],
                    "website_found_at": now_iso,
                    "is_negative": False,
                })
        for ccn in definitive_negatives:
            rows.append({
                "run_id": run_id, "ccn": ccn,
                "hospital_website": None,
                "website_found_at": now_iso,
                "is_negative": True,
            })

        BATCH = 500
        for i in range(0, len(rows), BATCH):
            errors = bq_client.insert_rows_json(staging_table, rows[i : i + BATCH])
            if errors:
                raise RuntimeError(f"Tier 3 staging insert failed at batch {i}: {errors[:3]}")

        # Two MERGE branches: matched rows get website+source+timestamp;
        # definitive-negative rows get only the timestamp (preserves NULL website).
        merge_sql = f"""
        MERGE `{checkpoint_table}` T
        USING `{staging_table}` S
        ON T.run_id = S.run_id AND T.ccn = S.ccn
        WHEN MATCHED AND NOT S.is_negative AND T.hospital_website IS NULL THEN
          UPDATE SET
            hospital_website = S.hospital_website,
            website_source   = 'google_places',
            website_found_at = S.website_found_at,
            last_updated_at  = S.website_found_at
        WHEN MATCHED AND S.is_negative AND T.website_found_at IS NULL THEN
          UPDATE SET
            website_found_at = S.website_found_at,
            last_updated_at  = S.website_found_at
        """
        bq_client.query(merge_sql).result()
        return len(rows)
    finally:
        bq_client.query(f"DROP TABLE IF EXISTS `{staging_table}`").result()


def mark_budget_exhausted(
    bq_client: bigquery.Client,
    project: str,
    run_id: str,
    pending_ccns: list[str],
    dataset: str = bq_checkpoint.DEFAULT_DATASET,
) -> None:
    """Record that these CCNs were not processed because the budget halted us.

    They're not failures — they're "budget ran out, retry next year." A future
    run with a higher budget OR a year later (when the cache would re-cover
    most non-budget-exhausted hospitals) will pick them up.
    """
    if not pending_ccns:
        return
    checkpoint_table = f"{project}.{dataset}.mrf_discovery_checkpoint"
    sql = f"""
    UPDATE `{checkpoint_table}`
    SET error_stage = 'stage3_tier3_budget_exhausted',
        error_message = 'Budget halt — retry on next run',
        last_updated_at = CURRENT_TIMESTAMP()
    WHERE run_id = @run_id
      AND ccn IN UNNEST(@ccns)
    """
    bq_client.query(
        sql,
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("run_id", "STRING", run_id),
            bigquery.ArrayQueryParameter("ccns", "STRING", pending_ccns),
        ]),
    ).result()


def run(
    bq_client: bigquery.Client,
    storage_client: storage.Client,
    project: str,
    run_id: str,
    api_key: str,
    max_places_cost: float,
    dataset: str = bq_checkpoint.DEFAULT_DATASET,
    limit: int | None = None,
    target_ccn: str | None = None,
    dry_run: bool = False,
) -> dict:
    targets = get_pending_hospitals(
        bq_client, project, run_id, dataset=dataset,
        limit=limit, target_ccn=target_ccn,
    )
    logger.info("Stage 3 Tier 3: %d hospitals pending", len(targets))
    if not targets:
        # Return the same shape main() expects so the early-exit log line
        # doesn't crash with KeyError.
        return {
            "target_count": 0,
            "matched": 0,
            "no_match": 0,
            "skipped_pre_call": 0,
            "by_outcome": {},
            "running_usd": 0.0,
            "text_search_calls": 0,
            "details_calls": 0,
            "halted": False,
            "pending_ccns_after_halt": 0,
            "applied": 0,
        }

    cache = load_cache_from_gcs(storage_client)
    logger.info("Loaded %d cached entries from gs://%s/%s",
                len(cache), CACHE_BUCKET, CACHE_OBJECT)

    cost_meter = CostMeter(budget_usd=max_places_cost)
    client = PlacesClient(api_key=api_key, cost_meter=cost_meter, cache=cache)

    matched: dict[str, dict] = {}
    # CCNs where Places gave us a definitive negative (no_result or
    # ambiguous_no_verify) — they need website_found_at set so re-runs
    # don't keep re-querying them. Q5a fix from the Phase 4 design.
    definitive_negatives: list[str] = []
    skipped_pre_call = 0
    no_match_count = 0
    by_outcome: dict[str, int] = {}
    pending_ccns: list[str] = [t["ccn"] for t in targets]
    halt_reason: str | None = None

    try:
        for i, hospital in enumerate(targets, start=1):
            ccn = hospital["ccn"]
            name = hospital["hospital_name"]
            state = hospital["state"]
            city = hospital.get("city")

            if not is_lookupable(name, state, city):
                skipped_pre_call += 1
                pending_ccns.remove(ccn)
                continue

            try:
                result = client.lookup(name, state, city)
            except BudgetExceeded as exc:
                halt_reason = str(exc)
                logger.error("Budget halt at hospital %d/%d: %s", i, len(targets), exc)
                break
            except Exception as exc:
                # Pipeline contract: one bad hospital cannot kill the run.
                # Record the error and continue. Cost may have been booked
                # by CostMeter before the failure (defensive accounting),
                # which is correct — Google may have charged us regardless.
                logger.exception(
                    "Tier 3 lookup error for ccn=%s: %s: %s",
                    ccn, type(exc).__name__, exc,
                )
                by_outcome["error"] = by_outcome.get("error", 0) + 1
                no_match_count += 1
                pending_ccns.remove(ccn)
                continue

            by_outcome[result.matched_via] = by_outcome.get(result.matched_via, 0) + 1
            pending_ccns.remove(ccn)

            if result.website:
                matched[ccn] = {
                    "website": result.website,
                    "formatted_address": result.formatted_address,
                    "place_id": result.place_id,
                    "matched_via": result.matched_via,
                }
            else:
                no_match_count += 1
                # Mark as definitive negative if Places returned no website
                # for any reason. The cache will short-circuit future runs at
                # $0, but we also set the BQ checkpoint timestamp so the
                # SQL filter for "pending Tier 3" stops including them.
                if result.matched_via in ("no_result", "ambiguous_no_verify", "cache"):
                    definitive_negatives.append(ccn)

            if i % 200 == 0:
                logger.info(
                    "  %d/%d processed (matched=%d skipped=%d no_match=%d) cost=$%.4f",
                    i, len(targets), len(matched), skipped_pre_call,
                    no_match_count, cost_meter.running_usd,
                )
                if not dry_run:
                    save_cache_to_gcs(storage_client, client.cache_snapshot())
    finally:
        # Final cache flush always happens, even on BudgetExceeded
        if not dry_run:
            save_cache_to_gcs(storage_client, client.cache_snapshot())
            archive_uri = snapshot_cache_to_archive(storage_client, client.cache_snapshot())
            logger.info("Cache snapshotted to %s", archive_uri)

    logger.info("Outcome distribution: %s", by_outcome)
    logger.info(
        "Cost: $%.4f spent (text_search=%d details=%d) of budget $%.2f",
        cost_meter.running_usd, cost_meter.text_search_calls,
        cost_meter.details_calls, cost_meter.budget_usd,
    )

    if halt_reason:
        # Budget exhausted — record the unprocessed CCNs
        if pending_ccns and not dry_run:
            mark_budget_exhausted(bq_client, project, run_id, pending_ccns, dataset)
        logger.warning(
            "Budget exhausted after %d hospitals processed; %d unprocessed",
            len(targets) - len(pending_ccns), len(pending_ccns),
        )

    apply_count = apply_results(
        bq_client, project, run_id, matched,
        definitive_negatives=definitive_negatives,
        dataset=dataset, dry_run=dry_run,
    )

    return {
        "target_count": len(targets),
        "matched": len(matched),
        "no_match": no_match_count,
        "definitive_negatives": len(definitive_negatives),
        "skipped_pre_call": skipped_pre_call,
        "by_outcome": by_outcome,
        "running_usd": cost_meter.running_usd,
        "text_search_calls": cost_meter.text_search_calls,
        "details_calls": cost_meter.details_calls,
        "halted": halt_reason is not None,
        "pending_ccns_after_halt": len(pending_ccns) if halt_reason else 0,
        "applied": apply_count,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--project", default="clarobill-prd")
    parser.add_argument("--dataset", default=bq_checkpoint.DEFAULT_DATASET)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--max-places-cost", type=float, default=DEFAULT_BUDGET,
        help=f"Hard cost ceiling in USD (default ${DEFAULT_BUDGET:.0f})",
    )
    parser.add_argument(
        "--cost-preview", action="store_true",
        help="Project the run cost without making any API call",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Process at most N hospitals (testing only)",
    )
    parser.add_argument(
        "--target-ccn", default=None,
        help="Process only this single CCN (live $0.03 validation only)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    bq_client = bigquery.Client(project=args.project)
    storage_client = storage.Client(project=args.project)

    targets = get_pending_hospitals(
        bq_client, args.project, args.run_id, dataset=args.dataset,
        limit=args.limit, target_ccn=args.target_ccn,
    )

    if args.cost_preview:
        preview = cost_preview(targets)
        print()
        print(f"Stage 3 Tier 3 cost preview (run_id={args.run_id})")
        print(f"  hospitals to process:        {preview['targets_total']:>6}")
        print(f"  pre-call rejections:         {preview['rejected_pre_call']:>6}")
        print(f"  expected text-search calls:  {preview['expected_text_search_calls']:>6}")
        print(f"  expected details calls:      {preview['expected_details_calls_single']:>6} (single-result)")
        print(f"  expected verification calls: {preview['expected_details_calls_ambiguous']:>6} (ambiguous, max 3 per)")
        print(f"  projected USD:               ${preview['projected_total_usd']:.2f}")
        print(f"  budget ceiling:              ${args.max_places_cost:.2f}")
        print(f"  headroom:                    ${args.max_places_cost - preview['projected_total_usd']:.2f}")
        print()
        if preview["projected_total_usd"] > args.max_places_cost:
            print("WARNING: projected cost exceeds budget. Adjust --max-places-cost or shrink scope.")
            return 2
        print("Reviewed and projected cost is acceptable? Re-run without --cost-preview to execute.")
        return 0

    api_key = load_api_key(args.project)
    summary = run(
        bq_client=bq_client,
        storage_client=storage_client,
        project=args.project,
        run_id=args.run_id,
        api_key=api_key,
        max_places_cost=args.max_places_cost,
        dataset=args.dataset,
        limit=args.limit,
        target_ccn=args.target_ccn,
        dry_run=args.dry_run,
    )
    logger.info(
        "Stage 3 Tier 3 complete: target=%d matched=%d skipped=%d no_match=%d "
        "halted=%s spent=$%.4f",
        summary["target_count"], summary["matched"], summary["skipped_pre_call"],
        summary["no_match"], summary["halted"], summary["running_usd"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
