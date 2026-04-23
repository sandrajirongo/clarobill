"""Tests for the email service.

Uses test_mode — no real emails are sent. Verifies the service
handles both happy path and edge cases without side effects.
"""

import pytest

from app.services.email_service import EmailService


@pytest.fixture()
def service() -> EmailService:
    """Email service in test mode — no SendGrid calls."""
    return EmailService(api_key="SG.test", from_email="test@clarobill.com", test_mode=True)


class TestSendReportEmail:
    def test_does_not_raise_in_test_mode(self, service: EmailService) -> None:
        # Should complete without error and without making network calls
        service.send_report_email(
            to_email="patient@example.com",
            bill_file_name="hospital-bill.pdf",
            report_pdf=b"%PDF-test-report",
            dispute_letter_docx=b"PK\x03\x04test-docx",
        )

    def test_handles_empty_pdf_bytes(self, service: EmailService) -> None:
        # Edge case — should not raise even with empty bytes in test mode
        service.send_report_email(
            to_email="patient@example.com",
            bill_file_name="bill.pdf",
            report_pdf=b"",
            dispute_letter_docx=b"",
        )
