"""Unit tests for NppesClient match-selection logic.

The HTTP and rate-limit layers are exercised in integration tests; here we
test the city/taxonomy preference scoring that matters for false-positive
prevention.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from mrf_discovery.nppes_client import (  # noqa: E402
    HOSPITAL_TAXONOMY_PREFIXES,
    LookupResult,
    NppesClient,
)


def _result(npi: str, name: str, city: str, taxonomy_code: str = "282N00000X") -> dict:
    return {
        "number": npi,
        "basic": {"organization_name": name},
        "addresses": [
            {"address_purpose": "LOCATION", "city": city, "state": "AL"},
        ],
        "taxonomies": [{"code": taxonomy_code, "primary": True}],
    }


class TestCacheKey:
    def test_normalizes_to_uppercase(self):
        assert NppesClient.cache_key("Mayo Clinic", "mn", "Rochester") == "MAYO CLINIC|MN|ROCHESTER"

    def test_handles_missing_city(self):
        assert NppesClient.cache_key("Mayo Clinic", "MN") == "MAYO CLINIC|MN|"


class TestSelectBest:
    def test_returns_no_match_for_empty_results(self):
        out = NppesClient._select_best([], expected_city="Dothan")
        assert out == LookupResult(npi=None, legal_name=None, matched_via="no_match")

    def test_picks_city_and_taxonomy_match(self):
        results = [
            _result("1111111111", "WRONG CITY HOSPITAL", "Birmingham"),
            _result("2222222222", "RIGHT HOSPITAL", "Dothan"),
        ]
        out = NppesClient._select_best(results, expected_city="Dothan")
        assert out.npi == "2222222222"
        assert out.matched_via == "city_and_taxonomy"

    def test_falls_back_to_taxonomy_only_when_no_city(self):
        results = [_result("1111111111", "HOSP", "Wherever")]
        out = NppesClient._select_best(results, expected_city=None)
        assert out.npi == "1111111111"
        assert out.matched_via == "taxonomy_only"

    def test_falls_back_to_city_only_when_taxonomy_misses(self):
        # Some hospitals are mis-tagged with non-hospital taxonomies
        results = [_result("1111111111", "HOSP", "Dothan", taxonomy_code="207RC0000X")]
        out = NppesClient._select_best(results, expected_city="Dothan")
        assert out.npi == "1111111111"
        assert out.matched_via == "city_only"

    def test_falls_back_to_first_result_when_nothing_matches(self):
        results = [_result("1111111111", "HOSP", "Wherever", taxonomy_code="207RC0000X")]
        out = NppesClient._select_best(results, expected_city="Dothan")
        assert out.npi == "1111111111"
        assert out.matched_via == "first_result"

    def test_city_match_is_case_insensitive(self):
        results = [_result("1111111111", "HOSP", "DOTHAN")]
        out = NppesClient._select_best(results, expected_city="dothan")
        assert out.matched_via == "city_and_taxonomy"

    def test_picks_higher_scored_when_multiple_pass(self):
        # First result has city only (score 10); second has city + taxonomy (score 15).
        # Verify we pick the second.
        results = [
            _result("1111111111", "FIRST", "Dothan", taxonomy_code="207RC0000X"),
            _result("2222222222", "SECOND", "Dothan", taxonomy_code="282N00000X"),
        ]
        out = NppesClient._select_best(results, expected_city="Dothan")
        assert out.npi == "2222222222"
        assert out.matched_via == "city_and_taxonomy"


class TestTaxonomyPrefixes:
    def test_includes_acute_care(self):
        # 282N = General Acute Care Hospital
        assert any("282".startswith(p) or p.startswith("282") for p in HOSPITAL_TAXONOMY_PREFIXES)

    def test_excludes_individual_provider_taxonomies(self):
        # Individual providers start with "207", "208", etc. — must NOT be in the prefix list
        for p in HOSPITAL_TAXONOMY_PREFIXES:
            assert not p.startswith("207")
            assert not p.startswith("208")


class TestClientCachingBehavior:
    def test_cache_hit_skips_api(self):
        seed_cache = {
            "MAYO CLINIC|MN|ROCHESTER": {
                "npi": "1234567890",
                "legal_name": "Mayo Clinic",
                "matched_via": "city_and_taxonomy",
                "checked_at": "2026-04-28T12:00:00Z",
            }
        }
        client = NppesClient(cache=seed_cache, min_interval=0)
        out = client.lookup("Mayo Clinic", "MN", "Rochester")
        assert out.npi == "1234567890"
        assert out.matched_via == "cache"

    def test_cache_snapshot_returns_copy(self):
        client = NppesClient(cache={"X": {"npi": "1"}})
        snap = client.cache_snapshot()
        snap["Y"] = {"npi": "2"}
        # Original cache should be unchanged
        assert "Y" not in client.cache_snapshot()

    def test_returns_no_match_for_empty_inputs(self):
        client = NppesClient(min_interval=0)
        assert client.lookup("", "AL").matched_via == "no_match"
        assert client.lookup("X", "").matched_via == "no_match"
