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
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<meta name="color-scheme" content="light" />
<style>
  :root {{ color-scheme: light; }}
  body {{ background-color: #F4F2EC !important; }}
</style>
</head>
<body style="margin:0;padding:0;background:#F4F2EC;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">

<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#F4F2EC;">
  <tr>
    <td align="center" style="padding:40px 16px 32px;">

      <table width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:540px;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 40px rgba(0,0,0,.06);">

        <!-- Sage accent bar -->
        <tr>
          <td style="background:#2D4A2A;height:5px;font-size:0;line-height:0;">&nbsp;</td>
        </tr>

        <!-- Logo -->
        <tr>
          <td align="center" style="padding:32px 40px 0;">
            <table cellpadding="0" cellspacing="0" border="0" style="display:inline-table;">
              <tr>
                <td style="vertical-align:middle;padding-right:10px;">
                  <span style="display:inline-block;width:36px;height:36px;border-radius:9px;background:#2D4A2A;font-family:Georgia,'Times New Roman',serif;font-style:italic;font-size:18px;font-weight:700;color:#C8F060;text-align:center;line-height:36px;">C</span>
                </td>
                <td style="vertical-align:middle;">
                  <span style="font-family:Georgia,'Times New Roman',serif;font-size:22px;font-weight:700;color:#1A1A14;letter-spacing:-0.02em;">Claro<em style="font-style:italic;">Bill</em></span>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="padding:28px 40px 36px;">

            <h1 style="font-family:Georgia,'Times New Roman',serif;font-size:24px;font-weight:700;color:#1A1A14;margin:0 0 12px;line-height:1.3;letter-spacing:-0.02em;">Your report is ready</h1>

            <p style="font-size:15px;color:#5A5A50;margin:0 0 20px;line-height:1.6;">
              Your medical bill analysis for <strong style="color:#1A1A14;">{bill_file_name}</strong> is complete. Two documents are attached to this email.
            </p>

            <!-- Attachments -->
            <table cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#F4F2EC;border-radius:12px;margin:8px 0 24px;">
              <tr>
                <td style="padding:20px 24px;">
                  <p style="font-size:12px;font-weight:700;color:#2D4A2A;text-transform:uppercase;letter-spacing:0.06em;margin:0 0 12px;">Attached documents</p>
                  <p style="font-size:13px;color:#5A5A50;margin:0 0 8px;line-height:1.5;">
                    <strong style="color:#1A1A14;">ClaroBill Report (PDF)</strong> &mdash; a full breakdown of every finding, line item, and potential overcharge.
                  </p>
                  <p style="font-size:13px;color:#5A5A50;margin:0;line-height:1.5;">
                    <strong style="color:#1A1A14;">Dispute Letter (Word document)</strong> &mdash; an editable letter pre-addressed to your provider&rsquo;s billing department. Open it in Word or Google Docs, fill in your details, and send.
                  </p>
                </td>
              </tr>
            </table>

            <p style="font-size:13px;color:#9A9A8E;margin:0;line-height:1.6;">
              Questions? Email us at <a href="mailto:support@clarobill.com" style="color:#2D4A2A;text-decoration:underline;">support@clarobill.com</a> &mdash; we&rsquo;re here to help.
            </p>

          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="padding:20px 40px 28px;border-top:1px solid #E2DDD4;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td style="font-size:12px;color:#9A9A8E;">
                  &copy; 2026 ClaroBill &nbsp;&middot;&nbsp;
                  <a href="https://clarobill.com/legal/privacy" style="color:#9A9A8E;text-decoration:underline;">Privacy</a>
                  &nbsp;&middot;&nbsp;
                  <a href="https://clarobill.com/legal/terms" style="color:#9A9A8E;text-decoration:underline;">Terms</a>
                  &nbsp;&middot;&nbsp;
                  <a href="mailto:support@clarobill.com" style="color:#9A9A8E;text-decoration:underline;">support@clarobill.com</a>
                </td>
              </tr>
            </table>
          </td>
        </tr>

      </table>
    </td>
  </tr>
</table>

</body>
</html>"""
