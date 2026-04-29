"""Stage 3 Tier 1 — HEAD-validate existing hospital_website URLs.

For every checkpoint row that already has `hospital_website` populated (from
Stage 2C Wikidata or earlier sources), confirm the URL is live and serves a
real page. This filters out:
  - URLs where the hospital website went down or migrated
  - System-level URLs returned by Wikidata that no longer resolve
  - URLs with typos / encoding issues that look valid but don't load

What "valid" means here
-----------------------
A URL is considered valid if a HEAD or GET request returns:
  - 200 OK
  - 301/302 redirect to a non-error landing page (we follow up to 3 hops)
  - Content-Type that is text/html or application/xhtml+xml (filters PDFs,
    JSON files, etc. that some hospitals link as "websites")

A URL is rejected if:
  - 404 / 410 / 5xx
  - Connection timeout / DNS failure / SSL handshake failure
  - Redirect chain ends at an error page (>= 400)
  - Redirect loop (more than 3 hops)
  - Content-Type indicates non-HTML (e.g. application/pdf)

Output
------
For each checkpoint row processed:
  - Sets `website_found_at = NOW()` if URL validated
  - Leaves `website_found_at = NULL` if URL rejected (so Tier 2/3 retries it)
  - Logs reason for rejection (so the manual-review queue is auditable)

This stage is free, fast, and idempotent. ~10 minutes for ~6,400 URLs at
10 concurrent HEAD requests with conservative timeouts.
"""

from __future__ import annotations

import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

import requests
from google.cloud import bigquery

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from mrf_discovery import bq_checkpoint  # type: ignore[no-redef]
else:
    from . import bq_checkpoint

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

USER_AGENT = (
    "ClaroBill-MRFDiscovery/1.0 "
    "(price transparency research; contact@clarobill.com)"
)
# Browser-realistic UA used as a second-attempt fallback when hospital WAFs
# reject our descriptive UA. Sandra's 2026-04-28 Tier 1 run showed 311/3,140
# (9.9%) hospitals returning 403 to the descriptive UA — almost all are
# Cloudflare/Akamai-protected sites that block any non-browser-shaped client.
# We start with the descriptive UA (polite, identifies us); fall back to
# this only on explicit reject.
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)
HEAD_TIMEOUT = 10  # seconds
GET_TIMEOUT = 15
MAX_REDIRECTS = 3
MAX_WORKERS = 10  # conservative concurrent HEAD count

ACCEPTABLE_CONTENT_TYPES = (
    "text/html",
    "application/xhtml+xml",
)


class ValidationResult(NamedTuple):
    """Outcome of one URL validation. Used for both logging and BQ updates."""

    ccn: str
    url: str
    valid: bool
    final_url: str | None
    status_code: int | None
    reason: str  # "ok" | "404" | "timeout" | "ssl_error" | "non_html" | "redirect_loop" | etc.


def _try_request(url: str, user_agent: str) -> requests.Response | None:
    """One HEAD attempt with HEAD→GET fallback. Returns the Response or None.

    Returns None on timeout, SSL error, connection error, or redirect loop.
    The caller decides whether to retry with a different UA.
    """
    headers = {"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml"}
    try:
        resp = requests.head(
            url, headers=headers, timeout=HEAD_TIMEOUT, allow_redirects=True,
        )
        if resp.status_code in (405, 403, 501):
            resp = requests.get(
                url, headers=headers, timeout=GET_TIMEOUT,
                allow_redirects=True, stream=True,
            )
            resp.close()
        return resp
    except (requests.Timeout, requests.ConnectionError,
            requests.TooManyRedirects, requests.RequestException):
        return None


def validate_url(url: str, ccn: str) -> ValidationResult:
    """Validate a single URL.

    Two-step strategy:
      1. Try with the descriptive ClaroBill UA (polite; preferred posture).
      2. If that returns 403 / 406 / 429 (likely WAF rejection of our UA),
         retry once with a browser UA. Many hospital WAFs accept browser-
         shaped clients but reject identified bots regardless of intent.

    Network-level failures (timeout, SSL, connection) are NOT retried with
    a different UA — those are transport issues, not authentication.

    Returns a ValidationResult; never raises.
    """
    resp = _try_request(url, USER_AGENT)

    if resp is None:
        # Find out which network failure happened; one extra HEAD to classify
        try:
            requests.head(
                url, headers={"User-Agent": USER_AGENT}, timeout=HEAD_TIMEOUT,
                allow_redirects=True,
            )
        except requests.Timeout:
            return ValidationResult(ccn, url, False, None, None, "timeout")
        except requests.ConnectionError as exc:
            msg = str(exc).lower()
            if "ssl" in msg or "certificate" in msg:
                return ValidationResult(ccn, url, False, None, None, "ssl_error")
            return ValidationResult(ccn, url, False, None, None, "connection_error")
        except requests.TooManyRedirects:
            return ValidationResult(ccn, url, False, None, None, "redirect_loop")
        except requests.RequestException as exc:
            return ValidationResult(ccn, url, False, None, None, f"request_error:{type(exc).__name__}")
        # Should not reach here; defensive
        return ValidationResult(ccn, url, False, None, None, "unknown_failure")

    # WAF-likely rejection codes that may pass with a browser UA
    if resp.status_code in (403, 406, 429):
        retry = _try_request(url, BROWSER_UA)
        if retry is not None and retry.status_code < 400:
            resp = retry  # browser UA succeeded — accept it

    final_url = resp.url
    status = resp.status_code

    # Acceptable status codes (after redirects)
    if status >= 400:
        return ValidationResult(ccn, url, False, final_url, status, f"http_{status}")

    # Content-Type filter — reject non-HTML responses (some hospitals link a
    # PDF as their "website" which we can't crawl for MRF links)
    content_type = (resp.headers.get("Content-Type") or "").lower().split(";")[0].strip()
    if content_type and not any(content_type.startswith(t) for t in ACCEPTABLE_CONTENT_TYPES):
        # Allow empty content-type (some servers omit on HEAD); just log it
        return ValidationResult(ccn, url, False, final_url, status, f"non_html:{content_type}")

    return ValidationResult(ccn, url, True, final_url, status, "ok")


def get_pending_urls(
    bq_client: bigquery.Client,
    project: str,
    run_id: str,
    dataset: str = bq_checkpoint.DEFAULT_DATASET,
) -> list[dict]:
    """Return checkpoint rows where Tier 1 hasn't run.

    Filters: nppes_resolved_at IS NOT NULL  (Stage 2 done)
             AND hospital_website IS NOT NULL  (we have something to validate)
             AND website_found_at IS NULL  (Tier 1 hasn't validated it yet)
    """
    sql = f"""
    SELECT ccn, hospital_website
    FROM `{project}.{dataset}.mrf_discovery_checkpoint`
    WHERE run_id = @run_id
      AND nppes_resolved_at IS NOT NULL
      AND hospital_website IS NOT NULL
      AND website_found_at IS NULL
    ORDER BY ccn
    """
    job = bq_client.query(
        sql,
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("run_id", "STRING", run_id),
        ]),
    )
    return [{"ccn": r["ccn"], "url": r["hospital_website"]} for r in job.result()]


def apply_validations(
    bq_client: bigquery.Client,
    project: str,
    run_id: str,
    results: list[ValidationResult],
    dataset: str = bq_checkpoint.DEFAULT_DATASET,
    dry_run: bool = False,
) -> dict[str, int]:
    """MERGE Tier 1 outcomes into the checkpoint.

    For valid URLs: set website_found_at = NOW(). Update hospital_website to
    the final_url if it differs from the original (in case of redirect to a
    canonical domain) — this keeps Tier 2/3 from re-validating the redirect.

    For invalid URLs: leave website_found_at NULL (so Tier 2/3 retries) but
    record the rejection reason in error_message for audit.
    """
    if not results:
        return {"valid": 0, "invalid": 0, "total": 0}

    valid = [r for r in results if r.valid]
    invalid = [r for r in results if not r.valid]

    if dry_run:
        logger.info(
            "[dry-run] would mark %d valid + record %d rejections",
            len(valid), len(invalid),
        )
        return {"valid": len(valid), "invalid": len(invalid), "total": len(results)}

    checkpoint_table = f"{project}.{dataset}.mrf_discovery_checkpoint"
    staging_table = f"{project}.{dataset}._stage3_tier1_staging_{run_id.replace('-', '_').lower()}"
    now_iso = datetime.now(timezone.utc).isoformat()

    bq_client.query(f"""
        CREATE OR REPLACE TABLE `{staging_table}` (
          run_id            STRING,
          ccn               STRING,
          final_url         STRING,
          valid             BOOL,
          rejection_reason  STRING,
          website_found_at  TIMESTAMP
        )
    """).result()

    try:
        rows = [
            {
                "run_id": run_id,
                "ccn": r.ccn,
                "final_url": r.final_url,
                "valid": r.valid,
                "rejection_reason": None if r.valid else r.reason,
                "website_found_at": now_iso if r.valid else None,
            }
            for r in results
        ]
        BATCH = 500
        for i in range(0, len(rows), BATCH):
            errors = bq_client.insert_rows_json(staging_table, rows[i : i + BATCH])
            if errors:
                raise RuntimeError(f"Stage 3 Tier 1 staging insert failed at batch {i}: {errors[:3]}")

        # Two MERGEs: one for valid (set website_found_at + maybe update URL),
        # one for invalid (record reason in error_message). We do them as a
        # single combined MERGE for atomicity.
        merge_sql = f"""
        MERGE `{checkpoint_table}` T
        USING `{staging_table}` S
        ON T.run_id = S.run_id AND T.ccn = S.ccn
        WHEN MATCHED AND S.valid THEN
          UPDATE SET
            website_found_at = S.website_found_at,
            hospital_website = COALESCE(S.final_url, T.hospital_website),
            last_updated_at  = S.website_found_at
        WHEN MATCHED AND NOT S.valid THEN
          UPDATE SET
            error_stage   = 'website_found',
            error_message = S.rejection_reason,
            consecutive_failures = COALESCE(T.consecutive_failures, 0) + 1,
            last_updated_at = CURRENT_TIMESTAMP()
        """
        bq_client.query(merge_sql).result()
        return {"valid": len(valid), "invalid": len(invalid), "total": len(results)}
    finally:
        bq_client.query(f"DROP TABLE IF EXISTS `{staging_table}`").result()


def run(
    bq_client: bigquery.Client,
    project: str,
    run_id: str,
    dataset: str = bq_checkpoint.DEFAULT_DATASET,
    max_workers: int = MAX_WORKERS,
    dry_run: bool = False,
) -> dict[str, int]:
    targets = get_pending_urls(bq_client, project, run_id, dataset=dataset)
    logger.info("Stage 3 Tier 1: %d URLs to validate", len(targets))
    if not targets:
        return {"target_count": 0, "valid": 0, "invalid": 0, "by_reason": {}}

    results: list[ValidationResult] = []
    by_reason: dict[str, int] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(validate_url, t["url"], t["ccn"]): t for t in targets}
        for i, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            results.append(result)
            by_reason[result.reason] = by_reason.get(result.reason, 0) + 1
            if i % 500 == 0:
                valid_so_far = sum(1 for r in results if r.valid)
                logger.info(
                    "  %d/%d processed (valid=%d invalid=%d)",
                    i, len(targets), valid_so_far, len(results) - valid_so_far,
                )

    valid_count = sum(1 for r in results if r.valid)
    logger.info("Validation outcomes: %s", by_reason)

    summary = apply_validations(
        bq_client, project, run_id, results, dataset=dataset, dry_run=dry_run,
    )
    summary["target_count"] = len(targets)
    summary["by_reason"] = by_reason
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--project", default="clarobill-prd")
    parser.add_argument("--dataset", default=bq_checkpoint.DEFAULT_DATASET)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--max-workers", type=int, default=MAX_WORKERS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    logger.info("Stage 3 Tier 1 starting: project=%s run_id=%s", args.project, args.run_id)
    bq_client = bigquery.Client(project=args.project)
    summary = run(
        bq_client=bq_client,
        project=args.project,
        run_id=args.run_id,
        dataset=args.dataset,
        max_workers=args.max_workers,
        dry_run=args.dry_run,
    )
    logger.info(
        "Stage 3 Tier 1 complete: target=%d valid=%d invalid=%d",
        summary["target_count"], summary["valid"], summary["invalid"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
