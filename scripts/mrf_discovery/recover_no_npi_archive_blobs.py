"""Resolve NPI for mrf_archive_index rows that failed with 'no NPI resolvable'.

Background
----------
After the 2026-05-05 recovery run, ~5,510 blobs remain in mrf_archive_index
with parse_status='failed' and parse_error='no NPI resolvable from JSON root,
URL, or scraper metadata'. These blobs never produced hospital_charges rows, so
resolve_ambiguous_npis.py (which sources from hospital_charges) cannot fix them.

URL breakdown:
  - 5,439: 9-digit EIN in filename (e.g. 941196203_st-mary_standardcharges.json)
  - 71:    formatted EIN XX-XXXXXXX (e.g. 62-1383977_hospital_standardcharges.json)
  - 967:   no numeric EIN (Ascension/Providence XLSX with hospital-name slug only)

Accuracy requirement
--------------------
A wrong NPI means we show a patient the wrong hospital's prices. This must be
zero-tolerance. The algorithm therefore uses two strict tiers:

Tier 1 — EIN direct lookup (for URLs that contain an EIN in the filename):
  The EIN is a federal tax ID. NPPES stores the EIN on each NPI record. If
  exactly one hospital NPI in NPPES has this EIN, that assignment is definitive
  with no ambiguity. If multiple NPIs share the EIN (a health system filing
  under a parent EIN), we accept only if exactly one of those NPIs achieves a
  perfect slug-name match (score=1.00) — i.e. the slug uniquely identifies one
  member of the health-system group.

Tier 2 — Strict name match (for no-EIN URLs, or EIN not found in NPPES):
  Accept only if:
    (a) score=1.00: the slug tokens EXACTLY equal the NPPES name tokens after
        stopword removal (Jaccard = 1.0, no missing or extra words on either
        side). Partial matches (0.67, 0.75, …) are rejected because we have no
        geographic constraint to distinguish "MERCY HOSPITAL — Merced" from
        "MERCY HOSPITAL — Springfield".
    (b) Globally unique: no other hospital in all of NPPES achieves score=1.00
        for this slug. Two NPPES entries named "ST MARY HOSPITAL" in different
        states both score 1.00 — we cannot tell which one the slug means, so
        both are rejected.
    (c) margin >= min_margin vs the runner-up score (extra safety net for cases
        where the name-token set is a subset of a longer NPPES name).

Anything that does not pass its tier's criteria stays unresolved. Leaving a
row without an NPI is always preferable to assigning a wrong one.

--- Running ---
  python scripts/mrf_discovery/recover_no_npi_archive_blobs.py --dry-run
  python scripts/mrf_discovery/recover_no_npi_archive_blobs.py --apply
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
    "llc", "lp", "llp", "plc", "pllc", "pa", "pc",
    "corp", "company", "co", "ltd",
})

_NON_HOSPITAL_NAME_HINTS = (
    "PHARMACY", "CLINIC", "PHYSICIANS", "PHYSICIAN GROUP", " GROUP",
    "MEDICAL GROUP", "PRACTICE", "ASSOCIATES", "OUTPATIENT", "URGENT CARE",
    "AMBULATORY", "SURGERY CENTER", "IMAGING",
)

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

# EIN patterns in MRF filenames — must be at the start of the basename.
_EIN9_SLUG_RE = re.compile(r"^(\d{9})_")
_EIN_DASH_RE = re.compile(r"^(\d{2})-(\d{7})_")

# Slug extraction for EIN-based filenames and plain-name filenames.
_EIN9_SLUG_CAPTURE = re.compile(r"\d{9}_(.+?)_(?i:standardcharges|standard-charges)")
_EIN_DASH_SLUG_CAPTURE = re.compile(r"\d{2}-\d{7}_(.+?)_(?i:standardcharges|standard-charges)")
_STD_SUFFIX_RE = re.compile(r"[_-]?(?:standardcharges|standard[_-]charges)$", re.IGNORECASE)


@dataclass(frozen=True)
class Match:
    url: str
    slug: str
    npi: str
    name: str
    resolution: str  # "ein_unique" | "ein_name" | "name_unique"
    score: float


def _tokenize(text: str) -> frozenset[str]:
    spaced = _CAMEL_BOUNDARY.sub(" ", text)
    return frozenset(
        w for w in re.split(r"[^a-z0-9]+", spaced.lower())
        if len(w) > 1 and w not in _STOPWORDS
    )


def _extract_ein_normalized(url: str) -> str | None:
    """Return a 9-digit EIN (no dashes) if one is present at the start of the filename."""
    basename = re.sub(r".*/", "", url.split("?", 1)[0])
    m = _EIN9_SLUG_RE.match(basename)
    if m:
        return m.group(1)
    m = _EIN_DASH_RE.match(basename)
    if m:
        return m.group(1) + m.group(2)
    return None


def _extract_slug(url: str) -> str | None:
    """Extract hospital-name slug from URL, supporting all three URL patterns."""
    basename = re.sub(r".*/", "", url.split("?", 1)[0])

    m = _EIN9_SLUG_CAPTURE.search(basename)
    if m:
        return m.group(1)

    m = _EIN_DASH_SLUG_CAPTURE.search(basename)
    if m:
        return m.group(1)

    # No-EIN: use filename stem, stripping standardcharges suffix if present.
    stem = Path(basename).stem
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


def fetch_target_urls() -> list[tuple[str, str, str | None]]:
    """Return [(url, slug, ein_or_None), ...] for all no-NPI failed archive rows."""
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
    skipped = 0
    for row in rows:
        url = row.get("url", "")
        slug = _extract_slug(url)
        if slug:
            ein = _extract_ein_normalized(url)
            out.append((url, slug, ein))
        else:
            skipped += 1
    logger.info(
        "Found %d target URLs with extractable slugs (%d skipped, no slug)",
        len(out), skipped,
    )
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


def fetch_nppes_by_eins(eins: set[str]) -> dict[str, list[tuple[str, str]]]:
    """Return {ein_9digit: [(npi, name), ...]} for hospital NPIs matching these EINs.

    NPPES may store the EIN as '9digits' or 'XX-XXXXXXX'; we query both forms
    and normalise results back to 9-digit keys.
    """
    if not eins:
        return {}
    formatted = {f"{e[:2]}-{e[2:]}" for e in eins}
    all_forms = eins | formatted
    ein_list = ", ".join(f'"{e}"' for e in sorted(all_forms))
    sql = f"""
    SELECT
      REGEXP_REPLACE(employer_identification_number_ein, r'-', '') AS ein,
      npi,
      provider_organization_name_legal_business_name AS name
    FROM `{NPPES_TABLE}`
    WHERE entity_type_code = 2
      AND npi_deactivation_date IS NULL
      AND employer_identification_number_ein IN ({ein_list})
      AND provider_organization_name_legal_business_name IS NOT NULL
      AND (
        STARTS_WITH(healthcare_provider_taxonomy_code_1, "{HOSPITAL_TAXONOMY_PREFIX}")
        OR STARTS_WITH(healthcare_provider_taxonomy_code_2, "{HOSPITAL_TAXONOMY_PREFIX}")
        OR STARTS_WITH(healthcare_provider_taxonomy_code_3, "{HOSPITAL_TAXONOMY_PREFIX}")
      )
    """
    logger.info("Querying NPPES by %d EINs...", len(eins))
    rows = _bq_query_json(sql, max_rows=50000)
    result: dict[str, list[tuple[str, str]]] = {}
    for row in rows:
        ein = (row.get("ein") or "").replace("-", "")
        npi = str(row.get("npi", ""))
        name = str(row.get("name", ""))
        if ein and npi and name:
            result.setdefault(ein, []).append((npi, name))
    logger.info("EIN lookup: %d EINs found in NPPES (of %d queried)", len(result), len(eins))
    return result


def _score_jaccard(slug_tokens: frozenset[str], name_tokens: frozenset[str]) -> float:
    if not slug_tokens or not name_tokens:
        return 0.0
    shared = slug_tokens & name_tokens
    union = slug_tokens | name_tokens
    return len(shared) / len(union)


def resolve(
    urls: list[tuple[str, str, str | None]],
    nppes: list[tuple[str, str]],
    nppes_by_ein: dict[str, list[tuple[str, str]]],
    min_margin: float,
) -> tuple[list[Match], list[tuple[str, str, str]]]:
    """Two-tier resolution. Returns (accepted_matches, rejected_reasons).

    rejected_reasons entries are (url, slug, reason_string).
    """
    # Pre-tokenize entire NPPES corpus once and build token frequency index.
    nppes_pre: list[tuple[str, str, frozenset[str]]] = [
        (npi, name, _tokenize(name)) for npi, name in nppes
    ]
    # token_freq[t] = number of distinct NPPES hospital names containing token t.
    # Used to reject single-token slug matches where the token is too generic
    # to identify a specific facility (e.g. "mercy" appears in 200+ names even
    # though "MERCY HEALTH" is the only name that REDUCES to just {mercy} after
    # stopwords — the uniqueness is an artifact of stopword removal, not a
    # genuine identifier).
    token_freq: dict[str, int] = {}
    for _, _, toks in nppes_pre:
        for t in toks:
            token_freq[t] = token_freq.get(t, 0) + 1

    accepted: list[Match] = []
    rejected: list[tuple[str, str, str]] = []

    for url, slug, ein in urls:
        slug_tokens = _tokenize(slug)
        if not slug_tokens:
            rejected.append((url, slug, "empty token set after stopword removal"))
            continue

        # ------------------------------------------------------------------
        # Tier 1: EIN direct lookup
        # ------------------------------------------------------------------
        if ein:
            candidates = nppes_by_ein.get(ein, [])

            if len(candidates) == 1:
                # Unique EIN → definitive, no name-match ambiguity possible.
                npi, name = candidates[0]
                accepted.append(Match(url=url, slug=slug, npi=npi, name=name,
                                      resolution="ein_unique", score=2.0))
                continue

            if len(candidates) > 1:
                # EIN shared by a health system. Pick the member hospital whose
                # name best matches the slug — but only if the match is perfect
                # AND unique within the candidate set.
                perfect: list[tuple[str, str]] = []
                for npi, name in candidates:
                    name_tokens = _tokenize(name)
                    score = _score_jaccard(slug_tokens, name_tokens)
                    if score >= 0.999:
                        perfect.append((npi, name))

                if len(perfect) == 1:
                    npi, name = perfect[0]
                    accepted.append(Match(url=url, slug=slug, npi=npi, name=name,
                                          resolution="ein_name", score=1.0))
                    continue

                if len(perfect) > 1:
                    rejected.append((url, slug,
                        f"EIN {ein}: {len(perfect)} candidates with perfect name match "
                        f"(ambiguous health-system EIN)"))
                else:
                    rejected.append((url, slug,
                        f"EIN {ein}: {len(candidates)} EIN candidates, none with "
                        f"score=1.00 name match"))
                continue

            # EIN not found in NPPES — fall through to Tier 2.

        # ------------------------------------------------------------------
        # Tier 2: Strict name match
        # Accepts only: score=1.00 AND globally unique name in NPPES corpus.
        # ------------------------------------------------------------------
        perfect_matches: list[tuple[str, str]] = []
        best_non_perfect_score: float = 0.0

        for npi, name, name_tokens in nppes_pre:
            if slug_tokens.isdisjoint(name_tokens):
                continue
            score = _score_jaccard(slug_tokens, name_tokens)
            if score >= 0.999:
                perfect_matches.append((npi, name))
            elif score > best_non_perfect_score:
                best_non_perfect_score = score

        if not perfect_matches:
            rejected.append((url, slug,
                f"no score=1.00 name match (best partial: {best_non_perfect_score:.2f})"))
            continue

        # Deduplicate by name — multiple NPPES rows for the same legal name
        # (e.g., parent org + branches) all count as ONE unique hospital.
        unique_names: dict[str, str] = {}  # normalised_name → npi (take first)
        for npi, name in perfect_matches:
            key = " ".join(sorted(_tokenize(name)))  # canonical key
            if key not in unique_names:
                unique_names[key] = npi

        if len(unique_names) > 1:
            names_found = [name for _, name in perfect_matches[:3]]
            rejected.append((url, slug,
                f"{len(unique_names)} distinct NPPES hospitals score 1.00 "
                f"(geographic ambiguity): {names_found}"))
            continue

        # Single-token safety: a slug that reduces to exactly one meaningful
        # word is only a safe identifier when that word is rare in the NPPES
        # corpus. "mercy" appears in 200+ hospital names — the uniqueness of
        # "MERCY HEALTH" (the only name that REDUCES to {mercy} after stopwords)
        # is an artefact of stopword removal, not a genuine facility identifier.
        # This is different from "gouverneur" or "rumford" which each appear in
        # only 1-2 NPPES names and genuinely identify a single hospital.
        if len(slug_tokens) == 1:
            sole_token = next(iter(slug_tokens))
            freq = token_freq.get(sole_token, 0)
            if freq > 5:
                rejected.append((url, slug,
                    f"single-token slug '{sole_token}' is too generic "
                    f"(appears in {freq} NPPES hospital names)"))
                continue

        # Unique perfect match. Also verify margin vs the best non-perfect
        # runner-up — guards against edge cases where the 1.00 match is a
        # subset of a slightly different name that also almost scores perfectly.
        margin = 1.0 - best_non_perfect_score
        if margin < min_margin:
            rejected.append((url, slug,
                f"score=1.00 unique name but margin {margin:.2f} < {min_margin} "
                f"vs runner-up {best_non_perfect_score:.2f}"))
            continue

        best_npi = next(iter(unique_names.values()))
        best_name = next(n for _, n in perfect_matches if _score_jaccard(slug_tokens, _tokenize(n)) >= 0.999)
        accepted.append(Match(url=url, slug=slug, npi=best_npi, name=best_name,
                               resolution="name_unique", score=1.0))

    return accepted, rejected


def apply_matches(matches: list[Match]) -> int:
    """Write NPI and reset parse_status to pending in mrf_archive_index."""
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
    return int(m.group(1)) if m else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="Write resolutions to BQ; default is dry-run.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Preview matches without writing (default; explicit flag for clarity).")
    ap.add_argument("--min-margin", type=float, default=0.1,
                    help="Min score gap between score=1.00 and runner-up (Tier 2 only, default 0.1).")
    ap.add_argument("--show", type=int, default=25,
                    help="Sample rows to print.")
    args = ap.parse_args()

    urls = fetch_target_urls()
    if not urls:
        logger.info("No target URLs found.")
        return 0

    eins_present = {ein for _, _, ein in urls if ein}
    nppes_by_ein = fetch_nppes_by_eins(eins_present)
    nppes = fetch_nppes_hospitals()

    accepted, rejected = resolve(urls, nppes, nppes_by_ein, args.min_margin)

    ein_unique = sum(1 for m in accepted if m.resolution == "ein_unique")
    ein_name   = sum(1 for m in accepted if m.resolution == "ein_name")
    name_only  = sum(1 for m in accepted if m.resolution == "name_unique")

    logger.info(
        "RESULTS: %d accepted (EIN-unique=%d, EIN+name=%d, name-unique=%d), "
        "%d rejected (of %d URLs)",
        len(accepted), ein_unique, ein_name, name_only, len(rejected), len(urls),
    )

    print(f"\n=== ACCEPTED ({len(accepted)} total, showing {min(args.show, len(accepted))}) ===")
    for m in accepted[: args.show]:
        print(f"  [{m.resolution}]  npi={m.npi}  slug={m.slug!r}  -> {m.name!r}")

    print(f"\n=== REJECTED ({len(rejected)} total, showing {min(args.show, len(rejected))}) ===")
    for url, slug, reason in rejected[: args.show]:
        print(f"  slug={slug!r}  reason={reason}")

    if args.apply:
        if not accepted:
            logger.info("No accepted matches — nothing to apply.")
            return 0
        updated = apply_matches(accepted)
        logger.info("APPLIED: %d mrf_archive_index rows updated to pending", updated)
    else:
        logger.info("Dry run. Re-run with --apply to write changes.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
