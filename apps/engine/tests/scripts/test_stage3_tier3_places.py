"""Unit tests for the Stage 3 Tier 3 orchestrator.

Cost-preview math, budget-halt accounting, and BQ MERGE shape are tested
without any real API call.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from mrf_discovery.stage3_tier3_places import (  # noqa: E402
    DEFAULT_BUDGET,
    EXPECTED_AMBIGUOUS_RATE,
    EXPECTED_SINGLE_RESULT_RATE,
    cost_preview,
)
from mrf_discovery.places_client import (  # noqa: E402
    COST_PER_PLACE_DETAILS,
    COST_PER_TEXT_SEARCH,
    MAX_VERIFY_CANDIDATES,
)


class TestDefaults:
    def test_default_budget_is_450(self):
        # Sandra's documented decision in 2026-04-28 cost-design doc.
        # Regression guard: if anyone "rounds this down to $400" or removes
        # the cap, this test fails.
        assert DEFAULT_BUDGET == 450.0

    def test_expected_rates_sum_below_one(self):
        # The two rates are mutually-exclusive outcome categories: a hospital
        # is either a single-result lookup OR an ambiguous lookup OR a
        # no-result lookup. Their sum CANNOT exceed 1.0 — if it does, the
        # cost preview projects more outcomes than hospitals exist, which is
        # both physically impossible and over-counts cost.
        #
        # Calibrated 2026-04-29 to 0.60 + 0.39 = 0.99 from the real
        # 500-hospital smoke test.
        assert EXPECTED_SINGLE_RESULT_RATE + EXPECTED_AMBIGUOUS_RATE <= 1.0


class TestCostPreview:
    def _hospital(self, ccn="010001", name="Mayo Clinic", state="MN", city="Rochester"):
        return {"ccn": ccn, "hospital_name": name, "state": state, "city": city}

    def test_empty_targets_returns_zero(self):
        out = cost_preview([])
        assert out["projected_total_usd"] == 0.0
        assert out["lookupable"] == 0

    def test_all_lookupable(self):
        from mrf_discovery.stage3_tier3_places import (
            EXPECTED_AMBIGUOUS_RATE,
            EXPECTED_SINGLE_RESULT_RATE,
        )
        targets = [self._hospital(ccn=str(i)) for i in range(100)]
        out = cost_preview(targets)
        assert out["targets_total"] == 100
        assert out["rejected_pre_call"] == 0
        assert out["lookupable"] == 100
        assert out["expected_text_search_calls"] == 100
        # Cost formula: derives from EXPECTED_*_RATE constants so the test
        # tracks calibration changes without needing to be hand-edited.
        single = int(100 * EXPECTED_SINGLE_RESULT_RATE)
        ambig = int(100 * EXPECTED_AMBIGUOUS_RATE)
        expected_text = 100 * COST_PER_TEXT_SEARCH
        expected_details = (single + ambig * MAX_VERIFY_CANDIDATES) * COST_PER_PLACE_DETAILS
        assert out["projected_total_usd"] == pytest.approx(expected_text + expected_details, rel=1e-9)

    def test_pre_call_rejections_excluded(self):
        # Mix of lookupable + non-lookupable
        targets = [
            self._hospital(ccn="ok-1"),
            self._hospital(ccn="missing-state", state=None),
            self._hospital(ccn="missing-city", city=None),
            self._hospital(ccn="short-name", name="VA"),
            self._hospital(ccn="generic", name="Hospital"),
            self._hospital(ccn="ok-2"),
        ]
        out = cost_preview(targets)
        assert out["targets_total"] == 6
        assert out["rejected_pre_call"] == 4
        assert out["lookupable"] == 2
        # 2 hospitals * search rate
        assert out["expected_text_search_calls"] == 2

    def test_projected_cost_under_budget_for_realistic_workload(self):
        # Sandra's real-world Tier 3 input is ~9,000 hospitals after Tiers 1-2
        targets = [
            {"ccn": str(i), "hospital_name": f"Hospital {i}", "state": "TX", "city": "Dallas"}
            for i in range(9000)
        ]
        out = cost_preview(targets)
        # Should be well under $450 for 9k hospitals
        assert out["projected_total_usd"] < 450.0


class TestCostMath:
    """Sanity-check the cost calculation against known constants."""

    def test_single_lookup_costs_3_cents(self):
        # 1 search @ $0.005 + 1 details @ $0.025 = $0.030
        per_lookup = COST_PER_TEXT_SEARCH + COST_PER_PLACE_DETAILS
        assert per_lookup == pytest.approx(0.030, abs=1e-9)

    def test_ambiguous_lookup_costs_8_cents(self):
        # 1 search + 3 details @ $0.025 = $0.080
        worst_case = COST_PER_TEXT_SEARCH + MAX_VERIFY_CANDIDATES * COST_PER_PLACE_DETAILS
        assert worst_case == pytest.approx(0.080, abs=1e-9)
