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

    def test_duplicate_instance_not_also_flagged_as_price_outlier(self, engine_with_data: RulesEngine) -> None:
        # 99214 at $350 is a price outlier (3.5x the $100 Medicare rate).
        # When the code is billed twice, the duplicate instance must not be counted
        # as both a DUPLICATE_CHARGE and a PRICE_OUTLIER — that would double-count
        # the same charge and inflate potential savings above total charges.
        items = [
            make_line_item("99214", 350.00),
            make_line_item("99214", 350.00),
        ]
        errors = engine_with_data.run(items)
        assert len([e for e in errors if e.code == "DUPLICATE_CHARGE"]) == 1
        # Only the original (non-duplicate) instance should produce a PRICE_OUTLIER.
        assert len([e for e in errors if e.code == "PRICE_OUTLIER"]) == 1
        # Total estimated savings must not exceed total charges ($700).
        total_savings = sum(e.estimated_overcharge for e in errors)
        total_charges = Decimal("700.00")
        assert total_savings <= total_charges


class TestPriceOutlierDetection:
    def test_flags_charge_above_threshold(self, engine_with_data: RulesEngine) -> None:
        # Medicare rate for 99214 is $100. 1.1x threshold = $110. $350 should be flagged.
        items = [make_line_item("99214", 350.00)]
        errors = engine_with_data.run(items)
        outlier_errors = [e for e in errors if e.code == "PRICE_OUTLIER"]
        assert len(outlier_errors) == 1
        assert outlier_errors[0].medicare_benchmark_rate == Decimal("100.00")

    def test_does_not_flag_charge_below_threshold(self, engine_with_data: RulesEngine) -> None:
        # $105 is 1.05x the $100 Medicare rate — below the 1.1x threshold
        items = [make_line_item("99214", 105.00)]
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
        # $900 cap × 1.1x threshold = $990. $2,500 should be flagged.
        items = [make_line_item("27447", 2500.00)]
        errors = opps_engine.run(items)
        facility_errors = [e for e in errors if e.code == "FACILITY_CHARGE_OUTLIER"]
        assert len(facility_errors) == 1
        assert facility_errors[0].medicare_benchmark_rate == Decimal("900.00")
        assert facility_errors[0].estimated_overcharge == Decimal("1600.00")

    def test_does_not_flag_charge_below_threshold(self, opps_engine: RulesEngine) -> None:
        # $950 is 1.056x the $900 cap — below the 1.1x threshold
        items = [make_line_item("27447", 950.00)]
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
        # $710 benchmark × 1.1x threshold = $781. $2,800 should be flagged.
        items = [make_line_item("A0427", 2800.00)]
        errors = amb_engine.run(items)
        amb_errors = [e for e in errors if e.code == "AMBULANCE_CHARGE_OUTLIER"]
        assert len(amb_errors) == 1
        assert amb_errors[0].severity == "warning"
        assert amb_errors[0].medicare_benchmark_rate == Decimal("710.00")

    def test_does_not_flag_charge_below_threshold(self, amb_engine: RulesEngine) -> None:
        # $750 is 1.056x the $710 benchmark — below the 1.1x threshold
        items = [make_line_item("A0427", 750.00)]
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
        # 15 miles × $9.33/mile benchmark. $10.00/mile is 1.07x — below 1.1x threshold.
        # (9.33 × 1.1 = $10.263; $10.00 < $10.263 → not flagged)
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
            unit_charge=10.00,
            total_charge=150.00,
            modifier=None,
            diagnosis_pointers=[],
        )
        errors = engine.run([item])
        amb_errors = [e for e in errors if e.code == "AMBULANCE_CHARGE_OUTLIER"]
        assert len(amb_errors) == 0


class TestTerminatedCodeDetection:
    # A0080: non-emergency transport, terminated 2003-01-01 (replaced by other codes)
    # E0190: positioning cushion, terminated 2021-12-31 (example of DME code retirement)
    TERM_DATES = {
        "A0080": date(2003, 1, 1),
        "E0190": date(2021, 12, 31),
    }

    @pytest.fixture()
    def term_engine(self) -> RulesEngine:
        return RulesEngine(
            ncci_edit_pairs={},
            medicare_rates={},
            hcpcs_termination_dates=self.TERM_DATES,
        )

    def test_flags_service_after_termination_date(self, term_engine: RulesEngine) -> None:
        # E0190 terminated 2021-12-31; a 2026 bill using it should be flagged.
        items = [make_line_item("E0190", 85.00, service_date=date(2026, 3, 15))]
        errors = term_engine.run(items)
        term_errors = [e for e in errors if e.code == "TERMINATED_CODE_BILLED"]
        assert len(term_errors) == 1
        assert term_errors[0].severity == "critical"
        assert term_errors[0].estimated_overcharge == Decimal("85.00")
        assert "E0190" in term_errors[0].description

    def test_does_not_flag_service_on_termination_date(self, term_engine: RulesEngine) -> None:
        # Service on the exact termination date is still valid (terminated = last valid date).
        items = [make_line_item("E0190", 85.00, service_date=date(2021, 12, 31))]
        errors = term_engine.run(items)
        term_errors = [e for e in errors if e.code == "TERMINATED_CODE_BILLED"]
        assert len(term_errors) == 0

    def test_does_not_flag_service_before_termination_date(self, term_engine: RulesEngine) -> None:
        # A0080 terminated 2003-01-01; a 2002 service using it is valid.
        items = [make_line_item("A0080", 45.00, service_date=date(2002, 6, 1))]
        errors = term_engine.run(items)
        term_errors = [e for e in errors if e.code == "TERMINATED_CODE_BILLED"]
        assert len(term_errors) == 0

    def test_does_not_flag_code_without_termination_date(self, term_engine: RulesEngine) -> None:
        # A0425 (ground mileage) is an active code not in the termination dict.
        items = [make_line_item("A0425", 200.00)]
        errors = term_engine.run(items)
        term_errors = [e for e in errors if e.code == "TERMINATED_CODE_BILLED"]
        assert len(term_errors) == 0

    def test_no_flag_when_termination_dates_not_loaded(self) -> None:
        engine = RulesEngine(ncci_edit_pairs={}, medicare_rates={})
        items = [make_line_item("E0190", 85.00)]
        errors = engine.run(items)
        term_errors = [e for e in errors if e.code == "TERMINATED_CODE_BILLED"]
        assert len(term_errors) == 0

    def test_flags_multiple_terminated_codes(self, term_engine: RulesEngine) -> None:
        items = [
            make_line_item("A0080", 45.00, service_date=date(2026, 1, 1)),
            make_line_item("E0190", 85.00, service_date=date(2026, 1, 1)),
            make_line_item("A0425", 200.00, service_date=date(2026, 1, 1)),  # active
        ]
        errors = term_engine.run(items)
        term_errors = [e for e in errors if e.code == "TERMINATED_CODE_BILLED"]
        assert len(term_errors) == 2
        flagged_codes = {e.description.split()[1] for e in term_errors}
        assert flagged_codes == {"A0080", "E0190"}


class TestHospitalChargeOutlier:
    # Gross charges sourced from realistic MRF data for a mid-size US hospital.
    # 99214 (office visit): $350 published gross charge
    # 27447 (total knee replacement): $28,000 published gross charge
    # 85025 (CBC): $85 published gross charge
    HOSPITAL_CHARGES = {
        "99214": Decimal("350.00"),
        "27447": Decimal("28000.00"),
        "85025": Decimal("85.00"),
    }

    @pytest.fixture()
    def hosp_engine(self) -> RulesEngine:
        return RulesEngine(
            ncci_edit_pairs={},
            medicare_rates={},
            hospital_charges=self.HOSPITAL_CHARGES,
        )

    def test_flags_charge_above_published_gross(self, hosp_engine: RulesEngine) -> None:
        # Hospital published $350 gross charge for 99214. $450 is 1.29x — above 1.1x threshold.
        items = [make_line_item("99214", 450.00)]
        errors = hosp_engine.run(items)
        hosp_errors = [e for e in errors if e.code == "HOSPITAL_CHARGE_OUTLIER"]
        assert len(hosp_errors) == 1
        assert hosp_errors[0].severity == "critical"
        assert hosp_errors[0].estimated_overcharge == Decimal("100.00")
        assert hosp_errors[0].medicare_benchmark_rate == Decimal("350.00")

    def test_does_not_flag_charge_at_published_gross(self, hosp_engine: RulesEngine) -> None:
        # Billing exactly the published gross charge is fine
        items = [make_line_item("99214", 350.00)]
        errors = hosp_engine.run(items)
        hosp_errors = [e for e in errors if e.code == "HOSPITAL_CHARGE_OUTLIER"]
        assert len(hosp_errors) == 0

    def test_does_not_flag_charge_below_threshold(self, hosp_engine: RulesEngine) -> None:
        # $370 is 1.057x the $350 published price — below the 1.1x threshold
        items = [make_line_item("99214", 370.00)]
        errors = hosp_engine.run(items)
        hosp_errors = [e for e in errors if e.code == "HOSPITAL_CHARGE_OUTLIER"]
        assert len(hosp_errors) == 0

    def test_flags_inflated_surgery_charge(self, hosp_engine: RulesEngine) -> None:
        # $28,000 gross charge for 27447. $35,000 is 1.25x — above 1.1x threshold.
        items = [make_line_item("27447", 35000.00)]
        errors = hosp_engine.run(items)
        hosp_errors = [e for e in errors if e.code == "HOSPITAL_CHARGE_OUTLIER"]
        assert len(hosp_errors) == 1
        assert hosp_errors[0].estimated_overcharge == Decimal("7000.00")

    def test_does_not_flag_unknown_cpt_code(self, hosp_engine: RulesEngine) -> None:
        # 36415 (venipuncture) is not in the hospital's published charges — skip it
        items = [make_line_item("36415", 9999.00)]
        errors = hosp_engine.run(items)
        hosp_errors = [e for e in errors if e.code == "HOSPITAL_CHARGE_OUTLIER"]
        assert len(hosp_errors) == 0

    def test_no_flag_when_hospital_charges_not_loaded(self) -> None:
        # Engine without hospital_charges should not run the rule at all
        engine = RulesEngine(ncci_edit_pairs={}, medicare_rates={})
        items = [make_line_item("99214", 99999.00)]
        errors = engine.run(items)
        hosp_errors = [e for e in errors if e.code == "HOSPITAL_CHARGE_OUTLIER"]
        assert len(hosp_errors) == 0

    def test_flags_only_the_outlier_code(self, hosp_engine: RulesEngine) -> None:
        # 99214 at $450 is flagged; 85025 at $90 (1.06x of $85) is not
        items = [
            make_line_item("99214", 450.00),
            make_line_item("85025", 90.00),
        ]
        errors = hosp_engine.run(items)
        hosp_errors = [e for e in errors if e.code == "HOSPITAL_CHARGE_OUTLIER"]
        assert len(hosp_errors) == 1
        assert hosp_errors[0].affected_indices == [0]



class TestNegotiatedRateExceeded:
    # Negotiated rates for a commercial PPO plan at a mid-size hospital.
    # These are realistic contracted rates — typically 30-60% below gross charge.
    # 99214 (office visit): $142 negotiated (vs $350 gross)
    # 27447 (total knee): $12,500 negotiated (vs $28,000 gross)
    # 71046 (chest X-ray 2-view): $95 negotiated
    NEGOTIATED_CHARGES = {
        "99214": Decimal("142.00"),
        "27447": Decimal("12500.00"),
        "71046": Decimal("95.00"),
    }

    @pytest.fixture()
    def neg_engine(self) -> RulesEngine:
        return RulesEngine(
            ncci_edit_pairs={},
            medicare_rates={},
            negotiated_charges=self.NEGOTIATED_CHARGES,
        )

    def test_flags_charge_above_negotiated_rate(self, neg_engine: RulesEngine) -> None:
        # $142 negotiated for 99214. $850 is 5.99x — far above 1.1x threshold.
        items = [make_line_item("99214", 850.00)]
        errors = neg_engine.run(items)
        neg_errors = [e for e in errors if e.code == "NEGOTIATED_RATE_EXCEEDED"]
        assert len(neg_errors) == 1
        assert neg_errors[0].severity == "critical"
        assert neg_errors[0].estimated_overcharge == Decimal("708.00")
        assert neg_errors[0].medicare_benchmark_rate == Decimal("142.00")

    def test_does_not_flag_charge_at_negotiated_rate(self, neg_engine: RulesEngine) -> None:
        items = [make_line_item("99214", 142.00)]
        errors = neg_engine.run(items)
        neg_errors = [e for e in errors if e.code == "NEGOTIATED_RATE_EXCEEDED"]
        assert len(neg_errors) == 0

    def test_does_not_flag_charge_below_threshold(self, neg_engine: RulesEngine) -> None:
        # $150 is 1.056x the $142 negotiated rate — below 1.1x threshold
        items = [make_line_item("99214", 150.00)]
        errors = neg_engine.run(items)
        neg_errors = [e for e in errors if e.code == "NEGOTIATED_RATE_EXCEEDED"]
        assert len(neg_errors) == 0

    def test_flags_surgery_billed_at_gross_not_negotiated(self, neg_engine: RulesEngine) -> None:
        # Common error: hospital bills gross charge $28,000 instead of $12,500 contracted rate
        items = [make_line_item("27447", 28000.00)]
        errors = neg_engine.run(items)
        neg_errors = [e for e in errors if e.code == "NEGOTIATED_RATE_EXCEEDED"]
        assert len(neg_errors) == 1
        assert neg_errors[0].estimated_overcharge == Decimal("15500.00")

    def test_does_not_flag_unknown_cpt_code(self, neg_engine: RulesEngine) -> None:
        # 85025 not in negotiated charges — skip, do not flag
        items = [make_line_item("85025", 9999.00)]
        errors = neg_engine.run(items)
        neg_errors = [e for e in errors if e.code == "NEGOTIATED_RATE_EXCEEDED"]
        assert len(neg_errors) == 0

    def test_no_flag_when_negotiated_charges_not_loaded(self) -> None:
        # Engine without negotiated_charges should not run the rule
        engine = RulesEngine(ncci_edit_pairs={}, medicare_rates={})
        items = [make_line_item("99214", 99999.00)]
        errors = engine.run(items)
        neg_errors = [e for e in errors if e.code == "NEGOTIATED_RATE_EXCEEDED"]
        assert len(neg_errors) == 0

    def test_flags_only_the_outlier_code(self, neg_engine: RulesEngine) -> None:
        # 99214 at $850 is flagged; 71046 at $100 (1.05x of $95) is not
        items = [
            make_line_item("99214", 850.00),
            make_line_item("71046", 100.00),
        ]
        errors = neg_engine.run(items)
        neg_errors = [e for e in errors if e.code == "NEGOTIATED_RATE_EXCEEDED"]
        assert len(neg_errors) == 1
        assert neg_errors[0].affected_indices == [0]

    def test_negotiated_and_hospital_charge_rules_both_fire(self) -> None:
        # When both negotiated_charges and hospital_charges are loaded, both rules run.
        # Each provides independent evidence — the report shows both.
        engine = RulesEngine(
            ncci_edit_pairs={},
            medicare_rates={},
            hospital_charges={"99214": Decimal("350.00")},
            negotiated_charges={"99214": Decimal("142.00")},
        )
        items = [make_line_item("99214", 850.00)]
        errors = engine.run(items)
        hosp_errors = [e for e in errors if e.code == "HOSPITAL_CHARGE_OUTLIER"]
        neg_errors = [e for e in errors if e.code == "NEGOTIATED_RATE_EXCEEDED"]
        assert len(hosp_errors) == 1
        assert len(neg_errors) == 1
        # Negotiated overcharge ($708) is larger than hospital charge overcharge ($500)
        assert neg_errors[0].estimated_overcharge > hosp_errors[0].estimated_overcharge


class TestMueViolation:
    """MUE (Medically Unlikely Edit) quantity violation detection tests."""

    @pytest.fixture()
    def mue_engine(self) -> RulesEngine:
        """Engine with MUE limits for common test codes."""
        return RulesEngine(
            ncci_edit_pairs={},
            medicare_rates={},
            mue_limits={
                "99213": (2, 2),   # max 2 units, policy (hard denial)
                "85025": (1, 2),   # max 1 unit, policy
                "99291": (1, 3),   # max 1 unit, clinical (documentable)
                "36415": (3, 1),   # max 3 units, claim edit (sum all lines)
                "00400": (0, 2),   # MUE value of 0 — not separately payable
            },
        )

    def _make(
        self,
        cpt_code: str,
        charge: float,
        quantity: int,
        service_date: date = date(2026, 3, 15),
    ) -> ParsedLineItem:
        return ParsedLineItem(
            cpt_code=cpt_code,
            description=f"Procedure {cpt_code}",
            service_date=service_date,
            quantity=quantity,
            unit_charge=charge,
            total_charge=charge * quantity,
            modifier=None,
            diagnosis_pointers=[],
            anesthesia_minutes=None,
        )

    def test_flags_quantity_above_mue_indicator_2(self, mue_engine: RulesEngine) -> None:
        # 99213 has MUE of 2 units — billing 5 is a critical violation
        items = [self._make("99213", 75.00, 5)]
        errors = mue_engine.run(items)
        mue_errors = [e for e in errors if e.code == "MUE_EXCEEDED"]
        assert len(mue_errors) == 1
        assert mue_errors[0].severity == "critical"
        assert mue_errors[0].estimated_overcharge == Decimal("225.00")  # 3 excess × $75

    def test_does_not_flag_quantity_at_mue_limit(self, mue_engine: RulesEngine) -> None:
        items = [self._make("99213", 75.00, 2)]
        errors = mue_engine.run(items)
        mue_errors = [e for e in errors if e.code == "MUE_EXCEEDED"]
        assert len(mue_errors) == 0

    def test_flags_indicator_3_as_warning(self, mue_engine: RulesEngine) -> None:
        # 99291 has MUE of 1, indicator 3 (clinical) — should be a warning, not critical
        items = [self._make("99291", 300.00, 3)]
        errors = mue_engine.run(items)
        mue_errors = [e for e in errors if e.code == "MUE_EXCEEDED"]
        assert len(mue_errors) == 1
        assert mue_errors[0].severity == "warning"

    def test_claim_edit_sums_across_lines_same_date(self, mue_engine: RulesEngine) -> None:
        # 36415 has MUE of 3, indicator 1 (claim edit) — two lines totaling 5 on same date
        items = [
            self._make("36415", 3.00, 2, date(2026, 3, 15)),
            self._make("36415", 3.00, 3, date(2026, 3, 15)),
        ]
        errors = mue_engine.run(items)
        mue_errors = [e for e in errors if e.code == "MUE_EXCEEDED"]
        assert len(mue_errors) == 1
        assert mue_errors[0].severity == "critical"
        assert len(mue_errors[0].affected_indices) == 2  # both lines flagged

    def test_claim_edit_does_not_flag_when_sum_at_limit(self, mue_engine: RulesEngine) -> None:
        # Two lines totaling exactly 3 — should not be flagged
        items = [
            self._make("36415", 3.00, 1, date(2026, 3, 15)),
            self._make("36415", 3.00, 2, date(2026, 3, 15)),
        ]
        errors = mue_engine.run(items)
        mue_errors = [e for e in errors if e.code == "MUE_EXCEEDED"]
        assert len(mue_errors) == 0

    def test_claim_edit_separate_dates_checked_independently(self, mue_engine: RulesEngine) -> None:
        # 3 units on each of two different dates — each is within limit independently
        items = [
            self._make("36415", 3.00, 3, date(2026, 3, 15)),
            self._make("36415", 3.00, 3, date(2026, 3, 16)),
        ]
        errors = mue_engine.run(items)
        mue_errors = [e for e in errors if e.code == "MUE_EXCEEDED"]
        assert len(mue_errors) == 0

    def test_mue_value_zero_flagged_as_critical(self, mue_engine: RulesEngine) -> None:
        # 00400 has MUE of 0 — not separately payable under any circumstances
        items = [self._make("00400", 50.00, 1)]
        errors = mue_engine.run(items)
        mue_errors = [e for e in errors if e.code == "MUE_EXCEEDED"]
        assert len(mue_errors) == 1
        assert mue_errors[0].severity == "critical"
        assert mue_errors[0].estimated_overcharge == Decimal("50.00")

    def test_no_flag_when_mue_limits_not_loaded(self) -> None:
        engine = RulesEngine(ncci_edit_pairs={}, medicare_rates={})
        items = [self._make("99213", 75.00, 999)]
        errors = engine.run(items)
        mue_errors = [e for e in errors if e.code == "MUE_EXCEEDED"]
        assert len(mue_errors) == 0

    def test_does_not_flag_code_without_mue_entry(self, mue_engine: RulesEngine) -> None:
        # 99214 is not in mue_limits — should not be flagged regardless of quantity
        items = [self._make("99214", 100.00, 50)]
        errors = mue_engine.run(items)
        mue_errors = [e for e in errors if e.code == "MUE_EXCEEDED"]
        assert len(mue_errors) == 0
