"""Tests for the AI analysis service.

Tests run in two modes:
  - test_mode=True  — fixture text, no API calls (existing behavior tests)
  - test_mode=False — mocked _call_gemini and _client.messages.create (provider path tests)
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
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


def _make_async_client() -> anthropic.AsyncAnthropic:
    """Return an AsyncAnthropic client with a dummy key (no real calls made)."""
    return anthropic.AsyncAnthropic(api_key="sk-ant-test")


@pytest.fixture()
def service() -> AiAnalysisService:
    """AI analysis service in test mode — no real API calls."""
    return AiAnalysisService(client=_make_async_client(), test_mode=True)


@pytest.fixture()
def live_service() -> AiAnalysisService:
    """AI analysis service with test_mode=False — providers are mocked per test."""
    return AiAnalysisService(client=_make_async_client(), test_mode=False)


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


class TestGeminiPrimaryPath:
    """Tests that Gemini is called first and its response is returned."""

    async def test_summary_uses_gemini_when_available(self, live_service: AiAnalysisService) -> None:
        errors = [make_error("DUPLICATE_CHARGE", "Duplicate", 100.00)]
        with patch.object(live_service, "_call_gemini", new=AsyncMock(return_value="Gemini summary text")) as mock_gemini:
            result = await live_service.generate_bill_summary(errors, [])
        mock_gemini.assert_awaited_once()
        assert result == "Gemini summary text"

    async def test_dispute_letter_uses_gemini_when_available(self, live_service: AiAnalysisService) -> None:
        errors = [make_error("DUPLICATE_CHARGE", "Duplicate", 200.00)]
        with patch.object(live_service, "_call_gemini", new=AsyncMock(return_value="Gemini letter text")) as mock_gemini:
            result = await live_service.generate_dispute_letter(errors, [], "bill.pdf")
        mock_gemini.assert_awaited_once()
        assert result == "Gemini letter text"

    async def test_no_empty_errors_returns_empty_letter_without_calling_gemini(
        self, live_service: AiAnalysisService
    ) -> None:
        with patch.object(live_service, "_call_gemini", new=AsyncMock()) as mock_gemini:
            result = await live_service.generate_dispute_letter([], [], "bill.pdf")
        mock_gemini.assert_not_awaited()
        assert result == ""


class TestClaudeFallbackPath:
    """Tests that Claude is used when Gemini fails, and that its response is returned."""

    def _mock_claude_response(self, text: str) -> MagicMock:
        message = MagicMock()
        message.content = [MagicMock(text=text)]
        return message

    async def test_summary_falls_back_to_claude_on_gemini_failure(self, live_service: AiAnalysisService) -> None:
        errors = [make_error("DUPLICATE_CHARGE", "Duplicate", 100.00)]
        claude_response = self._mock_claude_response("Claude summary text")
        with (
            patch.object(live_service, "_call_gemini", new=AsyncMock(side_effect=RuntimeError("Gemini 503"))),
            patch.object(live_service._client.messages, "create", new=AsyncMock(return_value=claude_response)),
        ):
            result = await live_service.generate_bill_summary(errors, [])
        assert result == "Claude summary text"

    async def test_dispute_letter_falls_back_to_claude_on_gemini_failure(self, live_service: AiAnalysisService) -> None:
        errors = [make_error("PRICE_OUTLIER", "Price outlier", 300.00)]
        claude_response = self._mock_claude_response("Claude letter text")
        with (
            patch.object(live_service, "_call_gemini", new=AsyncMock(side_effect=RuntimeError("Gemini 503"))),
            patch.object(live_service._client.messages, "create", new=AsyncMock(return_value=claude_response)),
        ):
            result = await live_service.generate_dispute_letter(errors, [], "bill.pdf")
        assert result == "Claude letter text"


class TestBothProvidersFail:
    """Tests that when both Gemini and Claude fail the exception propagates."""

    async def test_summary_propagates_claude_error_when_both_fail(self, live_service: AiAnalysisService) -> None:
        errors = [make_error("DUPLICATE_CHARGE", "Duplicate", 100.00)]
        with (
            patch.object(live_service, "_call_gemini", new=AsyncMock(side_effect=RuntimeError("Gemini down"))),
            patch.object(
                live_service._client.messages,
                "create",
                new=AsyncMock(side_effect=anthropic.APIStatusError("Claude down", response=MagicMock(status_code=529), body={})),
            ),
        ):
            with pytest.raises(anthropic.APIStatusError):
                await live_service.generate_bill_summary(errors, [])

    async def test_dispute_letter_propagates_claude_error_when_both_fail(self, live_service: AiAnalysisService) -> None:
        errors = [make_error("PRICE_OUTLIER", "Price outlier", 200.00)]
        with (
            patch.object(live_service, "_call_gemini", new=AsyncMock(side_effect=RuntimeError("Gemini down"))),
            patch.object(
                live_service._client.messages,
                "create",
                new=AsyncMock(side_effect=anthropic.APIStatusError("Claude down", response=MagicMock(status_code=529), body={})),
            ),
        ):
            with pytest.raises(anthropic.APIStatusError):
                await live_service.generate_dispute_letter(errors, [], "bill.pdf")
