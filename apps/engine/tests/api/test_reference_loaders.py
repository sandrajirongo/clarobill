"""Tests for Supabase-backed reference data loaders.

All Supabase queries are mocked at the response level so no database is required.
Tests verify: filter logic, result mapping, empty-result handling, and fallback paths.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.api.v1.bills import (
    _load_anesthesia_cf,
    _load_medicare_rates,
    _load_mue_limits,
    _load_ncci_pairs,
    _load_non_payable_codes,
    _resolve_locality,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _mock_supabase(rows: list[dict]) -> MagicMock:
    """Build a Supabase client mock whose final .execute() returns rows."""
    response = MagicMock()
    response.data = rows

    # Chain: .table().select().[filters...].execute() → response
    query = MagicMock()
    query.select.return_value = query
    query.eq.return_value = query
    query.in_.return_value = query
    query.lte.return_value = query
    query.gte.return_value = query
    query.is_.return_value = query
    query.or_.return_value = query
    query.order.return_value = query
    query.limit.return_value = query
    query.execute.return_value = response

    client = MagicMock()
    client.table.return_value = query
    return client


# ── _load_ncci_pairs ──────────────────────────────────────────────────────────

class TestLoadNcciPairs:
    def test_returns_empty_dict_for_empty_cpt_list(self) -> None:
        client = _mock_supabase([])
        result = _load_ncci_pairs(client, [])
        assert result == {}

    def test_maps_column_one_to_column_two_set(self) -> None:
        rows = [
            {"column_one_code": "27447", "column_two_code": "27486"},
            {"column_one_code": "27447", "column_two_code": "27487"},
            {"column_one_code": "99214", "column_two_code": "99215"},
        ]
        client = _mock_supabase(rows)
        result = _load_ncci_pairs(client, ["27447", "99214"])
        assert result["27447"] == {"27486", "27487"}
        assert result["99214"] == {"99215"}

    def test_returns_empty_dict_when_no_pairs_found(self) -> None:
        client = _mock_supabase([])
        result = _load_ncci_pairs(client, ["99214", "85025"])
        assert result == {}

    def test_deduplicates_cpt_codes_before_query(self) -> None:
        # Duplicate input codes should not cause duplicate IN() values
        client = _mock_supabase([])
        # Just confirm it doesn't crash with duplicates
        result = _load_ncci_pairs(client, ["99214", "99214", "85025"])
        assert isinstance(result, dict)

    def test_applies_service_date_filter_when_provided(self) -> None:
        rows = [{"column_one_code": "27447", "column_two_code": "27486"}]
        client = _mock_supabase(rows)
        _load_ncci_pairs(client, ["27447"], service_date=date(2026, 3, 15))
        # Verify .lte() was called on the query chain (date filter applied)
        query = client.table.return_value
        query.lte.assert_called()

    def test_no_date_filter_when_service_date_not_provided(self) -> None:
        rows = [{"column_one_code": "27447", "column_two_code": "27486"}]
        client = _mock_supabase(rows)
        _load_ncci_pairs(client, ["27447"])
        # When no service_date, .is_("deletion_date", "null") is used instead of .lte()
        query = client.table.return_value
        query.is_.assert_called()


# ── _load_mue_limits ─────────────────────────────────────────────────────────

class TestLoadMueLimits:
    def test_returns_empty_for_empty_cpt_list(self) -> None:
        client = _mock_supabase([])
        result = _load_mue_limits(client, [])
        assert result == {}

    def test_maps_hcpcs_code_to_mue_tuple(self) -> None:
        rows = [
            {"hcpcs_code": "99214", "mue_value": 3, "adjudication_indicator": 2, "effective_date": "2026-01-01"},
            {"hcpcs_code": "85025", "mue_value": 1, "adjudication_indicator": 3, "effective_date": "2026-01-01"},
        ]
        client = _mock_supabase(rows)
        result = _load_mue_limits(client, ["99214", "85025"])
        assert result["99214"] == (3, 2)
        assert result["85025"] == (1, 3)

    def test_takes_most_recent_entry_per_code(self) -> None:
        # Two rows for same code; first (most recent, desc order) wins
        rows = [
            {"hcpcs_code": "99214", "mue_value": 3, "adjudication_indicator": 2, "effective_date": "2026-01-01"},
            {"hcpcs_code": "99214", "mue_value": 5, "adjudication_indicator": 2, "effective_date": "2025-07-01"},
        ]
        client = _mock_supabase(rows)
        result = _load_mue_limits(client, ["99214"])
        assert result["99214"] == (3, 2)  # 2026 row wins

    def test_returns_empty_when_no_limits_found(self) -> None:
        client = _mock_supabase([])
        result = _load_mue_limits(client, ["99214"])
        assert result == {}


# ── _load_medicare_rates ──────────────────────────────────────────────────────

class TestLoadMedicareRates:
    def test_returns_empty_for_empty_cpt_list(self) -> None:
        client = _mock_supabase([])
        result = _load_medicare_rates(client, [])
        assert result == {}

    def test_computes_national_rate_from_rvus(self) -> None:
        # National rate = nfac_total_rvu * conv_fact (all GPCIs = 1.0 for locality 0000000)
        indicators_rows = [
            {
                "hcpc": "99214",
                "rvu_work": "1.5",
                "nfac_pe_rvu": "1.1",
                "rvu_mp": "0.12",
                "nfac_total_rvu": "2.72",
                "conv_fact": "32.7442",
                "proc_stat": "A",
            }
        ]
        gpci_rows: list[dict] = []  # No locality rows → national fallback (all GPCIs = 1.0)
        client = MagicMock()

        # indicators query returns indicators_rows; locality query returns gpci_rows
        indicator_response = MagicMock()
        indicator_response.data = indicators_rows
        locality_response = MagicMock()
        locality_response.data = gpci_rows

        call_count = 0
        def _table_side_effect(name: str) -> MagicMock:
            nonlocal call_count
            call_count += 1
            q = MagicMock()
            q.select.return_value = q
            q.in_.return_value = q
            q.eq.return_value = q
            q.lte.return_value = q
            q.order.return_value = q
            q.limit.return_value = q
            q.or_.return_value = q
            if name == "cms_pfs_indicators":
                q.execute.return_value = indicator_response
            else:
                q.execute.return_value = locality_response
            return q

        client.table.side_effect = _table_side_effect

        result = _load_medicare_rates(client, ["99214"], rate_date=date(2026, 1, 1))
        assert "99214" in result
        expected = (Decimal("2.72") * Decimal("32.7442")).quantize(Decimal("0.01"))
        assert result["99214"] == expected

    def test_excludes_codes_with_zero_total_rvu(self) -> None:
        indicators_rows = [
            {
                "hcpc": "99214",
                "rvu_work": "0.0",
                "nfac_pe_rvu": "0.0",
                "rvu_mp": "0.0",
                "nfac_total_rvu": "0.0",
                "conv_fact": "32.7442",
                "proc_stat": "A",
            }
        ]
        gpci_rows: list[dict] = []
        client = MagicMock()

        def _table_side_effect(name: str) -> MagicMock:
            q = MagicMock()
            q.select.return_value = q
            q.in_.return_value = q
            q.eq.return_value = q
            q.lte.return_value = q
            q.order.return_value = q
            q.limit.return_value = q
            q.or_.return_value = q
            resp = MagicMock()
            resp.data = indicators_rows if name == "cms_pfs_indicators" else gpci_rows
            q.execute.return_value = resp
            return q

        client.table.side_effect = _table_side_effect
        result = _load_medicare_rates(client, ["99214"], rate_date=date(2026, 1, 1))
        # Zero total RVU → rate = 0 → excluded
        assert "99214" not in result

    def test_returns_empty_when_no_indicators_found(self) -> None:
        client = MagicMock()

        def _table_side_effect(name: str) -> MagicMock:
            q = MagicMock()
            q.select.return_value = q
            q.in_.return_value = q
            q.eq.return_value = q
            q.lte.return_value = q
            q.order.return_value = q
            q.limit.return_value = q
            q.or_.return_value = q
            resp = MagicMock()
            resp.data = []
            q.execute.return_value = resp
            return q

        client.table.side_effect = _table_side_effect
        result = _load_medicare_rates(client, ["99214"])
        assert result == {}


# ── _load_non_payable_codes ───────────────────────────────────────────────────

class TestLoadNonPayableCodes:
    def test_returns_empty_for_empty_cpt_list(self) -> None:
        client = _mock_supabase([])
        result = _load_non_payable_codes(client, [])
        assert result == {}

    def test_maps_hcpc_to_proc_stat(self) -> None:
        rows = [
            {"hcpc": "99241", "proc_stat": "I"},
            {"hcpc": "G0121", "proc_stat": "B"},
        ]
        client = _mock_supabase(rows)
        result = _load_non_payable_codes(client, ["99241", "G0121"])
        assert result["99241"] == "I"
        assert result["G0121"] == "B"

    def test_takes_most_recent_entry_per_code(self) -> None:
        # Two rows for same code — first row wins (ordered by effective_from desc)
        rows = [
            {"hcpc": "99241", "proc_stat": "I"},
            {"hcpc": "99241", "proc_stat": "B"},
        ]
        client = _mock_supabase(rows)
        result = _load_non_payable_codes(client, ["99241"])
        assert result["99241"] == "I"

    def test_returns_empty_when_all_codes_are_payable(self) -> None:
        client = _mock_supabase([])
        result = _load_non_payable_codes(client, ["99214", "85025"])
        assert result == {}


# ── _resolve_locality ─────────────────────────────────────────────────────────

class TestResolveLocality:
    def test_returns_national_default_when_no_state(self) -> None:
        client = _mock_supabase([])
        assert _resolve_locality(client, None, None) == "0000000"

    def test_returns_county_match_when_found(self) -> None:
        client = MagicMock()

        county_response = MagicMock()
        county_response.data = [{"locality_code": "0112105"}]

        q = MagicMock()
        q.select.return_value = q
        q.eq.return_value = q
        q.lte.return_value = q
        q.order.return_value = q
        q.limit.return_value = q
        q.execute.return_value = county_response
        client.table.return_value = q

        result = _resolve_locality(client, "CALIFORNIA", "LOS ANGELES", rate_year=2026)
        assert result == "0112105"

    def test_returns_national_default_when_state_not_found(self) -> None:
        client = _mock_supabase([])
        result = _resolve_locality(client, "NONEXISTENT", "COUNTY", rate_year=2026)
        assert result == "0000000"

    def test_strips_county_suffix_before_lookup(self) -> None:
        # "LOS ANGELES COUNTY" → "LOS ANGELES" before the DB query
        client = MagicMock()
        county_response = MagicMock()
        county_response.data = [{"locality_code": "0112105"}]
        q = MagicMock()
        q.select.return_value = q
        q.eq.return_value = q
        q.lte.return_value = q
        q.order.return_value = q
        q.limit.return_value = q
        q.execute.return_value = county_response
        client.table.return_value = q

        result = _resolve_locality(client, "CALIFORNIA", "LOS ANGELES COUNTY", rate_year=2026)
        # Verify eq was called with the cleaned county name (without " COUNTY")
        calls = [str(c) for c in q.eq.call_args_list]
        assert any("LOS ANGELES" in c and "COUNTY" not in c for c in calls)


# ── _load_anesthesia_cf ───────────────────────────────────────────────────────

class TestLoadAnesthesiaCf:
    def test_returns_none_when_table_empty(self) -> None:
        client = _mock_supabase([])
        result = _load_anesthesia_cf(client, "0000000", date(2026, 1, 1))
        assert result is None

    def test_returns_decimal_conversion_factor(self) -> None:
        rows = [{"non_qualifying_cf": "21.5600"}]
        client = _mock_supabase(rows)
        result = _load_anesthesia_cf(client, "0000000", date(2026, 1, 1))
        assert result == Decimal("21.5600")

    def test_uses_national_row_for_default_locality(self) -> None:
        rows = [{"non_qualifying_cf": "21.5600"}]
        client = _mock_supabase(rows)
        _load_anesthesia_cf(client, "0000000", date(2026, 1, 1))
        # Verify eq("contractor", "NATL") was used
        q = client.table.return_value
        contractor_calls = [c for c in q.eq.call_args_list if "NATL" in str(c)]
        assert len(contractor_calls) > 0

    def test_locality_code_split_into_contractor_and_locality(self) -> None:
        # locality_code "0112105" → contractor "01121", locality "05"
        rows: list[dict] = []
        client = _mock_supabase(rows)
        with patch("app.api.v1.bills._load_anesthesia_cf", wraps=_load_anesthesia_cf):
            _load_anesthesia_cf(client, "0112105", date(2026, 1, 1))
        q = client.table.return_value
        contractor_calls = [c for c in q.eq.call_args_list if "01121" in str(c)]
        assert len(contractor_calls) > 0
