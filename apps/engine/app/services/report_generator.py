"""Report generator — converts analysis results into PDF and DOCX documents.

Produces two outputs:
  1. Full analysis report — branded PDF via fpdf2 (pure Python, < 1 second)
  2. Dispute letter — editable DOCX the patient fills in and sends

fpdf2 uses DejaVu Sans (a Unicode TTF font, installed via fonts-dejavu-core)
so any character Claude outputs — em dashes, smart quotes, etc. — renders
correctly without a sanitizer or character-map workaround.

Prerequisite: A 'reports' Supabase Storage bucket must exist and be private.
"""

import logging
import re
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from fpdf import FPDF  # type: ignore[import-untyped]

from app.models.bill import BillingError
from app.services.parser import ParsedLineItem

logger = logging.getLogger(__name__)

# Matches lines that begin a dispute section in the Claude plain-text output
_DISPUTE_HEADER_RE = re.compile(r"^Dispute\s+\d+\s*:", re.IGNORECASE)

# Brand colors as RGB tuples
_SAGE = (45, 74, 42)
_BODY = (26, 46, 24)
_MUTED = (107, 124, 106)
_RULE = (220, 220, 215)
_GRAY = (140, 140, 140)

# DejaVu Sans is a free Unicode TTF font that covers the full range of
# characters Claude may output. fonts-dejavu-core installs it to the
# standard Debian path; the matplotlib fallback covers local dev machines.
_DEJAVU_DIRS: list[Path] = [
    Path("/usr/share/fonts/truetype/dejavu"),   # Debian/Ubuntu (Cloud Run)
    Path("/usr/share/fonts/dejavu"),             # alternate Debian path
]
try:
    import matplotlib as _mpl  # noqa: PLC0415
    _DEJAVU_DIRS.append(Path(_mpl.__file__).parent / "mpl-data" / "fonts" / "ttf")
except ImportError:
    pass


def _dejavu(name: str) -> str:
    for d in _DEJAVU_DIRS:
        p = d / name
        if p.exists():
            return str(p)
    raise FileNotFoundError(
        f"{name} not found. Install fonts-dejavu-core (Debian) or matplotlib (dev)."
    )


class ReportGenerator:
    """Builds the branded analysis report PDF and the editable dispute letter DOCX."""

    def generate_report_pdf(
        self,
        errors: list[BillingError],
        line_items: list[ParsedLineItem],
        bill_file_name: str,
        ai_summary: str,
    ) -> bytes:
        """Generate the full analysis report as a branded letterhead PDF.

        Pure Python via fpdf2 — no system dependencies, completes in < 1 second.
        The caller may still run this in a thread pool executor if needed to avoid
        blocking the asyncio event loop on large bills.
        """
        total_charges = sum(Decimal(str(item.total_charge)) for item in line_items)
        total_savings = sum(e.estimated_overcharge for e in errors)

        pdf = FPDF(orientation="P", unit="mm", format="A4")
        pdf.set_margins(20, 20, 20)
        pdf.set_auto_page_break(auto=True, margin=24)
        pdf.add_page()

        # DejaVu Sans: Unicode TTF — handles all characters Claude may output
        pdf.add_font("DejaVu", style="",  fname=_dejavu("DejaVuSans.ttf"))
        pdf.add_font("DejaVu", style="B", fname=_dejavu("DejaVuSans-Bold.ttf"))
        pdf.add_font("DejaVu", style="I", fname=_dejavu("DejaVuSans-Oblique.ttf"))

        w = pdf.w - pdf.l_margin - pdf.r_margin  # usable width: 170mm

        # ── Letterhead ──────────────────────────────────────────────────────
        pdf.set_font("DejaVu", "B", 22)
        pdf.set_text_color(*_SAGE)
        name_display = bill_file_name[:60]
        name_px = pdf.get_string_width(name_display) + 2
        pdf.cell(w - name_px, 10, "ClaroBill", align="L")
        pdf.set_font("DejaVu", "", 9)
        pdf.set_text_color(*_MUTED)
        pdf.cell(name_px, 10, name_display, align="R", new_x="LMARGIN", new_y="NEXT")
        # 3px sage rule
        pdf.set_draw_color(*_SAGE)
        pdf.set_line_width(0.7)
        y = pdf.get_y()
        pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
        pdf.ln(7)

        # ── Metrics ─────────────────────────────────────────────────────────
        col = w / 3
        metrics = [
            (f"${total_charges:.2f}", "Total Charges"),
            (f"${total_savings:.2f}", "Potential Savings"),
            (str(len(errors)), "Issues Found"),
        ]
        pdf.set_font("DejaVu", "B", 18)
        pdf.set_text_color(*_SAGE)
        for val, _ in metrics:
            pdf.cell(col, 8, val, align="L")
        pdf.ln(8)
        pdf.set_font("DejaVu", "", 7)
        pdf.set_text_color(*_MUTED)
        for _, lbl in metrics:
            pdf.cell(col, 5, lbl.upper(), align="L")
        pdf.ln(12)

        # ── Section helper ───────────────────────────────────────────────────
        def section(title: str) -> None:
            pdf.set_font("DejaVu", "B", 8)
            pdf.set_text_color(*_SAGE)
            pdf.cell(0, 5, title.upper(), new_x="LMARGIN", new_y="NEXT")
            pdf.set_draw_color(*_SAGE)
            pdf.set_line_width(0.35)
            sy = pdf.get_y()
            pdf.line(pdf.l_margin, sy, pdf.w - pdf.r_margin, sy)
            pdf.ln(4)

        # ── Summary ─────────────────────────────────────────────────────────
        section("Summary")
        pdf.set_font("DejaVu", "", 10)
        pdf.set_text_color(*_BODY)
        pdf.multi_cell(0, 5.5, ai_summary)
        pdf.ln(8)

        # ── Findings ────────────────────────────────────────────────────────
        section("Findings")
        if not errors:
            pdf.set_font("DejaVu", "I", 10)
            pdf.set_text_color(*_MUTED)
            pdf.cell(0, 6, "No billing errors were detected.", new_x="LMARGIN", new_y="NEXT")
        else:
            # col widths: Finding(50) Severity(22) Description(78) Overcharge(20)
            cw = [50, 22, 78, 20]
            hdrs = ["Finding", "Severity", "Description", "Est. Overcharge"]
            aligns = ["L", "L", "L", "R"]
            pdf.set_font("DejaVu", "B", 8)
            pdf.set_text_color(*_MUTED)
            for h, c, a in zip(hdrs, cw, aligns):
                pdf.cell(c, 5, h, border="B", align=a)
            pdf.ln()
            for e in errors:
                pdf.set_draw_color(*_RULE)
                pdf.set_line_width(0.2)
                pdf.set_font("DejaVu", "B", 9)
                pdf.set_text_color(*_BODY)
                pdf.cell(cw[0], 7, e.code.replace("_", " ".title()[:28]), border="B")
                pdf.set_font("DejaVu", "", 9)
                pdf.cell(cw[1], 7, e.severity.capitalize(), border="B")
                pdf.cell(cw[2], 7, e.description[:65], border="B")
                pdf.set_font("DejaVu", "B", 9)
                pdf.cell(cw[3], 7, f"${e.estimated_overcharge:.2f}", border="B", align="R")
                pdf.ln()

        pdf.ln(8)

        # ── Line Items ───────────────────────────────────────────────────────
        section("Line Items")
        # col widths: CPT(20) Desc(82) Date(26) Charge(24) Modifier(18)
        cw2 = [20, 82, 26, 24, 18]
        li_hdrs = ["CPT", "Description", "Date", "Charge", "Mod"]
        li_aligns = ["L", "L", "L", "R", "L"]
        pdf.set_font("DejaVu", "B", 8)
        pdf.set_text_color(*_MUTED)
        for h, c, a in zip(li_hdrs, cw2, li_aligns):
            pdf.cell(c, 5, h, border="B", align=a)
        pdf.ln()
        for item in line_items:
            pdf.set_draw_color(*_RULE)
            pdf.set_line_width(0.2)
            pdf.set_font("DejaVu", "", 9)
            pdf.set_text_color(*_BODY)
            pdf.cell(cw2[0], 7, item.cpt_code, border="B")
            pdf.cell(cw2[1], 7, item.description[:55], border="B")
            pdf.cell(cw2[2], 7, str(item.service_date), border="B")
            pdf.set_font("DejaVu", "B", 9)
            pdf.cell(cw2[3], 7, f"${item.total_charge:.2f}", border="B", align="R")
            pdf.set_font("DejaVu", "", 9)
            pdf.cell(cw2[4], 7, item.modifier or "-", border="B")
            pdf.ln()

        # ── Footer ───────────────────────────────────────────────────────────
        pdf.ln(10)
        pdf.set_draw_color(*_RULE)
        pdf.set_line_width(0.3)
        fy = pdf.get_y()
        pdf.line(pdf.l_margin, fy, pdf.w - pdf.r_margin, fy)
        pdf.ln(4)
        pdf.set_font("DejaVu", "I", 9)
        pdf.set_text_color(*_SAGE)
        pdf.cell(0, 5, "ClaroBill", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("DejaVu", "", 8)
        pdf.set_text_color(*_GRAY)
        pdf.multi_cell(0, 4.5, (
            "Prepared using verified Medicare fee schedule data and AI-assisted billing analysis. "
            "ClaroBill cross-references your charges against published hospital prices, Medicare "
            "benchmark rates, and NCCI coding rules to identify errors and overcharges. "
            "Use this report to support a billing dispute with your provider or insurer."
        ))

        pdf_bytes = bytes(pdf.output())
        logger.info("Generated report PDF (%d bytes)", len(pdf_bytes))
        return pdf_bytes

    def generate_dispute_letter_docx(self, dispute_letter_text: str) -> bytes:
        """Convert the plain-text dispute letter to an editable Word document (.docx).

        The letter is parsed into paragraphs split on blank lines. Lines matching
        'Dispute N:' are rendered as bold section headers so the patient can navigate
        each dispute item easily before editing.
        """
        from docx import Document  # noqa: PLC0415
        from docx.shared import Pt, RGBColor  # noqa: PLC0415

        doc = Document()

        for section in doc.sections:
            from docx.shared import Inches  # noqa: PLC0415
            section.top_margin = Inches(1)
            section.bottom_margin = Inches(1)
            section.left_margin = Inches(1.25)
            section.right_margin = Inches(1.25)

        style = doc.styles["Normal"]
        style.font.name = "Georgia"
        style.font.size = Pt(11)

        def _add_para(
            text: str,
            bold: bool = False,
            space_before: int = 0,
            space_after: int = 10,
        ) -> None:
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(space_before)
            p.paragraph_format.space_after = Pt(space_after)
            p.paragraph_format.line_spacing = Pt(14)
            run = p.add_run(text)
            run.font.name = "Georgia"
            run.font.size = Pt(11)
            run.bold = bold
            run.font.color.rgb = RGBColor(0x00, 0x00, 0x00)

        paragraphs = [blk.strip() for blk in dispute_letter_text.split("\n\n") if blk.strip()]

        for block in paragraphs:
            lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
            if not lines:
                continue

            first_line = lines[0]
            is_dispute_header = bool(_DISPUTE_HEADER_RE.match(first_line))

            if is_dispute_header:
                _add_para(first_line, bold=True, space_before=8, space_after=4)
                body = " ".join(lines[1:])
                if body:
                    _add_para(body, space_after=10)
            elif len(lines) > 1:
                for ln in lines:
                    _add_para(ln, space_after=2)
                doc.add_paragraph().paragraph_format.space_after = Pt(6)
            else:
                _add_para(first_line, space_after=10)

        buf = BytesIO()
        doc.save(buf)
        logger.info("Generated dispute letter DOCX (%d bytes)", buf.tell())
        return buf.getvalue()
