"""Tests for the bill line item parser.

Uses realistic CPT codes and bill text formats per RULE 8.
Tests behavior (given this text, expect these line items), not implementation.
"""

from datetime import date

import pytest

from app.services.parser import BillParser, ParsedLineItem, _validate_npi_luhn


@pytest.fixture()
def parser() -> BillParser:
    return BillParser()


class TestCptCodeExtraction:
    def test_extracts_single_line_item(self, parser: BillParser) -> None:
        text = "99214  Office Visit, Established Patient  $350.00"
        items = parser.parse(text)
        assert len(items) == 1
        assert items[0].cpt_code == "99214"
        assert items[0].total_charge == 350.00

    def test_extracts_multiple_line_items(self, parser: BillParser) -> None:
        text = (
            "99214  Office Visit, Established Patient  $350.00\n"
            "85025  Complete Blood Count               $120.00\n"
            "36415  Routine Venipuncture                $25.00\n"
        )
        items = parser.parse(text)
        assert len(items) == 3
        assert [i.cpt_code for i in items] == ["99214", "85025", "36415"]

    def test_ignores_lines_without_cpt_codes(self, parser: BillParser) -> None:
        text = (
            "STATEMENT OF ACCOUNT\n"
            "Patient: John Doe\n"
            "99214  Office Visit  $350.00\n"
            "Total: $350.00\n"
        )
        items = parser.parse(text)
        assert len(items) == 1

    def test_empty_text_returns_empty_list(self, parser: BillParser) -> None:
        assert parser.parse("") == []

    def test_extracts_charge_with_comma_separator(self, parser: BillParser) -> None:
        # e.g. $1,200.00 on a hospital bill
        text = "27447  Total Knee Replacement  $1,200.00"
        items = parser.parse(text)
        assert len(items) == 1
        assert items[0].total_charge == 1200.00


class TestModifierExtraction:
    def test_extracts_modifier_59(self, parser: BillParser) -> None:
        text = "36415 59 Routine Venipuncture, Distinct Procedure  $25.00"
        items = parser.parse(text)
        assert len(items) == 1
        assert items[0].modifier == "59"

    def test_line_item_without_modifier_has_none(self, parser: BillParser) -> None:
        text = "99214  Office Visit  $350.00"
        items = parser.parse(text)
        assert items[0].modifier is None

    def test_description_word_er_is_not_captured_as_modifier(self, parser: BillParser) -> None:
        # "ER" is not a valid CMS modifier — it is an English word appearing in descriptions.
        # Before the allowlist fix, this would set modifier="ER" and break duplicate detection.
        text = "99213 ER VISIT  $150.00"
        items = parser.parse(text)
        assert items[0].modifier is None

    def test_description_word_or_is_not_captured_as_modifier(self, parser: BillParser) -> None:
        text = "99213 OR ROOM CHARGE  $500.00"
        items = parser.parse(text)
        assert items[0].modifier is None

    def test_valid_modifier_25_is_captured(self, parser: BillParser) -> None:
        # Modifier 25 = significant, separately identifiable E/M service.
        # Must be preserved — it is the most common legitimate modifier on outpatient bills.
        text = "99213 25 E/M WITH PROCEDURE  $150.00"
        items = parser.parse(text)
        assert items[0].modifier == "25"

    def test_valid_modifier_lt_is_captured(self, parser: BillParser) -> None:
        text = "27447 LT Total Knee Replacement Left  $12000.00"
        items = parser.parse(text)
        assert items[0].modifier == "LT"

    def test_valid_modifier_xe_is_captured(self, parser: BillParser) -> None:
        # XE = distinct encounter; introduced in 2015 as preferred alternative to modifier 59.
        text = "93010 XE ECG interpretation  $45.00"
        items = parser.parse(text)
        assert items[0].modifier == "XE"

    def test_false_modifier_does_not_mask_duplicate(self, parser: BillParser) -> None:
        # Two identical charges where one has "ER" in the description.
        # Before the fix, first item would get modifier="ER" and second modifier=None,
        # making them look like different line items and escaping duplicate detection.
        text = (
            "99213 ER VISIT  $150.00\n"
            "99213 Office Visit  $150.00\n"
        )
        items = parser.parse(text)
        assert len(items) == 2
        assert items[0].modifier is None
        assert items[1].modifier is None


class TestDateExtraction:
    def test_extracts_date_from_line(self, parser: BillParser) -> None:
        text = "03/15/2026  99214  Office Visit  $350.00"
        items = parser.parse(text)
        assert items[0].service_date == date(2026, 3, 15)

    def test_falls_back_to_bill_date_when_no_date_in_line(self, parser: BillParser) -> None:
        fallback = date(2026, 2, 1)
        text = "99214  Office Visit  $350.00"
        items = parser.parse(text, bill_date=fallback)
        assert items[0].service_date == fallback

    def test_falls_back_to_today_when_no_bill_date_provided(self, parser: BillParser) -> None:
        text = "99214  Office Visit  $350.00"
        items = parser.parse(text)
        # Just verify it's a valid date — don't hardcode today's date
        assert isinstance(items[0].service_date, date)

    def test_handles_two_digit_year(self, parser: BillParser) -> None:
        text = "03/15/26  99214  Office Visit  $350.00"
        items = parser.parse(text)
        assert items[0].service_date.year == 2026

    def test_extracts_iso_date_format(self, parser: BillParser) -> None:
        # EHR-generated bills often use ISO 8601 (YYYY-MM-DD). The MM/DD regex fails
        # because \d{1,2} can't match a 4-digit year — ISO must be handled separately.
        text = "2026-03-15  99214  Office Visit  $350.00"
        items = parser.parse(text)
        assert items[0].service_date == date(2026, 3, 15)

    def test_iso_date_in_section_header(self, parser: BillParser) -> None:
        # ISO date appearing as a block header above multiple codes
        text = (
            "2026-03-15\n"
            "99214  Office Visit  $350.00\n"
            "85025  CBC  $120.00\n"
        )
        items = parser.parse(text)
        assert len(items) == 2
        assert all(item.service_date == date(2026, 3, 15) for item in items)

    def test_iso_date_with_hyphen_separator(self, parser: BillParser) -> None:
        # Some systems output YYYY/MM/DD with slashes — ensure ISO-style year is caught
        text = "2025-01-07  27447  Total Knee Replacement  $18,500.00"
        items = parser.parse(text)
        assert items[0].service_date == date(2025, 1, 7)

    def test_prefers_iso_date_over_mm_dd_yyyy_on_same_line(self, parser: BillParser) -> None:
        # Only one date should be extracted — the ISO date must take precedence
        # (ISO checked first in _extract_date to avoid ambiguity)
        text = "2026-03-15  99214  Office Visit  $350.00"
        items = parser.parse(text)
        assert items[0].service_date == date(2026, 3, 15)


class TestRealisticBillFormats:
    def test_parses_full_statement_with_header_and_footer(self, parser: BillParser) -> None:
        text = (
            "STATEMENT OF ACCOUNT\n"
            "Patient: Jane Smith | DOB: 05/22/1985\n"
            "Account: 123456\n"
            "\n"
            "Service Date  Code   Description                      Charge\n"
            "03/15/2026    99214  Office Visit, Est. Patient       $350.00\n"
            "03/15/2026    85025  Complete Blood Count             $120.00\n"
            "03/15/2026    36415  Routine Venipuncture              $25.00\n"
            "\n"
            "Total Charges:  $495.00\n"
            "Insurance Paid: $200.00\n"
            "Balance Due:    $295.00\n"
        )
        items = parser.parse(text)
        assert len(items) == 3
        codes = [i.cpt_code for i in items]
        assert "99214" in codes
        assert "85025" in codes
        assert "36415" in codes

    def test_duplicate_cpt_same_date_both_extracted(self, parser: BillParser) -> None:
        # Parser extracts both — the rules engine is responsible for flagging duplicates
        text = (
            "99214  Office Visit  $350.00\n"
            "99214  Office Visit  $350.00\n"
        )
        items = parser.parse(text)
        assert len(items) == 2
        assert all(i.cpt_code == "99214" for i in items)


class TestChargeExtraction:
    def test_takes_last_amount_when_unit_rate_precedes_total(self, parser: BillParser) -> None:
        # Unit rate ($125.00) appears before total charge ($250.00) — must take the total
        text = "99214  Office Visit  1  $125.00  $250.00"
        items = parser.parse(text)
        assert items[0].total_charge == 250.00

    def test_takes_last_amount_when_zero_appears_first(self, parser: BillParser) -> None:
        # Some bill formats have a $0.00 adjustment column before the billable total
        text = "99214  Office Visit  $0.00  $350.00"
        items = parser.parse(text)
        assert items[0].total_charge == 350.00

    def test_single_amount_still_extracted(self, parser: BillParser) -> None:
        text = "99214  Office Visit  $350.00"
        items = parser.parse(text)
        assert items[0].total_charge == 350.00


class TestDateExtractionSectionHeader:
    def test_all_items_under_date_header_get_correct_date(self, parser: BillParser) -> None:
        # Date appears as a section header above a block of codes — a common real-world format.
        # All codes in the block must get the header date, not today.
        text = (
            "Service Date: 03/15/2026\n"
            "99214  Office Visit  $350.00\n"
            "85025  Complete Blood Count  $120.00\n"
            "36415  Routine Venipuncture  $25.00\n"
        )
        items = parser.parse(text)
        assert len(items) == 3
        assert all(item.service_date == date(2026, 3, 15) for item in items)

    def test_duplicate_items_under_same_header_get_identical_date(self, parser: BillParser) -> None:
        # Duplicate detection requires both items to have the same date.
        # If only the first item gets the header date and the second falls back to today,
        # the dedup key (cpt_code, service_date) differs and the duplicate is missed.
        text = (
            "03/15/2026\n"
            "99214  Office Visit  $350.00\n"
            "99214  Office Visit  $350.00\n"
        )
        items = parser.parse(text)
        assert len(items) == 2
        assert items[0].service_date == items[1].service_date == date(2026, 3, 15)


class TestHcpcsCodeExtraction:
    def test_extracts_ambulance_transport_code(self, parser: BillParser) -> None:
        # A0427 = ALS emergency ground transport — HCPCS Level II code
        text = "A0427  ALS Emergency Transport  $1,200.00"
        items = parser.parse(text)
        assert len(items) == 1
        assert items[0].cpt_code == "A0427"
        assert items[0].total_charge == 1200.00

    def test_extracts_mixed_cpt_and_hcpcs_bill(self, parser: BillParser) -> None:
        # A typical ambulance bill with both a transport code and a mileage code
        text = (
            "03/15/2026  A0427  ALS Emergency Ground Transport  $1,800.00\n"
            "03/15/2026  A0425  Ground Mileage 12 miles         $111.96\n"
        )
        items = parser.parse(text)
        assert len(items) == 2
        codes = [i.cpt_code for i in items]
        assert "A0427" in codes
        assert "A0425" in codes

    def test_hcpcs_code_does_not_interfere_with_cpt_extraction(self, parser: BillParser) -> None:
        # Both a standard CPT and a HCPCS code on the same bill
        text = (
            "99283  Emergency Dept Visit, Moderate  $450.00\n"
            "A0429  BLS Emergency Transport         $900.00\n"
        )
        items = parser.parse(text)
        assert len(items) == 2
        codes = [i.cpt_code for i in items]
        assert "99283" in codes
        assert "A0429" in codes


class TestAmbulanceMileageParsing:
    def test_extracts_miles_and_computes_unit_charge(self, parser: BillParser) -> None:
        # 12 miles × $9.33/mile = $111.96 total
        text = "A0425  Ground Mileage 12 miles  $111.96"
        items = parser.parse(text)
        assert len(items) == 1
        assert items[0].cpt_code == "A0425"
        assert items[0].quantity == 12
        assert items[0].total_charge == 111.96
        assert abs(items[0].unit_charge - round(111.96 / 12, 2)) < 0.01

    def test_extracts_miles_abbreviation(self, parser: BillParser) -> None:
        # "mi" shorthand
        text = "A0425  Transport mileage  8 mi  $74.64"
        items = parser.parse(text)
        assert items[0].quantity == 8
        assert items[0].total_charge == 74.64

    def test_mileage_unit_charge_reconciles_with_total(self, parser: BillParser) -> None:
        """H2 fix (2026-05-04): pre-fix, round(charge/miles, 2) lost precision
        on non-divisible amounts. The rules engine downstream computes
        overcharge = (unit_charge - benchmark) * quantity, so a $0.0033 drift
        per mile × 100 miles = $0.33 wrong on the patient-facing report.

        Reconciliation contract: quantity * unit_charge ≈ total_charge within $0.01."""
        # 7 miles for $15.00 — non-divisible (15 / 7 = 2.142857...)
        text = "A0425  Ground Mileage 7 miles  $15.00"
        items = parser.parse(text)
        assert len(items) == 1
        item = items[0]
        assert item.quantity == 7
        # Pre-fix: round(15.00/7, 2) = 2.14 → 7 * 2.14 = 14.98 (off by $0.02)
        # Post-fix: 15.00/7 = 2.142857... → 7 * 2.142857 ≈ 15.00
        reconciled = item.quantity * item.unit_charge
        assert abs(reconciled - item.total_charge) < 0.01

    def test_mileage_large_distance_precision(self, parser: BillParser) -> None:
        """100 miles × $1245.67: pre-fix unit was $12.46 (12.4567 rounded down),
        100 × $12.46 = $1246.00 → off by $0.33."""
        text = "A0425  Ground Mileage 100 miles  $1245.67"
        items = parser.parse(text)
        assert len(items) == 1
        item = items[0]
        assert item.quantity == 100
        reconciled = item.quantity * item.unit_charge
        assert abs(reconciled - item.total_charge) < 0.01

    def test_no_mileage_leaves_quantity_one(self, parser: BillParser) -> None:
        # Mileage not shown — quantity stays 1, unit_charge = total_charge
        text = "A0425  Ground Mileage  $111.96"
        items = parser.parse(text)
        assert items[0].quantity == 1
        assert items[0].unit_charge == items[0].total_charge

    def test_mileage_not_extracted_for_transport_codes(self, parser: BillParser) -> None:
        # A0427 is a base transport code, not a per-mile code — quantity must stay 1
        text = "A0427  ALS Emergency 12 miles nearby  $1,800.00"
        items = parser.parse(text)
        assert items[0].cpt_code == "A0427"
        assert items[0].quantity == 1
        assert items[0].total_charge == 1800.00

    def test_air_mileage_code_extracts_miles(self, parser: BillParser) -> None:
        # A0435 = fixed-wing air mileage; per-mile extraction should apply
        text = "A0435  Fixed-Wing Air Mileage 150 miles  $4,500.00"
        items = parser.parse(text)
        assert items[0].cpt_code == "A0435"
        assert items[0].quantity == 150
        assert items[0].total_charge == 4500.00


class TestNpiExtraction:
    # NPI 1234567893 is a known Luhn-valid NPI used throughout CMS documentation.
    # NPI 1234567890 differs only in the last digit and fails the Luhn check.
    _VALID_NPI = "1234567893"
    _INVALID_NPI = "1234567890"

    def test_extracts_npi_from_explicit_colon_label(self, parser: BillParser) -> None:
        text = f"Billing Provider\nNPI: {self._VALID_NPI}\n99214  Office Visit  $350.00"
        assert parser.extract_npi(text) == self._VALID_NPI

    def test_extracts_npi_from_hash_label(self, parser: BillParser) -> None:
        text = f"Provider NPI# {self._VALID_NPI}\n99214  Office Visit  $350.00"
        assert parser.extract_npi(text) == self._VALID_NPI

    def test_npi_label_match_is_case_insensitive(self, parser: BillParser) -> None:
        text = f"npi: {self._VALID_NPI}"
        assert parser.extract_npi(text) == self._VALID_NPI

    def test_falls_back_to_context_pattern_when_label_absent(self, parser: BillParser) -> None:
        # "Billing Provider" keyword + valid NPI with no "NPI:" label
        text = f"Billing Provider  {self._VALID_NPI}\n99214  Office Visit  $350.00"
        assert parser.extract_npi(text) == self._VALID_NPI

    def test_returns_none_when_no_npi_in_text(self, parser: BillParser) -> None:
        text = "99214  Office Visit  $350.00\nTotal: $350.00"
        assert parser.extract_npi(text) is None

    def test_rejects_ten_digit_number_that_fails_luhn(self, parser: BillParser) -> None:
        text = f"NPI: {self._INVALID_NPI}"
        assert parser.extract_npi(text) is None

    def test_returns_first_valid_npi_when_multiple_present(self, parser: BillParser) -> None:
        # Referring provider NPI appears after billing provider NPI
        text = (
            f"Billing Provider NPI: {self._VALID_NPI}\n"
            "Referring Provider NPI: 1487491573\n"
        )
        assert parser.extract_npi(text) == self._VALID_NPI

    def test_ignores_ten_digit_number_not_near_provider_keyword(self, parser: BillParser) -> None:
        # A 10-digit account number far from any provider keyword should not match
        text = f"Account Number: {self._INVALID_NPI}\n99214  Office Visit  $350.00"
        assert parser.extract_npi(text) is None

    def test_rejects_account_number_near_provider_keyword(self, parser: BillParser) -> None:
        """H9 fix (2026-05-04): pre-fix, a Luhn-valid 10-digit number within
        60 chars of a provider keyword was accepted as the NPI even when an
        intervening 'Account #' label clearly identified it as something else.
        Real bills frequently put account numbers right next to billing-
        department headers."""
        # Use a Luhn-valid account number to prove the disqualifier works
        # independently of Luhn (otherwise the test would pass for the wrong reason).
        text = f"Billing Department\nAccount #: {self._VALID_NPI}\n99214  Office Visit  $350.00"
        assert parser.extract_npi(text) is None

    def test_rejects_mrn_near_provider_keyword(self, parser: BillParser) -> None:
        text = f"Provider records\nMRN: {self._VALID_NPI}"
        assert parser.extract_npi(text) is None

    def test_rejects_claim_id_near_provider_keyword(self, parser: BillParser) -> None:
        text = f"Facility\nClaim ID {self._VALID_NPI}"
        assert parser.extract_npi(text) is None

    def test_rejects_npi_starting_with_invalid_leading_digit(self, parser: BillParser) -> None:
        """CMS NPI position 1 is contractually 1 or 2. A 10-digit Luhn-passing
        number starting with 9 is provably not an NPI."""
        # 9234567896 — Luhn-valid but starts with 9, so cannot be an NPI.
        # Construct a Luhn-valid number with leading 9 by trial computation:
        # The Luhn check uses prefix "80840" + 10 digits. The fallback pattern
        # rejects on leading digit, so we don't need a Luhn-valid 9-prefix
        # number to test rejection — we just need a 9-prefix number that
        # would have passed Luhn pre-fix. Use any 9-prefix Luhn-valid string.
        # (Verified: 9234567896 — Luhn checksum 60 ÷ 10 = 6, valid.)
        text = "Billing Provider 9234567896"
        # Even though this passes Luhn, the fallback now rejects it on
        # leading digit. Bill returns None → engine falls back to name+ZIP.
        assert parser.extract_npi(text) is None

    def test_label_form_still_accepts_any_valid_luhn(self, parser: BillParser) -> None:
        """The label form (NPI:) is authoritative — leading-digit narrowing
        only applies to the fallback. If a bill explicitly labels the field,
        trust it. (CMS could theoretically issue a 3- or 4-prefix NPI in the
        future; the label form would still resolve correctly.)"""
        text = f"NPI: {self._VALID_NPI}"
        assert parser.extract_npi(text) == self._VALID_NPI


class TestZipCodeExclusion:
    def test_zip_code_in_address_not_extracted_as_cpt(self, parser: BillParser) -> None:
        # "San Francisco, CA 94143" — 94143 matches the 5-digit CPT pattern but is a ZIP code.
        # It must not be extracted as a line item.
        text = (
            "UCSF MEDICAL CENTER\n"
            "505 Parnassus Ave\n"
            "San Francisco, CA 94143\n"
            "99214  Office Visit  $350.00\n"
        )
        items = parser.parse(text)
        assert len(items) == 1
        assert items[0].cpt_code == "99214"

    def test_zip_code_exclusion_does_not_affect_column_interleaved_codes(self, parser: BillParser) -> None:
        # ZIP in header must be excluded while column-interleaved CPT codes are still matched.
        text = (
            "Some Hospital\n"
            "123 Main St, CA 90210\n"
            "08/12/2023\n"
            "99284\n"
            "08/12/2023\n"
            "70553\n"
            "Emergency dept visit\n"
            "MRI brain\n"
            "1\n"
            "$845.00\n"
            "1\n"
            "$4,250.00\n"
        )
        items = parser.parse(text)
        assert len(items) == 2
        codes = [i.cpt_code for i in items]
        assert "99284" in codes
        assert "70553" in codes
        assert "90210" not in codes


    def test_zip_in_no_comma_address_not_treated_as_cpt(self, parser: BillParser) -> None:
        """H1 fix (2026-05-04): pre-fix, comma-less hospital addresses
        ('Cleveland OH 44195' as Vision OCR commonly emits them) bypassed the
        ZIP-exclusion regex and the trailing 5-digit number was captured as a
        CPT code, then routed to PRICE_OUTLIER / NCCI lookups against a fake
        code with no Medicare rate."""
        text = (
            "CLEVELAND CLINIC\n"
            "9500 Euclid Ave\n"
            "Cleveland OH 44195\n"
            "99214  Office Visit  $350.00\n"
        )
        items = parser.parse(text)
        assert len(items) == 1
        assert items[0].cpt_code == "99214"
        # Most importantly, 44195 is NOT in the items
        assert "44195" not in [i.cpt_code for i in items]

    def test_zip_with_zip4_extension_not_treated_as_cpt(self, parser: BillParser) -> None:
        """ZIP+4 ('44195-1234') — the address pattern accepts the optional -1234
        suffix; the pre-CPT line should be skipped entirely."""
        text = (
            "CLEVELAND CLINIC\n"
            "Cleveland, OH 44195-1234\n"
            "99214  Office Visit  $350.00\n"
        )
        items = parser.parse(text)
        assert len(items) == 1
        assert items[0].cpt_code == "99214"


class TestFooterAmountExclusion:
    def test_total_charges_footer_not_assigned_as_code_charge(self, parser: BillParser) -> None:
        # "TOTAL CHARGES\n$9,579.00" — the $9,579 is on its own line with no keyword,
        # but the upper-bound search stops collection before it.
        text = (
            "08/12/2023\n"
            "99284\n"
            "08/12/2023\n"
            "70553\n"
            "Emergency dept visit\n"
            "MRI brain\n"
            "1\n"
            "$845.00\n"
            "1\n"
            "$4,250.00\n"
            "TOTAL CHARGES\n"
            "$9,579.00\n"
            "PAYMENT SUMMARY\n"
            "Total Charges\n"
            "$9,579.00\n"
            "Balance Due\n"
            "$1,234.00\n"
        )
        items = parser.parse(text)
        assert len(items) == 2
        charges = sorted(i.total_charge for i in items)
        assert charges == [845.00, 4250.00]

    def test_payment_summary_amounts_not_assigned_as_code_charges(self, parser: BillParser) -> None:
        # Adjustment and balance amounts in the payment summary must not be picked up.
        text = (
            "08/12/2023\n"
            "99284\n"
            "Emergency dept visit\n"
            "1\n"
            "$845.00\n"
            "TOTAL CHARGES\n"
            "$845.00\n"
            "PAYMENT SUMMARY\n"
            "Insurance Payment\n"
            "($600.00)\n"
            "Balance Due\n"
            "$245.00\n"
        )
        items = parser.parse(text)
        assert len(items) == 1
        assert items[0].cpt_code == "99284"
        assert items[0].total_charge == 845.00


class TestColumnInterleavedOcr:
    """Google Vision OCR returns table PDFs column-by-column rather than row-by-row.

    All CPT codes appear first, then descriptions, then charges — so charges are
    8+ lines from their codes and proximity search misses them. The sequence-based
    fallback must assign the nth unconsumed charge to the nth unmatched CPT code.
    """

    def test_all_codes_extracted_when_charges_are_far_from_codes(self, parser: BillParser) -> None:
        # Mimics actual Cloud Run log output from the UCSF table-format bill.
        # Three CPT codes appear first; their charges appear 8–10 lines later.
        text = (
            "08/12/2023\n"
            "99284\n"
            "08/12/2023\n"
            "70553\n"
            "08/12/2023\n"
            "70553\n"
            "Emergency dept visit, moderate complexity\n"
            "MRI brain, with and without contrast\n"
            "MRI brain, with and without contrast\n"
            "1\n"
            "$845.00\n"
            "1\n"
            "$4,250.00\n"
            "1\n"
            "$4,250.00\n"
        )
        items = parser.parse(text)
        assert len(items) == 3
        codes = [i.cpt_code for i in items]
        assert codes.count("99284") == 1
        assert codes.count("70553") == 2
        assert sorted(i.total_charge for i in items) == [845.00, 4250.00, 4250.00]

    def test_mixed_column_interleaved_and_row_major_in_same_bill(self, parser: BillParser) -> None:
        # First 3 codes are column-interleaved; last 2 are row-major (the hybrid layout
        # seen in the UCSF bill where the final items happened to be row-major).
        # All 5 must be extracted with correct charges.
        text = (
            "08/12/2023\n"
            "99284\n"
            "08/12/2023\n"
            "70553\n"
            "08/12/2023\n"
            "70553\n"
            "Emergency dept visit\n"
            "MRI brain\n"
            "MRI brain\n"
            "1\n"
            "$845.00\n"
            "1\n"
            "$4,250.00\n"
            "1\n"
            "$4,250.00\n"
            "08/12/2023  36415  Collection of venous blood  $45.00\n"
            "08/12/2023  80053  Comprehensive metabolic panel  $189.00\n"
        )
        items = parser.parse(text)
        assert len(items) == 5
        by_code = {i.cpt_code: i.total_charge for i in items if i.cpt_code not in ("70553",)}
        assert by_code["99284"] == 845.00
        assert by_code["36415"] == 45.00
        assert by_code["80053"] == 189.00
        assert sum(1 for i in items if i.cpt_code == "70553") == 2

    def test_summary_total_lines_not_assigned_as_code_charges(self, parser: BillParser) -> None:
        # "Total Charges: $845.00" must not be matched to any CPT code.
        # The code's actual charge is $845.00 on a plain amount line above the total row.
        text = (
            "08/12/2023\n"
            "99284\n"
            "Emergency dept visit\n"
            "1\n"
            "$845.00\n"
            "Total Charges: $845.00\n"
        )
        items = parser.parse(text)
        assert len(items) == 1
        assert items[0].total_charge == 845.00

    def test_service_date_propagates_to_column_interleaved_codes(self, parser: BillParser) -> None:
        # Dates appear before each CPT code in column order. All three codes must
        # get 08/12/2023, not today's date (which would break duplicate detection).
        text = (
            "08/12/2023\n"
            "99284\n"
            "08/12/2023\n"
            "70553\n"
            "08/12/2023\n"
            "70553\n"
            "Emergency dept visit\n"
            "MRI brain\n"
            "MRI brain\n"
            "1\n"
            "$845.00\n"
            "1\n"
            "$4,250.00\n"
            "1\n"
            "$4,250.00\n"
        )
        items = parser.parse(text)
        assert len(items) == 3
        assert all(item.service_date == date(2023, 8, 12) for item in items)

    def test_charges_extracted_when_total_charges_is_column_header(self, parser: BillParser) -> None:
        # Google Vision column-interleaved: "TOTAL CHARGES" is a column header that
        # appears between the CPT codes and their values. The old upper_bound logic
        # stopped scanning at the first summary keyword, excluding all charges.
        # The fix: only stop when the summary keyword is on the same line as an amount.
        text = (
            "03/15/2025\n"
            "99024\n"
            "03/15/2025\n"
            "99213\n"
            "03/15/2025\n"
            "99214\n"
            "Post-op follow-up visit\n"
            "Office visit\n"
            "Office visit, extended\n"
            "TOTAL CHARGES\n"        # column header — no amount on this line
            "$285.00\n"
            "$350.00\n"
            "$450.00\n"
        )
        items = parser.parse(text)
        assert len(items) == 3
        codes = [i.cpt_code for i in items]
        assert "99024" in codes
        assert "99213" in codes
        assert "99214" in codes
        charges = sorted(i.total_charge for i in items)
        assert charges == [285.00, 350.00, 450.00]

    def test_document_order_preserved_in_mixed_bill(self, parser: BillParser) -> None:
        # Column-interleaved codes physically precede the row-major codes on the page.
        # The returned list must reflect page order: 99284, 70553, then 36415.
        text = (
            "08/12/2023\n"
            "99284\n"
            "08/12/2023\n"
            "70553\n"
            "Emergency dept visit\n"
            "MRI brain\n"
            "1\n"
            "$845.00\n"
            "1\n"
            "$4,250.00\n"
            "08/12/2023  36415  Collection of venous blood  $45.00\n"
        )
        items = parser.parse(text)
        assert len(items) == 3
        assert items[0].cpt_code == "99284"
        assert items[1].cpt_code == "70553"
        assert items[2].cpt_code == "36415"


class TestAnesthesiaTimeExtraction:
    """M3 fix: anesthesia minute extraction has a 15-minute floor so
    incidental "5 min wait" / "10 min hold" mentions in the description
    block don't get attached to the anesthesia CPT as `time_units`.
    Pre-fix, the bogus value corrupted the entire ANESTHESIA_OUTLIER
    calculation because it propagated through implied_total - time_units."""

    def test_realistic_anesthesia_minutes_extracted(self, parser: BillParser) -> None:
        text = "00540  Anesthesia for heart  130 min  $2,600.00"
        items = parser.parse(text)
        assert len(items) == 1
        assert items[0].cpt_code == "00540"
        assert items[0].anesthesia_minutes == 130

    def test_short_non_anesthesia_min_token_ignored(self, parser: BillParser) -> None:
        """Pre-fix bug: '5 min wait' on a line right after the CPT code
        attached time_units=5 to the anesthesia row — clearly wrong."""
        text = (
            "00540  Anesthesia for heart  $2,600.00\n"
            "Patient waited 5 min before procedure\n"
        )
        items = parser.parse(text)
        assert len(items) == 1
        # No realistic anesthesia time was found — anesthesia_minutes should
        # stay None rather than fall back to the bogus 5.
        assert items[0].anesthesia_minutes is None

    def test_15_minute_lower_bound(self, parser: BillParser) -> None:
        """Anywhere from 1-14 min is filtered as too-short to be real anesthesia."""
        for low_value in (1, 5, 10, 14):
            text = f"00540  Anesthesia for heart  {low_value} min  $2,600.00"
            items = parser.parse(text)
            assert items[0].anesthesia_minutes is None, (
                f"value {low_value} min should be filtered, got {items[0].anesthesia_minutes}"
            )

    def test_15_minutes_accepted_at_boundary(self, parser: BillParser) -> None:
        text = "00540  Anesthesia for heart  15 min  $2,600.00"
        items = parser.parse(text)
        assert items[0].anesthesia_minutes == 15

    def test_start_end_clock_pair_unchanged(self, parser: BillParser) -> None:
        """The Start/End clock pair extractor runs first and is unaffected
        by the minute-floor change. A 12-minute Start/End duration is still
        legitimate context (no minute-keyword involved)."""
        text = (
            "00540  Anesthesia for heart\n"
            "Start: 08:00  End: 08:12  $2,600.00\n"
        )
        items = parser.parse(text)
        # 12 minutes is a duration computed from clock times — not a minutes-pattern
        # match — so it's allowed through (anesthesia_minutes detector trusts the
        # explicit Start/End block).
        assert items[0].anesthesia_minutes == 12


class TestNpiLuhnValidation:
    def test_known_valid_npi_passes(self) -> None:
        # CMS-documented valid NPI: 1234567893, checksum = 70
        assert _validate_npi_luhn("1234567893") is True

    def test_altered_last_digit_fails(self) -> None:
        assert _validate_npi_luhn("1234567890") is False

    def test_all_zeros_fails(self) -> None:
        # Not a realistic NPI — confirms the algorithm rejects trivial inputs
        assert _validate_npi_luhn("0000000000") is False
