"""Tests for the AI analysis service.

Uses test_mode to avoid real Anthropic API calls.
Tests that the right content is produced given known inputs.
"""

from decimal import Decimal

import pytest

from app.models.bill import BillingError, BillingErrorCode, ErrorSeverity
from app.services.ai_analysis import AiAnalysisService
from app.services.parser import ParsedLineItem
from datetime import date


def make_error(code: str, description: str, overcharge: float) -> BillingError:
    return BillingError(
        code=BillingErrorCode(code),
        severity=ErrorSeverity.CRITICAL,
        affected_line_item_ids=["abc"],
        description=description,
        estimated_overcharge=Decimal(str(overcharge)),
        medicare_benchmark_rate=None,
    )


def make_line_item(cpt: str, charge: float) -> ParsedLineItem:
    return ParsedLineItem(
        cpt_code=cpt,
        description=f"Procedure {cpt}",
        service_date=date(2026, 3, 15),
        quantity=1,
        unit_charge=charge,
        total_charge=charge,
        modifier=None,
        diagnosis_pointers=[],
    )


@pytest.fixture()
def service() -> AiAnalysisService:
    """AI analysis service in test mode — no real API calls."""
    import anthropic
    client = anthropic.Anthropic(api_key="test-key")
    return AiAnalysisService(client=client, test_mode=True)


class TestGenerateBillSummary:
    async def test_returns_no_errors_message_when_empty(self, service: AiAnalysisService) -> None:
        summary = await service.generate_bill_summary([], [])
        assert "no" in summary.lower() or "not" in summary.lower()

    async def test_mentions_error_count_when_errors_present(self, service: AiAnalysisService) -> None:
        errors = [
            make_error("DUPLICATE_CHARGE", "Duplicate charge for CPT 99214", 350.00),
            make_error("PRICE_OUTLIER", "CPT 85025 billed at 3x Medicare rate", 80.00),
        ]
        summary = await service.generate_bill_summary(errors, [])
        assert "2" in summary

    async def test_mentions_total_overcharge(self, service: AiAnalysisService) -> None:
        errors = [make_error("DUPLICATE_CHARGE", "Duplicate", 350.00)]
        summary = await service.generate_bill_summary(errors, [])
        assert "350" in summary


class TestGenerateDisputeLetter:
    async def test_returns_empty_string_when_no_errors(self, service: AiAnalysisService) -> None:
        letter = await service.generate_dispute_letter([], [], "bill.pdf")
        assert letter == ""

    async def test_letter_contains_total_overcharge(self, service: AiAnalysisService) -> None:
        errors = [make_error("DUPLICATE_CHARGE", "Duplicate charge", 350.00)]
        letter = await service.generate_dispute_letter(errors, [], "bill.pdf")
        assert "350" in letter

    async def test_letter_contains_patient_placeholder(self, service: AiAnalysisService) -> None:
        errors = [make_error("NCCI_UNBUNDLING", "Unbundling detected", 100.00)]
        letter = await service.generate_dispute_letter(errors, [], "bill.pdf")
        assert "YOUR NAME" in letter
