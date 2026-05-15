"""Tests for scripts/mrf_discovery/system_sweepers.py.

All tests are offline (no real network calls). HTTP calls are patched at
the requests.Session level. Playwright calls are not tested here — those
require a headless browser and are exercised in integration smoke tests.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Allow running from repo root or from within scripts/ directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mrf_discovery import system_sweepers
from mrf_discovery.system_sweepers import (
    SweepResult,
    assign_urls_to_hospitals,
    extract_name_from_cms_filename,
    normalize_hospital_name,
    sweep_tenet_hyve,
)

# ---------------------------------------------------------------------------
# normalize_hospital_name
# ---------------------------------------------------------------------------


def test_normalize_strips_punctuation():
    # "St." → "st " (period → space), "Mary's" → "mary s" (apostrophe → space),
    # then multi-space collapse → single spaces throughout.
    assert normalize_hospital_name("St. Mary's Hospital") == "st mary s hospital"


def test_normalize_collapses_whitespace():
    assert normalize_hospital_name("  General   Medical  Center  ") == "general medical center"


def test_normalize_lowercases():
    assert normalize_hospital_name("KAISER FOUNDATION") == "kaiser foundation"


def test_normalize_empty():
    assert normalize_hospital_name("") == ""


# ---------------------------------------------------------------------------
# extract_name_from_cms_filename
# ---------------------------------------------------------------------------


def test_extract_name_standard_ein_format():
    url = "https://cdn.example.com/123456789_kaiser-oakland_standardcharges.csv"
    result = extract_name_from_cms_filename(url)
    assert result is not None
    assert "kaiser" in result
    assert "oakland" in result


def test_extract_name_with_npi():
    # EIN + NPI variant: {EIN}_{NPI}_{name}_standardcharges.{ext}
    url = "https://cdn.example.com/123456789_1234567890_sutter-davis_standardcharges.json"
    result = extract_name_from_cms_filename(url)
    assert result is not None
    assert "sutter" in result


def test_extract_name_gzip():
    url = "https://cdn.example.com/987654321_memorial-hospital_standardcharges.csv.gz"
    result = extract_name_from_cms_filename(url)
    assert result is not None
    assert "memorial" in result
    assert "hospital" in result


def test_extract_name_no_match():
    assert extract_name_from_cms_filename("https://example.com/some-other-file.pdf") is None


def test_extract_name_query_string_ignored():
    url = "https://cdn.example.com/111222333_valley-med_standardcharges.xlsx?v=2"
    result = extract_name_from_cms_filename(url)
    assert result is not None
    assert "valley" in result


# ---------------------------------------------------------------------------
# assign_urls_to_hospitals
# ---------------------------------------------------------------------------


def _make_hospital(ccn: str, name: str) -> dict:
    return {"ccn": ccn, "hospital_name": name, "hospital_npi": None, "state": "CA"}


def _mock_session_head_ok(url: str) -> bool:
    return True


@patch.object(system_sweepers, "_head_ok", return_value=True)
def test_assign_exact_name_match(mock_head):
    hospitals = [_make_hospital("050001", "Kaiser Foundation Hospital Oakland")]
    url = "https://cdn.example.com/123456789_kaiser-foundation-hospital-oakland_standardcharges.csv"
    pairs = [(url, extract_name_from_cms_filename(url))]
    results = assign_urls_to_hospitals(pairs, hospitals, "test", MagicMock())
    assert len(results) == 1
    assert results[0].ccn == "050001"
    assert results[0].mrf_url == url
    assert results[0].file_format == "csv"


@patch.object(system_sweepers, "_head_ok", return_value=True)
def test_assign_fuzzy_name_match(mock_head):
    # Slight difference (abbreviation) should still match above 0.65 threshold.
    hospitals = [_make_hospital("060001", "Sutter Davis Hospital")]
    url = "https://cdn.example.com/123456789_sutter-davis-hosp_standardcharges.json"
    pairs = [(url, extract_name_from_cms_filename(url))]
    results = assign_urls_to_hospitals(pairs, hospitals, "test", MagicMock())
    assert len(results) == 1
    assert results[0].ccn == "060001"


@patch.object(system_sweepers, "_head_ok", return_value=True)
def test_assign_no_match_below_threshold(mock_head):
    # Completely different name should produce no assignment.
    hospitals = [_make_hospital("070001", "Valley Medical Center")]
    url = "https://cdn.example.com/123456789_east-bay-surgery_standardcharges.csv"
    pairs = [(url, extract_name_from_cms_filename(url))]
    results = assign_urls_to_hospitals(pairs, hospitals, "test", MagicMock())
    assert results == []


@patch.object(system_sweepers, "_head_ok", return_value=False)
def test_assign_head_validation_failure(mock_head):
    # Even a name match produces no result when HEAD returns non-2xx.
    hospitals = [_make_hospital("080001", "Memorial Hospital")]
    url = "https://cdn.example.com/111222333_memorial-hospital_standardcharges.csv"
    pairs = [(url, extract_name_from_cms_filename(url))]
    results = assign_urls_to_hospitals(pairs, hospitals, "test", MagicMock())
    assert results == []


@patch.object(system_sweepers, "_head_ok", return_value=True)
def test_assign_multiple_hospitals(mock_head):
    hospitals = [
        _make_hospital("090001", "Kaiser Oakland"),
        _make_hospital("090002", "Kaiser San Francisco"),
        _make_hospital("090003", "Sutter Davis Hospital"),
    ]
    pairs = [
        ("https://cdn.example.com/111_kaiser-oakland_standardcharges.csv",
         "kaiser oakland"),
        ("https://cdn.example.com/222_kaiser-san-francisco_standardcharges.csv",
         "kaiser san francisco"),
        ("https://cdn.example.com/333_sutter-davis-hospital_standardcharges.json",
         "sutter davis hospital"),
    ]
    results = assign_urls_to_hospitals(pairs, hospitals, "test", MagicMock())
    assert len(results) == 3
    ccns = {r.ccn for r in results}
    assert ccns == {"090001", "090002", "090003"}


# ---------------------------------------------------------------------------
# sweep_tenet_hyve — offline fixture
# ---------------------------------------------------------------------------

_TENET_HTML_FIXTURE = """
<html><body>
<script>
const files = [
  "123456789_tenet-st-francis-hospital_standardcharges.json",
  "987654321_tenet-coastal-hospital_standardcharges.csv",
  "not_a_match_file.txt"
];
</script>
</body></html>
"""


@patch.object(system_sweepers, "_get_html", return_value=_TENET_HTML_FIXTURE)
@patch.object(system_sweepers, "_head_ok", return_value=True)
def test_sweep_tenet_parses_js_array(mock_head, mock_get):
    hospitals = [
        _make_hospital("T001", "Tenet St Francis Hospital"),
        _make_hospital("T002", "Tenet Coastal Hospital"),
    ]
    results, resolved = sweep_tenet_hyve(MagicMock(), hospitals)
    assert len(results) == 2
    assert resolved == {"T001", "T002"}
    methods = {r.discovery_method for r in results}
    assert methods == {"tenet_hyve"}


@patch.object(system_sweepers, "_get_html", return_value=None)
def test_sweep_tenet_empty_on_fetch_failure(mock_get):
    results, resolved = sweep_tenet_hyve(MagicMock(), [_make_hospital("X001", "Any Hospital")])
    assert results == []
    assert resolved == set()


@patch.object(system_sweepers, "_get_html", return_value="<html><p>no files here</p></html>")
def test_sweep_tenet_empty_when_no_js_array(mock_get):
    results, resolved = sweep_tenet_hyve(MagicMock(), [_make_hospital("X002", "Any Hospital")])
    assert results == []
    assert resolved == set()


_TENET_XLSX_FIXTURE = """
<html><body>
<script>
const files = [
  "123456789_tenet-mercy-general_standardcharges.xlsx",
  "987654321_tenet-coastal-hospital_standardcharges.json.gz"
];
</script>
</body></html>
"""


@patch.object(system_sweepers, "_get_html", return_value=_TENET_XLSX_FIXTURE)
@patch.object(system_sweepers, "_head_ok", return_value=True)
def test_sweep_tenet_picks_up_xlsx_and_gzip(mock_head, mock_get):
    # Previous hand-rolled regex only matched .json and .csv — missed .xlsx and .json.gz.
    hospitals = [
        _make_hospital("T003", "Tenet Mercy General"),
        _make_hospital("T004", "Tenet Coastal Hospital"),
    ]
    results, resolved = sweep_tenet_hyve(MagicMock(), hospitals)
    assert len(results) == 2, f"expected 2 results, got {len(results)}: {[r.mrf_url for r in results]}"
    formats = {r.file_format for r in results}
    assert "xlsx" in formats
    assert "json" in formats


# ---------------------------------------------------------------------------
# SweepResult dataclass
# ---------------------------------------------------------------------------


def test_sweep_result_frozen():
    sr = SweepResult(
        ccn="123456",
        hospital_npi=None,
        hospital_name="Test Hospital",
        state="TX",
        mrf_url="https://example.com/123456_test_standardcharges.csv",
        discovery_method="tenet_hyve",
        file_format="csv",
    )
    with pytest.raises((AttributeError, TypeError)):
        sr.ccn = "000000"  # type: ignore[misc]


def test_sweep_result_file_format_json():
    sr = SweepResult(
        ccn="123456", hospital_npi=None, hospital_name="H", state=None,
        mrf_url="https://example.com/123_h_standardcharges.json.gz",
        discovery_method="domain_dedup", file_format="json",
    )
    assert sr.file_format == "json"
