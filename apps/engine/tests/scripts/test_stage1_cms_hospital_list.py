"""Unit tests for stage1_cms_hospital_list.normalise_row.

The fetcher (network + pagination) is exercised end-to-end in the integration
test against a recorded CMS API fixture. The normalisation logic is what's
most likely to break when CMS adds or renames a field, so it gets the
fastest-feedback regression suite here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from mrf_discovery.stage1_cms_hospital_list import (  # noqa: E402
    _clean_str,
    _parse_int,
    normalise_row,
)


class TestCleanStr:
    def test_strips_whitespace(self):
        assert _clean_str("  hello  ") == "hello"

    def test_returns_none_for_empty(self):
        assert _clean_str("") is None
        assert _clean_str("   ") is None

    def test_returns_none_for_none(self):
        assert _clean_str(None) is None

    def test_returns_none_for_not_available(self):
        # CMS uses "Not Available" as a sentinel for missing data
        assert _clean_str("Not Available") is None
        assert _clean_str("not available") is None

    def test_coerces_non_string(self):
        assert _clean_str(123) == "123"


class TestParseInt:
    def test_parses_int_string(self):
        assert _parse_int("4") == 4
        assert _parse_int(" 5 ") == 5

    def test_returns_none_for_invalid(self):
        assert _parse_int("Not Available") is None
        assert _parse_int("") is None
        assert _parse_int("foo") is None

    def test_returns_none_for_none(self):
        assert _parse_int(None) is None


class TestNormaliseRow:
    def _full_row(self, **overrides) -> dict:
        base = {
            "facility_id": "010001",
            "facility_name": "Southeast Health Medical Center",
            "address": "1108 Ross Clark Circle",
            "citytown": "Dothan",
            "state": "AL",
            "zip_code": "36301",
            "telephone_number": "3347938701",
            "hospital_type": "Acute Care Hospitals",
            "hospital_ownership": "Government - Hospital District or Authority",
            "hospital_overall_rating": "3",
        }
        base.update(overrides)
        return base

    def test_full_row(self):
        out = normalise_row(self._full_row())
        assert out == {
            "ccn": "010001",
            "hospital_name": "Southeast Health Medical Center",
            "address": "1108 Ross Clark Circle",
            "city": "Dothan",
            "state": "AL",
            "zip_code": "36301",
            "phone": "3347938701",
            "hospital_type": "Acute Care Hospitals",
            "hospital_ownership": "Government - Hospital District or Authority",
            "overall_rating": 3,
        }

    def test_strips_whitespace_in_required_fields(self):
        out = normalise_row(self._full_row(facility_id="  010001  ", facility_name="  Southeast  "))
        assert out["ccn"] == "010001"
        assert out["hospital_name"] == "Southeast"

    def test_returns_none_when_facility_id_missing(self):
        assert normalise_row(self._full_row(facility_id="")) is None
        assert normalise_row(self._full_row(facility_id=None)) is None

    def test_returns_none_when_facility_name_missing(self):
        assert normalise_row(self._full_row(facility_name="")) is None
        assert normalise_row(self._full_row(facility_name=None)) is None

    def test_handles_not_available_rating(self):
        out = normalise_row(self._full_row(hospital_overall_rating="Not Available"))
        assert out["overall_rating"] is None

    def test_handles_missing_optional_fields(self):
        out = normalise_row({
            "facility_id": "010001",
            "facility_name": "X",
        })
        assert out["ccn"] == "010001"
        assert out["address"] is None
        assert out["city"] is None
        assert out["state"] is None
        assert out["overall_rating"] is None

    def test_handles_not_available_string_in_address(self):
        out = normalise_row(self._full_row(address="Not Available"))
        assert out["address"] is None

    def test_preserves_zip_with_dash(self):
        out = normalise_row(self._full_row(zip_code="36301-1234"))
        assert out["zip_code"] == "36301-1234"

    def test_preserves_phone_format_as_given(self):
        # CMS sometimes includes parens/dashes/spaces; we don't normalise
        out = normalise_row(self._full_row(telephone_number="(334) 793-8701"))
        assert out["phone"] == "(334) 793-8701"

    def test_returns_dict_with_no_extra_keys(self):
        out = normalise_row(self._full_row(extra_field="should be ignored"))
        assert "extra_field" not in out
        # exactly the 10 known checkpoint columns
        assert set(out.keys()) == {
            "ccn", "hospital_name", "address", "city", "state", "zip_code",
            "phone", "hospital_type", "hospital_ownership", "overall_rating",
        }

    def test_rejects_dod_facilities(self):
        # Sandra's 2026-04-28 real run pulled in 32 "Acute Care - Department
        # of Defense" rows. DoD has their own pricing rules and does NOT
        # publish CMS Hospital Price Transparency MRFs.
        assert normalise_row(self._full_row(hospital_type="Acute Care - Department of Defense")) is None

    def test_rejects_va_facilities(self):
        # 132 VA rows in the same real run. Same reasoning.
        assert normalise_row(self._full_row(hospital_type="Acute Care - Veterans Administration")) is None

    def test_dod_va_filter_is_case_insensitive(self):
        assert normalise_row(self._full_row(hospital_type="ACUTE CARE - DEPARTMENT OF DEFENSE")) is None
        assert normalise_row(self._full_row(hospital_type="acute care - veterans administration")) is None

    def test_keeps_civilian_acute_care(self):
        # Make sure the filter doesn't accidentally drop legitimate hospitals.
        out = normalise_row(self._full_row(hospital_type="Acute Care Hospitals"))
        assert out is not None
        assert out["hospital_type"] == "Acute Care Hospitals"
