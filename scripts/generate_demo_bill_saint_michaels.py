"""Generate a demo Saint Michaels itemized bill for the YC Loom walkthrough.

Mirrors the visual layout of Sandra's real Sutter Health bill
(Jirongo2026.pdf) so the Loom flow is visually consistent — but populated
with the validated Saint Michaels CPT 99214 overcharge data so the rules
engine produces a defensible, citation-backed finding when it runs.

Real reference data anchoring the demo (verified via BigQuery on 2026-05-01):
  - Hospital:  Saint Michael's Medical Center, Newark NJ (NPI 1568825545)
  - CPT 99214: $683.00 hospital gross, $96.84 Aetna negotiated rate
  - Headline: $850 billed (synthetic) → $753.16 defensible overcharge

Usage:
  python3 scripts/generate_demo_bill_saint_michaels.py
  → writes ~/Downloads/StMichaels-demo-bill.pdf
"""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF


# ── Demo bill data ──────────────────────────────────────────────────────────

PATIENT_NAME = "Jirongo, Sandra"
PATIENT_ADDR = ["312 24th St", "Apt 1220", "Oakland, CA 94612-4095"]
PATIENT_ACCT = "445082216"
INSURANCE = "Aetna"

HOSPITAL = "Saint Michael's Medical Center"
HOSPITAL_ADDR = ["111 Central Avenue", "Newark, NJ 07102-1903"]
HOSPITAL_PHONE = "973-877-5000"
HOSPITAL_EMAIL = "billing@smmcnj.org"

DATE_OF_BILL = "06/15/24"
ADMIT_DATE = "06/01/24"
DISCHARGE_DATE = "06/01/24"

# Line items. Every code is real; charges are within the realistic range
# observed across this hospital's published chargemaster. The keystone
# overcharge is CPT 99214 at $850 (the figure the rules engine flags
# against Saint Michaels' published Aetna negotiated rate of $96.84).
LINE_ITEMS = [
    # (svc_date, rev_code, cpt, px_number, description, qty, amount)
    ("06/01/2024", "0301", "85025", "43000009", "HCHG CBC AUTOMATED W/ AUTOMATED DIFFERENTIAL", 1, 217.00),
    ("06/01/2024", "0301", "80053", "42000004", "HCHG COMPREHENSIVE METABOLIC PANEL", 1, 471.00),
    ("06/01/2024", "0307", "81001", "47000001", "HCHG URINALYSIS AUTOMATED W/ MICROSCOPIC EXAM", 1, 141.00),
    ("06/01/2024", "0309", "36415", "47100001", "HCHG VENIPUNCTURE", 1, 50.00),
    ("06/01/2024", "0510", "99214", "55000214", "HCHG OFFICE/OUTPATIENT VISIT EST PT MOD COMPLEX", 1, 850.00),
    ("06/01/2024", "0450", "99284", "55000036", "HCHG ED LEVEL 4 W/PROC", 1, 1457.00),
]
TOTAL_CHARGES = sum(item[6] for item in LINE_ITEMS)

# Synthetic insurer payments + balance to mirror the Sutter bill structure.
INSURER_PAYMENT = 1850.00
INSURER_ADJUSTMENT = 850.00
DEDUCTIBLE = 200.00
COINSURANCE = 86.00
TOTAL_PAYMENTS = INSURER_PAYMENT + INSURER_ADJUSTMENT
CURRENT_BALANCE = TOTAL_CHARGES - TOTAL_PAYMENTS

# Summary by revenue code (totals by category — matches the Sutter format).
REV_SUMMARY = [
    ("0300", "Laboratory - General Classification", 879.00),
    ("0500", "Outpatient Services - General Classification", 850.00),
    ("0450", "Emergency Room - General Classification", 1457.00),
]


# ── PDF rendering ───────────────────────────────────────────────────────────

PAGE_W = 8.5  # inches (Letter)
PAGE_H = 11.0
MARGIN = 0.5

# Sutter uses #00A88E-ish teal for the header. We use a generic dark teal
# stand-in for the Saint Michaels demo so we don't clone Sutter's logo color
# pixel-for-pixel.
TEAL = (0, 119, 124)


def _write_pdf(out_path: Path) -> None:
    pdf = FPDF(orientation="P", unit="in", format="Letter")
    pdf.set_auto_page_break(False)
    pdf.add_page()

    # ── Header ──────────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*TEAL)
    pdf.set_xy(MARGIN, 0.5)
    pdf.cell(3.5, 0.35, "Saint Michael's Medical Center", border=0)

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_xy(4.5, 0.5)
    pdf.multi_cell(
        3.5,
        0.16,
        f"For billing inquiries, please contact us at {HOSPITAL_PHONE}.\n"
        f"Office hours Monday through Friday 8:00 AM to 5:00 PM.\n"
        f"You may email us at {HOSPITAL_EMAIL}.",
    )

    # ── Services Provided + Patient Account block ──────────────────────────
    y = 1.15
    pdf.set_font("Helvetica", "", 9)
    pdf.set_xy(MARGIN, y)
    pdf.cell(3.5, 0.18, "Services Provided at:")
    pdf.set_xy(MARGIN, y + 0.18)
    pdf.cell(3.5, 0.18, HOSPITAL)
    pdf.set_xy(MARGIN, y + 0.36)
    pdf.cell(3.5, 0.18, HOSPITAL_ADDR[0])
    pdf.set_xy(MARGIN, y + 0.54)
    pdf.cell(3.5, 0.18, HOSPITAL_ADDR[1])

    # Right block: Patient Name / Patient Account #
    box_x = 4.6
    box_w = 3.4
    pdf.set_draw_color(0, 0, 0)
    pdf.rect(box_x, y, box_w, 0.7)
    pdf.line(box_x + box_w / 2, y, box_x + box_w / 2, y + 0.7)
    pdf.line(box_x, y + 0.22, box_x + box_w, y + 0.22)

    pdf.set_font("Helvetica", "B", 9)
    pdf.set_xy(box_x, y)
    pdf.cell(box_w / 2, 0.22, "Patient Name", align="C")
    pdf.set_xy(box_x + box_w / 2, y)
    pdf.cell(box_w / 2, 0.22, "Patient Account #", align="C")

    pdf.set_font("Helvetica", "", 9)
    pdf.set_xy(box_x, y + 0.22)
    pdf.cell(box_w / 2, 0.48, PATIENT_NAME, align="C")
    pdf.set_xy(box_x + box_w / 2, y + 0.22)
    pdf.cell(box_w / 2, 0.48, PATIENT_ACCT, align="C")

    # Date of Bill / Admit / Discharge box, immediately below
    y2 = y + 0.85
    pdf.rect(box_x, y2, box_w, 0.4)
    third = box_w / 3
    pdf.line(box_x + third, y2, box_x + third, y2 + 0.4)
    pdf.line(box_x + 2 * third, y2, box_x + 2 * third, y2 + 0.4)
    pdf.line(box_x, y2 + 0.2, box_x + box_w, y2 + 0.2)

    pdf.set_font("Helvetica", "B", 9)
    pdf.set_xy(box_x, y2)
    pdf.cell(third, 0.2, "Date of Bill", align="C")
    pdf.set_xy(box_x + third, y2)
    pdf.cell(third, 0.2, "Admit Date", align="C")
    pdf.set_xy(box_x + 2 * third, y2)
    pdf.cell(third, 0.2, "Discharge Date", align="C")

    pdf.set_font("Helvetica", "", 9)
    pdf.set_xy(box_x, y2 + 0.2)
    pdf.cell(third, 0.2, DATE_OF_BILL, align="C")
    pdf.set_xy(box_x + third, y2 + 0.2)
    pdf.cell(third, 0.2, ADMIT_DATE, align="C")
    pdf.set_xy(box_x + 2 * third, y2 + 0.2)
    pdf.cell(third, 0.2, DISCHARGE_DATE, align="C")

    # ── Patient address block + Insurance Company box ──────────────────────
    y3 = y2 + 0.55
    pdf.set_font("Helvetica", "", 9)
    pdf.set_xy(MARGIN, y3)
    pdf.cell(3.5, 0.18, "Sandra Jirongo")
    pdf.set_xy(MARGIN, y3 + 0.18)
    pdf.cell(3.5, 0.18, PATIENT_ADDR[0])
    pdf.set_xy(MARGIN, y3 + 0.36)
    pdf.cell(3.5, 0.18, PATIENT_ADDR[1])
    pdf.set_xy(MARGIN, y3 + 0.54)
    pdf.cell(3.5, 0.18, PATIENT_ADDR[2])

    pdf.rect(box_x, y3, box_w, 0.42)
    pdf.line(box_x, y3 + 0.21, box_x + box_w, y3 + 0.21)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_xy(box_x + 0.05, y3 + 0.02)
    pdf.cell(box_w - 0.1, 0.18, "Insurance Company")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_xy(box_x + 0.05, y3 + 0.21)
    pdf.cell(box_w - 0.1, 0.18, f"{INSURANCE} - {INSURANCE} PPO")

    # ── Charges section ────────────────────────────────────────────────────
    y_charges = y3 + 0.85
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_xy(MARGIN, y_charges)
    pdf.cell(3, 0.22, "Charges")
    y_charges += 0.28

    # Column headers
    cols = [
        ("Svc Date", 0.85),
        ("Rev Code", 0.7),
        ("CPT(R)/HCPCS Code", 1.25),
        ("Px Number", 0.85),
        ("Description", 2.85),
        ("Qty", 0.4),
        ("Amt", 0.6),
    ]
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(230, 230, 230)
    x = MARGIN
    pdf.set_xy(MARGIN, y_charges)
    for label, w in cols:
        align = "R" if label in ("Qty", "Amt") else "L"
        pdf.cell(w, 0.2, label, align=align, fill=True)
        x += w
    y_charges += 0.2

    # Rows
    pdf.set_font("Helvetica", "", 8)
    for svc_date, rev, cpt, px, desc, qty, amt in LINE_ITEMS:
        pdf.set_xy(MARGIN, y_charges)
        for value, (_, w), align in zip(
            [svc_date, rev, cpt, px, desc, str(qty), f"{amt:,.2f}"],
            cols,
            ["L", "L", "L", "L", "L", "R", "R"],
        ):
            pdf.cell(w, 0.2, value, align=align)
        y_charges += 0.2

    # Total charges
    pdf.set_font("Helvetica", "B", 9)
    total_label_x = MARGIN + sum(w for _, w in cols[:5])
    pdf.set_xy(total_label_x, y_charges)
    pdf.cell(cols[5][1], 0.22, "Total Charges", align="R")
    pdf.cell(cols[6][1], 0.22, f"{TOTAL_CHARGES:,.2f}", align="R")
    y_charges += 0.34

    # ── Payments and Adjustments ────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_xy(MARGIN, y_charges)
    pdf.cell(3, 0.22, "Payments and Adjustments")
    y_charges += 0.28

    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(230, 230, 230)
    pa_cols = [("Date", 1.0), ("Description", 5.0), ("Amount", 1.5)]
    pdf.set_xy(MARGIN, y_charges)
    for label, w in pa_cols:
        align = "R" if label == "Amount" else "L"
        pdf.cell(w, 0.2, label, align=align, fill=True)
    y_charges += 0.2

    pdf.set_font("Helvetica", "", 8)
    pdf.set_xy(MARGIN, y_charges)
    pdf.cell(pa_cols[0][1], 0.2, "06/12/2024")
    pdf.cell(pa_cols[1][1], 0.2, "Aetna Pmt Insurance")
    pdf.cell(pa_cols[2][1], 0.2, f"({INSURER_PAYMENT:,.2f})", align="R")
    y_charges += 0.2

    pdf.set_xy(MARGIN + pa_cols[0][1], y_charges)
    pdf.cell(pa_cols[1][1], 0.2, f"   Deductible: {DEDUCTIBLE:.2f}")
    y_charges += 0.18
    pdf.set_xy(MARGIN + pa_cols[0][1], y_charges)
    pdf.cell(pa_cols[1][1], 0.2, f"   Coinsurance: {COINSURANCE:.2f}")
    y_charges += 0.2

    pdf.set_xy(MARGIN, y_charges)
    pdf.cell(pa_cols[0][1], 0.2, "06/12/2024")
    pdf.cell(pa_cols[1][1], 0.2, "Aetna Adj Contractual (Ins)")
    pdf.cell(pa_cols[2][1], 0.2, f"({INSURER_ADJUSTMENT:,.2f})", align="R")
    y_charges += 0.22

    pdf.set_font("Helvetica", "B", 8)
    pdf.set_xy(MARGIN + pa_cols[0][1], y_charges)
    pdf.cell(pa_cols[1][1], 0.2, "Total Insurance Payments and Adjustments")
    pdf.cell(pa_cols[2][1], 0.2, f"({TOTAL_PAYMENTS:,.2f})", align="R")
    y_charges += 0.4

    # ── Summary of Account ──────────────────────────────────────────────────
    pdf.set_draw_color(150, 150, 150)
    pdf.line(MARGIN, y_charges, PAGE_W - MARGIN, y_charges)
    pdf.set_draw_color(0, 0, 0)
    y_charges += 0.18

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_xy(MARGIN, y_charges)
    pdf.cell(3, 0.22, "Summary of Account")
    y_charges += 0.28

    pdf.set_font("Helvetica", "B", 9)
    pdf.set_xy(MARGIN, y_charges)
    pdf.cell(2, 0.22, "Charges")
    y_charges += 0.22

    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(230, 230, 230)
    sum_cols = [("Rev Code", 1.0), ("Description", 5.0), ("Amount", 1.5)]
    pdf.set_xy(MARGIN, y_charges)
    for label, w in sum_cols:
        align = "R" if label == "Amount" else "L"
        pdf.cell(w, 0.2, label, align=align, fill=True)
    y_charges += 0.2

    pdf.set_font("Helvetica", "", 8)
    for rev, desc, amt in REV_SUMMARY:
        pdf.set_xy(MARGIN, y_charges)
        pdf.cell(sum_cols[0][1], 0.2, rev)
        pdf.cell(sum_cols[1][1], 0.2, desc)
        pdf.cell(sum_cols[2][1], 0.2, f"{amt:,.2f}", align="R")
        y_charges += 0.2

    # ── Footer ──────────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "", 8)
    pdf.set_xy(MARGIN, PAGE_H - 0.6)
    pdf.multi_cell(
        PAGE_W - 2 * MARGIN,
        0.16,
        "Please refer to hospital account numbers for all inquiries and correspondence. "
        "This detail bill reflects charges, payments, and adjustments posted on this hospital "
        "account as of the date this detail was printed.",
    )
    pdf.set_xy(PAGE_W - MARGIN - 0.5, PAGE_H - 0.3)
    pdf.cell(0.5, 0.2, "1 of 1", align="R")

    pdf.output(str(out_path))


def main() -> int:
    out = Path.home() / "Downloads" / "StMichaels-demo-bill.pdf"
    _write_pdf(out)
    print(f"Wrote demo bill: {out}")
    print(f"  Total charges: ${TOTAL_CHARGES:,.2f}")
    print(f"  CPT 99214 billed: $850.00 (Saint Michaels published Aetna rate: $96.84)")
    print(f"  Defensible overcharge on this line: $753.16")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
