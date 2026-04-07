"""Report generator — converts analysis results into PDF documents.

Produces two PDFs:
  1. Full analysis report — findings, error details, line item table
  2. Dispute letter — ready-to-send letter for the patient

HTML is built with Python string formatting; weasyprint converts to PDF.

Prerequisite: A 'reports' Supabase Storage bucket must exist and be private.
Create it in the Supabase dashboard: Storage → New Bucket → name: 'reports', private: true.
"""

import logging
from decimal import Decimal

from app.models.bill import BillingError
from app.services.parser import ParsedLineItem

logger = logging.getLogger(__name__)

# Severity badge colours used in the report HTML
_SEVERITY_COLOUR = {
    "critical": "#c0392b",
    "warning": "#e67e22",
    "info": "#2980b9",
}


class ReportGenerator:
    """Builds HTML and converts to PDF bytes for the analysis report and dispute letter."""

    def generate_report_pdf(
        self,
        errors: list[BillingError],
        line_items: list[ParsedLineItem],
        bill_file_name: str,
        ai_summary: str,
    ) -> bytes:
        """Generate the full analysis report as a PDF.

        Args:
            errors: Detected billing errors.
            line_items: Parsed line items from the bill.
            bill_file_name: Original uploaded file name.
            ai_summary: Plain-English summary from Claude.

        Returns:
            PDF bytes.
        """
        html = self._build_report_html(errors, line_items, bill_file_name, ai_summary)
        return self._html_to_pdf(html)

    def generate_dispute_letter_pdf(self, dispute_letter_text: str) -> bytes:
        """Convert a plain-text dispute letter to a PDF.

        Args:
            dispute_letter_text: Text output from AiAnalysisService.generate_dispute_letter().

        Returns:
            PDF bytes.
        """
        html = self._build_dispute_letter_html(dispute_letter_text)
        return self._html_to_pdf(html)

    def _build_report_html(
        self,
        errors: list[BillingError],
        line_items: list[ParsedLineItem],
        bill_file_name: str,
        ai_summary: str,
    ) -> str:
        """Build the report HTML string. Separated from PDF conversion for testability."""
        total_charges = sum(Decimal(str(item.total_charge)) for item in line_items)
        total_savings = sum(e.estimated_overcharge for e in errors)
        estimated_fair = total_charges - total_savings

        error_rows = "".join(
            f"""<tr>
              <td><span style="color:{_SEVERITY_COLOUR.get(e.severity, '#333')};font-weight:bold">
                {e.severity.upper()}</span></td>
              <td>{e.code.replace('_', ' ').title()}</td>
              <td>{e.description}</td>
              <td style="text-align:right">${e.estimated_overcharge:.2f}</td>
            </tr>"""
            for e in errors
        )

        line_item_rows = "".join(
            f"""<tr>
              <td>{item.cpt_code}</td>
              <td>{item.description[:60]}</td>
              <td>{item.service_date}</td>
              <td style="text-align:right">${item.total_charge:.2f}</td>
              <td>{item.modifier or "—"}</td>
            </tr>"""
            for item in line_items
        )

        no_errors_notice = (
            "" if errors else
            '<p style="color:#27ae60;font-weight:bold">No billing errors were detected.</p>'
        )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: Georgia, "Times New Roman", serif; color: #1a1a2e;
            font-size: 12px; line-height: 1.6; padding: 48px; }}
    .header {{ background: #1a1a2e; color: white; padding: 24px 32px;
               margin: -48px -48px 40px -48px; }}
    .header h1 {{ font-size: 22px; font-weight: bold; letter-spacing: 0.5px; }}
    .header p {{ font-size: 11px; color: #aab; margin-top: 4px; }}
    h2 {{ font-size: 15px; color: #1a1a2e; margin: 32px 0 12px; border-bottom: 1px solid #e0e0e0;
          padding-bottom: 6px; }}
    .summary-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin: 24px 0; }}
    .card {{ border: 1px solid #ddd; border-radius: 6px; padding: 16px; text-align: center; }}
    .card .value {{ font-size: 22px; font-weight: bold; color: #1a1a2e; }}
    .card .label {{ font-size: 10px; color: #888; margin-top: 4px; text-transform: uppercase; }}
    .savings .value {{ color: #27ae60; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 11px; }}
    th {{ background: #f5f7fa; text-align: left; padding: 10px 12px; font-size: 10px;
          text-transform: uppercase; letter-spacing: 0.4px; color: #555; }}
    td {{ padding: 9px 12px; border-bottom: 1px solid #f0f0f0; vertical-align: top; }}
    .ai-summary {{ background: #f8f9ff; border-left: 3px solid #1a1a2e; padding: 16px 20px;
                   margin: 16px 0; font-style: italic; font-size: 12px; color: #333; }}
    .footer {{ margin-top: 48px; padding-top: 16px; border-top: 1px solid #e0e0e0;
               font-size: 9px; color: #999; line-height: 1.5; }}
  </style>
</head>
<body>
  <div class="header">
    <h1>Clarobill — Medical Bill Analysis Report</h1>
    <p>Bill: {bill_file_name} &nbsp;|&nbsp; Generated by Clarobill AI</p>
  </div>

  <div class="summary-grid">
    <div class="card">
      <div class="value">${total_charges:.2f}</div>
      <div class="label">Total Charges</div>
    </div>
    <div class="card savings">
      <div class="value">${total_savings:.2f}</div>
      <div class="label">Potential Savings</div>
    </div>
    <div class="card">
      <div class="value">{len(errors)}</div>
      <div class="label">Issues Found</div>
    </div>
  </div>

  <h2>Summary</h2>
  <div class="ai-summary">{ai_summary}</div>

  <h2>Findings</h2>
  {no_errors_notice}
  {'<table><thead><tr><th>Severity</th><th>Type</th><th>Description</th><th>Est. Overcharge</th></tr></thead><tbody>' + error_rows + '</tbody></table>' if errors else ''}

  <h2>Line Items</h2>
  <table>
    <thead>
      <tr><th>CPT Code</th><th>Description</th><th>Service Date</th><th>Charge</th><th>Modifier</th></tr>
    </thead>
    <tbody>{line_item_rows}</tbody>
  </table>

  <div class="footer">
    <strong>Disclaimer:</strong> This report is generated by an automated analysis tool and is for
    informational purposes only. It does not constitute legal or medical advice. Billing error
    determinations are based on publicly available CMS data and AI analysis — consult a qualified
    medical billing advocate for formal disputes. Clarobill is not responsible for outcomes of
    disputes filed based on this report.
  </div>
</body>
</html>"""

    def _build_dispute_letter_html(self, dispute_letter_text: str) -> str:
        """Wrap plain-text dispute letter in a clean PDF-ready HTML shell."""
        # Convert newlines to <br> and preserve paragraph breaks
        formatted = dispute_letter_text.replace("\n\n", "</p><p>").replace("\n", "<br>")
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <style>
    body {{ font-family: Georgia, "Times New Roman", serif; color: #1a1a2e;
            font-size: 12px; line-height: 1.8; padding: 72px; max-width: 600px; margin: 0 auto; }}
    p {{ margin-bottom: 16px; }}
    .header-note {{ font-size: 9px; color: #999; margin-bottom: 40px; font-style: italic; }}
  </style>
</head>
<body>
  <p class="header-note">Generated by Clarobill — fill in [YOUR NAME], [YOUR DATE OF BIRTH],
  and [DATE] before sending.</p>
  <p>{formatted}</p>
</body>
</html>"""

    @staticmethod
    def _html_to_pdf(html: str) -> bytes:
        """Convert an HTML string to PDF bytes using weasyprint."""
        from weasyprint import HTML  # noqa: PLC0415 — deferred import avoids startup cost

        pdf_bytes = HTML(string=html).write_pdf()
        logger.info("Generated PDF (%d bytes)", len(pdf_bytes))
        return pdf_bytes
