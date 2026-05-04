"""Resolve ambiguous EIN-only MRF URLs to hospital NPIs via NPPES name match.

Background
----------
The 5/3-5/4 parser run + 2026-05-04 backfill recovered 44.7M hospital_charges
rows but left 605.7M still NULL on hospital_npi. Of those, 499.7M come from
158 distinct URLs whose filenames embed a 9-digit EIN (parent-org tax ID) but
no NPI, AND whose entries in `hospital_directory.mrf_url` have multiple
candidate NPIs because the discovery process associated the same MRF URL
with many hospitals.

Examples of ambiguous URLs:
  https://www.dignityhealth.org/.../941196203_st-mary-medical-center-long-beach_standardcharges.json
  https://pricetransparency.providence.org/.../951675600_providence-st-joseph-medical-center_standardcharges.json
  https://www.christushealth.org/.../760591590_christushealthwestbeaumont_standardcharges.ashx

Approach
--------
The directory table is corrupted on these URLs (wrong NPIs assigned during
discovery), so directory-side disambiguation produces garbage. NPPES is the
authoritative ground truth: every hospital NPI registered in the US is in
`bigquery-public-data.nppes.npi_raw` with its legal organization name and
hospital taxonomy.

For each ambiguous URL we:
  1. Extract the filename slug (e.g., "st-mary-medical-center-long-beach")
  2. Tokenize and normalize (drop dashes, lowercase, drop stopwords)
  3. Score every hospital-taxonomy NPPES org name by word-overlap against
     the slug tokens.
  4. Take the top-1 match if score >= MIN_SCORE AND it has a meaningful
     margin over the runner-up (so genuinely ambiguous slugs like
     "saint-marys-hospital" don't get assigned blindly).

Why a separate script vs adding to the parser
---------------------------------------------
This is a one-time data backfill, not a steady-state pipeline step. Future
parser runs benefit from the existing URL-NPI fallback (commit cb9b420);
this script just cleans up the historical archive.

--- Running ---
  python scripts/mrf_discovery/resolve_ambiguous_npis.py --dry-run     # preview
  python scripts/mrf_discovery/resolve_ambiguous_npis.py --apply       # write
  python scripts/mrf_discovery/resolve_ambiguous_npis.py --min-score 0.7 --min-margin 0.2
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PROJECT = "clarobill-prd"
DATASET = "hospital_prices"
NPPES_TABLE = "bigquery-public-data.nppes.npi_raw"

# Hospital taxonomy codes — the "28*" prefix covers acute care, specialty,
# psychiatric, long-term care, and military hospitals. We also include 283*
# even though some 283* codes are nursing facilities — the name match has
# to do most of the lifting either way.
HOSPITAL_TAXONOMY_PREFIX = "28"

# Words to drop from slug + name before scoring. These appear in nearly every
# hospital name and add zero discriminative power; including them inflates
# scores for unrelated matches (e.g., "hospital" in slug matches every NPPES row).
_STOPWORDS = frozenset({
    "the", "of", "and", "a", "at", "for", "in", "on", "an",
    "hospital", "medical", "health", "healthcare", "center", "centre",
    "campus", "facility", "system", "services", "incorporated", "inc",
    "llc", "corp", "company", "co", "ltd",
})

# When NPPES has multiple rows scoring identically for the same slug, we
# prefer the one whose legal name does not look like a pharmacy / clinic /
# physician group. The taxonomy filter catches most non-hospital entities
# but NPPES data has known mislabeling (we observed 'X HOSPITAL PHARMACY'
# rows under hospital taxonomies). This is a tiebreaker only — if the
# canonical hospital isn't in NPPES we'd rather have no match than the
# pharmacy NPI.
_NON_HOSPITAL_NAME_HINTS = (
    "PHARMACY", "CLINIC", "PHYSICIANS", "PHYSICIAN GROUP", " GROUP",
    "MEDICAL GROUP", "PRACTICE", "ASSOCIATES", "OUTPATIENT", "URGENT CARE",
    "AMBULATORY", "SURGERY CENTER", "IMAGING",
)


@dataclass(frozen=True)
class Match:
    """Top-1 NPPES candidate for an ambiguous URL.

    score is shared_words / max(slug_word_count, name_word_count) — a
    Jaccard-style ratio that penalises both missing words and extra words.
    margin is score - second_best_score; high margin means the match is
    unambiguous, low margin means multiple candidates scored similarly.
    """

    url: str
    slug: str
    npi: str
    name: str
    shared_words: int
    score: float
    margin: float


_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def _tokenize(text: str) -> frozenset[str]:
    """Lowercase, split on non-alphanumerics + camelCase, drop stopwords.

    Many MRF URL slugs are camelCase with no separators
    (e.g., `ShastaRegionalMedicalCenter`, `SaintMaryOfNazarethHospital`).
    Splitting on word boundaries first turns these into proper tokens
    before the lowercase/stopword pass.
    """
    spaced = _CAMEL_BOUNDARY.sub(" ", text)
    return frozenset(
        w for w in re.split(r"[^a-z0-9]+", spaced.lower())
        if len(w) > 1 and w not in _STOPWORDS
    )


def _extract_slug(url: str) -> str | None:
    """Pull the hospital-name slug from an MRF filename.

    Pattern: `{9-digit-EIN}_{slug}_standardcharges.{ext}` (case-insensitive
    on `standardcharges`). Returns the slug or None if the filename does not
    follow this pattern.
    """
    basename = re.sub(r".*/", "", url.split("?", 1)[0])
    m = re.search(r"\d{9}_(.+?)_(?i:standardcharges|standard-charges)", basename)
    return m.group(1) if m else None


def _bq_query_json(sql: str, location: str | None = None, max_rows: int = 100000) -> list[dict]:
    """Run a SQL query via the `bq` CLI and return rows as a list of dicts.

    Uses the gcloud user credentials (no ADC dependency). `location` is
    needed when querying public datasets in a different multi-region
    (e.g. NPPES is `US`; our project is `us-central1`).
    """
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


def fetch_ambiguous_urls() -> list[tuple[str, str]]:
    """Return [(url, slug), ...] for the EIN-only ambiguous URLs."""
    sql = f"""
    SELECT DISTINCT source_mrf_url AS url
    FROM `{PROJECT}.{DATASET}.hospital_charges`
    WHERE (hospital_npi IS NULL OR hospital_npi = "")
      AND source_mrf_url IS NOT NULL
      AND REGEXP_EXTRACT(REGEXP_REPLACE(SPLIT(source_mrf_url, "?")[OFFSET(0)], r".*/", ""), r"(?:^|\\D)(\\d{{10}})(?:\\D|$)") IS NULL
      AND REGEXP_EXTRACT(REGEXP_REPLACE(SPLIT(source_mrf_url, "?")[OFFSET(0)], r".*/", ""), r"(?:^|\\D)(\\d{{9}})(?:\\D|$)") IS NOT NULL
    """
    logger.info("Querying ambiguous EIN-only URLs from hospital_charges...")
    rows = _bq_query_json(sql)
    out = []
    for row in rows:
        slug = _extract_slug(row["url"])
        if slug:
            out.append((row["url"], slug))
    logger.info("Found %d ambiguous URLs with extractable slugs", len(out))
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
    logger.info("Querying NPPES hospital subset (cross-region US, may take ~30s)...")
    rows = _bq_query_json(sql, location="US", max_rows=200000)
    out = [(str(r["npi"]), str(r["name"])) for r in rows if r.get("npi") and r.get("name")]
    logger.info("Loaded %d hospital-taxonomy NPIs from NPPES", len(out))
    return out


def score_match(slug_tokens: frozenset[str], name_tokens: frozenset[str]) -> tuple[int, float]:
    """Word-overlap score between slug and NPPES name.

    Returns (shared_word_count, jaccard_score). Jaccard = |shared| / |union|.
    Empty token sets yield (0, 0.0).
    """
    if not slug_tokens or not name_tokens:
        return 0, 0.0
    shared = slug_tokens & name_tokens
    union = slug_tokens | name_tokens
    return len(shared), len(shared) / len(union) if union else 0.0


def _build_token_frequency(nppes_pre: list[tuple[str, str, frozenset[str]]]) -> dict[str, int]:
    """Count, for each token, how many NPPES hospital names contain it.

    Used to reject single-token matches where the lone shared token is too
    generic to be a reliable identifier — e.g. 'mercy' appears in 100+
    hospital names, so 'mercy-hospital' matching 'MERCY HEALTH' is not a
    safe identification. Rare tokens (e.g. 'heywood', 'pelham') do uniquely
    identify a hospital and should not be rejected.
    """
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
    """For each URL, find the best NPPES match.

    Returns (accepted_matches, rejected) where rejected is the URLs that
    failed either threshold. Rejected entries record (url, top_name,
    top_score, margin) so we can spot-check why they failed.

    Acceptance rules:
      - score >= min_score AND margin >= min_margin (the standard path), OR
      - score == 1.0 (perfect token-set equality post-stopword)
    AND in either case:
      - shared_words >= 2, OR
      - shared_words == 1 AND that shared token appears in <= rare_token_threshold
        NPPES names (i.e., is uniquely identifying)
    """
    nppes_pre = [(npi, name, _tokenize(name)) for npi, name in nppes]
    token_freq = _build_token_frequency(nppes_pre)
    accepted: list[Match] = []
    rejected: list[tuple[str, str, float, float]] = []

    for url, slug in urls:
        slug_tokens = _tokenize(slug)
        if not slug_tokens:
            rejected.append((url, "<empty slug after tokenize>", 0.0, 0.0))
            continue

        # Score every NPPES candidate; rank by (shared_count desc, score desc,
        # is-canonical-hospital-name desc, shorter-name desc). The
        # canonical-hospital tiebreak prefers e.g. "X HOSPITAL" over
        # "X HOSPITAL PHARMACY" when both score identically.
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
        # Compute margin against the next candidate that scored *differently*.
        # When NPPES has multiple identically-named rows for the same hospital
        # (parent + branches), they all score 1.0 and naive margin is 0 even
        # though picking any of them is correct. Skip past identical-score
        # rows to find the real runner-up.
        runner_up_score = 0.0
        for s in scored[1:]:
            if s[1] < best_score:
                runner_up_score = s[1]
                break
        margin = best_score - runner_up_score

        # Perfect-content match (score == 1.0) means the slug words exactly
        # equal the NPPES name words after stopword removal — that's an
        # unambiguous identification of the hospital. Accept regardless of
        # margin; the tiebreak above already preferred the canonical row.
        unambiguous_perfect = best_score >= 0.999

        if not unambiguous_perfect and (best_score < min_score or margin < min_margin):
            rejected.append((url, best_name, best_score, margin))
            continue

        # Single-token-match safety: a 1-word match is only safe when that
        # word is rare in NPPES. 'mercy', 'methodist', 'community' appear in
        # hundreds of names; 'pelham', 'heywood', 'kadlec' uniquely identify
        # a single hospital.
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


def apply_matches(matches: list[Match]) -> tuple[int, int]:
    """Write accepted matches back to hospital_charges + mrf_archive_index.

    Inlines the (url, npi) pairs into a CTE rather than using a load job —
    158 rows is small enough to fit in a single SQL string and avoids the
    extra GCS staging hop.

    Returns (charge_rows_updated, archive_rows_updated).
    """
    if not matches:
        return 0, 0

    # Inline (url, npi) STRUCT array. SQL string-escape: just escape backslashes
    # and double quotes — every URL/NPI we have is well-formed.
    def _esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    pairs = ",\n      ".join(
        f'STRUCT("{_esc(m.url)}" AS url, "{_esc(m.npi)}" AS npi)' for m in matches
    )

    update_charges = f"""
    UPDATE `{PROJECT}.{DATASET}.hospital_charges` hc
    SET hospital_npi = t.npi
    FROM (SELECT * FROM UNNEST([
      {pairs}
    ])) t
    WHERE t.url = hc.source_mrf_url
      AND (hc.hospital_npi IS NULL OR hc.hospital_npi = "")
    """
    update_archive = f"""
    UPDATE `{PROJECT}.{DATASET}.mrf_archive_index` mai
    SET hospital_npi = t.npi
    FROM (SELECT * FROM UNNEST([
      {pairs}
    ])) t
    WHERE t.url = mai.source_mrf_url
      AND (mai.hospital_npi IS NULL OR mai.hospital_npi = "")
    """

    def _run_dml(sql: str) -> int:
        proc = subprocess.run(
            ["bq", "query", "--use_legacy_sql=false", "--format=json", sql],
            capture_output=True, text=True, check=True,
        )
        # bq emits "Number of affected rows: N" to stdout for DML queries
        # even with --format=json (the JSON output is empty for DML).
        # Status messages go to stderr.
        m = re.search(r"Number of affected rows:\s+(\d+)", proc.stdout + proc.stderr)
        return int(m.group(1)) if m else 0

    charge_rows = _run_dml(update_charges)
    archive_rows = _run_dml(update_archive)
    return charge_rows, archive_rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="Write resolutions to BQ; default is dry-run.")
    ap.add_argument("--min-score", type=float, default=0.5,
                    help="Min Jaccard score for a match to be accepted (default 0.5).")
    ap.add_argument("--min-margin", type=float, default=0.1,
                    help="Min score gap between top-1 and runner-up (default 0.1).")
    ap.add_argument("--show", type=int, default=20, help="Sample size to print.")
    args = ap.parse_args()

    urls = fetch_ambiguous_urls()
    nppes = fetch_nppes_hospitals()
    accepted, rejected = resolve(urls, nppes, args.min_score, args.min_margin)

    logger.info("RESULTS: %d accepted, %d rejected (of %d URLs)",
                len(accepted), len(rejected), len(urls))

    print("\n=== ACCEPTED (top sample) ===")
    for m in accepted[: args.show]:
        print(f"  npi={m.npi}  score={m.score:.2f} margin={m.margin:.2f}  slug={m.slug!r}  -> {m.name!r}")

    print("\n=== REJECTED (top sample) ===")
    for url, name, score, margin in rejected[: args.show]:
        slug = _extract_slug(url) or "<no slug>"
        print(f"  score={score:.2f} margin={margin:.2f}  slug={slug!r}  best={name!r}")

    if args.apply:
        if not accepted:
            logger.info("No accepted matches; nothing to apply.")
            return 0
        charge_rows, archive_rows = apply_matches(accepted)
        logger.info("APPLIED: %d charge rows, %d archive_index rows updated",
                    charge_rows, archive_rows)
    else:
        logger.info("Dry run. Re-run with --apply to write changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
