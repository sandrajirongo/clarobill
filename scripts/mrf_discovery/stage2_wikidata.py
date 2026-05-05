"""Stage 2C — Wikidata SPARQL fetcher for major hospital systems.

Large US hospital systems (HCA, Ascension, Mayo Clinic, Kaiser Permanente, etc.)
all have Wikidata entries with `official website (P856)` populated. A single
SPARQL query returns ~500 such records in under 5 seconds.

We use this to fill in websites for the long tail of hospitals that lack a
direct website source. Stage 3 (website discovery) extends this with domain
pattern inference and Google Places API lookups.

Match strategy
--------------
For each (system_name, website_url) pair from Wikidata, we fuzzy-match
system_name against checkpoint hospital_name using difflib.SequenceMatcher.
The threshold is 0.85 — high enough to avoid false positives on partial name
overlaps, low enough to handle "Mayo Clinic Hospital" matching "Mayo Clinic".

We only update checkpoint rows where hospital_website IS NULL. Wikidata
returns system-level URLs; if a hospital-specific URL is later found by
Stage 3, that will overwrite this fallback.

Caching
-------
The SPARQL endpoint is fast and free. We do not cache — re-running the same
query on each annual run reflects new Wikidata edits.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

import requests
from google.cloud import bigquery

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from mrf_discovery import bq_checkpoint  # type: ignore[no-redef]
else:
    from . import bq_checkpoint

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
USER_AGENT = (
    "ClaroBill-MRFDiscovery/1.0 "
    "(price transparency research; contact@clarobill.com)"
)
FUZZY_MATCH_THRESHOLD = 0.85

# Wikidata properties used:
#   P31  = instance of
#   P279 = subclass of
#   P856 = official website
#   P17  = country
# Wikidata entities used:
#   Q16917 = hospital
#   Q4287745 = hospital network / health system
#   Q30 = United States
SPARQL_QUERY = """
SELECT DISTINCT ?hospital ?name ?website WHERE {
  { ?hospital wdt:P31/wdt:P279* wd:Q16917 . }
  UNION
  { ?hospital wdt:P31/wdt:P279* wd:Q4287745 . }
  ?hospital wdt:P856 ?website .
  ?hospital wdt:P17 wd:Q30 .
  ?hospital rdfs:label ?name .
  FILTER(LANG(?name) = "en")
}
"""


def fetch_us_hospital_systems(
    sparql_endpoint: str = WIKIDATA_SPARQL,
    timeout: int = 60,
    *,
    cache_bucket: str | None = None,
    cache_year: int | None = None,
) -> list[dict]:
    """Run the SPARQL query, return [{name, website}, ...].

    Wikidata returns each entity once even if multiple websites exist for it
    (`DISTINCT` on hospital). If the same name appears with different websites
    (e.g. system + facility), we keep the first one returned.

    SF8 (Phase 8.5): retry-with-backoff (3 attempts, exponential) and GCS
    cache fallback. Pre-SF8 a transient Wikidata outage = entire annual
    discovery's Wikidata signal lost = ~500 long-tail hospitals' worth of
    coverage gone for a year. Now: persist successful results to
    gs://{cache_bucket}/wikidata/{year}.json; on all-3-fail, fall back
    to last year's cached snapshot. Cost analysis: ~65 MB Standard
    storage + 1 write/year + 1 read/year ≈ $0.02/year (CLAUDE.md Rule 16).
    """
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/sparql-results+json",
    }
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            resp = requests.get(
                sparql_endpoint, params={"query": SPARQL_QUERY}, headers=headers, timeout=timeout,
            )
            resp.raise_for_status()
            payload = resp.json()
            break
        except (requests.RequestException, ValueError) as exc:
            last_exc = exc
            if attempt < 2:
                sleep_s = 2 ** attempt
                logger.warning(
                    "Wikidata SPARQL attempt %d/3 failed (%s); retrying in %ds",
                    attempt + 1, exc, sleep_s,
                )
                time.sleep(sleep_s)
            else:
                logger.error(
                    "Wikidata SPARQL exhausted 3 retries: %s. Falling back to GCS cache.",
                    exc,
                )
    else:  # pragma: no cover — only reached when all retries fail
        # SF8 fallback: last year's snapshot from GCS.
        if cache_bucket and cache_year:
            cached = _load_wikidata_cache(cache_bucket, cache_year - 1)
            if cached is not None:
                logger.warning(
                    "Wikidata: using cached snapshot from year %d (%d rows). "
                    "Live SPARQL was unavailable: %s",
                    cache_year - 1, len(cached), last_exc,
                )
                return cached
        # No cache available — re-raise so the run fails loudly.
        raise RuntimeError(
            f"Wikidata SPARQL failed after 3 retries and no cache fallback "
            f"is available (cache_bucket={cache_bucket!r}, cache_year={cache_year!r}). "
            f"Last error: {last_exc}"
        )
    bindings = payload.get("results", {}).get("bindings", [])
    seen_names: set[str] = set()
    rows: list[dict] = []
    for b in bindings:
        name = (b.get("name", {}).get("value") or "").strip()
        website = _clean_url((b.get("website", {}).get("value") or "").strip())
        if not name or not website:
            continue
        key = name.lower()
        if key in seen_names:
            continue
        seen_names.add(key)
        rows.append({"name": name, "website": website})
    logger.info("Wikidata returned %d unique US hospitals/systems", len(rows))
    # SF8 fallback: persist this run's results so a future outage can
    # use them. Best-effort — a cache write failure must not fail the run.
    if cache_bucket and cache_year and rows:
        try:
            _save_wikidata_cache(cache_bucket, cache_year, rows)
        except Exception as exc:  # noqa: BLE001 — cache is best-effort
            logger.warning("Wikidata cache write failed (year=%d): %s", cache_year, exc)
    return rows


def _wikidata_cache_path(year: int) -> str:
    return f"wikidata/{year}.json"


def _save_wikidata_cache(bucket: str, year: int, rows: list[dict]) -> None:
    """Persist a Wikidata fetch result to GCS for next-year fallback. SF8."""
    from google.cloud import storage  # noqa: PLC0415 — lazy import; storage is heavy
    client = storage.Client()
    blob = client.bucket(bucket).blob(_wikidata_cache_path(year))
    blob.upload_from_string(json.dumps(rows), content_type="application/json")
    logger.info(
        "Cached %d Wikidata rows to gs://%s/%s",
        len(rows), bucket, _wikidata_cache_path(year),
    )


def _load_wikidata_cache(bucket: str, year: int) -> list[dict] | None:
    """Load a prior Wikidata snapshot from GCS, or None if not cached. SF8."""
    from google.cloud import storage  # noqa: PLC0415
    try:
        client = storage.Client()
        blob = client.bucket(bucket).blob(_wikidata_cache_path(year))
        if not blob.exists():
            return None
        data = blob.download_as_text()
        return list(json.loads(data))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Wikidata cache load failed (year=%d): %s", year, exc)
        return None


def _clean_url(val: str) -> str | None:
    if not val:
        return None
    s = val.strip()
    if not s:
        return None
    if not s.startswith(("http://", "https://")):
        s = "https://" + s
    return s


def match_to_checkpoint(
    candidates: list[dict],
    checkpoint_rows: list[dict],
    threshold: float = FUZZY_MATCH_THRESHOLD,
) -> dict[str, str]:
    """Fuzzy-match Wikidata candidates to checkpoint hospital names.

    Returns {ccn: website_url} for every checkpoint row whose name matches a
    Wikidata candidate name with similarity >= threshold. Each Wikidata
    candidate can map to multiple CCNs (a system entry like "HCA Healthcare"
    matches all 180 HCA facilities).

    Performance
    -----------
    Naïve O(N*M) where N = checkpoint rows (~14k) and M = candidates (~5k)
    is ~67M SequenceMatcher.ratio() calls and takes hours. Three pre-filters
    short-circuit most pairs:

      1. **Exact-match dict** — O(1) lookup before any fuzzy work.
      2. **Length-difference filter** — pairs with length ratio outside the
         threshold can never cross it (Levenshtein lower bound).
      3. **First-letter bucketing** — pairs whose first letters differ are
         filtered out. SequenceMatcher's `real_quick_ratio()` and
         `quick_ratio()` then act as cheap upper-bound filters before we
         call the expensive `ratio()`.

    Combined: ~14k × ~50 candidate buckets ≈ 700k cheap checks, of which
    ~5k pass the quick_ratio gate and reach the expensive ratio() call.
    Runtime: seconds instead of hours.
    """
    matches: dict[str, str] = {}
    if not candidates or not checkpoint_rows:
        return matches

    # Build exact-match dict (case-insensitive) for O(1) shortcut
    exact_lookup: dict[str, str] = {}
    for c in candidates:
        key = c["name"].lower()
        # If duplicates exist, first one wins (matches the iteration order
        # the previous implementation relied on).
        exact_lookup.setdefault(key, c["website"])

    # Bucket candidates by first character of the lowercased name. Pairs whose
    # first letters differ have a SequenceMatcher.ratio() ceiling well below
    # 0.85, so they can be eliminated cheaply. We keep the lowercased + URL
    # pre-computed so the inner loop is just comparison work.
    by_first_char: dict[str, list[tuple[str, str]]] = {}
    for c in candidates:
        c_lc = c["name"].lower()
        if not c_lc:
            continue
        by_first_char.setdefault(c_lc[0], []).append((c_lc, c["website"]))

    for row in checkpoint_rows:
        ccn = row.get("ccn")
        name = row.get("hospital_name")
        if not ccn or not name:
            continue
        name_lc = name.lower()

        # Tier 1: exact match in O(1)
        if name_lc in exact_lookup:
            matches[ccn] = exact_lookup[name_lc]
            continue

        # Tier 2: bucketed fuzzy match (only same-first-char candidates)
        first_char = name_lc[0] if name_lc else ""
        bucket = by_first_char.get(first_char, ())
        if not bucket:
            continue

        best_ratio = 0.0
        best_url: str | None = None
        name_len = len(name_lc)
        len_tolerance = name_len * (1 - threshold)

        for c_lc, c_url in bucket:
            # Length-difference filter (Levenshtein lower bound)
            if abs(len(c_lc) - name_len) > len_tolerance:
                continue

            # Cheap pre-filters from difflib
            sm = SequenceMatcher(None, name_lc, c_lc)
            if sm.real_quick_ratio() < threshold:
                continue
            if sm.quick_ratio() < threshold:
                continue

            ratio = sm.ratio()
            if ratio >= threshold and ratio > best_ratio:
                best_ratio = ratio
                best_url = c_url

        if best_url:
            matches[ccn] = best_url

    logger.info("Fuzzy-matched %d checkpoint rows to Wikidata systems", len(matches))
    return matches


def get_unresolved_websites(
    bq_client: bigquery.Client,
    project: str,
    run_id: str,
    dataset: str = bq_checkpoint.DEFAULT_DATASET,
) -> list[dict]:
    """Return ccn + hospital_name for checkpoint rows still missing a website."""
    sql = f"""
    SELECT ccn, hospital_name
    FROM `{project}.{dataset}.mrf_discovery_checkpoint`
    WHERE run_id = @run_id
      AND nppes_resolved_at IS NOT NULL
      AND hospital_website IS NULL
    """
    job = bq_client.query(
        sql,
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("run_id", "STRING", run_id),
        ]),
    )
    return [{"ccn": r["ccn"], "hospital_name": r["hospital_name"]} for r in job.result()]


def apply_matches(
    bq_client: bigquery.Client,
    project: str,
    run_id: str,
    matches: dict[str, str],
    dataset: str = bq_checkpoint.DEFAULT_DATASET,
    dry_run: bool = False,
) -> int:
    """Update checkpoint rows with Wikidata-sourced websites.

    Only updates rows where hospital_website IS NULL — does not overwrite
    NPPES-sourced URLs.
    """
    if not matches:
        return 0
    if dry_run:
        logger.info("[dry-run] would set hospital_website for %d CCNs from Wikidata", len(matches))
        return 0

    checkpoint_table = f"{project}.{dataset}.mrf_discovery_checkpoint"
    staging_table = f"{project}.{dataset}._stage2_wikidata_staging_{run_id.replace('-', '_').lower()}"
    now_iso = datetime.now(timezone.utc).isoformat()

    bq_client.query(f"""
        CREATE OR REPLACE TABLE `{staging_table}` (
          run_id              STRING,
          ccn                 STRING,
          hospital_website    STRING,
          last_updated_at     TIMESTAMP
        )
    """).result()

    try:
        rows = [
            {
                "run_id": run_id,
                "ccn": ccn,
                "hospital_website": url,
                "last_updated_at": now_iso,
            }
            for ccn, url in matches.items()
        ]
        # Batch in chunks of 500 for consistency with the other Stage 2 modules
        # and as defence against future scenarios where Wikidata returns more
        # matches than expected. See `stage2_pos_file.py` for the SSL-timeout
        # incident that motivated batching across the pipeline.
        BATCH = 500
        for i in range(0, len(rows), BATCH):
            errors = bq_client.insert_rows_json(staging_table, rows[i : i + BATCH])
            if errors:
                raise RuntimeError(f"Wikidata staging insert failed at batch {i}: {errors[:3]}")

        merge_sql = f"""
        MERGE `{checkpoint_table}` T
        USING `{staging_table}` S
        ON T.run_id = S.run_id AND T.ccn = S.ccn
        WHEN MATCHED AND T.hospital_website IS NULL THEN
          UPDATE SET
            hospital_website = S.hospital_website,
            website_source   = 'wikidata',
            last_updated_at  = S.last_updated_at
        """
        bq_client.query(merge_sql).result()
        return len(matches)
    finally:
        bq_client.query(f"DROP TABLE IF EXISTS `{staging_table}`").result()


def run(
    bq_client: bigquery.Client,
    project: str,
    run_id: str,
    dataset: str = bq_checkpoint.DEFAULT_DATASET,
    dry_run: bool = False,
) -> dict[str, int]:
    # SF8: pass through GCS cache config from env so the function can
    # fall back to last year's snapshot when Wikidata is unreachable.
    # MRF_DISCOVERY_CACHE_BUCKET should point at a Standard-class bucket
    # in the same project (e.g. gs://mrf-discovery-cache).
    import os  # noqa: PLC0415
    cache_bucket = os.environ.get("MRF_DISCOVERY_CACHE_BUCKET", "").strip() or None
    cache_year = datetime.now(timezone.utc).year
    candidates = fetch_us_hospital_systems(
        cache_bucket=cache_bucket, cache_year=cache_year,
    )
    unresolved = get_unresolved_websites(bq_client, project, run_id, dataset=dataset)
    logger.info(
        "Stage 2C: %d Wikidata candidates, %d checkpoint rows missing website",
        len(candidates), len(unresolved),
    )
    matches = match_to_checkpoint(candidates, unresolved)
    updated = apply_matches(bq_client, project, run_id, matches, dataset=dataset, dry_run=dry_run)
    return {
        "wikidata_candidates": len(candidates),
        "unresolved_pre": len(unresolved),
        "matched": len(matches),
        "updated": updated,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--project", default="clarobill-prd")
    parser.add_argument("--dataset", default=bq_checkpoint.DEFAULT_DATASET)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    logger.info("Stage 2C starting: project=%s run_id=%s", args.project, args.run_id)
    client = bigquery.Client(project=args.project)
    summary = run(
        bq_client=client,
        project=args.project,
        run_id=args.run_id,
        dataset=args.dataset,
        dry_run=args.dry_run,
    )
    logger.info(
        "Stage 2C complete: candidates=%d unresolved_pre=%d matched=%d updated=%d",
        summary["wikidata_candidates"], summary["unresolved_pre"],
        summary["matched"], summary["updated"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
