"""Report generator — converts analysis results into PDF and DOCX documents.

Produces two outputs:
  1. Full analysis report — branded PDF (findings, line items, AI summary)
  2. Dispute letter — editable DOCX the patient fills in and sends

HTML → PDF via WeasyPrint (synchronous, run in executor by the caller).
Dispute letter → DOCX via python-docx (fast, in-memory).

Prerequisite: A 'reports' Supabase Storage bucket must exist and be private.
Create it in the Supabase dashboard: Storage → New Bucket → name: 'reports', private: true.
"""

import logging
import re
from decimal import Decimal
from io import BytesIO

from app.models.bill import BillingError
from app.services.parser import ParsedLineItem

logger = logging.getLogger(__name__)

_SEVERITY_BADGE = {
    "critical": ("CRITICAL", "#991b1b", "#fee2e2"),
    "warning": ("WARNING", "#92400e", "#fef3c7"),
    "info": ("INFO", "#1e40af", "#dbeafe"),
}

# Matches lines that begin a dispute section in the Claude plain-text output
_DISPUTE_HEADER_RE = re.compile(r"^Dispute\s+\d+\s*:", re.IGNORECASE)


class ReportGenerator:
    """Builds the branded analysis report PDF and the editable dispute letter DOCX."""

    def generate_report_pdf(
        self,
        errors: list[BillingError],
        line_items: list[ParsedLineItem],
        bill_file_name: str,
        ai_summary: str,
    ) -> bytes:
        """Generate the full analysis report as a branded PDF.

        This method is synchronous (WeasyPrint) — the caller must run it in a
        thread pool executor so it does not block the asyncio event loop.
        """
        html = self._build_report_html(errors, line_items, bill_file_name, ai_summary)
        return self._html_to_pdf(html)

    def generate_dispute_letter_docx(self, dispute_letter_text: str) -> bytes:
        """Convert the plain-text dispute letter to an editable Word document (.docx).

        The letter is parsed into paragraphs split on blank lines. Lines matching
        'Dispute N:' are rendered as bold section headers so the patient can navigate
        each dispute item easily before editing.
        """
        from docx import Document  # noqa: PLC0415
        from docx.shared import Pt, RGBColor  # noqa: PLC0415
        from docx.oxml.ns import qn  # noqa: PLC0415
        from docx.oxml import OxmlElement  # noqa: PLC0415

        doc = Document()

        # Page margins
        for section in doc.sections:
            from docx.shared import Inches  # noqa: PLC0415
            section.top_margin = Inches(1)
            section.bottom_margin = Inches(1)
            section.left_margin = Inches(1.25)
            section.right_margin = Inches(1.25)

        # Default body style
        style = doc.styles["Normal"]
        style.font.name = "Georgia"
        style.font.size = Pt(11)

        def _add_para(text: str, bold: bool = False, space_before: int = 0, space_after: int = 10) -> None:
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(space_before)
            p.paragraph_format.space_after = Pt(space_after)
            p.paragraph_format.line_spacing = Pt(14)
            run = p.add_run(text)
            run.font.name = "Georgia"
            run.font.size = Pt(11)
            run.bold = bold
            if bold:
                run.font.color.rgb = RGBColor(0x2D, 0x4A, 0x2A)  # sage

        # Split on blank lines → paragraphs
        paragraphs = [blk.strip() for blk in dispute_letter_text.split("\n\n") if blk.strip()]

        for block in paragraphs:
            # Each block may contain multiple lines (e.g., recipient address block)
            lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
            if not lines:
                continue

            first_line = lines[0]
            is_dispute_header = bool(_DISPUTE_HEADER_RE.match(first_line))

            if is_dispute_header:
                # "Dispute N:" line bold, rest of block as regular paragraph
                _add_para(first_line, bold=True, space_before=8, space_after=4)
                body = " ".join(lines[1:])
                if body:
                    _add_para(body, space_after=10)
            elif len(lines) > 1:
                # Multi-line block (address block, closing) — one paragraph per line
                for ln in lines:
                    _add_para(ln, space_after=2)
                # Extra gap after the block
                doc.add_paragraph().paragraph_format.space_after = Pt(6)
            else:
                _add_para(first_line, space_after=10)

        buf = BytesIO()
        doc.save(buf)
        logger.info("Generated dispute letter DOCX (%d bytes)", buf.tell())
        return buf.getvalue()

    def _build_report_html(
        self,
        errors: list[BillingError],
        line_items: list[ParsedLineItem],
        bill_file_name: str,
        ai_summary: str,
    ) -> str:
        total_charges = sum(Decimal(str(item.total_charge)) for item in line_items)
        total_savings = sum(e.estimated_overcharge for e in errors)

        def _badge(severity: str) -> str:
            label, color, bg = _SEVERITY_BADGE.get(severity, ("INFO", "#1e40af", "#dbeafe"))
            return (
                f'<span style="display:inline-block;padding:2px 8px;border-radius:4px;'
                f'background:{bg};color:{color};font-size:9px;font-weight:700;'
                f'letter-spacing:0.5px;text-transform:uppercase">{label}</span>'
            )

        error_rows = "".join(
            f"""<tr>
              <td style="padding:10px 12px;border-bottom:1px solid #e8e4da;background:{'#faf9f5' if i % 2 else 'white'}">{_badge(e.severity)}</td>
              <td style="padding:10px 12px;border-bottom:1px solid #e8e4da;background:{'#faf9f5' if i % 2 else 'white'};font-weight:600">{e.code.replace('_', ' ').title()}</td>
              <td style="padding:10px 12px;border-bottom:1px solid #e8e4da;background:{'#faf9f5' if i % 2 else 'white'}">{e.description}</td>
              <td style="padding:10px 12px;border-bottom:1px solid #e8e4da;background:{'#faf9f5' if i % 2 else 'white'};text-align:right;font-weight:700;color:#2D4A2A">${e.estimated_overcharge:.2f}</td>
            </tr>"""
            for i, e in enumerate(errors)
        )

        line_item_rows = "".join(
            f"""<tr>
              <td style="padding:9px 12px;border-bottom:1px solid #e8e4da;background:{'#faf9f5' if i % 2 else 'white'};font-weight:600">{item.cpt_code}</td>
              <td style="padding:9px 12px;border-bottom:1px solid #e8e4da;background:{'#faf9f5' if i % 2 else 'white'}">{item.description[:60]}</td>
              <td style="padding:9px 12px;border-bottom:1px solid #e8e4da;background:{'#faf9f5' if i % 2 else 'white'}">{item.service_date}</td>
              <td style="padding:9px 12px;border-bottom:1px solid #e8e4da;background:{'#faf9f5' if i % 2 else 'white'};text-align:right">${item.total_charge:.2f}</td>
              <td style="padding:9px 12px;border-bottom:1px solid #e8e4da;background:{'#faf9f5' if i % 2 else 'white'};color:#6b7c6a">{item.modifier or '—'}</td>
            </tr>"""
            for i, item in enumerate(line_items)
        )

        findings_table = (
            f"""<table style="width:100%;border-collapse:collapse;margin-top:12px;font-size:11px">
              <thead>
                <tr>
                  <th style="background:#2D4A2A;color:#C8F060;text-align:left;padding:10px 12px;font-size:9px;text-transform:uppercase;letter-spacing:0.6px">Severity</th>
                  <th style="background:#2D4A2A;color:#C8F060;text-align:left;padding:10px 12px;font-size:9px;text-transform:uppercase;letter-spacing:0.6px">Type</th>
                  <th style="background:#2D4A2A;color:#C8F060;text-align:left;padding:10px 12px;font-size:9px;text-transform:uppercase;letter-spacing:0.6px">Description</th>
                  <th style="background:#2D4A2A;color:#C8F060;text-align:right;padding:10px 12px;font-size:9px;text-transform:uppercase;letter-spacing:0.6px">Est. Overcharge</th>
                </tr>
              </thead>
              <tbody>{error_rows}</tbody>
            </table>"""
            if errors else
            '<p style="color:#2D4A2A;font-weight:600;padding:12px 0">No billing errors were detected.</p>'
        )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <style>
    /* System fonts only — no external @import so WeasyPrint renders without network I/O */
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: Arial, 'Liberation Sans', sans-serif; color: #1a2e18;
            background: #F4F2EC; font-size: 12px; line-height: 1.6; padding: 48px; }}
    .header {{ background: #2D4A2A; padding: 28px 36px; margin: -48px -48px 40px -48px; }}
    .logo {{ font-family: Georgia, 'Liberation Serif', serif; font-size: 28px; font-weight: 700;
             font-style: italic; letter-spacing: -0.5px; }}
    .logo .claro {{ color: #C8F060; }}
    .logo .bill {{ color: white; font-style: normal; }}
    .header-sub {{ font-size: 11px; color: #8aab86; margin-top: 6px; }}
    h2 {{ font-family: Georgia, 'Liberation Serif', serif; font-size: 16px; color: #2D4A2A;
          margin: 36px 0 14px; padding-bottom: 8px;
          border-bottom: 2px solid #C8F060; }}
    .summary-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin: 28px 0; }}
    .card {{ background: white; border: 1px solid #ddd; border-radius: 8px; padding: 20px; text-align: center; }}
    .card-savings {{ background: #2D4A2A; border-color: #2D4A2A; }}
    .value {{ font-family: Georgia, 'Liberation Serif', serif; font-size: 26px; font-weight: 700; color: #2D4A2A; }}
    .value-savings {{ color: #C8F060; }}
    .label {{ font-size: 9px; color: #6b7c6a; margin-top: 6px;
              text-transform: uppercase; letter-spacing: 0.7px; }}
    .label-savings {{ color: #8aab86; }}
    .ai-summary {{ background: white; border-left: 4px solid #C8F060; padding: 18px 22px;
                   margin: 16px 0 4px; font-size: 13px; color: #1a2e18; line-height: 1.75;
                   font-style: italic; }}
    .footer {{ margin-top: 52px; padding-top: 16px; border-top: 1px solid #d4d0c8;
               font-size: 9px; color: #888; line-height: 1.6; }}
    .watermark {{ font-family: Georgia, 'Liberation Serif', serif; font-size: 10px;
                  color: #2D4A2A; font-style: italic; margin-bottom: 6px; }}
  </style>
</head>
<body>
  <div class="header">
    <div class="logo"><span class="claro">Claro</span><span class="bill">Bill</span></div>
    <div class="header-sub">Medical Bill Analysis Report &nbsp;|&nbsp; {bill_file_name}</div>
  </div>

  <div class="summary-grid">
    <div class="card">
      <div class="value">${total_charges:.2f}</div>
      <div class="label">Total Charges</div>
    </div>
    <div class="card card-savings">
      <div class="value value-savings">${total_savings:.2f}</div>
      <div class="label label-savings">Potential Savings</div>
    </div>
    <div class="card">
      <div class="value">{len(errors)}</div>
      <div class="label">Issues Found</div>
    </div>
  </div>

  <h2>Summary</h2>
  <div class="ai-summary">{ai_summary}</div>

  <h2>Findings</h2>
  {findings_table}

  <h2>Line Items</h2>
  <table style="width:100%;border-collapse:collapse;margin-top:12px;font-size:11px">
    <thead>
      <tr>
        <th style="background:#2D4A2A;color:#C8F060;text-align:left;padding:10px 12px;font-size:9px;text-transform:uppercase;letter-spacing:0.6px">CPT Code</th>
        <th style="background:#2D4A2A;color:#C8F060;text-align:left;padding:10px 12px;font-size:9px;text-transform:uppercase;letter-spacing:0.6px">Description</th>
        <th style="background:#2D4A2A;color:#C8F060;text-align:left;padding:10px 12px;font-size:9px;text-transform:uppercase;letter-spacing:0.6px">Service Date</th>
        <th style="background:#2D4A2A;color:#C8F060;text-align:right;padding:10px 12px;font-size:9px;text-transform:uppercase;letter-spacing:0.6px">Charge</th>
        <th style="background:#2D4A2A;color:#C8F060;text-align:left;padding:10px 12px;font-size:9px;text-transform:uppercase;letter-spacing:0.6px">Modifier</th>
      </tr>
    </thead>
    <tbody>{line_item_rows}</tbody>
  </table>

  <div class="footer">
    <div class="watermark">ClaroBill</div>
    This report is generated by an automated analysis tool for informational purposes only.
    It does not constitute legal or medical advice. Billing error determinations are based on
    publicly available CMS data and AI analysis — consult a qualified medical billing advocate
    for formal disputes. ClaroBill is not responsible for outcomes of disputes filed based on
    this report.
  </div>
</body>
</html>"""

    @staticmethod
    def _html_to_pdf(html: str) -> bytes:
        from weasyprint import HTML  # noqa: PLC0415
        pdf_bytes = HTML(string=html).write_pdf()
        logger.info("Generated report PDF (%d bytes)", len(pdf_bytes))
        return pdf_bytes
