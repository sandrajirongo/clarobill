"""Resolve NPI for mrf_archive_index rows that failed with 'no NPI resolvable'.

Background
----------
After the 2026-05-05 recovery run, 5,510 blobs remain in mrf_archive_index
with parse_status='failed' and parse_error='no NPI resolvable from JSON root,
URL, or scraper metadata'. These blobs never produced hospital_charges rows, so
resolve_ambiguous_npis.py (which sources from hospital_charges) cannot fix them.

URL breakdown:
  - 5,439: 9-digit EIN in filename (e.g. 941196203_st-mary_standardcharges.json)
  - 71:    formatted EIN XX-XXXXXXX (e.g. 62-1383977_hospital_standardcharges.json)
  - 967:   no numeric EIN (Ascension/Providence XLSX with hospital-name slug only)

Approach
--------
1. Query mrf_archive_index directly for the target rows.
2. Extract a hospital-name slug from the URL (three patterns handled below).
3. Score against NPPES hospital-taxonomy names via Jaccard word-overlap
   (same algorithm as resolve_ambiguous_npis.py).
4. Write accepted matches:
     UPDATE mrf_archive_index SET hospital_npi = <npi>, parse_status = 'pending'
   so the parser picks them up on the next run.

Slug extraction rules
---------------------
  EIN-9:      {9-digit-EIN}_{slug}_standardcharges.{ext}
  EIN-dash:   {2d}-{7d}_{slug}_standardcharges.{ext}   (normalised to same pattern)
  No-EIN:     basename-without-extension, stripped of any trailing _standardcharges
              suffix (Ascension/Providence files use plain hospital-name stems)

--- Running ---
  python scripts/mrf_discovery/recover_no_npi_archive_blobs.py --dry-run
  python scripts/mrf_discovery/recover_no_npi_archive_blobs.py --apply
  python scripts/mrf_discovery/recover_no_npi_archive_blobs.py --min-score 0.4 --apply
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PROJECT = "clarobill-prd"
DATASET = "hospital_prices"
NPPES_TABLE = "bigquery-public-data.nppes.npi_raw"
HOSPITAL_TAXONOMY_PREFIX = "28"

_PARSE_ERROR = "no NPI resolvable from JSON root, URL, or scraper metadata"

_STOPWORDS = frozenset({
    "the", "of", "and", "a", "at", "for", "in", "on", "an",
    "hospital", "medical", "health", "healthcare", "center", "centre",
    "campus", "facility", "system", "services", "incorporated", "inc",
    "llc", "corp", "company", "co", "ltd",
})

_NON_HOSPITAL_NAME_HINTS = (
    "PHARMACY", "CLINIC", "PHYSICIANS", "PHYSICIAN GROUP", " GROUP",
    "MEDICAL GROUP", "PRACTICE", "ASSOCIATES", "OUTPATIENT", "URGENT CARE",
    "AMBULATORY", "SURGERY CENTER", "IMAGING",
)

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


@dataclass(frozen=True)
class Match:
    url: str
    slug: str
    npi: str
    name: str
    shared_words: int
    score: float
    margin: float


def _tokenize(text: str) -> frozenset[str]:
    spaced = _CAMEL_BOUNDARY.sub(" ", text)
    return frozenset(
        w for w in re.split(r"[^a-z0-9]+", spaced.lower())
        if len(w) > 1 and w not in _STOPWORDS
    )


# Matches standard EIN prefix (9-digit or XX-XXXXXXX) then slug then standardcharges
_EIN9_SLUG_RE = re.compile(r"\d{9}_(.+?)_(?i:standardcharges|standard-charges)")
_EIN_DASH_SLUG_RE = re.compile(r"\d{2}-\d{7}_(.+?)_(?i:standardcharges|standard-charges)")
_STD_SUFFIX_RE = re.compile(r"[_-]?(?:standardcharges|standard[_-]charges)$", re.IGNORECASE)


def _extract_slug(url: str) -> str | None:
    """Extract hospital-name slug from URL, supporting all three URL patterns."""
    basename = re.sub(r".*/", "", url.split("?", 1)[0])

    # Pattern 1: plain 9-digit EIN prefix
    m = _EIN9_SLUG_RE.search(basename)
    if m:
        return m.group(1)

    # Pattern 2: formatted EIN (XX-XXXXXXX)
    m = _EIN_DASH_SLUG_RE.search(basename)
    if m:
        return m.group(1)

    # Pattern 3: no EIN — use filename stem, stripping standardcharges suffix if present
    stem = Path(basename).stem
    # Strip double-extension (.xlsx → already gone; .json.gz → strip .json)
    if stem.endswith(".json") or stem.endswith(".csv"):
        stem = Path(stem).stem
    stem = _STD_SUFFIX_RE.sub("", stem).strip("-_")
    return stem if stem else None


def _bq_query_json(sql: str, location: str | None = None, max_rows: int = 200000) -> list[dict]:
    args = [
        "bq", "query",
        "--use_legacy_sql=false",
        "--format=json",
        f"--max_rows={max_rows}",
    ]
    if location:
        args.append(f"--location={location}")
    args.append(sql)
    proc = subprocess.run(args, capture_output=True, text=True, check=True)
    return json.loads(proc.stdout) if proc.stdout.strip() else []


def fetch_target_urls() -> list[tuple[str, str]]:
    """Return [(url, slug), ...] for all no-NPI failed archive rows."""
    sql = f"""
    SELECT DISTINCT source_mrf_url AS url
    FROM `{PROJECT}.{DATASET}.mrf_archive_index`
    WHERE parse_status = 'failed'
      AND parse_error = '{_PARSE_ERROR}'
      AND source_mrf_url IS NOT NULL
    """
    logger.info("Querying no-NPI failed rows from mrf_archive_index...")
    rows = _bq_query_json(sql)
    out = []
    for row in rows:
        url = row.get("url", "")
        slug = _extract_slug(url)
        if slug:
            out.append((url, slug))
        else:
            logger.debug("Could not extract slug from: %s", url)
    logger.info("Found %d target URLs with extractable slugs (of %d total)", len(out), len(rows))
    return out


def fetch_nppes_hospitals() -> list[tuple[str, str]]:
    """Return [(npi, legal_name), ...] of all active hospital-taxonomy NPIs."""
    sql = f"""
    SELECT npi, provider_organization_name_legal_business_name AS name
    FROM `{NPPES_TABLE}`
    WHERE entity_type_code = 2
      AND npi_deactivation_date IS NULL
      AND provider_organization_name_legal_business_name IS NOT NULL
      AND (
        STARTS_WITH(healthcare_provider_taxonomy_code_1, "{HOSPITAL_TAXONOMY_PREFIX}")
        OR STARTS_WITH(healthcare_provider_taxonomy_code_2, "{HOSPITAL_TAXONOMY_PREFIX}")
        OR STARTS_WITH(healthcare_provider_taxonomy_code_3, "{HOSPITAL_TAXONOMY_PREFIX}")
      )
    """
    logger.info("Querying NPPES hospital subset (cross-region US, ~30s)...")
    rows = _bq_query_json(sql, location="US", max_rows=200000)
    out = [(str(r["npi"]), str(r["name"])) for r in rows if r.get("npi") and r.get("name")]
    logger.info("Loaded %d hospital-taxonomy NPIs from NPPES", len(out))
    return out


def score_match(slug_tokens: frozenset[str], name_tokens: frozenset[str]) -> tuple[int, float]:
    if not slug_tokens or not name_tokens:
        return 0, 0.0
    shared = slug_tokens & name_tokens
    union = slug_tokens | name_tokens
    return len(shared), len(shared) / len(union) if union else 0.0


def _build_token_frequency(nppes_pre: list[tuple[str, str, frozenset[str]]]) -> dict[str, int]:
    freq: dict[str, int] = {}
    for _, _, tokens in nppes_pre:
        for t in tokens:
            freq[t] = freq.get(t, 0) + 1
    return freq


def resolve(
    urls: list[tuple[str, str]],
    nppes: list[tuple[str, str]],
    min_score: float,
    min_margin: float,
    rare_token_threshold: int = 5,
) -> tuple[list[Match], list[tuple[str, str, float, float]]]:
    nppes_pre = [(npi, name, _tokenize(name)) for npi, name in nppes]
    token_freq = _build_token_frequency(nppes_pre)
    accepted: list[Match] = []
    rejected: list[tuple[str, str, float, float]] = []

    for url, slug in urls:
        slug_tokens = _tokenize(slug)
        if not slug_tokens:
            rejected.append((url, "<empty slug after tokenize>", 0.0, 0.0))
            continue

        scored: list[tuple[int, float, int, str, str]] = []
        for npi, name, name_tokens in nppes_pre:
            if slug_tokens.isdisjoint(name_tokens):
                continue
            shared, score = score_match(slug_tokens, name_tokens)
            looks_canonical = 0 if any(h in name.upper() for h in _NON_HOSPITAL_NAME_HINTS) else 1
            scored.append((shared, score, looks_canonical, npi, name))

        if not scored:
            rejected.append((url, "<no NPPES candidate shares any token>", 0.0, 0.0))
            continue

        scored.sort(key=lambda x: (-x[0], -x[1], -x[2], len(x[4])))
        best_shared, best_score, _, best_npi, best_name = scored[0]

        runner_up_score = 0.0
        for s in scored[1:]:
            if s[1] < best_score:
                runner_up_score = s[1]
                break
        margin = best_score - runner_up_score

        unambiguous_perfect = best_score >= 0.999

        if not unambiguous_perfect and (best_score < min_score or margin < min_margin):
            rejected.append((url, best_name, best_score, margin))
            continue

        if best_shared < 2:
            best_name_tokens = _tokenize(best_name)
            shared_tokens = slug_tokens & best_name_tokens
            if not shared_tokens:
                rejected.append((url, best_name, best_score, margin))
                continue
            rarest = min(token_freq.get(t, 999_999) for t in shared_tokens)
            if rarest > rare_token_threshold:
                rejected.append((url, f"{best_name} (token too common: freq={rarest})", best_score, margin))
                continue

        accepted.append(Match(
            url=url, slug=slug, npi=best_npi, name=best_name,
            shared_words=best_shared, score=best_score, margin=margin,
        ))

    return accepted, rejected


def apply_matches(matches: list[Match]) -> int:
    """Write NPI and reset parse_status to pending in mrf_archive_index.

    Returns the number of archive rows updated.
    """
    if not matches:
        return 0

    def _esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    pairs = ",\n      ".join(
        f'STRUCT("{_esc(m.url)}" AS url, "{_esc(m.npi)}" AS npi)' for m in matches
    )

    sql = f"""
    UPDATE `{PROJECT}.{DATASET}.mrf_archive_index` mai
    SET hospital_npi = t.npi,
        parse_status = 'pending',
        parse_error   = NULL
    FROM (SELECT * FROM UNNEST([
      {pairs}
    ])) t
    WHERE t.url = mai.source_mrf_url
      AND mai.parse_status = 'failed'
    """

    proc = subprocess.run(
        ["bq", "query", "--use_legacy_sql=false", "--format=json", sql],
        capture_output=True, text=True, check=True,
    )
    m = re.search(r"Number of affected rows:\s+(\d+)", proc.stdout + proc.stderr)
    updated = int(m.group(1)) if m else 0
    return updated


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="Write resolutions to BQ; default is dry-run.")
    ap.add_argument("--min-score", type=float, default=0.5,
                    help="Min Jaccard score for acceptance (default 0.5).")
    ap.add_argument("--min-margin", type=float, default=0.1,
                    help="Min score gap to runner-up (default 0.1).")
    ap.add_argument("--show", type=int, default=25,
                    help="Sample rows to print from accepted and rejected.")
    args = ap.parse_args()

    urls = fetch_target_urls()
    if not urls:
        logger.info("No target URLs found. Nothing to do.")
        return 0

    nppes = fetch_nppes_hospitals()
    accepted, rejected = resolve(urls, nppes, args.min_score, args.min_margin)

    logger.info(
        "RESULTS: %d accepted, %d rejected (of %d URLs with slugs)",
        len(accepted), len(rejected), len(urls),
    )

    print(f"\n=== ACCEPTED ({len(accepted)} total, showing {min(args.show, len(accepted))}) ===")
    for m in accepted[: args.show]:
        print(f"  npi={m.npi}  score={m.score:.2f}  margin={m.margin:.2f}  "
              f"slug={m.slug!r}  -> {m.name!r}")

    print(f"\n=== REJECTED ({len(rejected)} total, showing {min(args.show, len(rejected))}) ===")
    for url, name, score, margin in rejected[: args.show]:
        slug = _extract_slug(url) or "<no slug>"
        print(f"  score={score:.2f}  margin={margin:.2f}  slug={slug!r}  best={name!r}")

    if args.apply:
        if not accepted:
            logger.info("No accepted matches — nothing to apply.")
            return 0
        updated = apply_matches(accepted)
        logger.info("APPLIED: %d mrf_archive_index rows updated to pending", updated)
    else:
        logger.info("Dry run. Re-run with --apply to write changes and reset to pending.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
