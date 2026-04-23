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


class TestGenerateReportPdf:
    def test_returns_valid_pdf(self, generator: ReportGenerator) -> None:
        pdf = generator.generate_report_pdf([], [], "my-bill.pdf", "No errors found.")
        assert isinstance(pdf, bytes)
        assert pdf[:4] == b"%PDF"

    def test_non_empty_with_errors(self, generator: ReportGenerator) -> None:
        errors = [make_error("DUPLICATE_CHARGE", 350.00)]
        items = [make_line_item("99214", 350.00)]
        pdf = generator.generate_report_pdf(errors, items, "bill.pdf", "Found 1 error.")
        assert len(pdf) > 500

    def test_no_errors_still_generates(self, generator: ReportGenerator) -> None:
        pdf = generator.generate_report_pdf([], [], "clean-bill.pdf", "Clean bill.")
        assert pdf[:4] == b"%PDF"

    def test_multiple_line_items(self, generator: ReportGenerator) -> None:
        items = [make_line_item("99214", 350.00), make_line_item("85025", 120.00)]
        pdf = generator.generate_report_pdf([], items, "bill.pdf", "Summary.")
        assert pdf[:4] == b"%PDF"

    def test_unicode_in_ai_summary_does_not_crash(self, generator: ReportGenerator) -> None:
        # Claude routinely outputs em dashes, smart quotes, ellipses
        summary = "You were overcharged — by $350. “Doubt the bill,” we say…"
        pdf = generator.generate_report_pdf([], [], "bill.pdf", summary)
        assert pdf[:4] == b"%PDF"

    def test_unicode_in_error_description_does_not_crash(self, generator: ReportGenerator) -> None:
        errors = [make_error("DUPLICATE_CHARGE", 100.00)]
        errors[0] = errors[0].model_copy(update={"description": "Charged twice — see line 3"})
        pdf = generator.generate_report_pdf(errors, [], "bill.pdf", "Summary.")
        assert pdf[:4] == b"%PDF"


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


@python_docx_available
def test_generate_dispute_letter_docx_returns_bytes(generator: ReportGenerator) -> None:
    docx_bytes = generator.generate_dispute_letter_docx("Dear Provider,\n\nDispute 1:\n\nCharged twice.\n\n[YOUR NAME]")
    assert isinstance(docx_bytes, bytes)
    assert docx_bytes[:2] == b"PK"
