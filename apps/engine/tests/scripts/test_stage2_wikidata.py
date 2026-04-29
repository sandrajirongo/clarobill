"""Unit tests for stage2_wikidata.match_to_checkpoint.

The SPARQL fetcher is exercised against the live endpoint in an integration
test. The matcher is the most failure-prone piece because fuzzy-matching can
silently produce false positives.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from mrf_discovery.stage2_wikidata import (  # noqa: E402
    FUZZY_MATCH_THRESHOLD,
    _clean_url,
    match_to_checkpoint,
)


class TestCleanUrl:
    def test_adds_protocol(self):
        assert _clean_url("hospital.org") == "https://hospital.org"

    def test_preserves_https(self):
        assert _clean_url("https://hospital.org") == "https://hospital.org"

    def test_preserves_http(self):
        assert _clean_url("http://hospital.org") == "http://hospital.org"

    def test_returns_none_for_empty(self):
        assert _clean_url("") is None
        assert _clean_url("   ") is None


class TestMatchToCheckpoint:
    def test_exact_match(self):
        candidates = [{"name": "Mayo Clinic", "website": "https://mayoclinic.org"}]
        checkpoint = [{"ccn": "240008", "hospital_name": "Mayo Clinic"}]
        assert match_to_checkpoint(candidates, checkpoint) == {
            "240008": "https://mayoclinic.org",
        }

    def test_case_insensitive(self):
        candidates = [{"name": "MAYO CLINIC", "website": "https://mayoclinic.org"}]
        checkpoint = [{"ccn": "240008", "hospital_name": "mayo clinic"}]
        assert match_to_checkpoint(candidates, checkpoint) == {
            "240008": "https://mayoclinic.org",
        }

    def test_fuzzy_above_threshold(self):
        # Typo / minor formatting difference — should match.
        # "Mayo Clinic" vs "Mayo Clinc" (one missing letter) is ~0.95 similarity.
        candidates = [{"name": "Mayo Clinic", "website": "https://mayoclinic.org"}]
        checkpoint = [{"ccn": "240008", "hospital_name": "Mayo Clinc"}]
        result = match_to_checkpoint(candidates, checkpoint)
        assert result == {"240008": "https://mayoclinic.org"}

    def test_substring_does_NOT_match(self):
        # "Mayo Clinic" vs "Mayo Clinic Hospital" is only ~0.71 similarity.
        # We deliberately reject these because false positives at this layer
        # produce wrong-website -> wrong-MRF -> wrong-overcharge-claim, which
        # is the worst class of defect for ClaroBill. Strict threshold is the
        # correct safety choice; substring matching belongs in a different
        # layer if we ever want it.
        candidates = [{"name": "Mayo Clinic", "website": "https://mayoclinic.org"}]
        checkpoint = [{"ccn": "240008", "hospital_name": "Mayo Clinic Hospital"}]
        assert match_to_checkpoint(candidates, checkpoint) == {}

    def test_below_threshold_does_not_match(self):
        # "St Vincents Birmingham" vs "Mayo Clinic" — low similarity, must not match
        candidates = [{"name": "Mayo Clinic", "website": "https://mayoclinic.org"}]
        checkpoint = [{"ccn": "010023", "hospital_name": "St Vincents Birmingham"}]
        assert match_to_checkpoint(candidates, checkpoint) == {}

    def test_multiple_ccns_match_one_candidate(self):
        # System entry like "HCA Healthcare" matching multiple HCA facilities
        candidates = [{"name": "HCA Healthcare", "website": "https://hcahealthcare.com"}]
        checkpoint = [
            {"ccn": "100001", "hospital_name": "HCA Healthcare"},
            {"ccn": "100002", "hospital_name": "HCA Healthcare"},
        ]
        result = match_to_checkpoint(candidates, checkpoint)
        assert result == {
            "100001": "https://hcahealthcare.com",
            "100002": "https://hcahealthcare.com",
        }

    def test_picks_best_match_when_multiple_candidates_pass_threshold(self):
        candidates = [
            {"name": "Mayo Clinic", "website": "https://mayoclinic.org"},
            {"name": "Mayo Clinic Health System", "website": "https://mayoclinichealthsystem.org"},
        ]
        # The hospital name "Mayo Clinic" matches the first candidate exactly
        # and the second candidate weakly. We want the exact match to win.
        checkpoint = [{"ccn": "240008", "hospital_name": "Mayo Clinic"}]
        result = match_to_checkpoint(candidates, checkpoint)
        assert result == {"240008": "https://mayoclinic.org"}

    def test_skips_rows_with_no_ccn(self):
        candidates = [{"name": "Mayo Clinic", "website": "https://mayoclinic.org"}]
        checkpoint = [{"ccn": None, "hospital_name": "Mayo Clinic"}]
        assert match_to_checkpoint(candidates, checkpoint) == {}

    def test_skips_rows_with_no_name(self):
        candidates = [{"name": "Mayo Clinic", "website": "https://mayoclinic.org"}]
        checkpoint = [{"ccn": "240008", "hospital_name": None}]
        assert match_to_checkpoint(candidates, checkpoint) == {}

    def test_empty_inputs(self):
        assert match_to_checkpoint([], []) == {}
        assert match_to_checkpoint(
            [{"name": "Mayo Clinic", "website": "https://mayoclinic.org"}], [],
        ) == {}
        assert match_to_checkpoint(
            [], [{"ccn": "240008", "hospital_name": "Mayo Clinic"}],
        ) == {}

    def test_threshold_constant_is_strict(self):
        # 0.85 is high enough to avoid the most embarrassing false positives.
        # If anyone "cleans up" the constant, this test reminds them why it
        # was that high.
        assert FUZZY_MATCH_THRESHOLD == 0.85
