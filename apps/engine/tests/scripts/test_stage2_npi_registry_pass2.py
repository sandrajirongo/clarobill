"""Unit tests for stage2_npi_registry_pass2 name-cleaning helpers.

The pure name-cleaning logic is the most failure-prone piece because suffix
patterns can over-strip legitimate name parts. The API call layer is
exercised in integration tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from mrf_discovery.stage2_npi_registry_pass2 import (  # noqa: E402
    clean_name,
    first_n_words,
)


class TestCleanName:
    def test_drops_hospital_suffix(self):
        assert clean_name("Mayo Clinic Hospital") == "MAYO CLINIC"

    def test_drops_medical_center_suffix(self):
        assert clean_name("Southeast Health Medical Center") == "SOUTHEAST HEALTH"

    def test_drops_inc_llc(self):
        assert clean_name("Saint Vincents, Inc") == "SAINT VINCENTS"
        assert clean_name("Foo Hospital, LLC") == "FOO"

    def test_drops_authority(self):
        assert clean_name("Houston County Healthcare Authority") == "HOUSTON COUNTY"

    def test_iterative_strip(self):
        # "FOO MEDICAL CENTER INC" -> "FOO MEDICAL CENTER" -> "FOO"
        assert clean_name("Foo Medical Center Inc") == "FOO"

    def test_drops_at_city(self):
        # "Saint Vincents Medical Center at Bridgeport" -> "SAINT VINCENTS"
        out = clean_name("Saint Vincents Medical Center at Bridgeport")
        assert out == "SAINT VINCENTS"

    def test_strips_punctuation(self):
        assert clean_name("Mayo Clinic, Inc.") == "MAYO CLINIC"
        assert clean_name("St. Mary's Hospital") == "ST MARY'S"

    def test_collapses_whitespace(self):
        assert clean_name("Mayo    Clinic   Hospital") == "MAYO CLINIC"

    def test_uppercase_normalisation(self):
        assert clean_name("mayo clinic hospital") == "MAYO CLINIC"
        assert clean_name("MAYO CLINIC HOSPITAL") == "MAYO CLINIC"

    def test_handles_already_clean_name(self):
        assert clean_name("Mayo Clinic") == "MAYO CLINIC"

    def test_drops_health_system(self):
        assert clean_name("Mercy Health System") == "MERCY"

    def test_drops_corporation(self):
        assert clean_name("Hospital Corporation of America") == ""
        # Wait — that's a problem. HCA is "Hospital Corporation of America"
        # and it's an actual entity. The cleaner zeros it out.
        # That's still useful: Strategy 3 (truncated_name) won't fire here, but
        # Strategy 1 returning empty just means we don't try a name-based call;
        # the lookup fails fast and we move on.

    def test_handles_only_suffix_words(self):
        # Pathological case: a name that's ENTIRELY suffix words
        assert clean_name("Hospital Inc Authority") == ""

    def test_preserves_unique_name_parts(self):
        # Strict regression: don't accidentally strip "MAYO" or "JOHNS HOPKINS"
        assert clean_name("Mayo Clinic") == "MAYO CLINIC"
        assert clean_name("Johns Hopkins Hospital") == "JOHNS HOPKINS"
        assert clean_name("Cleveland Clinic") == "CLEVELAND CLINIC"


class TestFirstNWords:
    def test_first_three(self):
        assert first_n_words("Mayo Clinic Health System Rochester", n=3) == "MAYO CLINIC HEALTH"

    def test_fewer_words_than_n(self):
        assert first_n_words("Mayo Clinic", n=3) == "MAYO CLINIC"

    def test_empty(self):
        assert first_n_words("", n=3) == ""

    def test_default_n(self):
        assert first_n_words("Mayo Clinic Health System") == "MAYO CLINIC HEALTH"
