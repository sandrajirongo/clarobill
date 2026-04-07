"""Tests for the report generator.

Tests HTML generation directly (fast, no system deps).
PDF conversion requires weasyprint + cairo/pango — tested only when available.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.models.bill import BillingError, BillingErrorCode, ErrorSeverity
from app.services.parser import ParsedLineItem
from app.services.report_generator import ReportGenerator


def make_error(code: str, overcharge: float) -> BillingError:
    return BillingError(
        code=BillingErrorCode(code),
        severity=ErrorSeverity.CRITICAL,
        affected_line_item_ids=["abc"],
        description=f"Test description for {code}",
        estimated_overcharge=Decimal(str(overcharge)),
        medicare_benchmark_rate=Decimal("100.00"),
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
def generator() -> ReportGenerator:
    return ReportGenerator()


class TestBuildReportHtml:
    def test_includes_bill_file_name(self, generator: ReportGenerator) -> None:
        html = generator._build_report_html([], [], "my-bill.pdf", "No errors found.")
        assert "my-bill.pdf" in html

    def test_includes_ai_summary(self, generator: ReportGenerator) -> None:
        summary = "We found 2 potential errors totalling $430."
        html = generator._build_report_html([], [], "bill.pdf", summary)
        assert summary in html

    def test_includes_total_charges(self, generator: ReportGenerator) -> None:
        items = [make_line_item("99214", 350.00), make_line_item("85025", 120.00)]
        html = generator._build_report_html([], items, "bill.pdf", "Summary.")
        assert "470.00" in html

    def test_includes_error_descriptions(self, generator: ReportGenerator) -> None:
        errors = [make_error("DUPLICATE_CHARGE", 350.00)]
        html = generator._build_report_html(errors, [], "bill.pdf", "Summary.")
        assert "Test description for DUPLICATE_CHARGE" in html

    def test_includes_disclaimer(self, generator: ReportGenerator) -> None:
        html = generator._build_report_html([], [], "bill.pdf", "Summary.")
        assert "Disclaimer" in html

    def test_no_errors_notice_shown_when_empty(self, generator: ReportGenerator) -> None:
        html = generator._build_report_html([], [], "bill.pdf", "Clean bill.")
        assert "No billing errors were detected" in html


class TestBuildDisputeLetterHtml:
    def test_includes_letter_text(self, generator: ReportGenerator) -> None:
        letter = "Dear Billing Department,\n\nI dispute this charge.\n\nSincerely,\n[YOUR NAME]"
        html = generator._build_dispute_letter_html(letter)
        assert "I dispute this charge" in html

    def test_includes_placeholder_instruction(self, generator: ReportGenerator) -> None:
        html = generator._build_dispute_letter_html("Letter text.")
        assert "YOUR NAME" in html


def _weasyprint_available() -> bool:
    """Check whether weasyprint's system dependencies (pango, cairo) are available."""
    try:
        from weasyprint import HTML  # noqa: PLC0415
        HTML(string="<p>test</p>").write_pdf()
        return True
    except Exception:
        return False


weasyprint_available = pytest.mark.skipif(
    not _weasyprint_available(),
    reason="weasyprint system dependencies (pango/cairo) not installed",
)


class TestPdfGeneration:
    @weasyprint_available
    def test_generate_report_pdf_returns_bytes(self, generator: ReportGenerator) -> None:
        errors = [make_error("DUPLICATE_CHARGE", 350.00)]
        items = [make_line_item("99214", 350.00)]
        pdf = generator.generate_report_pdf(errors, items, "bill.pdf", "Found 1 error.")
        assert isinstance(pdf, bytes)
        assert len(pdf) > 0
        assert pdf[:4] == b"%PDF"

    @weasyprint_available
    def test_generate_dispute_letter_pdf_returns_bytes(self, generator: ReportGenerator) -> None:
        pdf = generator.generate_dispute_letter_pdf("Dear Provider,\n\n[YOUR NAME]")
        assert isinstance(pdf, bytes)
        assert pdf[:4] == b"%PDF"
