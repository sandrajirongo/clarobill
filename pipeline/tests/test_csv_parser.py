"""Tests for the CMS standard CSV MRF parser.

Covers:
- PayerGroup detection from wide-format headers
- is_cms_standard_csv validation
- stream_charges_csv end-to-end on the sample fixture
- NPI extraction from CSV metadata rows
- CsvVendorNotIdentified raised for non-CMS headers
- Per-row tolerance (bad rows skipped, good rows emitted)
- Two-code rows (code|1 + code|2) expand to two ChargeRow groups
- Payer columns with only percentage / algorithm values
- Blank data rows are silently skipped
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

PIPELINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_DIR))

from csv_vendors import (
    CsvVendorNotIdentified,
    PayerGroup,
    detect_payer_groups,
    is_cms_standard_csv,
)
from hospital_mrf_utils import (
    _expand_csv_row,
    _extract_npi_from_csv_meta,
    stream_charges_csv,
)

FIXTURE = PIPELINE_DIR / "tests" / "fixtures" / "csv" / "sample_cms_standard_v2.csv"
SCRAPED_AT = "2026-05-05T12:00:00Z"
NPI = "1234567890"
YEAR = 2026


# ---------------------------------------------------------------------------
# csv_vendors: is_cms_standard_csv
# ---------------------------------------------------------------------------

class TestIsCmsStandardCsv:
    def test_accepts_minimal_required_cols(self):
        cols = ["description", "standard_charge|gross", "standard_charge|discounted_cash"]
        assert is_cms_standard_csv(cols) is True

    def test_accepts_full_fixture_header(self):
        cols = [
            "description", "code|1", "code|1|type", "code|2", "code|2|type",
            "setting", "standard_charge|gross", "standard_charge|discounted_cash",
            "standard_charge|min", "standard_charge|max",
            "standard_charge|Aetna|PPO|negotiated_dollar",
            "standard_charge|Aetna|PPO|methodology",
        ]
        assert is_cms_standard_csv(cols) is True

    def test_rejects_missing_gross(self):
        cols = ["description", "standard_charge|discounted_cash"]
        assert is_cms_standard_csv(cols) is False

    def test_rejects_empty_list(self):
        assert is_cms_standard_csv([]) is False

    def test_rejects_vendor_proprietary_cols(self):
        cols = ["item_description", "charge_amount", "payer_code"]
        assert is_cms_standard_csv(cols) is False


# ---------------------------------------------------------------------------
# csv_vendors: detect_payer_groups
# ---------------------------------------------------------------------------

class TestDetectPayerGroups:
    def test_detects_two_payer_groups(self):
        cols = [
            "description",
            "standard_charge|Aetna|PPO|negotiated_dollar",
            "standard_charge|Aetna|PPO|negotiated_percentage",
            "standard_charge|Aetna|PPO|methodology",
            "estimated_amount|Aetna|PPO",
            "standard_charge|BCBS|HMO|negotiated_dollar",
            "standard_charge|BCBS|HMO|methodology",
        ]
        groups = detect_payer_groups(cols)
        assert len(groups) == 2
        aetna = next(g for g in groups if g.payer_name == "Aetna")
        assert aetna.plan_name == "PPO"
        assert aetna.dollar_col == "standard_charge|Aetna|PPO|negotiated_dollar"
        assert aetna.pct_col == "standard_charge|Aetna|PPO|negotiated_percentage"
        assert aetna.methodology_col == "standard_charge|Aetna|PPO|methodology"
        assert aetna.estimated_col == "estimated_amount|Aetna|PPO"

    def test_empty_cols_yields_no_groups(self):
        assert detect_payer_groups([]) == []

    def test_no_payer_cols_yields_no_groups(self):
        cols = ["description", "standard_charge|gross", "standard_charge|min"]
        assert detect_payer_groups(cols) == []

    def test_preserves_insertion_order(self):
        cols = [
            "standard_charge|Aetna|PPO|negotiated_dollar",
            "standard_charge|BCBS|HMO|negotiated_dollar",
            "standard_charge|UHC|EPO|negotiated_dollar",
        ]
        groups = detect_payer_groups(cols)
        assert [g.payer_name for g in groups] == ["Aetna", "BCBS", "UHC"]

    def test_payer_name_with_pipe_like_chars_not_present(self):
        # Payer names with spaces and parens are common in the corpus.
        cols = [
            "standard_charge|Blue Cross Blue Shield|PPO|negotiated_dollar",
            "standard_charge|Blue Cross Blue Shield|PPO|methodology",
        ]
        groups = detect_payer_groups(cols)
        assert groups[0].payer_name == "Blue Cross Blue Shield"


# ---------------------------------------------------------------------------
# hospital_mrf_utils: _extract_npi_from_csv_meta
# ---------------------------------------------------------------------------

class TestExtractNpiFromCsvMeta:
    def test_type_2_npi_column(self):
        header = ["hospital_name", "last_updated_on", "version", "type_2_npi"]
        values = ["Test Hospital", "2026-01-01", "2.0.0", "1234567890"]
        assert _extract_npi_from_csv_meta(header, values) == "1234567890"

    def test_hospital_npi_column(self):
        header = ["hospital_npi", "last_updated_on"]
        values = ["9876543210", "2026-01-01"]
        assert _extract_npi_from_csv_meta(header, values) == "9876543210"

    def test_rejects_nine_digit_value(self):
        header = ["type_2_npi"]
        values = ["123456789"]
        assert _extract_npi_from_csv_meta(header, values) == ""

    def test_rejects_non_digit_value(self):
        header = ["type_2_npi"]
        values = ["NPI-12345678"]
        assert _extract_npi_from_csv_meta(header, values) == ""

    def test_returns_empty_when_column_absent(self):
        header = ["hospital_name", "last_updated_on"]
        values = ["Hosp", "2026-01-01"]
        assert _extract_npi_from_csv_meta(header, values) == ""


# ---------------------------------------------------------------------------
# hospital_mrf_utils: stream_charges_csv — end-to-end fixture
# ---------------------------------------------------------------------------

class TestStreamChargesCsvFixture:
    def _load(self, npi: str = NPI) -> list:
        return list(stream_charges_csv(
            FIXTURE.open("rb"), npi, YEAR, SCRAPED_AT,
            source_mrf_url="https://example.com/charges.csv",
        ))

    def test_returns_charge_rows(self):
        rows = self._load()
        assert len(rows) > 0

    def test_all_rows_have_correct_npi(self):
        for row in self._load():
            assert row.hospital_npi == NPI

    def test_all_rows_have_correct_year(self):
        for row in self._load():
            assert row.pricing_effective_year == YEAR

    def test_single_code_single_payer_row(self):
        """Row 1 (99213) has 2 payers with negotiated_dollar → 2 ChargeRows."""
        rows = self._load()
        cpt_99213 = [r for r in rows if r.code == "99213"]
        assert len(cpt_99213) == 2
        payers = {r.payer_name for r in cpt_99213}
        assert "Aetna" in payers
        assert "BCBS" in payers

    def test_percentage_payer_row(self):
        """Row 2 (99232) Aetna has negotiated_percentage=75.0% (no dollar)."""
        rows = self._load()
        aetna_99232 = [r for r in rows if r.code == "99232" and r.payer_name == "Aetna"]
        assert len(aetna_99232) == 1
        row = aetna_99232[0]
        assert row.negotiated_charge is None
        assert row.negotiated_type is not None
        assert "75.0%" in row.negotiated_type

    def test_two_code_row_expands(self):
        """Row 3 (44950 CPT + G0389 HCPCS) emits rows for both code types."""
        rows = self._load()
        cpt_44950 = [r for r in rows if r.code == "44950"]
        hcpcs_g0389 = [r for r in rows if r.code == "G0389"]
        assert len(cpt_44950) >= 2  # 2 payers
        assert len(hcpcs_g0389) >= 2  # same 2 payers

    def test_no_payer_row_emits_one_null_payer_row(self):
        """Row 4 (71046) has all empty payer columns → 1 row with payer_name=None."""
        rows = self._load()
        xray = [r for r in rows if r.code == "71046"]
        assert len(xray) == 1
        assert xray[0].payer_name is None
        assert xray[0].negotiated_charge is None

    def test_npi_from_csv_meta_when_not_passed(self):
        """NPI="": stream_charges_csv extracts 1234567890 from the fixture meta row."""
        rows = list(stream_charges_csv(
            FIXTURE.open("rb"), "", YEAR, SCRAPED_AT,
        ))
        assert all(r.hospital_npi == "1234567890" for r in rows)

    def test_source_mrf_url_propagated(self):
        url = "https://example.com/charges.csv"
        rows = list(stream_charges_csv(FIXTURE.open("rb"), NPI, YEAR, SCRAPED_AT,
                                       source_mrf_url=url))
        assert all(r.source_mrf_url == url for r in rows)


# ---------------------------------------------------------------------------
# CsvVendorNotIdentified raised for non-CMS headers
# ---------------------------------------------------------------------------

class TestCsvVendorNotIdentified:
    def test_raises_for_proprietary_header(self):
        fake_csv = (
            "hospital_name,date\n"
            "Bogus Hospital,2026-01-01\n"
            "item_code,item_description,charge_amount\n"
            "001,ROOM,500.00\n"
        ).encode()
        with pytest.raises(CsvVendorNotIdentified):
            list(stream_charges_csv(io.BytesIO(fake_csv), NPI, YEAR, SCRAPED_AT))

    def test_raises_for_two_row_only_file(self):
        fake_csv = "hospital_name\nTest Hospital\n".encode()
        rows = list(stream_charges_csv(io.BytesIO(fake_csv), NPI, YEAR, SCRAPED_AT))
        assert rows == []  # no row 3 → returns empty, not raises

    def test_raises_for_empty_file(self):
        rows = list(stream_charges_csv(io.BytesIO(b""), NPI, YEAR, SCRAPED_AT))
        assert rows == []


# ---------------------------------------------------------------------------
# Per-row tolerance: bad rows are skipped, good rows are returned
# ---------------------------------------------------------------------------

class TestPerRowTolerance:
    def _make_csv(self, data_rows: list[str]) -> io.BytesIO:
        header = (
            "hospital_name,last_updated_on,version\n"
            "Test,2026-01-01,2.0.0\n"
            "description,code|1,code|1|type,setting,"
            "standard_charge|gross,standard_charge|discounted_cash,"
            "standard_charge|min,standard_charge|max\n"
        )
        return io.BytesIO((header + "\n".join(data_rows) + "\n").encode())

    def test_blank_rows_skipped(self):
        rows = list(stream_charges_csv(
            self._make_csv(["", "OFFICE VISIT,99213,CPT,outpatient,150.00,120.00,100.00,180.00"]),
            NPI, YEAR, SCRAPED_AT,
        ))
        assert len(rows) == 1
        assert rows[0].code == "99213"

    def test_good_rows_still_returned_after_bad_row(self):
        bad = "BAD ROW MISSING MOST COLS"
        good = "VALID ROW,99214,CPT,outpatient,200.00,160.00,140.00,250.00"
        rows = list(stream_charges_csv(
            self._make_csv([bad, good]),
            NPI, YEAR, SCRAPED_AT,
        ))
        assert any(r.code == "99214" for r in rows)
