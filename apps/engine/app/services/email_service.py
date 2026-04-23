"""Email service — sends reports and dispute letters via SendGrid.

All outbound email is funnelled through this module. Test mode logs the email
details without making any network calls — safe for CI and development.

Never log the recipient email address as it is PHI-adjacent.
"""

import base64
import logging

import sendgrid
from sendgrid.helpers.mail import (
    Attachment,
    ContentId,
    Disposition,
    FileContent,
    FileName,
    FileType,
    Mail,
)

logger = logging.getLogger(__name__)


class EmailService:
    """Sends transactional emails with PDF attachments via SendGrid."""

    def __init__(self, api_key: str, from_email: str, test_mode: bool = False) -> None:
        self._from_email = from_email
        self._test_mode = test_mode
        if not test_mode:
            self._client = sendgrid.SendGridAPIClient(api_key=api_key)

    def send_report_email(
        self,
        to_email: str,
        bill_file_name: str,
        report_pdf: bytes,
        dispute_letter_docx: bytes,
    ) -> None:
        """Send the analysis report and dispute letter to the patient.

        Args:
            to_email: Recipient email address.
            bill_file_name: Original bill filename — used in the subject line.
            report_pdf: Full analysis report PDF bytes.
            dispute_letter_docx: Editable dispute letter Word document bytes.
        """
        if self._test_mode:
            logger.info(
                "TEST MODE — email not sent. report=%d bytes, letter=%d bytes",
                len(report_pdf),
                len(dispute_letter_docx),
            )
            return

        message = Mail(
            from_email=self._from_email,
            to_emails=to_email,
            subject=f"Your ClaroBill Report — {bill_file_name}",
            html_content=self._email_body_html(bill_file_name),
        )

        docx_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        message.attachment = [
            self._make_attachment(report_pdf, "clarobill-report.pdf", "clarobill-report", "application/pdf"),
            self._make_attachment(dispute_letter_docx, "dispute-letter.docx", "dispute-letter", docx_mime),
        ]

        response = self._client.send(message)
        logger.info("Report email sent, status=%s", response.status_code)

    @staticmethod
    def _make_attachment(file_bytes: bytes, filename: str, content_id: str, mime_type: str) -> Attachment:
        attachment = Attachment()
        attachment.file_content = FileContent(base64.b64encode(file_bytes).decode())
        attachment.file_type = FileType(mime_type)
        attachment.file_name = FileName(filename)
        attachment.disposition = Disposition("attachment")
        attachment.content_id = ContentId(content_id)
        return attachment

    @staticmethod
    def _email_body_html(bill_file_name: str) -> str:
        return f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#1a1a2e">
          <div style="background:#1a1a2e;padding:24px 32px;margin-bottom:32px">
            <h1 style="color:white;font-size:20px;margin:0">Clarobill</h1>
          </div>
          <p>Your medical bill analysis is ready.</p>
          <p>We've attached two documents to this email:</p>
          <ul>
            <li><strong>ClaroBill Report (PDF)</strong> — a full breakdown of findings and potential
              overcharges on <em>{bill_file_name}</em>.</li>
            <li><strong>Dispute Letter (Word document)</strong> — an editable letter addressed to
              your provider's billing department. Open it in Word or Google Docs, fill in the
              highlighted placeholders, and send.</li>
          </ul>
          <p>If you have questions, reply to this email.</p>
          <hr style="border:none;border-top:1px solid #eee;margin:32px 0">
          <p style="font-size:11px;color:#999">
            Clarobill is an informational tool. This report does not constitute legal or medical advice.
          </p>
        </div>"""
