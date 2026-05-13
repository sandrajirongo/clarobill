"""Stage 3 Tier 2 — Domain pattern inference for hospitals without a URL.

For checkpoint rows where Tier 1 didn't validate a URL (because there was no
URL to validate), try common slug-based domain patterns and HEAD-check each.
First valid pattern wins, after a name-in-page cross-validation.

Why this works
--------------
Many hospitals own predictable domains derived from their name. "Memorial
Hospital" in Springfield → memorialhospital.org. "Saint John's Health Center"
→ saintjohns.org. Trying ~10 patterns per hospital recovers a small but free
fraction (estimated 3-5%) before we ever spend a Google Places dollar.

Patterns tried (in order)
-------------------------
For a hospital with name "Saint Vincent's Memorial Hospital":
  slug = "saintvincentsmemorial"  (lower, alphanum-only, no spaces)
  short = "saintvincents"          (drop common suffixes after first 2-3 words)

  https://{slug}.org
  https://{slug}.com
  https://www.{slug}.org
  https://www.{slug}.com
  https://{short}.org
  https://{short}hospital.org
  https://{short}health.org
  https://{short}healthcare.org
  https://{short}medicalcenter.org

False-positive protection
-------------------------
A pattern's domain may resolve to a parked-domain page or unrelated business.
Before accepting, we fetch the homepage HTML and verify the hospital name
appears in the `<title>` or first `<h1>` (case-insensitive substring match
against any 5+ char word from the hospital name).

Cost: free. Each hospital generates up to ~10 HEAD requests + 1 GET on the
first hit. Conservative concurrency to avoid hammering DNS.
"""

from __future__ import annotations

import argparse
import logging
import re
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
HEAD_TIMEOUT = 5  # short — pattern domains either resolve fast or aren't ours
GET_TIMEOUT = 10
MAX_WORKERS = 8

# Words that are common to many hospitals and dilute the slug. Stripped from
# the "short" form. Order doesn't matter; we strip all matches.
GENERIC_WORDS = frozenset({
    "HOSPITAL", "HOSPITALS",
    "MEDICAL", "CENTER", "CENTRE",
    "HEALTH", "HEALTHCARE", "HEALTHCARE",
    "SYSTEM", "SYSTEMS",
    "MEMORIAL", "REGIONAL",
    "GENERAL", "COMMUNITY",
    "AT", "OF", "THE", "AND",
    "INC", "LLC", "LLP",
})

# Slug-cleaning regex: drop everything that isn't a-z0-9
_SLUG_NON_ALNUM = re.compile(r"[^a-z0-9]+")


class TierTwoResult(NamedTuple):
    ccn: str
    found_url: str | None  # None means no pattern matched
    matched_pattern: str | None
    rejection_summary: str  # e.g. "tried 10 patterns, none resolved"


def slugify(name: str) -> str:
    """Lowercase + strip non-alphanumeric for domain pattern matching."""
    return _SLUG_NON_ALNUM.sub("", name.lower())


def short_slug(name: str) -> str:
    """Drop generic-word components, then slugify.

    'Saint Vincent's Memorial Hospital' → 'saintvincents'
    'Mayo Clinic Hospital' → 'mayoclinic'
    'Mercy Health System' → 'mercy'
    """
    words = re.split(r"\s+", name.upper())
    kept = [w for w in words if w and w not in GENERIC_WORDS]
    return _SLUG_NON_ALNUM.sub("", "".join(kept).lower())


# Minimum slug length to attempt a domain pattern. Below this, slugs are
# either empty (all-generic names like "Hospital Inc") or too short to be
# distinctive ("VA", "St"). DNS labels also have a 1-character minimum, so
# anything < 2 chars produces malformed URLs that crash IDNA encoding.
MIN_SLUG_LEN = 3


def candidate_urls(hospital_name: str) -> list[str]:
    """Generate ordered list of candidate URLs for a hospital name.

    Most likely successful patterns first so we short-circuit early. Empty
    or too-short slugs return [] — the slug must satisfy DNS label rules
    (1-63 chars, alphanumeric-only at this point since we strip everything
    else in slugify). MIN_SLUG_LEN = 3 to avoid both DNS label issues and
    obviously-wrong matches against single-character TLDs.
    """
    slug = slugify(hospital_name)
    short = short_slug(hospital_name)

    if not slug or len(slug) < MIN_SLUG_LEN:
        return []

    candidates: list[str] = []
    seen: set[str] = set()

    def _add(url: str) -> None:
        if url not in seen:
            candidates.append(url)
            seen.add(url)

    # Most common: short name + .org. Only use `short` if it's distinctive.
    if short and len(short) >= MIN_SLUG_LEN:
        _add(f"https://{short}.org")
        _add(f"https://www.{short}.org")
        _add(f"https://{short}hospital.org")
        _add(f"https://{short}health.org")
        _add(f"https://{short}healthcare.org")
        _add(f"https://{short}medicalcenter.org")
        _add(f"https://{short}.com")

    # Full slug fallback
    _add(f"https://{slug}.org")
    _add(f"https://www.{slug}.org")
    _add(f"https://{slug}.com")

    return candidates


def hospital_name_keywords(name: str, min_word_len: int = 5) -> list[str]:
    """Return distinctive keywords from a hospital name.

    Used for cross-validation: "Saint Vincent's Memorial Hospital" yields
    ["VINCENT'S", "MEMORIAL"] (drops generics and short words). At least one
    keyword must appear in the candidate page's title/h1 for the URL to
    pass validation.
    """
    words = re.split(r"\s+", name.upper())
    return [
        w for w in words
        if len(w) >= min_word_len and w not in GENERIC_WORDS
    ]


def verify_hospital_in_page(url: str, name: str) -> bool:
    """Fetch the page and check if any hospital-name keyword appears.

    Looks at the first 64 KB of the response body. We don't parse HTML — a
    case-insensitive substring search against the raw bytes is fine because:
    - Title and H1 text appears verbatim in the source
    - We only need ONE keyword to match (high recall, modest precision)
    - HTML attribute values like <meta description> also count, which is
      desirable (some hospital sites have hospital name in meta tags but
      not in title/h1).
    """
    keywords = hospital_name_keywords(name)
    if not keywords:
        return False

    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
            timeout=GET_TIMEOUT,
            stream=True,
        )
        if resp.status_code >= 400:
            resp.close()
            return False
        # SF9 (Phase 8.4): pre-fix this called resp.raw.read(65536,
        # decode_content=True) without a Content-Length pre-check —
        # urllib3 buffers internally before decode, so a misconfigured
        # CDN serving a 500MB binary as text/html could OOM the worker.
        # Same S5 pattern that was fixed in Stage 4 via _read_capped.
        # Reuse that defense here:
        content_length = resp.headers.get("Content-Length")
        if content_length:
            try:
                if int(content_length) > 65536 * 16:  # 1 MiB hard cap
                    resp.close()
                    logger.debug(
                        "Skipping %s: Content-Length=%s exceeds verify cap",
                        url, content_length,
                    )
                    return False
            except (ValueError, TypeError):
                pass
        # Read first 64 KB only
        body = resp.raw.read(65536, decode_content=True)
        resp.close()
    except (requests.RequestException, OSError):
        return False

    body_upper = body.decode("utf-8", errors="replace").upper()
    return any(kw in body_upper for kw in keywords)


def try_patterns(ccn: str, hospital_name: str) -> TierTwoResult:
    """Iterate candidate URLs; return the first that HEAD-succeeds AND verifies.

    Wraps each candidate's request in broad exception handling so no single
    hospital's URL malformation can crash the run. The bq_checkpoint contract
    requires that one bad hospital cannot kill the pipeline; we honour that
    by catching anything from the requests + urllib3 + IDNA stack.
    """
    candidates = candidate_urls(hospital_name)
    if not candidates:
        return TierTwoResult(ccn, None, None, "empty_slug")

    headers = {"User-Agent": USER_AGENT}
    tried = 0
    for url in candidates:
        tried += 1
        resp = None
        try:
            resp = requests.head(
                url, headers=headers, timeout=HEAD_TIMEOUT, allow_redirects=True,
            )
        except requests.RequestException:
            # HTTP-layer error — wrong hostname, DNS failure, SSL, timeout
            continue
        except (UnicodeError, ValueError, OSError):
            # IDNA encoding error, malformed URL, or low-level socket issue.
            # Should not reach here if candidate_urls validates length, but
            # belt-and-suspenders: log and continue.
            logger.debug("Pattern URL malformed for ccn=%s: %r", ccn, url)
            continue

        if resp.status_code >= 400:
            continue
        # HEAD succeeded; verify with a GET
        try:
            if verify_hospital_in_page(url, hospital_name):
                return TierTwoResult(ccn, resp.url, url, "ok")
        except Exception:
            # verify_hospital_in_page already handles its own exceptions, but
            # any escape (e.g. unicode in keyword) shouldn't kill the worker.
            continue

    return TierTwoResult(ccn, None, None, f"tried_{tried}_no_match")


def get_pending_hospitals(
    bq_client: bigquery.Client,
    project: str,
    run_id: str,
    dataset: str = bq_checkpoint.DEFAULT_DATASET,
) -> list[dict]:
    """Hospitals that need Tier 2 — Stage 2 done, no URL, name + state present."""
    sql = f"""
    SELECT ccn, hospital_name, state, city
    FROM `{project}.{dataset}.mrf_discovery_checkpoint`
    WHERE run_id = @run_id
      AND nppes_resolved_at IS NOT NULL
      AND hospital_website IS NULL
      AND website_found_at IS NULL
      AND hospital_name IS NOT NULL
      AND state IS NOT NULL
    ORDER BY ccn
    """
    job = bq_client.query(
        sql,
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("run_id", "STRING", run_id),
        ]),
    )
    return [dict(row) for row in job.result()]


def apply_tier2_results(
    bq_client: bigquery.Client,
    project: str,
    run_id: str,
    results: list[TierTwoResult],
    dataset: str = bq_checkpoint.DEFAULT_DATASET,
    dry_run: bool = False,
) -> dict[str, int]:
    """MERGE Tier 2 outcomes into the checkpoint.

    Only writes hospital_website + website_source for matched hospitals.
    No-match rows are left untouched (Tier 3 retries them).
    """
    matched = [r for r in results if r.found_url]
    no_match = [r for r in results if not r.found_url]

    if dry_run:
        logger.info(
            "[dry-run] would set hospital_website for %d hospitals; %d unmatched",
            len(matched), len(no_match),
        )
        return {"matched": len(matched), "no_match": len(no_match), "total": len(results)}

    if not matched:
        return {"matched": 0, "no_match": len(no_match), "total": len(results)}

    checkpoint_table = f"{project}.{dataset}.mrf_discovery_checkpoint"
    staging_table = f"{project}.{dataset}._stage3_tier2_staging_{run_id.replace('-', '_').lower()}"
    now_iso = datetime.now(timezone.utc).isoformat()

    bq_client.query(f"""
        CREATE OR REPLACE TABLE `{staging_table}` (
          run_id            STRING,
          ccn               STRING,
          hospital_website  STRING,
          website_found_at  TIMESTAMP
        )
    """).result()

    try:
        rows = [
            {
                "run_id": run_id,
                "ccn": r.ccn,
                "hospital_website": r.found_url,
                "website_found_at": now_iso,
            }
            for r in matched
        ]
        BATCH = 500
        for i in range(0, len(rows), BATCH):
            errors = bq_client.insert_rows_json(staging_table, rows[i : i + BATCH])
            if errors:
                raise RuntimeError(f"Stage 3 Tier 2 staging insert failed: {errors[:3]}")

        merge_sql = f"""
        MERGE `{checkpoint_table}` T
        USING `{staging_table}` S
        ON T.run_id = S.run_id AND T.ccn = S.ccn
        WHEN MATCHED AND T.hospital_website IS NULL THEN
          UPDATE SET
            hospital_website = S.hospital_website,
            website_source   = 'pattern_inference',
            website_found_at = S.website_found_at,
            last_updated_at  = S.website_found_at
        """
        bq_client.query(merge_sql).result()
        return {"matched": len(matched), "no_match": len(no_match), "total": len(results)}
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
    targets = get_pending_hospitals(bq_client, project, run_id, dataset=dataset)
    logger.info("Stage 3 Tier 2: %d hospitals to try patterns for", len(targets))
    if not targets:
        return {"target_count": 0, "matched": 0, "no_match": 0}

    results: list[TierTwoResult] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(try_patterns, t["ccn"], t["hospital_name"]): t for t in targets
        }
        for i, future in enumerate(as_completed(futures), start=1):
            try:
                results.append(future.result())
            except Exception as exc:
                # Last-resort guard: even if try_patterns somehow leaks an
                # exception, record a failed result and keep going. The
                # pipeline contract is that one bad hospital cannot kill
                # the run.
                target = futures[future]
                logger.exception(
                    "Worker raised for ccn=%s: %s: %s",
                    target.get("ccn"), type(exc).__name__, exc,
                )
                results.append(TierTwoResult(
                    target.get("ccn", "unknown"), None, None,
                    f"worker_error:{type(exc).__name__}",
                ))
            if i % 200 == 0:
                matched_so_far = sum(1 for r in results if r.found_url)
                logger.info(
                    "  %d/%d processed (matched=%d)", i, len(targets), matched_so_far,
                )

    summary = apply_tier2_results(
        bq_client, project, run_id, results, dataset=dataset, dry_run=dry_run,
    )
    summary["target_count"] = len(targets)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--project", default="clarobill-prd")
    parser.add_argument("--dataset", default=bq_checkpoint.DEFAULT_DATASET)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--max-workers", type=int, default=MAX_WORKERS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    logger.info("Stage 3 Tier 2 starting: project=%s run_id=%s", args.project, args.run_id)
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
        "Stage 3 Tier 2 complete: target=%d matched=%d no_match=%d",
        summary["target_count"], summary["matched"], summary["no_match"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
