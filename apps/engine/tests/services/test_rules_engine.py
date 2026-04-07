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
