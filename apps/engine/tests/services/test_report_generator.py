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
        assert "informational purposes only" in html

    def test_no_errors_notice_shown_when_empty(self, generator: ReportGenerator) -> None:
        html = generator._build_report_html([], [], "bill.pdf", "Clean bill.")
        assert "No billing errors were detected" in html


def _python_docx_available() -> bool:
    try:
        import docx  # noqa: PLC0415, F401
        return True
    except ImportError:
        return False


python_docx_available = pytest.mark.skipif(
    not _python_docx_available(),
    reason="python-docx not installed",
)


class TestDisputeLetterDocx:
    @python_docx_available
    def test_returns_bytes(self, generator: ReportGenerator) -> None:
        letter = "Dear Billing Department,\n\nI dispute this charge.\n\nSincerely,\n[YOUR NAME]"
        result = generator.generate_dispute_letter_docx(letter)
        assert isinstance(result, bytes)
        assert len(result) > 0

    @python_docx_available
    def test_docx_magic_bytes(self, generator: ReportGenerator) -> None:
        result = generator.generate_dispute_letter_docx("Dispute 1:\n\nCharged twice.\n\nSincerely,\n[YOUR NAME]")
        # DOCX is a ZIP archive — starts with PK magic bytes
        assert result[:2] == b"PK"

    @python_docx_available
    def test_dispute_header_bold(self, generator: ReportGenerator) -> None:
        from docx import Document  # noqa: PLC0415
        from io import BytesIO  # noqa: PLC0415
        letter = "Dispute 1: Duplicate charge.\n\nYou were charged twice for CPT 99214.\n\nSincerely,\n[YOUR NAME]"
        result = generator.generate_dispute_letter_docx(letter)
        doc = Document(BytesIO(result))
        bold_runs = [r for p in doc.paragraphs for r in p.runs if r.bold]
        assert any("Dispute 1" in r.text for r in bold_runs)


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

    @python_docx_available
    def test_generate_dispute_letter_docx_returns_bytes(self, generator: ReportGenerator) -> None:
        docx_bytes = generator.generate_dispute_letter_docx("Dear Provider,\n\nDispute 1:\n\nCharged twice.\n\n[YOUR NAME]")
        assert isinstance(docx_bytes, bytes)
        assert docx_bytes[:2] == b"PK"
