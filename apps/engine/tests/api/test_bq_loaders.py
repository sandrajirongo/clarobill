"""Tests for BigQuery-backed reference data loaders in app/api/v1/bills.py.

All BigQuery calls are mocked at `bq.query(...).result()` returning row dicts.
No real BigQuery client is constructed.

Coverage targets the loaders that the integration test exercises only at the
None-bq path (since `_build_bq_client` returns None in the test env). These
unit tests pin the BQ-active paths: query construction, parameter binding,
result mapping, and the graceful-empty fallbacks.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.api.v1.bills import (
    _filter_npis_with_charges,
    _load_hospital_charges,
    _load_negotiated_ceiling,
    _load_negotiated_charges,
    _query_charges_by_npi,
    _resolve_npi_by_name,
    _resolve_payer_aliases,
)


def _bq_returning(rows_per_call: list[list[dict[str, Any]]]) -> MagicMock:
    """Build a BQ client mock whose .query().result() returns rows in order.

    Each call to client.query(...) returns a fresh job whose .result() returns
    one batch of rows. Lets a single test exercise loaders that fire multiple
    queries (e.g. _resolve_npi_by_name's progressive passes).
    """
    client = MagicMock()
    jobs = []
    for batch in rows_per_call:
        job = MagicMock()
        job.result.return_value = iter(batch)
        jobs.append(job)
    client.query.side_effect = jobs
    return client


def _bq_raising(exc: Exception) -> MagicMock:
    client = MagicMock()
    job = MagicMock()
    job.result.side_effect = exc
    client.query.return_value = job
    return client


# ── _query_charges_by_npi ─────────────────────────────────────────────────────


class TestQueryChargesByNpi:
    def test_returns_decimal_dict_per_code(self) -> None:
        bq = _bq_returning([[
            {"code": "99214", "gross_charge": 425.00},
            {"code": "85025", "gross_charge": 145.50},
        ]])
        result = _query_charges_by_npi(bq, "proj.dataset", ["99214", "85025"], "1234567893", 2026)
        assert result == {
            "99214": Decimal("425.00"),
            "85025": Decimal("145.50"),
        }

    def test_quantizes_to_two_decimal_places(self) -> None:
        """Hospital MRFs publish at 4-6 decimal places; we round to cents."""
        bq = _bq_returning([[
            {"code": "99214", "gross_charge": 425.123456},
        ]])
        result = _query_charges_by_npi(bq, "proj.dataset", ["99214"], "1234567893", 2026)
        assert result["99214"] == Decimal("425.12")

    def test_returns_empty_on_query_exception(self) -> None:
        """Graceful failure: a transient BQ outage must not crash the pipeline."""
        bq = _bq_raising(RuntimeError("BQ timeout"))
        result = _query_charges_by_npi(bq, "proj.dataset", ["99214"], "1234567893", 2026)
        assert result == {}

    def test_closest_prior_year_when_exact_unavailable(self) -> None:
        """service_year=2025 with only 2024 data → returns 2024 rates (not empty)."""
        bq = _bq_returning([[{"code": "99214", "gross_charge": 395.00}]])
        result = _query_charges_by_npi(bq, "proj.dataset", ["99214"], "1234567893", 2025)
        assert result == {"99214": Decimal("395.00")}
        # Verify the query uses hospital_charges and references @service_year.
        # (bigquery is fully mocked in tests so we inspect the query string directly.)
        query_str = bq.query.call_args.args[0]
        assert "hospital_charges" in query_str
        assert "@service_year" in query_str

    def test_returns_empty_when_no_prior_year_data(self) -> None:
        """service_year=2023 but hospital only has 2024+ pricing → empty result."""
        bq = _bq_returning([[]])
        result = _query_charges_by_npi(bq, "proj.dataset", ["99214"], "1234567893", 2023)
        assert result == {}


# ── _load_hospital_charges ────────────────────────────────────────────────────


class TestLoadHospitalCharges:
    def test_returns_empty_when_bq_is_none(self) -> None:
        result = _load_hospital_charges(None, ["99214"], "1234567893", None, 2026)
        assert result == {}

    def test_returns_empty_when_no_cpt_codes(self) -> None:
        result = _load_hospital_charges(MagicMock(), [], "1234567893", None, 2026)
        assert result == {}

    def test_returns_empty_when_no_hospital_identity(self) -> None:
        """No NPI and no name → no way to query hospital-specific data."""
        result = _load_hospital_charges(MagicMock(), ["99214"], None, None, 2026)
        assert result == {}

    def test_uses_npi_directly_when_provided(self) -> None:
        """When NPI is present, skip name resolution and query directly."""
        bq = _bq_returning([[{"code": "99214", "gross_charge": 425.00}]])
        result = _load_hospital_charges(
            bq, ["99214"], hospital_npi="1234567893", hospital_name="Cleveland Clinic",
            service_year=2026,
        )
        assert result == {"99214": Decimal("425.00")}
        # Only one query — name resolution path was skipped.
        assert bq.query.call_count == 1

    def test_falls_back_to_name_resolution_when_no_npi(self) -> None:
        """Name resolution returns NPI; then the charge query fires."""
        bq = _bq_returning([
            # _resolve_npi_by_name pass 1 (name+state+zip)
            [{"hospital_npi": "1234567893"}],
            # _filter_npis_with_charges
            [{"hospital_npi": "1234567893"}],
            # _query_charges_by_npi
            [{"code": "99214", "gross_charge": 425.00}],
        ])
        result = _load_hospital_charges(
            bq, ["99214"], hospital_npi=None, hospital_name="Cleveland Clinic",
            service_year=2026, hospital_state="OH", hospital_zip="44195",
        )
        assert result == {"99214": Decimal("425.00")}

    def test_returns_empty_when_name_unresolvable(self) -> None:
        """Name resolution fails (no rows on any pass) → no charge query fires."""
        bq = _bq_returning([[], [], []])  # All three name passes empty
        result = _load_hospital_charges(
            bq, ["99214"], hospital_npi=None, hospital_name="Nonexistent Hospital",
            service_year=2026, hospital_state="ZZ",
        )
        assert result == {}


# ── _resolve_npi_by_name ──────────────────────────────────────────────────────


class TestResolveNpiByName:
    def test_returns_npi_on_first_pass_match(self) -> None:
        """name+state+zip pass succeeds and gives a single charge-bearing NPI."""
        bq = _bq_returning([
            # Pass 1: directory query
            [{"hospital_npi": "1234567893"}],
            # _filter_npis_with_charges
            [{"hospital_npi": "1234567893"}],
        ])
        npi = _resolve_npi_by_name(
            bq, "proj.dataset", "Cleveland Clinic",
            hospital_state="OH", hospital_zip="44195",
        )
        assert npi == "1234567893"

    def test_falls_through_to_name_only_when_state_pass_ambiguous(self) -> None:
        """Pass 1 (name+state+zip): 2 hits, no charges → ambiguous.
        Pass 2 (name+state): 2 hits, 1 with charges → returns that NPI."""
        bq = _bq_returning([
            # Pass 1 directory: 2 hits
            [{"hospital_npi": "1111111111"}, {"hospital_npi": "2222222222"}],
            # Pass 1 charges filter: 0 with charges → continue
            [],
            # Pass 2 directory: 2 hits
            [{"hospital_npi": "1111111111"}, {"hospital_npi": "3333333333"}],
            # Pass 2 charges filter: 1 with charges → return
            [{"hospital_npi": "3333333333"}],
        ])
        npi = _resolve_npi_by_name(
            bq, "proj.dataset", "Saint Michael's",
            hospital_state="NJ", hospital_zip="07102",
        )
        assert npi == "3333333333"

    def test_returns_none_when_all_passes_fail(self) -> None:
        bq = _bq_returning([[], [], []])
        npi = _resolve_npi_by_name(
            bq, "proj.dataset", "Nonexistent",
            hospital_state="ZZ", hospital_zip="00000",
        )
        assert npi is None

    def test_returns_none_when_query_raises(self) -> None:
        bq = _bq_raising(RuntimeError("BQ down"))
        npi = _resolve_npi_by_name(bq, "proj.dataset", "Cleveland Clinic")
        assert npi is None

    def test_skips_to_name_only_when_no_state(self) -> None:
        """No state/zip provided → only the name-only pass attempted."""
        bq = _bq_returning([
            [{"hospital_npi": "1234567893"}],
            [{"hospital_npi": "1234567893"}],
        ])
        npi = _resolve_npi_by_name(bq, "proj.dataset", "Cleveland Clinic")
        assert npi == "1234567893"
        # Only 2 calls: directory + charge filter (single pass).
        assert bq.query.call_count == 2


# ── _filter_npis_with_charges ─────────────────────────────────────────────────


class TestFilterNpisWithCharges:
    def test_returns_subset_present_in_hospital_charges(self) -> None:
        bq = _bq_returning([[{"hospital_npi": "1111111111"}]])
        result = _filter_npis_with_charges(
            bq, "proj.dataset", ["1111111111", "2222222222"],
        )
        assert result == ["1111111111"]

    def test_empty_input_returns_empty(self) -> None:
        bq = MagicMock()
        result = _filter_npis_with_charges(bq, "proj.dataset", [])
        assert result == []
        bq.query.assert_not_called()

    def test_returns_none_on_query_failure(self) -> None:
        """H15 (Phase 8.3): None signals 'presence check unavailable'
        (transient outage) — distinct from [] which means 'definitively no
        NPIs'. Caller treats None as 'abort resolution' rather than
        'narrow to next pass that may match wrong hospital'."""
        bq = _bq_raising(RuntimeError("BQ down"))
        result = _filter_npis_with_charges(bq, "proj.dataset", ["1111111111"])
        assert result is None


# ── _resolve_payer_aliases ────────────────────────────────────────────────────


class TestResolvePayerAliases:
    def test_returns_aliases_for_matching_payer_group(self) -> None:
        bq = _bq_returning([
            # Lookup query: finds canonical group
            [{"payer_group": "anthem-bcbs"}],
            # Alias fetch query
            [
                {"alias": "Anthem"},
                {"alias": "Anthem Blue Cross"},
                {"alias": "Anthem Blue Cross Blue Shield"},
            ],
        ])
        result = _resolve_payer_aliases(bq, "proj.dataset", "Anthem Blue Cross")
        assert result == ["Anthem", "Anthem Blue Cross", "Anthem Blue Cross Blue Shield"]

    def test_returns_empty_when_no_canonical_group(self) -> None:
        """Fallback path: caller switches to substring matching when this is empty."""
        bq = _bq_returning([[]])
        result = _resolve_payer_aliases(bq, "proj.dataset", "Unknown Insurer")
        assert result == []

    def test_returns_empty_when_alias_table_missing(self) -> None:
        """Pre-seed state: payer_name_aliases table doesn't exist yet."""
        bq = _bq_raising(RuntimeError("Table not found: payer_name_aliases"))
        result = _resolve_payer_aliases(bq, "proj.dataset", "Anthem")
        assert result == []

    def test_returns_empty_when_alias_fetch_fails(self) -> None:
        bq = MagicMock()
        # First query (lookup): succeeds and returns a group
        lookup_job = MagicMock()
        lookup_job.result.return_value = iter([{"payer_group": "anthem-bcbs"}])
        # Second query (alias fetch): raises
        alias_job = MagicMock()
        alias_job.result.side_effect = RuntimeError("transient")
        bq.query.side_effect = [lookup_job, alias_job]
        result = _resolve_payer_aliases(bq, "proj.dataset", "Anthem")
        assert result == []


# ── _load_negotiated_charges ──────────────────────────────────────────────────


class TestLoadNegotiatedCharges:
    def test_returns_empty_when_bq_is_none(self) -> None:
        result = _load_negotiated_charges(
            None, ["99214"], "1234567893", None, "Anthem", "Choice POS I", 2026,
        )
        assert result == {}

    def test_returns_empty_when_no_cpt_codes(self) -> None:
        result = _load_negotiated_charges(
            MagicMock(), [], "1234567893", None, "Anthem", "Choice POS I", 2026,
        )
        assert result == {}

    def test_returns_empty_when_no_payer_or_plan(self) -> None:
        """Without payer+plan, the engine has no way to query the contract rate
        — returning empty disables NEGOTIATED_RATE_EXCEEDED rather than guessing."""
        result_no_payer = _load_negotiated_charges(
            MagicMock(), ["99214"], "1234567893", None, None, "Choice POS I", 2026,
        )
        result_no_plan = _load_negotiated_charges(
            MagicMock(), ["99214"], "1234567893", None, "Anthem", None, 2026,
        )
        assert result_no_payer == {}
        assert result_no_plan == {}

    def test_returns_empty_when_no_hospital_identity(self) -> None:
        result = _load_negotiated_charges(
            MagicMock(), ["99214"], None, None, "Anthem", "Choice POS I", 2026,
        )
        assert result == {}

    def test_uses_alias_path_when_aliases_table_seeded(self) -> None:
        """payer_name_aliases returns ≥1 group → alias query fires (IN UNNEST path)."""
        bq = _bq_returning([
            # _resolve_payer_aliases lookup
            [{"payer_group": "anthem-bcbs"}],
            # _resolve_payer_aliases alias fetch
            [{"alias": "Anthem"}, {"alias": "Anthem BCBS"}],
            # main negotiated_charges query (alias path)
            [{"code": "99214", "negotiated_charge": 280.50}],
        ])
        result = _load_negotiated_charges(
            bq, ["99214"], hospital_npi="1234567893", hospital_name=None,
            payer_name="Anthem", plan_name="Choice POS I", service_year=2026,
        )
        assert result == {"99214": Decimal("280.50")}

    def test_falls_back_to_substring_when_aliases_empty(self) -> None:
        """payer_name_aliases empty → CONTAINS_SUBSTR fallback fires."""
        bq = _bq_returning([
            # _resolve_payer_aliases lookup (no rows)
            [],
            # main negotiated_charges query (substring fallback)
            [{"code": "99214", "negotiated_charge": 295.00}],
        ])
        result = _load_negotiated_charges(
            bq, ["99214"], hospital_npi="1234567893", hospital_name=None,
            payer_name="Some Niche Insurer", plan_name="HMO Plus", service_year=2026,
        )
        assert result == {"99214": Decimal("295.00")}

    def test_returns_empty_when_no_negotiated_rows(self) -> None:
        """Hospital may not publish per-payer rates for these codes — empty
        is the expected outcome, not an error."""
        bq = _bq_returning([
            [{"payer_group": "anthem-bcbs"}],
            [{"alias": "Anthem"}],
            [],  # No rows from the negotiated charges query
        ])
        result = _load_negotiated_charges(
            bq, ["99214"], hospital_npi="1234567893", hospital_name=None,
            payer_name="Anthem", plan_name="Choice POS I", service_year=2026,
        )
        assert result == {}

    def test_returns_empty_on_query_exception(self) -> None:
        bq = MagicMock()
        # _resolve_payer_aliases path - quick failure → empty alias list
        # then the main query also fails
        lookup_job = MagicMock()
        lookup_job.result.side_effect = RuntimeError("aliases table missing")
        main_job = MagicMock()
        main_job.result.side_effect = RuntimeError("hospital_charges query failed")
        bq.query.side_effect = [lookup_job, main_job]

        result = _load_negotiated_charges(
            bq, ["99214"], hospital_npi="1234567893", hospital_name=None,
            payer_name="Anthem", plan_name="Choice POS I", service_year=2026,
        )
        assert result == {}


# ── _load_negotiated_ceiling ──────────────────────────────────────────────────


class TestLoadNegotiatedCeiling:
    def test_returns_empty_when_bq_is_none(self) -> None:
        result = _load_negotiated_ceiling(None, ["99214"], "1234567893", None, 2026)
        assert result == {}

    def test_returns_empty_when_no_hospital_identity(self) -> None:
        result = _load_negotiated_ceiling(MagicMock(), ["99214"], None, None, 2026)
        assert result == {}

    def test_returns_max_negotiated_per_code_with_npi(self) -> None:
        bq = _bq_returning([
            [{"code": "99214", "ceiling_rate": 410.00},
             {"code": "85025", "ceiling_rate": 138.75}],
        ])
        result = _load_negotiated_ceiling(
            bq, ["99214", "85025"], hospital_npi="1234567893", hospital_name=None,
            service_year=2026,
        )
        assert result == {
            "99214": Decimal("410.00"),
            "85025": Decimal("138.75"),
        }

    def test_resolves_npi_from_name_when_npi_missing(self) -> None:
        bq = _bq_returning([
            # _resolve_npi_by_name pass 1 directory
            [{"hospital_npi": "1234567893"}],
            # _filter_npis_with_charges
            [{"hospital_npi": "1234567893"}],
            # main ceiling query
            [{"code": "99214", "ceiling_rate": 410.00}],
        ])
        result = _load_negotiated_ceiling(
            bq, ["99214"], hospital_npi=None,
            hospital_name="Cleveland Clinic", service_year=2026,
            hospital_state="OH", hospital_zip="44195",
        )
        assert result == {"99214": Decimal("410.00")}

    def test_returns_empty_when_name_unresolvable(self) -> None:
        bq = _bq_returning([[], [], []])  # All passes fail
        result = _load_negotiated_ceiling(
            bq, ["99214"], hospital_npi=None, hospital_name="Nonexistent",
            service_year=2026, hospital_state="ZZ",
        )
        assert result == {}

    def test_returns_empty_on_query_exception(self) -> None:
        bq = _bq_raising(RuntimeError("BQ down"))
        result = _load_negotiated_ceiling(
            bq, ["99214"], hospital_npi="1234567893", hospital_name=None,
            service_year=2026,
        )
        assert result == {}

    def test_returns_empty_when_no_ceiling_rows(self) -> None:
        bq = _bq_returning([[]])
        result = _load_negotiated_ceiling(
            bq, ["99214"], hospital_npi="1234567893", hospital_name=None,
            service_year=2026,
        )
        assert result == {}

    def test_uses_year_aware_query(self) -> None:
        """Ceiling query must target hospital_charges with @service_year filter."""
        bq = _bq_returning([[{"code": "99214", "ceiling_rate": 410.00}]])
        _load_negotiated_ceiling(
            bq, ["99214"], hospital_npi="1234567893", hospital_name=None,
            service_year=2024,
        )
        query_str = bq.query.call_args.args[0]
        assert "hospital_charges" in query_str
        assert "@service_year" in query_str
