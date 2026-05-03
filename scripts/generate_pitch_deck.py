"""Generate ClaroBill pitch deck PDF."""
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

# 16:9 landscape, 13.333 x 7.5 inches
W, H = 960.0, 540.0
PAGE = (W, H)

SAGE = HexColor("#2D4A2A")
SAGE_DARK = HexColor("#1E3019")
LIME = HexColor("#C8F060")
CREAM = HexColor("#F4F2EC")
GRAY = HexColor("#8A8A85")
GRAY_DARK = HexColor("#5C5C58")
RULE = HexColor("#B8C2A8")

FONTS_DIR = Path("/tmp/fonts")
pdfmetrics.registerFont(TTFont("Fraunces", str(FONTS_DIR / "Fraunces-Regular.ttf")))
pdfmetrics.registerFont(TTFont("Fraunces-Bold", str(FONTS_DIR / "Fraunces-Bold.ttf")))
pdfmetrics.registerFont(TTFont("Fraunces-Italic", str(FONTS_DIR / "Fraunces-Italic.ttf")))
pdfmetrics.registerFont(TTFont("Fraunces-BoldItalic", str(FONTS_DIR / "Fraunces-BoldItalic.ttf")))
pdfmetrics.registerFont(TTFont("Syne", str(FONTS_DIR / "Syne-Regular.ttf")))
pdfmetrics.registerFont(TTFont("Syne-Medium", str(FONTS_DIR / "Syne-Medium.ttf")))
pdfmetrics.registerFont(TTFont("Syne-Bold", str(FONTS_DIR / "Syne-Bold.ttf")))

OUT = Path("/home/user/clarobill/clarobill-pitch-deck-v1.pdf")


def fill(c: canvas.Canvas, color) -> None:
    c.setFillColor(color)


def stroke(c: canvas.Canvas, color) -> None:
    c.setStrokeColor(color)


def page_bg(c: canvas.Canvas, color=CREAM) -> None:
    fill(c, color)
    c.rect(0, 0, W, H, stroke=0, fill=1)


def wordmark(c: canvas.Canvas, x: float, y: float, size: float,
             color=SAGE, dot_color=LIME) -> None:
    """Draw 'ClaroBill.' wordmark: Claro roman + Bill italic + lime period."""
    fill(c, color)
    c.setFont("Fraunces-Bold", size)
    c.drawString(x, y, "Claro")
    claro_w = c.stringWidth("Claro", "Fraunces-Bold", size)
    c.setFont("Fraunces-BoldItalic", size)
    c.drawString(x + claro_w, y, "Bill")
    bill_w = c.stringWidth("Bill", "Fraunces-BoldItalic", size)
    fill(c, dot_color)
    c.setFont("Fraunces-Bold", size)
    c.drawString(x + claro_w + bill_w, y, ".")


def wordmark_width(size: float) -> float:
    cw = pdfmetrics.stringWidth("Claro", "Fraunces-Bold", size)
    bw = pdfmetrics.stringWidth("Bill", "Fraunces-BoldItalic", size)
    dw = pdfmetrics.stringWidth(".", "Fraunces-Bold", size)
    return cw + bw + dw


def headline(c: canvas.Canvas, text: str, y: float, size: float = 36,
             x: float = 60, rule_width: float = 80) -> float:
    """Draw a headline with thin sage rule line under it. Returns y of rule line."""
    fill(c, SAGE_DARK)
    c.setFont("Fraunces-Bold", size)
    c.drawString(x, y, text)
    rule_y = y - 14
    stroke(c, SAGE)
    c.setLineWidth(1.4)
    c.line(x, rule_y, x + rule_width, rule_y)
    return rule_y


def wrap_text(text: str, font: str, size: float, max_w: float) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        candidate = (cur + " " + w).strip()
        if pdfmetrics.stringWidth(candidate, font, size) <= max_w:
            cur = candidate
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def body(c: canvas.Canvas, text: str, x: float, y: float, max_w: float,
         size: float = 14, color=GRAY_DARK, font: str = "Syne",
         leading: float = 1.55) -> float:
    fill(c, color)
    c.setFont(font, size)
    lines = wrap_text(text, font, size, max_w)
    line_h = size * leading
    for i, line in enumerate(lines):
        c.drawString(x, y - i * line_h, line)
    return y - (len(lines)) * line_h


def caption(c: canvas.Canvas, text: str, x: float, y: float, max_w: float,
            size: float = 10, color=GRAY) -> float:
    return body(c, text, x, y, max_w, size=size, color=color, font="Syne", leading=1.5)


def italic_caption(c: canvas.Canvas, text: str, x: float, y: float,
                   max_w: float, size: float = 9.5, color=GRAY) -> float:
    fill(c, color)
    c.setFont("Fraunces-Italic", size)
    lines = wrap_text(text, "Fraunces-Italic", size, max_w)
    line_h = size * 1.45
    for i, line in enumerate(lines):
        c.drawString(x, y - i * line_h, line)
    return y - len(lines) * line_h


def big_stat(c: canvas.Canvas, number: str, label: str, x: float, y: float,
             num_size: float = 64, label_size: float = 11,
             label_w: float = 240) -> None:
    fill(c, SAGE)
    c.setFont("Fraunces-Bold", num_size)
    c.drawString(x, y, number)
    fill(c, GRAY_DARK)
    c.setFont("Syne", label_size)
    # Clear the serif descender (e.g. the "$" tail in "$1,300") with proportional padding.
    label_y = y - (num_size * 0.30 + 8)
    lines = wrap_text(label, "Syne", label_size, label_w)
    for i, line in enumerate(lines):
        c.drawString(x, label_y - i * label_size * 1.45, line)


def footer(c: canvas.Canvas, slide_num: int, total: int = 12) -> None:
    wordmark(c, 60, 26, 13, color=GRAY, dot_color=LIME)
    fill(c, GRAY)
    c.setFont("Syne", 10)
    label = f"{slide_num:02d} / {total:02d}"
    tw = c.stringWidth(label, "Syne", 10)
    c.drawString(W - 60 - tw, 28, label)


# ---------- SLIDES ----------

def slide_1_title(c: canvas.Canvas) -> None:
    page_bg(c, CREAM)

    # subtle lime accent bar top-left
    fill(c, LIME)
    c.rect(60, H - 70, 56, 6, stroke=0, fill=1)

    # Wordmark, very large, centered horizontally on left-weighted layout
    size = 120
    ww = wordmark_width(size)
    x = (W - ww) / 2
    wordmark(c, x, H / 2 + 30, size)

    # Tagline
    fill(c, SAGE_DARK)
    c.setFont("Fraunces-Italic", 28)
    tag = "Find errors in your medical bill."
    tw = c.stringWidth(tag, "Fraunces-Italic", 28)
    c.drawString((W - tw) / 2, H / 2 - 20, tag)

    # Sub line
    fill(c, GRAY_DARK)
    c.setFont("Syne", 13)
    sub = "Public beta  ·  clarobill.com"
    sw = c.stringWidth(sub, "Syne", 13)
    c.drawString((W - sw) / 2, H / 2 - 50, sub)

    # Founder line at bottom
    fill(c, GRAY)
    c.setFont("Syne", 11)
    f = "Sandra Jirongo  ·  May 2026"
    fw = c.stringWidth(f, "Syne", 11)
    c.drawString((W - fw) / 2, 60, f)

    c.showPage()


def slide_2_problem(c: canvas.Canvas) -> None:
    page_bg(c, CREAM)
    headline(c, "80% of US medical bills contain at least one error.", H - 90,
             size=34, rule_width=120)

    # Three big stats in a row
    y_num = H - 230
    big_stat(c, "80%", "of medical bills contain at least one error.",
             60, y_num, num_size=78, label_w=240)
    big_stat(c, "$1,300", "average overcharge on bills above $10K.",
             370, y_num, num_size=78, label_w=240)
    big_stat(c, "1.2B", "medical bills issued in the US every year.",
             680, y_num, num_size=78, label_w=240)

    # Body
    body_text = ("Patients have no way to spot the errors. Human advocates who can "
                 "charge 25 to 35 percent of recovered savings, and take six weeks. "
                 "The result: $30 billion a year in unrecovered patient overcharges.")
    body(c, body_text, 60, 180, W - 120, size=14)

    # Citations
    italic_caption(c, "Sources: Medical Billing Advocates of America; U.S. GAO.",
                   60, 80, W - 120)

    footer(c, 2)
    c.showPage()


def slide_3_solution(c: canvas.Canvas) -> None:
    page_bg(c, CREAM)
    headline(c, "ClaroBill audits any bill in three minutes.", H - 90,
             size=34, rule_width=120)

    # Three step boxes
    box_w = 260
    gap = 30
    total_w = box_w * 3 + gap * 2
    start_x = (W - total_w) / 2
    box_y = 200
    box_h = 170

    steps = [
        ("01", "Upload", "Bill in PDF or photo."),
        ("02", "Audit", "Deep audit runs against published hospital rates and standard billing rules."),
        ("03", "Dispute", "Receive a detailed report and a ready-to-send dispute letter."),
    ]
    for i, (num, title, text) in enumerate(steps):
        x = start_x + i * (box_w + gap)
        # box
        fill(c, HexColor("#EAE8E0"))
        c.roundRect(x, box_y, box_w, box_h, 10, stroke=0, fill=1)
        # step number in lime accent
        fill(c, SAGE)
        c.setFont("Fraunces-Bold", 14)
        c.drawString(x + 22, box_y + box_h - 30, num)
        # small lime tick
        fill(c, LIME)
        c.rect(x + 22, box_y + box_h - 38, 22, 3, stroke=0, fill=1)
        # title
        fill(c, SAGE_DARK)
        c.setFont("Fraunces-Bold", 26)
        c.drawString(x + 22, box_y + box_h - 70, title)
        # description
        body(c, text, x + 22, box_y + box_h - 95, box_w - 44, size=12,
             color=GRAY_DARK, leading=1.5)

    # Sub line
    fill(c, SAGE)
    c.setFont("Fraunces-Italic", 18)
    sub = "Free to analyze. Pay only when we find savings worth disputing."
    sw = c.stringWidth(sub, "Fraunces-Italic", 18)
    c.drawString((W - sw) / 2, 130, sub)

    footer(c, 3)
    c.showPage()


def slide_4_why_now(c: canvas.Canvas) -> None:
    page_bg(c, CREAM)

    # Two-line headline to avoid overflow
    fill(c, SAGE_DARK)
    c.setFont("Fraunces-Bold", 30)
    c.drawString(60, H - 90, "The federal Hospital Price Transparency Rule")
    c.drawString(60, H - 130, "went live in 2021.")
    stroke(c, SAGE)
    c.setLineWidth(1.4)
    c.line(60, H - 148, 180, H - 148)

    # Big year stat on left, with proportional descender clearance for caption.
    num_size = 170
    num_y = H - 350
    fill(c, SAGE)
    c.setFont("Fraunces-Bold", num_size)
    c.drawString(60, num_y, "2021")

    fill(c, GRAY_DARK)
    c.setFont("Syne-Medium", 12)
    c.drawString(60, num_y - (num_size * 0.30 + 8), "the year the data became public.")

    # Right side: body
    rx = 540
    body_text = ("Every U.S. hospital is now legally required to publish their "
                 "negotiated rates with every insurer in machine-readable form.")
    body(c, body_text, rx, H - 200, W - rx - 60, size=15, color=SAGE_DARK)

    body_text2 = ("The data is public. Almost no one has built a consumer product on it. "
                  "The regulatory window is permanent.")
    body(c, body_text2, rx, H - 290, W - rx - 60, size=15, color=GRAY_DARK)

    italic_caption(c,
                   "Source: Centers for Medicare & Medicaid Services, Hospital Price Transparency Final Rule (CMS-1717-F2).",
                   60, 90, W - 120)

    footer(c, 4)
    c.showPage()


def slide_5_data_moat(c: canvas.Canvas) -> None:
    page_bg(c, CREAM)
    headline(c, "13,800 hospitals indexed.", H - 90, size=34, rule_width=120)

    # Three stat blocks
    y_num = H - 230
    big_stat(c, "13,800", "hospitals in our pricing index.",
             60, y_num, num_size=72, label_w=240)
    big_stat(c, "524M", "published rates queryable in seconds.",
             370, y_num, num_size=72, label_w=240)
    big_stat(c, "Year-partitioned", "every bill audited against the rates in force on the service date.",
             680, y_num, num_size=28, label_w=240)

    body_text = ("ClaroBill is the first consumer audit engine running directly against "
                 "the federally mandated pricing data. Every finding cites a specific dollar "
                 "in published source data. No human guesswork.")
    body(c, body_text, 60, 200, W - 120, size=14)

    italic_caption(c,
                   "Source: Centers for Medicare & Medicaid Services Hospital Price Transparency datasets, ingested 2025-2026.",
                   60, 80, W - 120)

    footer(c, 5)
    c.showPage()


def slide_6_how_it_works(c: canvas.Canvas) -> None:
    page_bg(c, CREAM)
    headline(c, "Citation-backed findings. Every dollar traceable.", H - 90,
             size=30, rule_width=120)

    # Sub headline
    fill(c, GRAY_DARK)
    c.setFont("Syne-Medium", 13)
    c.drawString(60, H - 130, "Deterministic, not predictive.")

    # Demo example block (sage card)
    card_x, card_y = 60, 160
    card_w, card_h = 540, 230
    fill(c, SAGE_DARK)
    c.roundRect(card_x, card_y, card_w, card_h, 10, stroke=0, fill=1)

    fill(c, LIME)
    c.setFont("Syne-Medium", 10)
    c.drawString(card_x + 24, card_y + card_h - 32, "EXAMPLE FINDING")

    fill(c, CREAM)
    c.setFont("Fraunces-Bold", 22)
    c.drawString(card_x + 24, card_y + card_h - 70, "CPT 99214")

    fill(c, HexColor("#D8DBC8"))
    c.setFont("Syne", 12)
    c.drawString(card_x + 24, card_y + card_h - 95, "Billed amount")
    fill(c, CREAM)
    c.setFont("Fraunces-Bold", 18)
    c.drawString(card_x + 24, card_y + card_h - 120, "$850.00")

    fill(c, HexColor("#D8DBC8"))
    c.setFont("Syne", 12)
    c.drawString(card_x + 200, card_y + card_h - 95,
                 "Saint Michael's published Aetna rate")
    fill(c, CREAM)
    c.setFont("Fraunces-Bold", 18)
    c.drawString(card_x + 200, card_y + card_h - 120, "$96.84")

    # divider line
    stroke(c, HexColor("#506849"))
    c.setLineWidth(0.6)
    c.line(card_x + 24, card_y + 70, card_x + card_w - 24, card_y + 70)

    fill(c, LIME)
    c.setFont("Syne-Medium", 10)
    c.drawString(card_x + 24, card_y + 50, "DEFENSIBLE OVERCHARGE")
    fill(c, LIME)
    c.setFont("Fraunces-Bold", 30)
    c.drawString(card_x + 24, card_y + 18, "$753.16")

    # Right side: explainer
    rx = 640
    body_text = ("A 13-rule deterministic engine checks each line item against published rates, "
                 "the hospital's own list price, billing-code combinations, and procedure-quantity edits.")
    body(c, body_text, rx, H - 200, W - rx - 60, size=13, color=SAGE_DARK)

    body_text2 = ("AI handles only patient-facing language generation, never the inference itself.")
    body(c, body_text2, rx, H - 320, W - rx - 60, size=13, color=GRAY_DARK)

    footer(c, 6)
    c.showPage()


def slide_7_traction(c: canvas.Canvas) -> None:
    page_bg(c, CREAM)
    headline(c, "60+ users in the first week. Zero marketing spend.",
             H - 90, size=30, rule_width=120)

    # Five stat blocks: 3 top row, 2 bottom row
    top_y = H - 220
    bot_y = H - 380

    big_stat(c, "60+", "unique users in the first week.",
             60, top_y, num_size=64, label_w=220)
    big_stat(c, "42", "DAU peak on launch day, May 2, 2026.",
             360, top_y, num_size=64, label_w=240)
    big_stat(c, "30%", "landing-to-second-page conversion.",
             660, top_y, num_size=64, label_w=240)

    big_stat(c, "17%", "complete a full first session (avg 2h 41m to third pageview).",
             60, bot_y, num_size=64, label_w=320)
    big_stat(c, "<100", "bills processed in beta. Every engaged cohort wants the dispute letter.",
             420, bot_y, num_size=64, label_w=420)

    body_text = ("All distribution organic so far. Twitter drove a third of traffic without paid ads.")
    body(c, body_text, 60, 90, W - 120, size=13, color=SAGE_DARK)

    footer(c, 7)
    c.showPage()


def slide_8_business_model(c: canvas.Canvas) -> None:
    page_bg(c, CREAM)
    headline(c, "Outcome-based pricing. The patient sees value before they pay.",
             H - 90, size=26, rule_width=120)

    # Pricing table (5 tiers as cards)
    tiers = [
        ("Free", "savings ≤ $20", "no fee, ever"),
        ("$14.99", "savings $20 to $150", ""),
        ("$79.99", "savings $150 to $750", ""),
        ("$129.99", "savings $750 to $1,500", ""),
        ("$199.99", "savings $1,500+", ""),
    ]
    card_w = 165
    gap = 12
    total_w = card_w * 5 + gap * 4
    start_x = (W - total_w) / 2
    card_y = 220
    card_h = 170

    for i, (price, range_, note) in enumerate(tiers):
        x = start_x + i * (card_w + gap)
        # card
        if i == 0:
            fill(c, LIME)
            c.roundRect(x, card_y, card_w, card_h, 8, stroke=0, fill=1)
            price_color = SAGE_DARK
            text_color = SAGE_DARK
        else:
            fill(c, SAGE if i == 3 else HexColor("#EAE8E0"))
            c.roundRect(x, card_y, card_w, card_h, 8, stroke=0, fill=1)
            price_color = CREAM if i == 3 else SAGE
            text_color = CREAM if i == 3 else GRAY_DARK

        fill(c, price_color)
        c.setFont("Fraunces-Bold", 26)
        c.drawString(x + 16, card_y + card_h - 50, price)
        fill(c, text_color)
        c.setFont("Syne", 11)
        for j, line in enumerate(wrap_text(range_, "Syne", 11, card_w - 32)):
            c.drawString(x + 16, card_y + card_h - 80 - j * 14, line)
        if note:
            fill(c, text_color)
            c.setFont("Fraunces-Italic", 11)
            c.drawString(x + 16, card_y + 20, note)

    # Comparison line
    fill(c, SAGE_DARK)
    c.setFont("Fraunces-Italic", 14)
    cmp_a = "Human advocates: 25 to 35 percent of recovered savings."
    aw = c.stringWidth(cmp_a, "Fraunces-Italic", 14)
    c.drawString((W - aw) / 2, 175, cmp_a)

    fill(c, GRAY_DARK)
    c.setFont("Syne", 12)
    cmp_b = ("On a $1,300 finding that's $325 to $455. ClaroBill delivers the same outcome "
             "for $129.99, in three minutes instead of six weeks.")
    bw = c.stringWidth(cmp_b, "Syne", 12)
    c.drawString((W - bw) / 2, 150, cmp_b)

    footer(c, 8)
    c.showPage()


def slide_9_unit_econ(c: canvas.Canvas) -> None:
    page_bg(c, CREAM)
    headline(c, "Unit economics that scale.", H - 90, size=34, rule_width=120)

    # Left column: unit economics
    fill(c, GRAY)
    c.setFont("Syne-Medium", 11)
    c.drawString(60, H - 140, "UNIT ECONOMICS")

    metrics = [
        ("~$70", "weighted ARPU per paid bill."),
        ("30 to 40%", "expected free-to-paid conversion."),
        ("~$140", "LTV (2 paid bills per active user per year)."),
        ("~$25", "CAC at scale (SEO + organic share)."),
        ("~5.6x", "LTV / CAC ratio."),
    ]
    y = H - 175
    for num, label in metrics:
        fill(c, SAGE)
        c.setFont("Fraunces-Bold", 26)
        c.drawString(60, y, num)
        nw = c.stringWidth(num, "Fraunces-Bold", 26)
        fill(c, GRAY_DARK)
        c.setFont("Syne", 12)
        c.drawString(60 + nw + 14, y + 6, label)
        y -= 50

    # Right column: TAM
    rx = 540
    fill(c, GRAY)
    c.setFont("Syne-Medium", 11)
    c.drawString(rx, H - 140, "MARKET SIZE")

    tams = [
        ("$5B", "/ year existing human-advocate market."),
        ("$30B", "/ year unrecovered patient overcharges."),
        ("1.2B", "medical bills issued annually."),
    ]
    y = H - 200
    for num, label in tams:
        fill(c, SAGE)
        c.setFont("Fraunces-Bold", 56)
        c.drawString(rx, y, num)
        nw = c.stringWidth(num, "Fraunces-Bold", 56)
        fill(c, GRAY_DARK)
        c.setFont("Syne", 12)
        c.drawString(rx + nw + 14, y + 14, label)
        y -= 80

    italic_caption(c, "Sources: Medical Billing Advocates of America; U.S. GAO; CMS NHE.",
                   60, 80, W - 120)
    footer(c, 9)
    c.showPage()


def slide_10_roadmap(c: canvas.Canvas) -> None:
    page_bg(c, CREAM)
    headline(c, "From consumer wedge to billing-department-as-software.",
             H - 90, size=28, rule_width=120)

    # Three tier arc visual: stacked horizontal bars
    tiers = [
        ("TODAY", "Consumer wedge.",
         "Patient-facing audit and dispute letter. Live in beta.",
         LIME, SAGE_DARK),
        ("NEXT", "B2B API. Post-Demo Day.",
         "Hospital billing teams, self-funded employers, insurance claims teams pay $50 to $200 per audit. $100M+ ARR opportunity at maturity.",
         SAGE, CREAM),
        ("END STATE", "Billing departments are software, not floors of people.",
         "ClaroBill becomes the audit infrastructure of U.S. healthcare billing.",
         SAGE_DARK, CREAM),
    ]

    bar_x = 60
    bar_w = W - 120
    bar_h = 95
    gap = 15
    start_y = H - 160 - bar_h

    for i, (tag, title, desc, bg, fg) in enumerate(tiers):
        y = start_y - i * (bar_h + gap)
        # Bar with progressive width to suggest growth
        width = bar_w * (0.55 + 0.225 * i)
        fill(c, bg)
        c.roundRect(bar_x, y, width, bar_h, 10, stroke=0, fill=1)

        # tag
        fill(c, fg)
        c.setFont("Syne-Bold", 10)
        c.drawString(bar_x + 24, y + bar_h - 24, tag)

        fill(c, fg)
        c.setFont("Fraunces-Bold", 20)
        c.drawString(bar_x + 24, y + bar_h - 50, title)

        fill(c, fg)
        c.setFont("Syne", 11)
        for j, line in enumerate(wrap_text(desc, "Syne", 11, width - 48)):
            c.drawString(bar_x + 24, y + bar_h - 70 - j * 14, line)

    footer(c, 10)
    c.showPage()


def slide_11_projection(c: canvas.Canvas) -> None:
    page_bg(c, CREAM)
    headline(c, "Conservative projection.", H - 90, size=34, rule_width=120)

    # Three-row table
    rows = [
        ("Year 1", "post-funding", "50 to 75K bills", "$1 to $2M ARR"),
        ("Year 3", "scale phase", "1M+ bills / year", "$30 to $50M ARR (consumer)"),
        ("Year 5", "platform phase", "5M+ bills / year", "$200M+ ARR (with B2B)"),
    ]

    table_x = 60
    table_w = W - 120
    row_h = 80
    start_y = H - 175

    # column widths
    c1, c2, c3 = 130, 170, 240
    col_xs = [table_x + 24, table_x + 24 + c1, table_x + 24 + c1 + c2,
              table_x + 24 + c1 + c2 + c3]

    # header
    fill(c, GRAY)
    c.setFont("Syne-Medium", 10)
    c.drawString(col_xs[0], start_y + 18, "PERIOD")
    c.drawString(col_xs[1], start_y + 18, "PHASE")
    c.drawString(col_xs[2], start_y + 18, "VOLUME")
    c.drawString(col_xs[3], start_y + 18, "ARR")

    for i, (period, phase, volume, arr) in enumerate(rows):
        y = start_y - (i + 1) * row_h
        # alternating row tint
        if i % 2 == 0:
            fill(c, HexColor("#EAE8E0"))
            c.roundRect(table_x, y, table_w, row_h - 8, 6, stroke=0, fill=1)

        fill(c, SAGE)
        c.setFont("Fraunces-Bold", 26)
        c.drawString(col_xs[0], y + 30, period)

        fill(c, GRAY_DARK)
        c.setFont("Fraunces-Italic", 14)
        c.drawString(col_xs[1], y + 34, phase)

        fill(c, SAGE_DARK)
        c.setFont("Syne-Medium", 14)
        c.drawString(col_xs[2], y + 34, volume)

        fill(c, SAGE_DARK)
        c.setFont("Fraunces-Bold", 18)
        c.drawString(col_xs[3], y + 32, arr)

    # Honest unknown line
    italic_caption(c,
                   ("Honest unknown: consumer free-to-paid conversion. Beta data supports 30 to 40 "
                    "percent, but volume is under 100 bills. Confident range at 1,000+ bills."),
                   60, 90, W - 120, size=11)

    footer(c, 11)
    c.showPage()


def slide_12_team(c: canvas.Canvas) -> None:
    page_bg(c, CREAM)
    headline(c, "Solo founder. Built every layer in three months.",
             H - 90, size=30, rule_width=120)

    # Left side: founder info
    fill(c, SAGE)
    c.setFont("Fraunces-Bold", 38)
    c.drawString(60, H - 170, "Sandra Jirongo")

    fill(c, GRAY_DARK)
    c.setFont("Fraunces-Italic", 16)
    c.drawString(60, H - 200, "Founder. Engineer. Berkeley Haas alumna.")

    body_text = ("Built the data pipeline, OCR, rules engine, frontend, payment flow, "
                 "and AI-assisted dispute letters. Solo, in Oakland.")
    body(c, body_text, 60, H - 240, 460, size=13, color=GRAY_DARK)

    # Hiring + advisor
    fill(c, GRAY)
    c.setFont("Syne-Medium", 11)
    c.drawString(60, 250, "HIRING POST-FUNDING")
    fill(c, SAGE_DARK)
    c.setFont("Syne", 12)
    c.drawString(60, 230, "Full-stack engineer (month 2).")
    c.drawString(60, 212, "Growth and SEO operator (month 3 to 4).")

    fill(c, GRAY)
    c.setFont("Syne-Medium", 11)
    c.drawString(60, 175, "ADVISORY")
    fill(c, SAGE_DARK)
    c.setFont("Syne", 12)
    c.drawString(60, 155,
                 "In active conversation with Hubert Thieblot (Founders Inc).")

    # Right side: close panel
    panel_x = 580
    panel_y = 100
    panel_w = W - panel_x - 60
    panel_h = H - 140 - panel_y
    fill(c, SAGE_DARK)
    c.roundRect(panel_x, panel_y, panel_w, panel_h, 12, stroke=0, fill=1)

    # Wordmark inside panel
    wordmark(c, panel_x + 30, panel_y + panel_h - 60, 38,
             color=CREAM, dot_color=LIME)

    fill(c, HexColor("#D8DBC8"))
    c.setFont("Fraunces-Italic", 13)
    c.drawString(panel_x + 30, panel_y + panel_h - 95,
                 "Find errors in your medical bill.")

    # divider
    stroke(c, HexColor("#506849"))
    c.setLineWidth(0.6)
    c.line(panel_x + 30, panel_y + panel_h - 125,
           panel_x + panel_w - 30, panel_y + panel_h - 125)

    # Try it
    fill(c, LIME)
    c.setFont("Syne-Medium", 10)
    c.drawString(panel_x + 30, panel_y + panel_h - 155, "TRY IT")
    fill(c, CREAM)
    c.setFont("Fraunces-Bold", 17)
    c.drawString(panel_x + 30, panel_y + panel_h - 178, "clarobill.com")
    try_url = "https://www.clarobill.com"
    c.linkURL(try_url,
              (panel_x + 30, panel_y + panel_h - 184,
               panel_x + 30 + 200, panel_y + panel_h - 162),
              relative=0)

    # Watch demo
    fill(c, LIME)
    c.setFont("Syne-Medium", 10)
    c.drawString(panel_x + 30, panel_y + panel_h - 208, "WATCH DEMO")
    fill(c, CREAM)
    c.setFont("Fraunces-Bold", 14)
    demo_label = "clarobill.com/demo"
    c.drawString(panel_x + 30, panel_y + panel_h - 230, demo_label)
    demo_url = "https://www.clarobill.com/demo"
    c.linkURL(demo_url,
              (panel_x + 30, panel_y + panel_h - 236,
               panel_x + 30 + 230, panel_y + panel_h - 214),
              relative=0)

    # Reach out
    fill(c, LIME)
    c.setFont("Syne-Medium", 10)
    c.drawString(panel_x + 30, panel_y + 50, "REACH OUT")
    fill(c, CREAM)
    c.setFont("Fraunces-Bold", 14)
    c.drawString(panel_x + 30, panel_y + 26, "sandra@clarobill.com")
    c.linkURL("mailto:sandra@clarobill.com",
              (panel_x + 30, panel_y + 20,
               panel_x + 30 + 220, panel_y + 42),
              relative=0)

    footer(c, 12)
    c.showPage()


def main() -> None:
    c = canvas.Canvas(str(OUT), pagesize=PAGE)
    c.setTitle("ClaroBill Pitch Deck")
    c.setAuthor("Sandra Jirongo")
    c.setSubject("ClaroBill Seed Pitch, May 2026")

    slide_1_title(c)
    slide_2_problem(c)
    slide_3_solution(c)
    slide_4_why_now(c)
    slide_5_data_moat(c)
    slide_6_how_it_works(c)
    slide_7_traction(c)
    slide_8_business_model(c)
    slide_9_unit_econ(c)
    slide_10_roadmap(c)
    slide_11_projection(c)
    slide_12_team(c)

    c.save()
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
