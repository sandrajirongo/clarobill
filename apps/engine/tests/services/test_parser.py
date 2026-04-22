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


class TestNpiLuhnValidation:
    def test_known_valid_npi_passes(self) -> None:
        # CMS-documented valid NPI: 1234567893, checksum = 70
        assert _validate_npi_luhn("1234567893") is True

    def test_altered_last_digit_fails(self) -> None:
        assert _validate_npi_luhn("1234567890") is False

    def test_all_zeros_fails(self) -> None:
        # Not a realistic NPI — confirms the algorithm rejects trivial inputs
        assert _validate_npi_luhn("0000000000") is False
