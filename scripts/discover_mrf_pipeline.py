"""Top-level orchestrator for the CMS-direct MRF discovery pipeline.

Runs every stage of the annual hospital-discovery pipeline in dependency order,
checkpointed via BigQuery `mrf_discovery_checkpoint` so a crashed run resumes
where it left off.

Stages (defined in `scripts/mrf_discovery/`):

  Stage 1   stage1_cms_hospital_list      seed checkpoint from CMS PI list
  Stage 2A  stage2_pos_file               POS file enrichment + new hospitals
  Stage 2B  stage2_npi_registry           NPI lookup via NPPES Registry API
  Stage 2B' stage2_npi_registry_pass2     name-cleaned NPI re-pass for misses
  Stage 2C  stage2_wikidata               Wikidata SPARQL website seeder
  Stage 3.1 stage3_tier1_validate_urls    HEAD-validate existing URLs (free)
  Stage 3.2 stage3_tier2_pattern_inference  Domain pattern inference (free)
  Stage 3.3 stage3_tier3_places           Google Places API (PAID — gated)

Run modes
---------
    # Standard annual run with new run_id
    python scripts/discover_mrf_pipeline.py --project clarobill-prd

    # Resume a specific run (e.g. after a crash)
    python scripts/discover_mrf_pipeline.py --run-id <id> --project clarobill-prd

    # Start from a specific stage (skip earlier ones — useful for re-running
    # only the costly Tier 3 with a fresh budget)
    python scripts/discover_mrf_pipeline.py --start-stage stage3_tier3 --run-id <id>

    # Cost-preview Tier 3 without making API calls (preserves all earlier work)
    python scripts/discover_mrf_pipeline.py --start-stage stage3_tier3 \\
        --tier3-cost-preview --run-id <id>

    # Custom Tier 3 budget (default $450, hard ceiling)
    python scripts/discover_mrf_pipeline.py --tier3-max-cost 200 --run-id <id>

Resumability contract
---------------------
Every stage queries the checkpoint for "rows where my predecessor finished AND
I haven't yet" — there's no in-orchestrator state. If the orchestrator dies
mid-stage, restarting it picks up exactly where the failed stage left off
because the checkpoint timestamps are persisted incrementally. Stages don't
talk to each other; they all talk to the BQ checkpoint.

Stage 3 Tier 3 specifically halts cleanly on budget exhaustion and marks
remaining hospitals with `error_stage='stage3_tier3_budget_exhausted'`. A
follow-up `--start-stage stage3_tier3` run with a fresh budget picks up
those rows.

What this orchestrator does NOT do
----------------------------------
- It does not retry within a stage. If Stage 2B fails, the orchestrator stops
  and surfaces the error. The intent is "human reviews, then re-launches" —
  not "auto-retry until the credit card is empty."
- It does not run Phase 4 (the effective-dated archiver + parser). That's a
  separate weekly job. This orchestrator runs the annual discovery only.
- It does not publish any data outside BigQuery. The annual snapshot of the
  Places API cache is written to GCS by Stage 3 Tier 3 itself.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from google.cloud import bigquery, storage

# Allow running as a script
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mrf_discovery import bq_checkpoint
from mrf_discovery import stage1_cms_hospital_list
from mrf_discovery import stage2_pos_file
from mrf_discovery import stage2_npi_registry
from mrf_discovery import stage2_npi_registry_pass2
from mrf_discovery import stage2_wikidata
from mrf_discovery import stage3_tier1_validate_urls
from mrf_discovery import stage3_tier2_pattern_inference
from mrf_discovery import stage3_tier3_places
from mrf_discovery import stage4_extract_mrf_urls

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Stage execution order. Each entry is (name, runner_fn, requires_storage_client).
# Adding a new stage means appending here AND making sure it implements the
# checkpoint contract (idempotent on re-run, advances rows by setting its
# completion timestamp).
STAGES: list[tuple[str, str]] = [
    ("stage1_cms",         "Stage 1 — CMS PI list seeder"),
    ("stage2_pos",         "Stage 2A — POS file enrichment"),
    ("stage2_npi",         "Stage 2B — NPI Registry API"),
    ("stage2_npi_pass2",   "Stage 2B' — NPI re-pass with name cleaning"),
    ("stage2_wikidata",    "Stage 2C — Wikidata SPARQL websites"),
    ("stage3_tier1",       "Stage 3.1 — Validate existing URLs"),
    ("stage3_tier2",       "Stage 3.2 — Domain pattern inference"),
    ("stage3_tier3",       "Stage 3.3 — Google Places API (PAID)"),
    ("stage4_mrf_urls",    "Stage 4 — Crawl websites for MRF URLs"),
]


def _stage_index(name: str) -> int:
    for i, (key, _label) in enumerate(STAGES):
        if key == name:
            return i
    raise ValueError(
        f"Unknown stage {name!r}; valid: {[s[0] for s in STAGES]}"
    )


def _print_run_summary(
    bq_client: bigquery.Client,
    project: str,
    run_id: str,
    dataset: str,
    started_at: datetime,
) -> dict[str, int]:
    """Print a final coverage summary for the run."""
    summary = bq_checkpoint.get_run_summary(bq_client, project, run_id, dataset)
    elapsed = datetime.now(timezone.utc) - started_at

    print()
    print(f"=== Run summary: {run_id} ===")
    print(f"  duration:           {elapsed}")
    print(f"  total checkpoint:   {summary.get('total', 0):,}")
    print(f"  cms_loaded:         {summary.get('cms_loaded', 0):,}")
    print(f"  nppes_resolved:     {summary.get('nppes_resolved', 0):,}")
    print(f"  website_found:      {summary.get('website_found', 0):,}")
    print(f"  crawl_complete:     {summary.get('crawl_complete', 0):,}")
    print(f"  mrf_validated:      {summary.get('mrf_validated', 0):,}")
    print(f"  bq_committed:       {summary.get('bq_committed', 0):,}")
    print(f"  hospitals w/ NPI:   {summary.get('with_npi', 0):,}")
    print(f"  hospitals w/ site:  {summary.get('with_website', 0):,}")
    print(f"  errored rows:       {summary.get('errored', 0):,}")
    print()
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--project", default="clarobill-prd")
    parser.add_argument("--dataset", default=bq_checkpoint.DEFAULT_DATASET)
    parser.add_argument(
        "--run-id",
        default=None,
        help="Resume an existing run, or omit to generate a fresh run_id.",
    )
    parser.add_argument(
        "--start-stage",
        choices=[s[0] for s in STAGES],
        default=None,
        help="Skip stages prior to this one. Useful for re-running only Tier 3 "
             "after a budget exhaustion or for selectively re-doing one stage.",
    )
    parser.add_argument(
        "--stop-after",
        choices=[s[0] for s in STAGES],
        default=None,
        help="Run up to and including this stage, then stop.",
    )
    parser.add_argument(
        "--tier3-max-cost",
        type=float,
        default=stage3_tier3_places.DEFAULT_BUDGET,
        help=f"Hard cost ceiling for Stage 3 Tier 3 in USD (default ${stage3_tier3_places.DEFAULT_BUDGET:.0f}).",
    )
    parser.add_argument(
        "--tier3-cost-preview",
        action="store_true",
        help="When Tier 3 starts, run cost-preview only (no API calls). Then exit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run every stage in its dry-run mode (no BQ writes, no API calls).",
    )
    parser.add_argument(
        "--gap-fill-only",
        action="store_true",
        help="Quarterly gap-fill mode: only crawl/process hospitals where "
             "validated_mrf_urls is still NULL (i.e. previous run couldn't "
             "find them) plus any new CMS-listed hospitals. Skips the heavy "
             "Tier 3 paid stage by default unless --include-tier3 is also "
             "passed. Designed for the May/Aug/Nov quarterly runs.",
    )
    parser.add_argument(
        "--include-tier3",
        action="store_true",
        help="When combined with --gap-fill-only, allows Tier 3 (paid) to "
             "run during the gap-fill. Off by default — quarterly gap-fills "
             "should be free unless explicitly opted in.",
    )
    args = parser.parse_args(argv)

    run_id = args.run_id or bq_checkpoint.new_run_id()
    started_at = datetime.now(timezone.utc)
    logger.info("=== Pipeline start: project=%s run_id=%s ===", args.project, run_id)
    if args.dry_run:
        logger.warning("DRY-RUN mode — no BQ writes, no paid API calls")

    bq_client = bigquery.Client(project=args.project)
    storage_client = storage.Client(project=args.project)

    start_idx = _stage_index(args.start_stage) if args.start_stage else 0
    stop_idx = _stage_index(args.stop_after) if args.stop_after else len(STAGES) - 1

    for i, (key, label) in enumerate(STAGES):
        if i < start_idx:
            logger.info("Skipping (before --start-stage): %s", label)
            continue
        if i > stop_idx:
            logger.info("Stopping (--stop-after %s reached)", args.stop_after)
            break

        logger.info("--- %s ---", label)
        stage_start = time.monotonic()

        try:
            if key == "stage1_cms":
                stage1_cms_hospital_list.run(
                    bq_client=bq_client, project=args.project, run_id=run_id,
                    dataset=args.dataset, dry_run=args.dry_run,
                )
            elif key == "stage2_pos":
                stage2_pos_file.run(
                    bq_client=bq_client, project=args.project, run_id=run_id,
                    dataset=args.dataset, dry_run=args.dry_run,
                )
            elif key == "stage2_npi":
                stage2_npi_registry.run(
                    bq_client=bq_client, storage_client=storage_client,
                    project=args.project, run_id=run_id, dataset=args.dataset,
                    dry_run=args.dry_run,
                )
            elif key == "stage2_npi_pass2":
                stage2_npi_registry_pass2.run(
                    bq_client=bq_client, storage_client=storage_client,
                    project=args.project, run_id=run_id, dataset=args.dataset,
                    dry_run=args.dry_run,
                )
            elif key == "stage2_wikidata":
                stage2_wikidata.run(
                    bq_client=bq_client, project=args.project, run_id=run_id,
                    dataset=args.dataset, dry_run=args.dry_run,
                )
            elif key == "stage3_tier1":
                stage3_tier1_validate_urls.run(
                    bq_client=bq_client, project=args.project, run_id=run_id,
                    dataset=args.dataset, dry_run=args.dry_run,
                )
            elif key == "stage3_tier2":
                stage3_tier2_pattern_inference.run(
                    bq_client=bq_client, project=args.project, run_id=run_id,
                    dataset=args.dataset, dry_run=args.dry_run,
                )
            elif key == "stage3_tier3":
                if args.gap_fill_only and not args.include_tier3:
                    logger.info(
                        "Stage 3 Tier 3 skipped (--gap-fill-only without "
                        "--include-tier3). Quarterly gap-fills run free stages only."
                    )
                    elapsed = time.monotonic() - stage_start
                    logger.info("--- %s skipped (%.1fs) ---", label, elapsed)
                    continue
                if args.tier3_cost_preview:
                    targets = stage3_tier3_places.get_pending_hospitals(
                        bq_client, args.project, run_id, dataset=args.dataset,
                    )
                    preview = stage3_tier3_places.cost_preview(targets)
                    print()
                    print(f"Stage 3 Tier 3 cost preview (run_id={run_id})")
                    print(f"  hospitals to process:        {preview['targets_total']:>6}")
                    print(f"  pre-call rejections:         {preview['rejected_pre_call']:>6}")
                    print(f"  expected text-search calls:  {preview['expected_text_search_calls']:>6}")
                    print(f"  expected details calls:      {preview['expected_details_calls_single']:>6} (single-result)")
                    print(f"  expected verification calls: {preview['expected_details_calls_ambiguous']:>6} (ambiguous, max 3 per)")
                    print(f"  projected USD:               ${preview['projected_total_usd']:.2f}")
                    print(f"  budget ceiling:              ${args.tier3_max_cost:.2f}")
                    print(f"  headroom:                    ${args.tier3_max_cost - preview['projected_total_usd']:.2f}")
                    print()
                    logger.info("Cost-preview only — exiting before API calls")
                    return 0
                api_key = stage3_tier3_places.load_api_key(args.project)
                stage3_tier3_places.run(
                    bq_client=bq_client, storage_client=storage_client,
                    project=args.project, run_id=run_id, api_key=api_key,
                    max_places_cost=args.tier3_max_cost,
                    dataset=args.dataset, dry_run=args.dry_run,
                )
            elif key == "stage4_mrf_urls":
                # Stage 4 doesn't have a dry-run mode of its own — when the
                # orchestrator is in --dry-run, skip Stage 4 entirely (it
                # would otherwise hit thousands of real hospital websites).
                if args.dry_run:
                    logger.info("Stage 4 skipped under --dry-run.")
                else:
                    stage4_extract_mrf_urls.run(
                        bq=bq_client, project=args.project, run_id=run_id,
                        dataset=args.dataset,
                    )
        except Exception as exc:
            logger.exception("Stage %s FAILED: %s", key, exc)
            logger.error(
                "Pipeline halted. Re-run with --run-id %s --start-stage %s "
                "after fixing the underlying issue.", run_id, key,
            )
            _print_run_summary(bq_client, args.project, run_id, args.dataset, started_at)
            return 2

        elapsed = time.monotonic() - stage_start
        logger.info("--- %s complete (%.1fs) ---", label, elapsed)

    _print_run_summary(bq_client, args.project, run_id, args.dataset, started_at)
    logger.info("=== Pipeline complete: run_id=%s ===", run_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
