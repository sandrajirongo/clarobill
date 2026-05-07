"""Generate ClaroBill pre-seed cap table as a Google Sheets-compatible .xlsx file.

Tabs:
  1. Summary               -- ownership snapshot at each stage
  2. Founder Common        -- Sandra's grant + vesting
  3. SAFE Schedule         -- $1.25M target broken into checks
  4. Pro Forma Conversion  -- what the SAFEs convert into at a $20M post seed round
  5. Assumptions           -- editable inputs that drive every other tab

The intent is that opening this in Google Sheets and editing the
Assumptions tab cascades through the formulas. Every dollar is
defensible from a single input.
"""
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

OUT = Path("/home/user/clarobill/docs/applications/clarobill-cap-table.xlsx")

SAGE = "2D4A2A"
SAGE_LIGHT = "EAE8E0"
LIME = "C8F060"
CREAM = "F4F2EC"

HEADER_FILL = PatternFill("solid", fgColor=SAGE)
HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
SUB_FILL = PatternFill("solid", fgColor=SAGE_LIGHT)
SUB_FONT = Font(name="Calibri", size=10, bold=True, color=SAGE)
ACCENT_FILL = PatternFill("solid", fgColor=LIME)
ACCENT_FONT = Font(name="Calibri", size=11, bold=True, color=SAGE)
NORMAL_FONT = Font(name="Calibri", size=11)
ITALIC = Font(name="Calibri", size=10, italic=True, color="6E6E6E")

THIN = Side(border_style="thin", color="C8C8C8")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

CENTER = Alignment(horizontal="center", vertical="center")
LEFT = Alignment(horizontal="left", vertical="center")
RIGHT = Alignment(horizontal="right", vertical="center")
WRAP = Alignment(horizontal="left", vertical="top", wrap_text=True)


def style_header_row(ws, row: int, ncols: int) -> None:
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = CENTER
        cell.border = BORDER


def style_subheader_row(ws, row: int, ncols: int) -> None:
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill = SUB_FILL
        cell.font = SUB_FONT
        cell.border = BORDER


def set_widths(ws, widths: list[int]) -> None:
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def fmt(cell, number_format: str) -> None:
    cell.number_format = number_format


def build_assumptions(wb: Workbook):
    ws = wb.create_sheet("Assumptions")
    set_widths(ws, [42, 18, 60])

    ws["A1"] = "Assumption"
    ws["B1"] = "Value"
    ws["C1"] = "Notes"
    style_header_row(ws, 1, 3)

    rows = [
        ("Total authorized shares",          10_000_000, "Standard Delaware C-corp authorization at formation."),
        ("Founder grant (Sandra Jirongo)",   8_000_000,  "80% of authorized at formation. 4-year vest, 1-year cliff, monthly thereafter."),
        ("Option pool reserved",             2_000_000,  "20% of authorized. Pool sized for the next ~24 months of hiring."),
        ("Pre-seed raise target ($)",        1_250_000,  "From fundraising-strategy.md. Funds 18-22 months."),
        ("SAFE post-money cap ($)",          11_250_000, "Default cap. Flex to $12-13M if Speedrun or YC accept."),
        ("SAFE discount",                    0.20,       "Used at next priced round if cap is above the round's pre-money."),
        ("Assumed seed round size ($)",      4_000_000,  "Pro forma input. Mid-range 2026 healthcare AI seed round."),
        ("Assumed seed pre-money ($)",       20_000_000, "Pro forma input. Drives SAFE conversion price."),
        ("Assumed seed option pool refresh", 0.10,       "Standard pre-money top-up at the seed round."),
    ]
    for i, (label, value, note) in enumerate(rows, start=2):
        ws.cell(row=i, column=1, value=label).font = NORMAL_FONT
        c = ws.cell(row=i, column=2, value=value)
        c.font = ACCENT_FONT
        c.alignment = RIGHT
        ws.cell(row=i, column=3, value=note).font = ITALIC
        ws.cell(row=i, column=3).alignment = WRAP

    fmt(ws["B2"], "#,##0")
    fmt(ws["B3"], "#,##0")
    fmt(ws["B4"], "#,##0")
    fmt(ws["B5"], '"$"#,##0')
    fmt(ws["B6"], '"$"#,##0')
    fmt(ws["B7"], "0.0%")
    fmt(ws["B8"], '"$"#,##0')
    fmt(ws["B9"], '"$"#,##0')
    fmt(ws["B10"], "0.0%")

    ws["A12"] = "Named ranges"
    ws["A12"].font = SUB_FONT
    ws["A13"] = "All formulas reference cells in this tab. Edit a value here and every other tab updates."
    ws["A13"].font = ITALIC

    # Define names used across other sheets
    add_name(wb, "AuthShares",       "Assumptions!$B$2")
    add_name(wb, "FounderGrant",     "Assumptions!$B$3")
    add_name(wb, "OptionPool",       "Assumptions!$B$4")
    add_name(wb, "RaiseTotal",       "Assumptions!$B$5")
    add_name(wb, "SafeCap",          "Assumptions!$B$6")
    add_name(wb, "SafeDiscount",     "Assumptions!$B$7")
    add_name(wb, "SeedRoundSize",    "Assumptions!$B$8")
    add_name(wb, "SeedPreMoney",     "Assumptions!$B$9")
    add_name(wb, "SeedPoolRefresh",  "Assumptions!$B$10")


def add_name(wb: Workbook, name: str, ref: str) -> None:
    from openpyxl.workbook.defined_name import DefinedName
    wb.defined_names[name] = DefinedName(name=name, attr_text=ref)


def openpyxl_named_range(ref: str):
    """Deprecated helper retained for backward compatibility."""
    from openpyxl.workbook.defined_name import DefinedName
    return DefinedName(name="_tmp", attr_text=ref)


def build_summary(wb: Workbook):
    ws = wb.create_sheet("Summary", 0)
    set_widths(ws, [32, 18, 18, 18, 18])

    ws["A1"] = "ClaroBill cap table"
    ws["A1"].font = Font(name="Calibri", size=18, bold=True, color=SAGE)
    ws["A2"] = "Pre-seed snapshot, prepared 2026-05-07. Founder: Sandra Jirongo."
    ws["A2"].font = ITALIC

    ws["A4"] = "Stage"
    ws["B4"] = "Shares (founder + pool)"
    ws["C4"] = "SAFEs raised ($)"
    ws["D4"] = "Founder ownership"
    ws["E4"] = "Notes"
    style_header_row(ws, 4, 5)

    ws["A5"] = "At formation"
    ws["B5"] = "=AuthShares"
    ws["C5"] = 0
    ws["D5"] = "=FounderGrant/AuthShares"
    ws["E5"] = "Sandra: 8M common, 2M reserved option pool, 0 SAFEs."
    ws["A6"] = "Post pre-seed (SAFEs outstanding)"
    ws["B6"] = "=AuthShares"
    ws["C6"] = "=RaiseTotal"
    ws["D6"] = "=FounderGrant/AuthShares"
    ws["E6"] = "$1.25M of SAFEs do not affect cap table until conversion."
    ws["A7"] = "Post seed (SAFEs converted, pool refreshed)"
    ws["B7"] = "='Pro Forma Conversion'!B19"
    ws["C7"] = 0
    ws["D7"] = "='Pro Forma Conversion'!D11"
    ws["E7"] = "Assumes $4M seed at $20M pre, 10% pre-money pool refresh."

    for r in range(5, 8):
        ws.cell(row=r, column=1).font = NORMAL_FONT
        ws.cell(row=r, column=2).number_format = "#,##0"
        ws.cell(row=r, column=3).number_format = '"$"#,##0'
        ws.cell(row=r, column=4).number_format = "0.0%"
        ws.cell(row=r, column=5).font = ITALIC
        ws.cell(row=r, column=5).alignment = WRAP
        for col in range(1, 6):
            ws.cell(row=r, column=col).border = BORDER

    ws["A9"] = "Headline numbers"
    ws["A9"].font = SUB_FONT
    headlines = [
        ("Pre-money valuation (SAFE cap minus raise)", "=SafeCap-RaiseTotal", '"$"#,##0'),
        ("Post-money valuation (SAFE cap)",            "=SafeCap",             '"$"#,##0'),
        ("Total raise target",                          "=RaiseTotal",          '"$"#,##0'),
        ("SAFE discount",                               "=SafeDiscount",        "0.0%"),
        ("Founder dilution from this round (approx.)", "=RaiseTotal/SafeCap",  "0.0%"),
        ("Founder dilution at seed round (approx.)",   "=1-'Pro Forma Conversion'!D11", "0.0%"),
    ]
    for i, (label, formula, num_fmt) in enumerate(headlines, start=10):
        ws.cell(row=i, column=1, value=label).font = NORMAL_FONT
        c = ws.cell(row=i, column=2, value=formula)
        c.font = ACCENT_FONT
        c.alignment = RIGHT
        c.number_format = num_fmt

    ws["A18"] = "Tabs in this workbook"
    ws["A18"].font = SUB_FONT
    tabs = [
        ("Founder Common", "Sandra's 8M-share grant and the vesting schedule."),
        ("SAFE Schedule",  "Per-investor SAFE checks summing to the raise target."),
        ("Pro Forma Conversion", "What the SAFEs convert into at a $4M seed at $20M pre."),
        ("Assumptions",    "All inputs that drive every formula. Edit here, watch the rest update."),
    ]
    for i, (name, desc) in enumerate(tabs, start=19):
        ws.cell(row=i, column=1, value=name).font = ACCENT_FONT
        ws.cell(row=i, column=2, value=desc).font = ITALIC
        ws.merge_cells(start_row=i, start_column=2, end_row=i, end_column=5)
        ws.cell(row=i, column=2).alignment = WRAP


def build_founder(wb: Workbook):
    ws = wb.create_sheet("Founder Common")
    set_widths(ws, [28, 18, 18, 50])

    ws["A1"] = "Founder common stock grant"
    ws["A1"].font = Font(name="Calibri", size=14, bold=True, color=SAGE)

    ws["A3"] = "Holder"
    ws["B3"] = "Shares"
    ws["C3"] = "% of outstanding"
    ws["D3"] = "Terms"
    style_header_row(ws, 3, 4)

    ws["A4"] = "Sandra Jirongo"
    ws["B4"] = "=FounderGrant"
    ws["C4"] = "=FounderGrant/AuthShares"
    ws["D4"] = ("4-year vest, 1-year cliff, monthly thereafter. "
                "Common stock, par value $0.0001. 83(b) election filed at grant.")

    ws["A5"] = "Option pool (reserved, unissued)"
    ws["B5"] = "=OptionPool"
    ws["C5"] = "=OptionPool/AuthShares"
    ws["D5"] = "Reserved for first two hires plus a buffer for advisors."

    ws["A6"] = "Total outstanding + reserved"
    ws["B6"] = "=B4+B5"
    ws["C6"] = "=B6/AuthShares"
    ws["D6"] = "Equals authorized shares at formation."

    for r in range(4, 7):
        ws.cell(row=r, column=2).number_format = "#,##0"
        ws.cell(row=r, column=3).number_format = "0.0%"
        ws.cell(row=r, column=4).font = ITALIC
        ws.cell(row=r, column=4).alignment = WRAP
        for col in range(1, 5):
            ws.cell(row=r, column=col).border = BORDER

    ws["A8"] = "Vesting schedule (illustrative, by month)"
    ws["A8"].font = SUB_FONT

    ws["A9"] = "Month"
    ws["B9"] = "Vested shares"
    ws["C9"] = "% of grant"
    ws["D9"] = "Milestone"
    style_subheader_row(ws, 9, 4)

    milestones = [
        (0,  "=0",                        "=B10/FounderGrant", "Grant date. Cliff in effect."),
        (12, "=FounderGrant*0.25",        "=B11/FounderGrant", "Cliff hits. 25% of grant vests at once."),
        (24, "=FounderGrant*0.50",        "=B12/FounderGrant", "Halfway point."),
        (36, "=FounderGrant*0.75",        "=B13/FounderGrant", "Three-year mark."),
        (48, "=FounderGrant*1.00",        "=B14/FounderGrant", "Fully vested."),
    ]
    for i, (month, shares_formula, pct_formula, milestone) in enumerate(milestones, start=10):
        ws.cell(row=i, column=1, value=month).alignment = RIGHT
        ws.cell(row=i, column=2, value=shares_formula).number_format = "#,##0"
        ws.cell(row=i, column=3, value=pct_formula).number_format = "0.0%"
        ws.cell(row=i, column=4, value=milestone).font = ITALIC
        ws.cell(row=i, column=4).alignment = WRAP
        for col in range(1, 5):
            ws.cell(row=i, column=col).border = BORDER


def build_safe_schedule(wb: Workbook):
    ws = wb.create_sheet("SAFE Schedule")
    set_widths(ws, [28, 16, 14, 14, 12, 32])

    ws["A1"] = "SAFE Schedule (target $1.25M)"
    ws["A1"].font = Font(name="Calibri", size=14, bold=True, color=SAGE)
    ws["A2"] = ("Standard YC post-money SAFE form. All notes share the same cap, "
                "discount, and MFN. Replace placeholder names as commitments come in.")
    ws["A2"].font = ITALIC
    ws.merge_cells("A2:F2")

    ws["A4"] = "Investor"
    ws["B4"] = "Check size ($)"
    ws["C4"] = "Cap ($)"
    ws["D4"] = "Discount"
    ws["E4"] = "MFN"
    ws["F4"] = "Status / notes"
    style_header_row(ws, 4, 6)

    safe_rows = [
        ("Lead investor (TBD)",         750_000, "=SafeCap", "=SafeDiscount", "Yes", "Target lead at $11.25M post cap. Anchors the round."),
        ("a16z Speedrun (if accepted)", 1_000_000, 13_300_000, 0.0, "No",       "Standard $1M for ~7%. Sets a higher cap if accepted."),
        ("YC S26 (if accepted)",        500_000,  "Uncapped MFN", 0.0, "Yes",   "Standard YC $500K MFN + $125K for 7% post."),
        ("Founders Inc (Hubert)",       150_000, "=SafeCap", "=SafeDiscount", "Yes", "In conversation. Anchor angel + advisory."),
        ("Angel 1",                      50_000, "=SafeCap", "=SafeDiscount", "Yes", "Healthcare ops operator."),
        ("Angel 2",                      50_000, "=SafeCap", "=SafeDiscount", "Yes", "Fintech founder, consumer pricing exposure."),
        ("Angel 3",                      50_000, "=SafeCap", "=SafeDiscount", "Yes", "Minerva alumni network."),
        ("Angel 4",                      50_000, "=SafeCap", "=SafeDiscount", "Yes", "Ex-Anthropic / OpenAI engineer."),
        ("Reserve / buffer",            150_000, "=SafeCap", "=SafeDiscount", "Yes", "Final pieces of the round, post-Demo Day."),
    ]
    start_row = 5
    for i, (name, size, cap, discount, mfn, note) in enumerate(safe_rows):
        r = start_row + i
        ws.cell(row=r, column=1, value=name).font = NORMAL_FONT
        ws.cell(row=r, column=2, value=size).number_format = '"$"#,##0'
        ws.cell(row=r, column=3, value=cap).number_format = '"$"#,##0'
        ws.cell(row=r, column=4, value=discount).number_format = "0.0%"
        ws.cell(row=r, column=5, value=mfn).alignment = CENTER
        ws.cell(row=r, column=6, value=note).font = ITALIC
        ws.cell(row=r, column=6).alignment = WRAP
        for col in range(1, 7):
            ws.cell(row=r, column=col).border = BORDER

    total_row = start_row + len(safe_rows)
    ws.cell(row=total_row, column=1, value="TOTAL").font = ACCENT_FONT
    ws.cell(row=total_row, column=1).fill = ACCENT_FILL
    sum_formula = f"=SUM(B{start_row}:B{total_row - 1})"
    c = ws.cell(row=total_row, column=2, value=sum_formula)
    c.number_format = '"$"#,##0'
    c.font = ACCENT_FONT
    c.fill = ACCENT_FILL
    for col in range(3, 7):
        ws.cell(row=total_row, column=col).fill = ACCENT_FILL

    ws.cell(row=total_row + 2, column=1,
            value="Realistic close path: lead + Founders Inc + 4 angels + reserve = $1.20M.").font = ITALIC
    ws.cell(row=total_row + 2, column=1).alignment = WRAP
    ws.merge_cells(start_row=total_row + 2, start_column=1,
                   end_row=total_row + 2, end_column=6)


def build_pro_forma(wb: Workbook):
    ws = wb.create_sheet("Pro Forma Conversion")
    set_widths(ws, [40, 16, 16, 16, 38])

    ws["A1"] = "Pro Forma: SAFEs convert at a $4M seed round at $20M pre"
    ws["A1"].font = Font(name="Calibri", size=14, bold=True, color=SAGE)
    ws["A2"] = ("Edit Assumptions!B8 and B9 to model different seed-round scenarios. "
                "All conversion math below recomputes from those two inputs.")
    ws["A2"].font = ITALIC
    ws.merge_cells("A2:E2")

    ws["A4"] = "Step"
    ws["B4"] = "Value"
    ws["C4"] = "Shares (approx.)"
    ws["D4"] = "% post-seed"
    ws["E4"] = "Notes"
    style_header_row(ws, 4, 5)

    rows = [
        ("Seed round size",                          "=SeedRoundSize",                                              "",                                                  "",                                  "Money the seed lead invests."),
        ("Seed pre-money",                            "=SeedPreMoney",                                               "",                                                  "",                                  "Pre-money negotiated with seed lead."),
        ("Seed post-money",                           "=SeedPreMoney+SeedRoundSize",                                  "",                                                  "",                                  "Pre + seed dollars."),
        ("Effective conversion price (SAFE -> common)", "=MIN(SafeCap, SeedPreMoney*(1-SafeDiscount))/AuthShares",    "",                                                  "",                                  "Lower of SAFE cap or discounted pre-money."),
        ("Shares issued for SAFEs",                   "",                                                            "=RaiseTotal/B8",                                    "=C9/B19",                            "SAFE dollars / conversion price."),
        ("Shares issued for seed lead",               "",                                                            "=SeedRoundSize/(SeedPreMoney/AuthShares)",          "=C10/B19",                           "Seed dollars at the seed pre-money price."),
        ("Founder ownership post-seed",                "",                                                            "=FounderGrant",                                     "=C11/B19",                           "Sandra's grant, unchanged in absolute shares."),
        ("Existing option pool (pre-refresh)",         "",                                                            "=OptionPool",                                       "=C12/B19",                           "Reserved at formation."),
        ("New option pool top-up at seed",             "",                                                            "=B19*SeedPoolRefresh",                              "=C13/B19",                           "Top-up sized off post-seed cap."),
        ("Total post-seed shares outstanding",         "",                                                            "=C9+C10+C11+C12+C13",                               "=1",                                 "Sum of all share rows above."),
    ]
    for i, (label, b, c, d, note) in enumerate(rows, start=5):
        ws.cell(row=i, column=1, value=label).font = NORMAL_FONT
        if b:
            ws.cell(row=i, column=2, value=b).number_format = '"$"#,##0'
        if c:
            ws.cell(row=i, column=3, value=c).number_format = "#,##0"
        if d:
            ws.cell(row=i, column=4, value=d).number_format = "0.0%"
        ws.cell(row=i, column=5, value=note).font = ITALIC
        ws.cell(row=i, column=5).alignment = WRAP
        for col in range(1, 6):
            ws.cell(row=i, column=col).border = BORDER

    # Effective conversion price: dollars per share, not whole-pre-money
    ws["B8"].value = "=MIN(SafeCap, SeedPreMoney*(1-SafeDiscount))/AuthShares"
    ws["B8"].number_format = '"$"0.0000'

    # Total shares outstanding lives on row 19 below the table.
    ws["A19"] = "Total post-seed shares outstanding"
    ws["A19"].font = ACCENT_FONT
    ws["A19"].fill = ACCENT_FILL
    ws["B19"] = "=C9+C10+C11+C12+C13"
    ws["B19"].number_format = "#,##0"
    ws["B19"].font = ACCENT_FONT
    ws["B19"].fill = ACCENT_FILL

    # Helper rows below for the dilution stack
    ws["A21"] = "Final cap table (post-seed)"
    ws["A21"].font = SUB_FONT

    ws["A22"] = "Holder"
    ws["B22"] = "Shares"
    ws["C22"] = "% post-seed"
    ws["D22"] = "Capital in"
    style_header_row(ws, 22, 4)

    ws["A23"] = "Sandra Jirongo (founder common)"
    ws["B23"] = "=FounderGrant"
    ws["C23"] = "=B23/B19"
    ws["D23"] = 0

    ws["A24"] = "SAFE investors (pre-seed)"
    ws["B24"] = "=C9"
    ws["C24"] = "=B24/B19"
    ws["D24"] = "=RaiseTotal"

    ws["A25"] = "Seed lead"
    ws["B25"] = "=C10"
    ws["C25"] = "=B25/B19"
    ws["D25"] = "=SeedRoundSize"

    ws["A26"] = "Existing option pool"
    ws["B26"] = "=OptionPool"
    ws["C26"] = "=B26/B19"
    ws["D26"] = 0

    ws["A27"] = "New option pool (seed top-up)"
    ws["B27"] = "=C13"
    ws["C27"] = "=B27/B19"
    ws["D27"] = 0

    ws["A28"] = "TOTAL"
    ws["A28"].font = ACCENT_FONT
    ws["A28"].fill = ACCENT_FILL
    ws["B28"] = "=SUM(B23:B27)"
    ws["C28"] = "=SUM(C23:C27)"
    ws["D28"] = "=SUM(D23:D27)"

    for r in range(23, 29):
        ws.cell(row=r, column=2).number_format = "#,##0"
        ws.cell(row=r, column=3).number_format = "0.0%"
        ws.cell(row=r, column=4).number_format = '"$"#,##0'
        for col in range(1, 5):
            ws.cell(row=r, column=col).border = BORDER

    ws["B28"].font = ACCENT_FONT
    ws["B28"].fill = ACCENT_FILL
    ws["C28"].font = ACCENT_FONT
    ws["C28"].fill = ACCENT_FILL
    ws["D28"].font = ACCENT_FONT
    ws["D28"].fill = ACCENT_FILL

    # Pull the founder ownership for Summary tab
    ws["D11"].value = "=B23/B19" if False else "=FounderGrant/B19"


def main() -> None:
    wb = Workbook()
    # Remove the default sheet; we'll add Summary first via index.
    default = wb.active
    wb.remove(default)

    build_summary(wb)
    build_founder(wb)
    build_safe_schedule(wb)
    build_pro_forma(wb)
    build_assumptions(wb)

    # Re-order so Summary is first, Assumptions is last.
    wb.move_sheet("Summary", offset=-wb.index(wb["Summary"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(OUT))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
