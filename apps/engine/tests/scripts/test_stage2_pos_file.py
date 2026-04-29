"""Unit tests for stage2_pos_file pure helpers.

The fetcher and apply_to_checkpoint are exercised in integration tests against
real BigQuery; these unit tests cover the parser/normaliser logic where most
of the source-format risk lives.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from mrf_discovery.stage2_pos_file import (  # noqa: E402
    HOSPITAL_PRVDR_CTGRY_CDS,
    _category_label,
    _clean,
    _parse_int,
    is_hospital,
    normalise_pos_row,
)


class TestIsHospital:
    @pytest.mark.parametrize("cd", sorted(HOSPITAL_PRVDR_CTGRY_CDS))
    def test_accepts_every_hospital_category(self, cd):
        assert is_hospital({"PRVDR_CTGRY_CD": cd, "STATE_CD": "AL"}) is True

    @pytest.mark.parametrize("cd", ["00", "03", "05", "10", "15", "16", "20", "99", ""])
    def test_rejects_non_hospital_categories(self, cd):
        assert is_hospital({"PRVDR_CTGRY_CD": cd, "STATE_CD": "AL"}) is False

    @pytest.mark.parametrize("cd", ["21", "22"])
    def test_rejects_distinct_part_units(self, cd):
        # 15,324 distinct-part psychiatric unit rows leaked into Sandra's
        # 2026-04-28 real run because the filter included these codes.
        # Parent hospital's MRF covers them; we exclude.
        assert is_hospital({"PRVDR_CTGRY_CD": cd, "STATE_CD": "AL"}) is False

    @pytest.mark.parametrize("state", ["CN", "MX", "XX", "ZZ"])
    def test_rejects_non_us_states(self, state):
        # Sandra's 2026-04-28 run pulled in 263 CN + 7 MX rows. Cross-border
        # facilities exist in CMS POS but are out of scope for ClaroBill.
        assert is_hospital({"PRVDR_CTGRY_CD": "01", "STATE_CD": state}) is False

    @pytest.mark.parametrize("state", ["AL", "CA", "TX", "PR", "VI", "GU", "AE"])
    def test_accepts_us_states_and_territories(self, state):
        assert is_hospital({"PRVDR_CTGRY_CD": "01", "STATE_CD": state}) is True

    def test_handles_whitespace(self):
        assert is_hospital({"PRVDR_CTGRY_CD": "  01  ", "STATE_CD": "  AL  "}) is True

    def test_handles_lowercase_state(self):
        assert is_hospital({"PRVDR_CTGRY_CD": "01", "STATE_CD": "al"}) is True

    def test_handles_missing_field(self):
        assert is_hospital({}) is False
        assert is_hospital({"PRVDR_CTGRY_CD": None}) is False
        assert is_hospital({"PRVDR_CTGRY_CD": "01"}) is False  # missing STATE_CD


class TestCleanAndParse:
    def test_clean_strips(self):
        assert _clean("  hello  ") == "hello"

    def test_clean_returns_none_for_empty(self):
        assert _clean("") is None
        assert _clean("   ") is None
        assert _clean(None) is None

    def test_parse_int_valid(self):
        assert _parse_int("420") == 420
        assert _parse_int(" 420 ") == 420

    def test_parse_int_invalid(self):
        assert _parse_int("") is None
        assert _parse_int(None) is None
        assert _parse_int("foo") is None


class TestCategoryLabel:
    def test_known_codes(self):
        assert _category_label("01") == "Short-term Acute Care Hospital"
        assert _category_label("14") == "Critical Access Hospital"
        assert _category_label("06") == "Psychiatric Hospital"

    def test_unknown_code(self):
        assert _category_label("99") is None
        assert _category_label("") is None

    def test_none(self):
        assert _category_label(None) is None


class TestNormalisePosRow:
    def _row(self, **overrides) -> dict:
        base = {
            "PRVDR_NUM": "010001",
            "FAC_NAME": "SOUTHEAST HEALTH MEDICAL CENTER",
            "ST_ADR": "1108 ROSS CLARK CIRCLE",
            "CITY_NAME": "DOTHAN",
            "STATE_CD": "AL",
            "ZIP_CD": "36301",
            "PHNE_NUM": "3347938701",
            "PRVDR_CTGRY_CD": "01",
            "BED_CNT": "420",
            "INTRMDRY_CARR_CD": "10111",
        }
        base.update(overrides)
        return base

    def test_full_row(self):
        out = normalise_pos_row(self._row())
        assert out == {
            "ccn": "010001",
            "hospital_name": "SOUTHEAST HEALTH MEDICAL CENTER",
            "address": "1108 ROSS CLARK CIRCLE",
            "city": "DOTHAN",
            "state": "AL",
            "zip_code": "36301",
            "phone": "3347938701",
            "hospital_type": "Short-term Acute Care Hospital",
            "bed_count": 420,
            "medicare_carrier_code": "10111",
        }

    def test_returns_none_when_ccn_missing(self):
        assert normalise_pos_row(self._row(PRVDR_NUM="")) is None
        assert normalise_pos_row(self._row(PRVDR_NUM=None)) is None

    def test_returns_none_when_name_missing(self):
        assert normalise_pos_row(self._row(FAC_NAME="")) is None

    def test_handles_empty_optional_fields(self):
        out = normalise_pos_row({"PRVDR_NUM": "010001", "FAC_NAME": "X"})
        assert out["ccn"] == "010001"
        assert out["address"] is None
        assert out["bed_count"] is None
        assert out["medicare_carrier_code"] is None
        assert out["hospital_type"] is None

    def test_unknown_category_label_is_none(self):
        out = normalise_pos_row(self._row(PRVDR_CTGRY_CD="99"))
        # Unknown PRVDR_CTGRY_CD => no human label, but the row still parses
        # because hospital_type is not a required column. is_hospital() is the
        # gate that excludes non-hospital categories before normalise_pos_row
        # is called.
        assert out["hospital_type"] is None

    def test_preserves_zip_with_dash(self):
        out = normalise_pos_row(self._row(ZIP_CD="36301-1234"))
        assert out["zip_code"] == "36301-1234"

    def test_no_extra_keys(self):
        out = normalise_pos_row(self._row(SOMETHING_RANDOM="ignore me"))
        assert "SOMETHING_RANDOM" not in out
        assert set(out.keys()) == {
            "ccn", "hospital_name", "address", "city", "state", "zip_code",
            "phone", "hospital_type", "bed_count", "medicare_carrier_code",
        }
