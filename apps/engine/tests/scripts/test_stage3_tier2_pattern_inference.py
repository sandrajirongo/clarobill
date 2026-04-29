"""Unit tests for Stage 3 Tier 2 pattern-inference pure helpers."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from mrf_discovery.stage3_tier2_pattern_inference import (  # noqa: E402
    GENERIC_WORDS,
    TierTwoResult,
    candidate_urls,
    hospital_name_keywords,
    short_slug,
    slugify,
)


class TestSlugify:
    def test_basic(self):
        assert slugify("Mayo Clinic") == "mayoclinic"

    def test_with_apostrophe(self):
        assert slugify("Saint Vincent's") == "saintvincents"

    def test_with_punctuation(self):
        assert slugify("Mayo, Inc.") == "mayoinc"

    def test_uppercase(self):
        assert slugify("MAYO CLINIC") == "mayoclinic"

    def test_with_numbers(self):
        assert slugify("UF Health Shands") == "ufhealthshands"

    def test_empty(self):
        assert slugify("") == ""


class TestShortSlug:
    def test_drops_hospital(self):
        assert short_slug("Mayo Clinic Hospital") == "mayoclinic"

    def test_drops_medical_center(self):
        assert short_slug("Southeast Medical Center") == "southeast"

    def test_drops_health_system(self):
        assert short_slug("Mercy Health System") == "mercy"

    def test_keeps_distinctive_name(self):
        assert short_slug("Cleveland Clinic") == "clevelandclinic"

    def test_drops_at(self):
        assert short_slug("UCSF at Mission Bay") == "ucsfmissionbay"

    def test_punctuation_in_distinctive_name(self):
        assert short_slug("Saint Vincent's Hospital") == "saintvincents"


class TestCandidateUrls:
    def test_returns_multiple_patterns(self):
        urls = candidate_urls("Mayo Clinic Hospital")
        assert len(urls) >= 5
        # Most likely patterns first
        assert urls[0].endswith("mayoclinic.org") or urls[0].endswith("www.mayoclinic.org")

    def test_includes_short_and_full(self):
        urls = candidate_urls("Mayo Clinic Hospital")
        assert any("mayoclinic" in u for u in urls)
        assert any("mayoclinichospital" in u for u in urls)

    def test_dedupes(self):
        # Hospital where short_slug == slug — should not produce duplicates
        urls = candidate_urls("Cleveland")
        assert len(urls) == len(set(urls))

    def test_empty_name_returns_empty(self):
        assert candidate_urls("") == []
        assert candidate_urls("!!!") == []

    def test_short_slug_returns_empty(self):
        # Regression: Sandra's 2026-04-28 Tier 2 run crashed with
        # UnicodeError when a hospital with name "VA" or "St" (≤2 chars
        # after slugify) produced "https://.org" candidates. DNS labels
        # have a 1-char minimum and IDNA encoding rejects empty segments.
        assert candidate_urls("VA") == []
        assert candidate_urls("St") == []
        assert candidate_urls("a") == []

    def test_all_generic_words_produces_full_slug_only(self):
        # When all words are generic, short_slug returns "" but slugify
        # returns the concatenated full text. We use only the full slug;
        # the short-form patterns are skipped. URLs are well-formed DNS
        # labels that just won't match a real hospital — that's correct
        # behavior (the verification GET will reject them).
        out = candidate_urls("Hospital Inc")
        assert len(out) > 0
        # Only full-slug patterns should appear (no short_slug-derived ones)
        assert all("hospitalinc" in u for u in out)

    def test_no_malformed_urls_in_candidates(self):
        # Defense: every URL produced must have a non-empty hostname between
        # `https://` and the first `.`. Catches the Sandra-2026-04-28 bug
        # where a degenerate slug produced `https://.org`.
        for name in ("Hospital Inc", "Health System", "VA Medical Center"):
            for url in candidate_urls(name):
                # Strip protocol
                rest = url.removeprefix("https://").removeprefix("http://")
                # Hostname is everything before the first `/` (or whole rest)
                hostname = rest.split("/", 1)[0]
                # First label must be at least one char before any dot
                first_label = hostname.split(".", 1)[0]
                assert first_label, f"Empty first label in {url!r} for {name!r}"
                assert len(first_label) >= 1, f"Too-short label in {url!r}"


class TestHospitalNameKeywords:
    def test_drops_generics(self):
        out = hospital_name_keywords("Mayo Clinic Hospital")
        assert "HOSPITAL" not in out
        assert "MAYO" not in out  # too short (4 chars)

    def test_keeps_distinctive(self):
        out = hospital_name_keywords("Saint Vincent's Memorial Hospital")
        assert "VINCENT'S" in out

    def test_min_length_filter(self):
        # 4-character words like "MAYO" are filtered (too generic by length)
        out = hospital_name_keywords("Mayo Clinic")
        assert "MAYO" not in out
        assert "CLINIC" in out

    def test_custom_min_length(self):
        out = hospital_name_keywords("Mayo Clinic", min_word_len=4)
        assert "MAYO" in out


class TestGenericWords:
    def test_includes_common(self):
        for word in ("HOSPITAL", "MEDICAL", "CENTER", "HEALTH"):
            assert word in GENERIC_WORDS

    def test_excludes_distinctive(self):
        for word in ("MAYO", "CLEVELAND", "CEDARS"):
            assert word not in GENERIC_WORDS


class TestTierTwoResult:
    def test_namedtuple(self):
        r = TierTwoResult("010001", "https://x.com", "https://x.org", "ok")
        assert r.ccn == "010001"
        assert r.found_url == "https://x.com"
        assert r.rejection_summary == "ok"
