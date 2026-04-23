"""Tests for pure pipeline utility functions in app/api/v1/bills.py.

These functions have no external dependencies — all tests run in < 1ms each.
Tests for Supabase-backed loaders are in test_reference_loaders.py (mocked).
"""

from datetime import date
from decimal import Decimal

import pytest

from app.api.v1.bills import (
    _derive_ncci_context,
    _derive_rate_date,
    _map_errors_to_line_items,
    _mime_type_from_path,
)
from app.models.bill import BillingErrorCode, ErrorSeverity
from app.services.parser import ParsedLineItem
from app.services.rules_engine import DetectedError


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_line_item(cpt: str, charge: float, d: date | None = None) -> ParsedLineItem:
    return ParsedLineItem(
        cpt_code=cpt,
        description="Test procedure",
        service_date=d or date(2026, 3, 15),
        quantity=1,
        unit_charge=Decimal(str(charge)),
        total_charge=Decimal(str(charge)),
        modifier=None,
        diagnosis_pointers=[],
    )


def _make_detected_error(
    code: str,
    affected: tuple[int, ...],
    overcharge: float = 0.0,
) -> DetectedError:
    return DetectedError(
        code=code,
        severity="warning",
        affected_indices=affected,
        description="Test error",
        estimated_overcharge=Decimal(str(overcharge)),
        medicare_benchmark_rate=None,
    )


# ── _mime_type_from_path ──────────────────────────────────────────────────────

class TestMimeTypeFromPath:
    def test_pdf_extension(self) -> None:
        assert _mime_type_from_path("user/bill.pdf") == "application/pdf"

    def test_jpg_extension(self) -> None:
        assert _mime_type_from_path("user/bill.jpg") == "image/jpeg"

    def test_jpeg_extension(self) -> None:
        assert _mime_type_from_path("user/bill.jpeg") == "image/jpeg"

    def test_png_extension(self) -> None:
        assert _mime_type_from_path("user/bill.png") == "image/png"

    def test_unknown_extension_returns_octet_stream(self) -> None:
        assert _mime_type_from_path("user/bill.tiff") == "application/octet-stream"

    def test_uppercase_extension_handled(self) -> None:
        # rsplit + lower() should normalize PDF, JPG, etc.
        assert _mime_type_from_path("user/bill.PDF") == "application/pdf"

    def test_no_extension_returns_octet_stream(self) -> None:
        assert _mime_type_from_path("user/bill") == "application/octet-stream"

    def test_path_with_dots_in_directory(self) -> None:
        # Only the final suffix should be used as the extension
        assert _mime_type_from_path("user.name/bill.pdf") == "application/pdf"


# ── _derive_rate_date ─────────────────────────────────────────────────────────

class TestDeriveRateDate:
    def test_single_item_returns_its_date(self) -> None:
        items = [_make_line_item("99214", 350.0, date(2026, 3, 15))]
        assert _derive_rate_date(items) == date(2026, 3, 15)

    def test_most_common_date_wins(self) -> None:
        items = [
            _make_line_item("99214", 350.0, date(2026, 3, 15)),
            _make_line_item("85025", 120.0, date(2026, 3, 15)),
            _make_line_item("36415", 25.0, date(2026, 3, 16)),
        ]
        assert _derive_rate_date(items) == date(2026, 3, 15)

    def test_tied_frequency_picks_most_recent(self) -> None:
        items = [
            _make_line_item("99214", 350.0, date(2026, 3, 14)),
            _make_line_item("85025", 120.0, date(2026, 3, 15)),
        ]
        assert _derive_rate_date(items) == date(2026, 3, 15)

    def test_empty_list_returns_today(self) -> None:
        result = _derive_rate_date([])
        assert result == date.today()

    def test_all_same_date_returns_that_date(self) -> None:
        d = date(2025, 6, 1)
        items = [_make_line_item(c, 100.0, d) for c in ("99213", "85025", "36415")]
        assert _derive_rate_date(items) == d

    def test_item_without_service_date_is_excluded(self) -> None:
        # service_date is required in ParsedLineItem — but test that None-dated items
        # (if the field is somehow None at runtime) don't crash rate date derivation
        items = [
            _make_line_item("99214", 350.0, date(2026, 3, 15)),
            _make_line_item("85025", 120.0, date(2026, 3, 15)),
        ]
        # Simulate a None service_date by patching after construction
        # (Pydantic strict mode prevents None, so we test via object.__setattr__)
        patched = items[0]
        object.__setattr__(patched, "service_date", None)
        result = _derive_rate_date(items)
        assert result == date(2026, 3, 15)


# ── _derive_ncci_context ──────────────────────────────────────────────────────

class TestDeriveNcciContext:
    def test_standard_cpt_codes_give_practitioner_medicare(self) -> None:
        service_type, payer_type = _derive_ncci_context(["99214", "85025", "36415"], None)
        assert service_type == "practitioner"
        assert payer_type == "medicare"

    def test_medicaid_plan_type_gives_medicaid_payer(self) -> None:
        _, payer_type = _derive_ncci_context(["99214"], "medicaid")
        assert payer_type == "medicaid"

    def test_commercial_plan_type_maps_to_medicare_edits(self) -> None:
        # Commercial plans use Medicare NCCI as the national floor
        _, payer_type = _derive_ncci_context(["99214"], "commercial")
        assert payer_type == "medicare"

    def test_dme_code_prefix_e0_gives_dme_service_type(self) -> None:
        service_type, _ = _derive_ncci_context(["E0143", "99214"], None)
        assert service_type == "dme"

    def test_dme_code_prefix_k0_gives_dme_service_type(self) -> None:
        service_type, _ = _derive_ncci_context(["K0001", "85025"], None)
        assert service_type == "dme"

    def test_dme_code_prefix_l0_gives_dme_service_type(self) -> None:
        service_type, _ = _derive_ncci_context(["L0450"], None)
        assert service_type == "dme"

    def test_supply_code_prefix_a4_gives_dme_service_type(self) -> None:
        service_type, _ = _derive_ncci_context(["A4253"], None)
        assert service_type == "dme"

    def test_ambulance_code_prefix_a0_gives_dme_service_type(self) -> None:
        service_type, _ = _derive_ncci_context(["A0427"], None)
        assert service_type == "dme"

    def test_empty_code_list_gives_practitioner(self) -> None:
        service_type, payer_type = _derive_ncci_context([], None)
        assert service_type == "practitioner"
        assert payer_type == "medicare"

    def test_none_code_in_list_does_not_crash(self) -> None:
        # Handles edge case where a code could be an empty string
        service_type, _ = _derive_ncci_context(["", "99214"], None)
        assert service_type == "practitioner"


# ── _map_errors_to_line_items ─────────────────────────────────────────────────

class TestMapErrorsToLineItems:
    _LINE_IDS = [
        "uuid-0000",
        "uuid-0001",
        "uuid-0002",
        "uuid-0003",
    ]

    def test_single_error_maps_to_correct_line_item_id(self) -> None:
        error = _make_detected_error("DUPLICATE_CHARGE", (1,), 250.0)
        result = _map_errors_to_line_items([error], self._LINE_IDS)
        assert len(result) == 1
        assert result[0].affected_line_item_ids == ["uuid-0001"]

    def test_error_affecting_multiple_indices(self) -> None:
        error = _make_detected_error("DUPLICATE_CHARGE", (0, 2), 350.0)
        result = _map_errors_to_line_items([error], self._LINE_IDS)
        assert result[0].affected_line_item_ids == ["uuid-0000", "uuid-0002"]

    def test_multiple_errors_mapped_independently(self) -> None:
        errors = [
            _make_detected_error("DUPLICATE_CHARGE", (0, 1), 350.0),
            _make_detected_error("PRICE_OUTLIER", (2,), 200.0),
        ]
        result = _map_errors_to_line_items(errors, self._LINE_IDS)
        assert len(result) == 2
        assert result[0].affected_line_item_ids == ["uuid-0000", "uuid-0001"]
        assert result[1].affected_line_item_ids == ["uuid-0002"]

    def test_out_of_bounds_index_is_skipped(self) -> None:
        # If the rules engine emits an index beyond the line item count, skip it
        error = _make_detected_error("DUPLICATE_CHARGE", (0, 99), 350.0)
        result = _map_errors_to_line_items([error], self._LINE_IDS)
        # Only index 0 is valid; index 99 is out of range
        assert result[0].affected_line_item_ids == ["uuid-0000"]

    def test_empty_errors_list(self) -> None:
        result = _map_errors_to_line_items([], self._LINE_IDS)
        assert result == []

    def test_empty_line_item_ids_produces_empty_affected_list(self) -> None:
        error = _make_detected_error("DUPLICATE_CHARGE", (0,), 350.0)
        result = _map_errors_to_line_items([error], [])
        assert result[0].affected_line_item_ids == []

    def test_billing_error_code_and_severity_preserved(self) -> None:
        error = DetectedError(
            code="NCCI_UNBUNDLING",
            severity="critical",
            affected_indices=(0,),
            description="Code X bundles code Y",
            estimated_overcharge=Decimal("500.00"),
            medicare_benchmark_rate=Decimal("150.00"),
        )
        result = _map_errors_to_line_items([error], self._LINE_IDS)
        assert result[0].code == BillingErrorCode.NCCI_UNBUNDLING
        assert result[0].severity == ErrorSeverity.CRITICAL
        assert result[0].estimated_overcharge == Decimal("500.00")
        assert result[0].medicare_benchmark_rate == Decimal("150.00")

    def test_description_preserved_in_billing_error(self) -> None:
        error = _make_detected_error("PRICE_OUTLIER", (0,), 100.0)
        error_with_desc = DetectedError(
            code=error.code,
            severity=error.severity,
            affected_indices=error.affected_indices,
            description="Charge $450 is 5.3× the Medicare rate of $85",
            estimated_overcharge=error.estimated_overcharge,
            medicare_benchmark_rate=error.medicare_benchmark_rate,
        )
        result = _map_errors_to_line_items([error_with_desc], self._LINE_IDS)
        assert result[0].description == "Charge $450 is 5.3× the Medicare rate of $85"
