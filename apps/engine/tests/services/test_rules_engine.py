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
