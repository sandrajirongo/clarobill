"""Tests for the billing rules engine.

Uses real CPT codes and realistic charge amounts per RULE 8.
Each test exercises behavior, not implementation.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.services.parser import ParsedLineItem
from app.services.rules_engine import RulesEngine


def make_line_item(
    cpt_code: str,
    charge: float,
    service_date: date = date(2026, 3, 15),
    modifier: str | None = None,
    anesthesia_minutes: int | None = None,
) -> ParsedLineItem:
    """Factory for test line items with realistic CPT codes."""
    return ParsedLineItem(
        cpt_code=cpt_code,
        description=f"Procedure {cpt_code}",
        service_date=service_date,
        quantity=1,
        unit_charge=charge,
        total_charge=charge,
        modifier=modifier,
        diagnosis_pointers=[],
        anesthesia_minutes=anesthesia_minutes,
    )


@pytest.fixture()
def engine_with_data() -> RulesEngine:
    """Rules engine with realistic NCCI pairs and Medicare rates."""
    ncci_pairs = {
        # 99213 (established patient visit) bundles 36415 (routine blood draw)
        "99213": {"36415"},
        # 27447 (total knee replacement) bundles 27370 (injection into knee)
        "27447": {"27370"},
    }
    medicare_rates = {
        "99214": Decimal("100.00"),   # Established office visit, moderate complexity
        "99213": Decimal("75.00"),    # Established office visit, low complexity
        "85025": Decimal("10.00"),    # Complete blood count
        "36415": Decimal("3.00"),     # Routine venipuncture
    }
    return RulesEngine(ncci_edit_pairs=ncci_pairs, medicare_rates=medicare_rates)


class TestDuplicateDetection:
    def test_flags_identical_cpt_and_date(self, engine_with_data: RulesEngine) -> None:
        items = [
            make_line_item("99214", 350.00),
            make_line_item("99214", 350.00),  # Same code, same date
        ]
        errors = engine_with_data.run(items)
        duplicate_errors = [e for e in errors if e.code == "DUPLICATE_CHARGE"]
        assert len(duplicate_errors) == 1
        assert 0 in duplicate_errors[0].affected_indices
        assert 1 in duplicate_errors[0].affected_indices

    def test_does_not_flag_same_code_different_dates(self, engine_with_data: RulesEngine) -> None:
        items = [
            make_line_item("99214", 350.00, service_date=date(2026, 3, 1)),
            make_line_item("99214", 350.00, service_date=date(2026, 3, 8)),
        ]
        errors = engine_with_data.run(items)
        duplicate_errors = [e for e in errors if e.code == "DUPLICATE_CHARGE"]
        assert len(duplicate_errors) == 0

    def test_estimated_overcharge_equals_duplicate_charge(self, engine_with_data: RulesEngine) -> None:
        charge = 350.00
        items = [make_line_item("99214", charge), make_line_item("99214", charge)]
        errors = engine_with_data.run(items)
        duplicate = next(e for e in errors if e.code == "DUPLICATE_CHARGE")
        assert duplicate.estimated_overcharge == Decimal("350.00")

    def test_empty_bill_returns_no_errors(self, engine_with_data: RulesEngine) -> None:
        assert engine_with_data.run([]) == []


class TestPriceOutlierDetection:
    def test_flags_charge_above_threshold(self, engine_with_data: RulesEngine) -> None:
        # Medicare rate for 99214 is $100. 2x threshold = $200. $350 should be flagged.
        items = [make_line_item("99214", 350.00)]
        errors = engine_with_data.run(items)
        outlier_errors = [e for e in errors if e.code == "PRICE_OUTLIER"]
        assert len(outlier_errors) == 1
        assert outlier_errors[0].medicare_benchmark_rate == Decimal("100.00")

    def test_does_not_flag_charge_below_threshold(self, engine_with_data: RulesEngine) -> None:
        # $150 is 1.5x the $100 Medicare rate — below the 2x threshold
        items = [make_line_item("99214", 150.00)]
        errors = engine_with_data.run(items)
        outlier_errors = [e for e in errors if e.code == "PRICE_OUTLIER"]
        assert len(outlier_errors) == 0

    def test_no_outlier_for_unknown_cpt_code(self, engine_with_data: RulesEngine) -> None:
        # 99999 is not in the Medicare rate table
        items = [make_line_item("99999", 10000.00)]
        errors = engine_with_data.run(items)
        outlier_errors = [e for e in errors if e.code == "PRICE_OUTLIER"]
        assert len(outlier_errors) == 0


class TestNcciUnbundling:
    def test_flags_unbundled_pair(self, engine_with_data: RulesEngine) -> None:
        # 99213 bundles 36415 per NCCI — billing both is unbundling
        items = [make_line_item("99213", 95.00), make_line_item("36415", 25.00)]
        errors = engine_with_data.run(items)
        ncci_errors = [e for e in errors if e.code == "NCCI_UNBUNDLING"]
        assert len(ncci_errors) == 1

    def test_modifier_59_overrides_ncci_edit(self, engine_with_data: RulesEngine) -> None:
        # Modifier 59 indicates a distinct procedure — overrides the NCCI edit
        items = [
            make_line_item("99213", 95.00),
            make_line_item("36415", 25.00, modifier="59"),
        ]
        errors = engine_with_data.run(items)
        ncci_errors = [e for e in errors if e.code == "NCCI_UNBUNDLING"]
        assert len(ncci_errors) == 0

    def test_no_error_when_only_component_present(self, engine_with_data: RulesEngine) -> None:
        # 36415 alone is fine — only an error when paired with 99213
        items = [make_line_item("36415", 25.00)]
        errors = engine_with_data.run(items)
        ncci_errors = [e for e in errors if e.code == "NCCI_UNBUNDLING"]
        assert len(ncci_errors) == 0


class TestNonPayableCodeDetection:
    @pytest.fixture()
    def engine_with_non_payable(self) -> RulesEngine:
        return RulesEngine(
            ncci_edit_pairs={},
            medicare_rates={},
            non_payable_codes={
                "97799": "I",   # Inactive unlisted physical medicine code
                "99499": "B",   # Bundled unlisted E&M code
                "S9999": "N",   # Non-covered HCPCS S code
            },
        )

    def test_flags_inactive_code_as_critical(self, engine_with_non_payable: RulesEngine) -> None:
        items = [make_line_item("97799", 150.00)]
        errors = engine_with_non_payable.run(items)
        non_payable = [e for e in errors if e.code == "NON_PAYABLE_CODE"]
        assert len(non_payable) == 1
        assert non_payable[0].severity == "critical"
        assert non_payable[0].estimated_overcharge == Decimal("150.00")

    def test_flags_bundled_code_as_critical(self, engine_with_non_payable: RulesEngine) -> None:
        items = [make_line_item("99499", 200.00)]
        errors = engine_with_non_payable.run(items)
        non_payable = [e for e in errors if e.code == "NON_PAYABLE_CODE"]
        assert len(non_payable) == 1
        assert non_payable[0].severity == "critical"

    def test_flags_non_covered_code_as_warning(self, engine_with_non_payable: RulesEngine) -> None:
        items = [make_line_item("S9999", 75.00)]
        errors = engine_with_non_payable.run(items)
        non_payable = [e for e in errors if e.code == "NON_PAYABLE_CODE"]
        assert len(non_payable) == 1
        assert non_payable[0].severity == "warning"

    def test_does_not_flag_unknown_code(self, engine_with_non_payable: RulesEngine) -> None:
        # 99214 is not in the non_payable_codes dict — should not be flagged
        items = [make_line_item("99214", 350.00)]
        errors = engine_with_non_payable.run(items)
        non_payable = [e for e in errors if e.code == "NON_PAYABLE_CODE"]
        assert len(non_payable) == 0

    def test_flags_multiple_non_payable_codes(self, engine_with_non_payable: RulesEngine) -> None:
        items = [
            make_line_item("97799", 150.00),
            make_line_item("99499", 200.00),
        ]
        errors = engine_with_non_payable.run(items)
        non_payable = [e for e in errors if e.code == "NON_PAYABLE_CODE"]
        assert len(non_payable) == 2


class TestAnesthesiaOutlierDetection:
    # 2026 national non-qualifying anesthesia CF = $20.4975
    ANES_CF = Decimal("20.4975")

    @pytest.fixture()
    def anes_engine(self) -> RulesEngine:
        return RulesEngine(
            ncci_edit_pairs={},
            medicare_rates={},
            anesthesia_cf=self.ANES_CF,
        )

    def test_flags_inflated_base_units(self, anes_engine: RulesEngine) -> None:
        # 60 min = 4 time units. Charge of $1,500 implies:
        # implied_total = 1500 / 20.4975 ≈ 73.2 units
        # implied_base  = 73.2 - 4 = 69.2 → well above 25 ceiling
        items = [make_line_item("00840", 1500.00, anesthesia_minutes=60)]
        errors = anes_engine.run(items)
        anes_errors = [e for e in errors if e.code == "ANESTHESIA_OUTLIER"]
        assert len(anes_errors) == 1
        assert anes_errors[0].severity == "critical"

    def test_flags_charge_less_than_time_alone(self, anes_engine: RulesEngine) -> None:
        # 120 min = 8 time units × $20.4975 = $163.98 minimum
        # Charge of $50 is less than the time cost alone — impossible
        items = [make_line_item("00840", 50.00, anesthesia_minutes=120)]
        errors = anes_engine.run(items)
        anes_errors = [e for e in errors if e.code == "ANESTHESIA_OUTLIER"]
        assert len(anes_errors) == 1
        assert anes_errors[0].severity == "critical"

    def test_flags_ceiling_violation_without_time(self, anes_engine: RulesEngine) -> None:
        # No OCR time. $5,000 implies 5000/20.4975 ≈ 244 units — far above 80 ceiling
        items = [make_line_item("00840", 5000.00, anesthesia_minutes=None)]
        errors = anes_engine.run(items)
        anes_errors = [e for e in errors if e.code == "ANESTHESIA_OUTLIER"]
        assert len(anes_errors) == 1
        assert anes_errors[0].severity == "warning"

    def test_does_not_flag_reasonable_charge_with_time(self, anes_engine: RulesEngine) -> None:
        # 90 min = 6 time units. Reasonable anesthesia code has 7 base units.
        # Expected: (7 + 6) × 20.4975 = $266.47
        # Charge of $280 implies base = 280/20.4975 - 6 = 7.66 → well within range
        items = [make_line_item("00840", 280.00, anesthesia_minutes=90)]
        errors = anes_engine.run(items)
        anes_errors = [e for e in errors if e.code == "ANESTHESIA_OUTLIER"]
        assert len(anes_errors) == 0

    def test_non_anesthesia_code_not_checked(self, anes_engine: RulesEngine) -> None:
        # 99214 is not in the 00100–01999 range — anesthesia rule should ignore it
        items = [make_line_item("99214", 5000.00, anesthesia_minutes=None)]
        errors = anes_engine.run(items)
        anes_errors = [e for e in errors if e.code == "ANESTHESIA_OUTLIER"]
        assert len(anes_errors) == 0

    def test_no_anesthesia_check_when_cf_not_loaded(self) -> None:
        # Engine without anesthesia_cf should not run the rule at all
        engine = RulesEngine(ncci_edit_pairs={}, medicare_rates={}, anesthesia_cf=None)
        items = [make_line_item("00840", 9999.00, anesthesia_minutes=10)]
        errors = engine.run(items)
        anes_errors = [e for e in errors if e.code == "ANESTHESIA_OUTLIER"]
        assert len(anes_errors) == 0


class TestAnesthesiaExactBaseUnits:
    """Exact base unit validation using published CMS tables."""

    # 2026 national non-qualifying anesthesia CF = $20.4975
    ANES_CF = Decimal("20.4975")

    # CPT 00840 (intraperitoneal procedures) = 7 published base units
    BASE_UNITS = {"00840": 7}

    @pytest.fixture()
    def anes_engine(self) -> RulesEngine:
        return RulesEngine(
            ncci_edit_pairs={},
            medicare_rates={},
            anesthesia_cf=self.ANES_CF,
            anesthesia_base_units=self.BASE_UNITS,
        )

    def test_flags_excess_base_units_vs_published_value(self, anes_engine: RulesEngine) -> None:
        # 7 published base units + 6 time units (90 min) → expected $266.47
        # Charge of $400 implies (400/20.4975) - 6 = 13.5 base units → 6.5 over published 7
        items = [make_line_item("00840", 400.00, anesthesia_minutes=90)]
        errors = anes_engine.run(items)
        anes_errors = [e for e in errors if e.code == "ANESTHESIA_OUTLIER"]
        assert len(anes_errors) == 1
        assert anes_errors[0].severity == "critical"
        # Overcharge = (13.5 - 7) × 20.4975 ≈ $133.23
        assert anes_errors[0].estimated_overcharge > Decimal("100")

    def test_does_not_flag_charge_matching_published_base_units(self, anes_engine: RulesEngine) -> None:
        # (7 base + 6 time) × 20.4975 = $266.47 — exactly correct
        items = [make_line_item("00840", 266.47, anesthesia_minutes=90)]
        errors = anes_engine.run(items)
        anes_errors = [e for e in errors if e.code == "ANESTHESIA_OUTLIER"]
        assert len(anes_errors) == 0

    def test_allows_half_unit_rounding_tolerance(self, anes_engine: RulesEngine) -> None:
        # Slightly over but within 0.5 unit tolerance — should not flag
        # 7.4 implied base units (published = 7, tolerance = 0.5)
        # charge = (7.4 + 6) × 20.4975 = $274.67
        items = [make_line_item("00840", 274.67, anesthesia_minutes=90)]
        errors = anes_engine.run(items)
        anes_errors = [e for e in errors if e.code == "ANESTHESIA_OUTLIER"]
        assert len(anes_errors) == 0

    def test_overcharge_amount_reflects_published_base_units(self, anes_engine: RulesEngine) -> None:
        # 10 implied base units vs 7 published → overcharge = 3 × CF
        # charge = (10 + 6) × 20.4975 = $327.96
        expected_overcharge = Decimal("3") * self.ANES_CF
        items = [make_line_item("00840", 327.96, anesthesia_minutes=90)]
        errors = anes_engine.run(items)
        anes_errors = [e for e in errors if e.code == "ANESTHESIA_OUTLIER"]
        assert len(anes_errors) == 1
        assert abs(anes_errors[0].estimated_overcharge - expected_overcharge) < Decimal("0.10")

    def test_falls_back_to_heuristic_for_unknown_code(self, anes_engine: RulesEngine) -> None:
        # 00100 is not in the base_units fixture — should fall back to the >25 heuristic
        # charge implies 69 base units (well above 25 ceiling) → should still flag
        items = [make_line_item("00100", 1500.00, anesthesia_minutes=60)]
        errors = anes_engine.run(items)
        anes_errors = [e for e in errors if e.code == "ANESTHESIA_OUTLIER"]
        assert len(anes_errors) == 1


class TestFacilityChargeOutlier:
    # 27447 (total knee replacement) OPPS cap of $900.00 for this locality
    OPPS_RATES = {
        "27447": Decimal("900.00"),
        "27370": Decimal("150.00"),
    }

    @pytest.fixture()
    def opps_engine(self) -> RulesEngine:
        return RulesEngine(
            ncci_edit_pairs={},
            medicare_rates={},
            opps_rates=self.OPPS_RATES,
        )

    def test_flags_charge_above_threshold(self, opps_engine: RulesEngine) -> None:
        # $900 cap × 2x threshold = $1,800. $2,500 should be flagged.
        items = [make_line_item("27447", 2500.00)]
        errors = opps_engine.run(items)
        facility_errors = [e for e in errors if e.code == "FACILITY_CHARGE_OUTLIER"]
        assert len(facility_errors) == 1
        assert facility_errors[0].medicare_benchmark_rate == Decimal("900.00")
        assert facility_errors[0].estimated_overcharge == Decimal("1600.00")

    def test_does_not_flag_charge_below_threshold(self, opps_engine: RulesEngine) -> None:
        # $1,500 is 1.67x the $900 cap — below the 2x threshold
        items = [make_line_item("27447", 1500.00)]
        errors = opps_engine.run(items)
        facility_errors = [e for e in errors if e.code == "FACILITY_CHARGE_OUTLIER"]
        assert len(facility_errors) == 0

    def test_no_flag_for_unknown_code(self, opps_engine: RulesEngine) -> None:
        # 99214 is not in the OPPS rates — no facility rule applies
        items = [make_line_item("99214", 9999.00)]
        errors = opps_engine.run(items)
        facility_errors = [e for e in errors if e.code == "FACILITY_CHARGE_OUTLIER"]
        assert len(facility_errors) == 0

    def test_no_flag_when_opps_rates_not_loaded(self) -> None:
        # Engine without opps_rates should not run the rule
        engine = RulesEngine(ncci_edit_pairs={}, medicare_rates={})
        items = [make_line_item("27447", 9999.00)]
        errors = engine.run(items)
        facility_errors = [e for e in errors if e.code == "FACILITY_CHARGE_OUTLIER"]
        assert len(facility_errors) == 0

    def test_severity_is_warning(self, opps_engine: RulesEngine) -> None:
        items = [make_line_item("27447", 2500.00)]
        errors = opps_engine.run(items)
        facility_errors = [e for e in errors if e.code == "FACILITY_CHARGE_OUTLIER"]
        assert facility_errors[0].severity == "warning"


class TestAmbulanceChargeOutlier:
    # 2026 ALS emergency (A0427) urban rate for a mid-range locality: ~$710
    # 2026 ground mileage (A0425) urban per-mile rate: ~$9.33
    AMBULANCE_RATES = {
        "A0427": Decimal("710.00"),   # ALS emergency ground transport
        "A0428": Decimal("374.00"),   # BLS non-emergency ground transport
        "A0431": Decimal("4650.00"),  # Helicopter (rotary-wing)
        "A0425": Decimal("9.33"),     # Ground mileage, per statute mile
    }

    @pytest.fixture()
    def amb_engine(self) -> RulesEngine:
        return RulesEngine(
            ncci_edit_pairs={},
            medicare_rates={},
            ambulance_rates=self.AMBULANCE_RATES,
        )

    def test_flags_inflated_transport_charge(self, amb_engine: RulesEngine) -> None:
        # $710 benchmark × 2 = $1,420 threshold. $2,800 should be flagged.
        items = [make_line_item("A0427", 2800.00)]
        errors = amb_engine.run(items)
        amb_errors = [e for e in errors if e.code == "AMBULANCE_CHARGE_OUTLIER"]
        assert len(amb_errors) == 1
        assert amb_errors[0].severity == "warning"
        assert amb_errors[0].medicare_benchmark_rate == Decimal("710.00")

    def test_does_not_flag_charge_below_threshold(self, amb_engine: RulesEngine) -> None:
        # $1,200 is 1.69x the $710 benchmark — below the 2x threshold
        items = [make_line_item("A0427", 1200.00)]
        errors = amb_engine.run(items)
        amb_errors = [e for e in errors if e.code == "AMBULANCE_CHARGE_OUTLIER"]
        assert len(amb_errors) == 0

    def test_flags_helicopter_charge(self, amb_engine: RulesEngine) -> None:
        # $4,650 benchmark × 2 = $9,300 threshold. $25,000 is a common air ambulance overcharge.
        items = [make_line_item("A0431", 25000.00)]
        errors = amb_engine.run(items)
        amb_errors = [e for e in errors if e.code == "AMBULANCE_CHARGE_OUTLIER"]
        assert len(amb_errors) == 1
        assert amb_errors[0].estimated_overcharge == Decimal("25000.00") - Decimal("4650.00")

    def test_no_flag_for_unknown_ambulance_code(self, amb_engine: RulesEngine) -> None:
        # A0430 (fixed-wing) is not in the fixture rates — should not be flagged
        items = [make_line_item("A0430", 50000.00)]
        errors = amb_engine.run(items)
        amb_errors = [e for e in errors if e.code == "AMBULANCE_CHARGE_OUTLIER"]
        assert len(amb_errors) == 0

    def test_no_flag_for_non_ambulance_code(self, amb_engine: RulesEngine) -> None:
        # Standard CPT code — ambulance rule should ignore it entirely
        items = [make_line_item("99214", 9999.00)]
        errors = amb_engine.run(items)
        amb_errors = [e for e in errors if e.code == "AMBULANCE_CHARGE_OUTLIER"]
        assert len(amb_errors) == 0

    def test_no_flag_when_ambulance_rates_not_loaded(self) -> None:
        engine = RulesEngine(ncci_edit_pairs={}, medicare_rates={})
        items = [make_line_item("A0427", 99999.00)]
        errors = engine.run(items)
        amb_errors = [e for e in errors if e.code == "AMBULANCE_CHARGE_OUTLIER"]
        assert len(amb_errors) == 0

    def test_mileage_code_uses_unit_charge_when_quantity_known(self) -> None:
        # A0425 at $9.33/mile benchmark. 20 miles billed at $30/mile = $600 total.
        # $30/mile is 3.2x the $9.33 benchmark — should be flagged using unit_charge.
        engine = RulesEngine(
            ncci_edit_pairs={},
            medicare_rates={},
            ambulance_rates={"A0425": Decimal("9.33")},
        )
        item = ParsedLineItem(
            cpt_code="A0425",
            description="Ground mileage",
            service_date=date(2026, 3, 15),
            quantity=20,
            unit_charge=30.00,   # per-mile charge billed
            total_charge=600.00, # 20 × $30
            modifier=None,
            diagnosis_pointers=[],
        )
        errors = engine.run([item])
        amb_errors = [e for e in errors if e.code == "AMBULANCE_CHARGE_OUTLIER"]
        assert len(amb_errors) == 1
        # Overcharge = (30 - 9.33) × 20 miles = $413.40
        assert abs(amb_errors[0].estimated_overcharge - Decimal("413.40")) < Decimal("0.01")

    def test_mileage_code_falls_back_to_total_when_quantity_one(self) -> None:
        # When quantity=1 (miles unknown), only flag wildly inflated totals.
        # $9.33 benchmark × 2 = $18.66. A total of $500 with unknown mileage is flagged.
        engine = RulesEngine(
            ncci_edit_pairs={},
            medicare_rates={},
            ambulance_rates={"A0425": Decimal("9.33")},
        )
        item = ParsedLineItem(
            cpt_code="A0425",
            description="Ground mileage",
            service_date=date(2026, 3, 15),
            quantity=1,
            unit_charge=500.00,
            total_charge=500.00,
            modifier=None,
            diagnosis_pointers=[],
        )
        errors = engine.run([item])
        amb_errors = [e for e in errors if e.code == "AMBULANCE_CHARGE_OUTLIER"]
        assert len(amb_errors) == 1

    def test_reasonable_mileage_charge_not_flagged(self) -> None:
        # 15 miles × $9.33/mile = $139.95 total. $12.00/mile = $180 total.
        # $12.00/mile is 1.29x the $9.33 benchmark — below 2x threshold.
        engine = RulesEngine(
            ncci_edit_pairs={},
            medicare_rates={},
            ambulance_rates={"A0425": Decimal("9.33")},
        )
        item = ParsedLineItem(
            cpt_code="A0425",
            description="Ground mileage",
            service_date=date(2026, 3, 15),
            quantity=15,
            unit_charge=12.00,
            total_charge=180.00,
            modifier=None,
            diagnosis_pointers=[],
        )
        errors = engine.run([item])
        amb_errors = [e for e in errors if e.code == "AMBULANCE_CHARGE_OUTLIER"]
        assert len(amb_errors) == 0
