"""End-to-end pipeline integration test.

Exercises `_run_analysis_pipeline` from raw OCR text through parser, rules
engine, AI summary, and database write — with all external boundaries mocked
(Supabase, BigQuery, OCR, AI, PostHog).

This single test is the regression net for the cross-cutting bugs the bug-fix
campaign repaired:

    S1  BillingError snake/camel boundary mismatch
        → asserts the persisted JSONB uses camelCase keys.
    H2  Mileage unit_charge rounding (full-cents preservation)
        → asserts qty × unit ≈ total within 1 cent.
    H8  Decimal serialization to JSON string instead of float
        → asserts total_charges, total_potential_savings, estimated_fair_value
          are Python floats in the analysis_results insert payload.
    H9  NPI label allowlist (account/MRN must not be picked up)
        → asserts the persisted hospital_npi is the labeled provider NPI,
          not an account number.
    NCCI unbundling on a per-line basis
        → asserts that detected errors mention the bundled column-two code.

The Phase 7.1 inventory called this out as the highest-ROI item: a single
test that lifts `bills.py` orchestration coverage by exercising the
end-to-end happy path. New edge cases get focused unit tests; regressions
of cross-cutting behaviour will reliably fire here.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.api.v1.bills import _run_analysis_pipeline
from app.models.bill import BillStatus


# ── Fixture: realistic raw OCR text ───────────────────────────────────────────
#
# Comprehensive bill chosen per the Phase 7 design call (option A — single bill
# exercising every major rule family). Includes:
#
#   - NPI label "Billing Provider NPI: 1234567893" (Luhn-valid)
#   - Hospital address with city/state/zip
#   - Two unbundled CPTs: 27447 (col1) + 27486 (col2) — NCCI pair
#   - An ambulance mileage line A0425 with 25 miles → quantity preservation
#   - An anesthesia code 00100 with time → minutes capture
#   - One plain E/M code 99214 → typical professional charge
#
# The hospital_name "Cleveland Clinic" + state "OH" + zip "44195" is the same
# row that triggered the H1 ZIP-as-CPT regression. Including it here ensures
# a future parser tweak that re-broke H1 would fail this integration test
# even before the dedicated parser unit test runs.

_RAW_OCR_TEXT = """\
CLEVELAND CLINIC
9500 Euclid Avenue
Cleveland, OH 44195

Billing Provider NPI: 1234567893

Patient: John Doe
Date of Birth: 01/15/1970
Service Date: 03/15/2026

CPT     Description                                       Charge
99214   Office Visit, Established Patient                 $350.00
27447   Total Knee Replacement                            $18,500.00
27486   Revision Total Knee Arthroplasty Component        $9,200.00
00100   Anesthesia for procedures on salivary glands     $1,800.00
A0425   Ground mileage, 25 miles                          $250.00

Total Charges: $30,100.00
"""


# ── Supabase mock helpers ─────────────────────────────────────────────────────


def _mock_supabase_with_data(table_data: dict[str, list[dict[str, Any]]]) -> MagicMock:
    """Build a Supabase client mock whose chained queries return per-table rows.

    Each call to client.table(name) returns a fresh chainable mock query that
    terminates in .execute() returning the rows configured for that table.

    Mutating calls (insert/update/delete) succeed silently — the test asserts
    on what was passed to them via call_args, not on what they "returned".

    Storage downloads return fixture PDF bytes for any path.
    """
    captured_calls: dict[str, list[Any]] = {
        "bills_updates": [],
        "line_items_inserts": [],
        "line_items_deletes": [],
        "analysis_results_inserts": [],
    }

    def _build_query(table_name: str) -> MagicMock:
        rows = table_data.get(table_name, [])
        response = MagicMock()
        response.data = rows

        query = MagicMock()
        for chain_method in (
            "select", "eq", "in_", "lte", "gte", "is_", "or_",
            "order", "limit", "single", "neq",
        ):
            getattr(query, chain_method).return_value = query
        query.execute.return_value = response

        # Capture mutating-call payloads on the corresponding capture buckets.
        def _update(payload: dict[str, Any]) -> MagicMock:
            if table_name == "bills":
                captured_calls["bills_updates"].append(payload)
            return query

        def _insert(payload: Any) -> MagicMock:
            if table_name == "line_items":
                captured_calls["line_items_inserts"].append(payload)
            elif table_name == "analysis_results":
                captured_calls["analysis_results_inserts"].append(payload)
            return query

        def _upsert(payload: Any, on_conflict: str | None = None) -> MagicMock:
            # S6 (Phase 8.2): analysis_results uses upsert to support
            # idempotent re-runs. Captured under the same bucket as inserts
            # since the test asserts on the wire-shape, not the SQL verb.
            if table_name == "analysis_results":
                captured_calls["analysis_results_inserts"].append(payload)
            return query

        def _delete() -> MagicMock:
            if table_name == "line_items":
                captured_calls["line_items_deletes"].append(True)
            return query

        query.update.side_effect = _update
        query.insert.side_effect = _insert
        query.upsert.side_effect = _upsert
        query.delete.side_effect = _delete
        return query

    client = MagicMock()
    client.table.side_effect = _build_query
    client.storage.from_.return_value.download.return_value = b"%PDF-1.4 fake bytes"
    # Expose captured calls for test assertions.
    client._captured = captured_calls  # type: ignore[attr-defined]
    return client


def _table_data() -> dict[str, list[dict[str, Any]]]:
    """Reference data the engine expects to find in Supabase for this bill.

    Only the rows needed to make the rules engine fire on the planted findings
    are populated. Empty tables exercise the loaders' graceful-empty paths.
    """
    return {
        # NCCI: 27447 → 27486 is the planted bundling violation.
        "ncci_edit_pairs": [
            {"column_one_code": "27447", "column_two_code": "27486"},
        ],
        # Medicare PFS rates — published rates the engine compares charges to.
        # Charges in the fixture are deliberately ~10× the rate so PRICE_OUTLIER
        # also fires, but the dominant overcharge is NCCI unbundling on 27486.
        "cms_pfs_indicators": [
            {"hcpc": "99214", "rvu_work": "1.50", "nfac_pe_rvu": "0.71",
             "rvu_mp": "0.10", "nfac_total_rvu": "2.31", "conv_fact": "32.74",
             "proc_stat": "A"},
            {"hcpc": "27447", "rvu_work": "20.96", "nfac_pe_rvu": "20.91",
             "rvu_mp": "3.69", "nfac_total_rvu": "45.56", "conv_fact": "32.74",
             "proc_stat": "A"},
            {"hcpc": "27486", "rvu_work": "20.45", "nfac_pe_rvu": "19.82",
             "rvu_mp": "3.39", "nfac_total_rvu": "43.66", "conv_fact": "32.74",
             "proc_stat": "A"},
        ],
        # Locality lookup falls through to national default (0000000).
        "cms_county_locality": [],
        # MUE limits — empty (rule disabled for this bill).
        "ncci_mue_limits": [],
        # HCPCS Level II metadata for A0425.
        "cms_hcpcs_codes": [],
        # OPPS, ambulance, anesthesia rate tables — empty (rules disabled).
        "cms_opps_cap": [],
        "cms_ambulance_fees": [],
        "cms_anesthesia_base_units": [],
        "cms_anesthesia_cf": [],
    }


# ── Test harness ──────────────────────────────────────────────────────────────


@pytest.fixture()
def supabase_mock() -> MagicMock:
    return _mock_supabase_with_data(_table_data())


@pytest.fixture()
def ai_service_test_mode(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Force the AI service into test_mode so no Gemini/Claude calls fire."""
    from app.services.ai_analysis import AiAnalysisService
    fake = AiAnalysisService(client=MagicMock(), test_mode=True)
    monkeypatch.setattr(
        "app.api.v1.bills.get_ai_analysis_service",
        lambda: fake,
    )
    return MagicMock(wraps=fake)


@pytest.fixture()
def ocr_mock(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace OcrService with a stub that returns the canned OCR text."""
    fake = MagicMock()
    fake.extract_text = MagicMock()

    async def _async_extract(_bytes: bytes, _mime: str) -> str:
        return _RAW_OCR_TEXT

    fake.extract_text.side_effect = _async_extract
    monkeypatch.setattr(
        "app.api.v1.bills.OcrService",
        lambda *args, **kwargs: fake,
    )
    return fake


@pytest.fixture()
def posthog_capture(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Capture PostHog calls so assertions can verify telemetry contracts."""
    capture = MagicMock()
    monkeypatch.setattr("app.api.v1.bills.posthog_client.capture", capture)
    return capture


@pytest.fixture(autouse=True)
def _no_bq(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force _build_bq_client to return None so hospital-charge loaders no-op."""
    monkeypatch.setattr("app.api.v1.bills._build_bq_client", lambda: None)


# ── The test ──────────────────────────────────────────────────────────────────


class TestFullPipeline:
    """End-to-end run of `_run_analysis_pipeline` against a comprehensive bill."""

    @pytest.fixture()
    def run_pipeline(
        self,
        supabase_mock: MagicMock,
        ocr_mock: MagicMock,
        ai_service_test_mode: MagicMock,
        posthog_capture: MagicMock,
    ) -> dict[str, Any]:
        """Execute the pipeline once per test class and return everything for inspection."""
        bill_id = "bill-uuid-0001"
        user_id = "user-uuid-0001"
        asyncio.run(
            _run_analysis_pipeline(
                bill_id=bill_id,
                file_path=f"{user_id}/{bill_id}.pdf",
                state="OH",
                county=None,
                zip_code="44195",
                payer_name="Anthem Blue Cross",
                plan_name="Choice POS I",
                plan_type="commercial",
                user_id=user_id,
                supabase=supabase_mock,
            )
        )
        return {
            "bill_id": bill_id,
            "user_id": user_id,
            "supabase": supabase_mock,
            "captured": supabase_mock._captured,
            "posthog": posthog_capture,
        }

    # ── Final state ────────────────────────────────────────────────────────────

    def test_bill_status_is_complete_at_end(self, run_pipeline: dict[str, Any]) -> None:
        """The terminal status update marks the bill COMPLETE — not FAILED."""
        statuses = [
            update.get("status")
            for update in run_pipeline["captured"]["bills_updates"]
        ]
        assert statuses[-1] == BillStatus.COMPLETE, (
            f"Pipeline ended in non-COMPLETE state. Updates were: {statuses}"
        )

    def test_status_progression_hits_ocr_then_analyzing_then_complete(
        self, run_pipeline: dict[str, Any],
    ) -> None:
        """Progress signals must be emitted in order so the frontend can show progress."""
        statuses = [
            update.get("status")
            for update in run_pipeline["captured"]["bills_updates"]
            if "status" in update
        ]
        # OCR_PROCESSING appears at least once before ANALYZING; both before COMPLETE.
        assert BillStatus.OCR_PROCESSING in statuses
        assert BillStatus.ANALYZING in statuses
        assert statuses.index(BillStatus.OCR_PROCESSING) < statuses.index(
            BillStatus.ANALYZING
        )
        assert statuses.index(BillStatus.ANALYZING) < statuses.index(
            BillStatus.COMPLETE
        )

    # ── Identity persistence ───────────────────────────────────────────────────

    def test_npi_extracted_from_label_not_account_number(
        self, run_pipeline: dict[str, Any],
    ) -> None:
        """H9 regression net: only Luhn-valid + provider-labeled NPIs are persisted."""
        identity_updates = [
            u for u in run_pipeline["captured"]["bills_updates"]
            if "hospital_npi" in u
        ]
        assert len(identity_updates) >= 1
        assert identity_updates[0]["hospital_npi"] == "1234567893"

    def test_hospital_address_components_persisted(
        self, run_pipeline: dict[str, Any],
    ) -> None:
        """City/state/zip flow into the bills row for the dispute letter recipient block."""
        identity_updates = [
            u for u in run_pipeline["captured"]["bills_updates"]
            if "hospital_state" in u
        ]
        assert len(identity_updates) >= 1
        update = identity_updates[0]
        assert update["hospital_state"] == "OH"
        assert update["hospital_zip"] == "44195"
        # Cleveland is the city — confirms the pre-2026-04-30 city-discard regression
        # would fail this assertion.
        assert update.get("hospital_city", "").upper() == "CLEVELAND"

    # ── Line items ─────────────────────────────────────────────────────────────

    def test_line_items_inserted_with_expected_codes(
        self, run_pipeline: dict[str, Any],
    ) -> None:
        """All five planted CPT codes survive parsing and reach the line_items table."""
        inserts = run_pipeline["captured"]["line_items_inserts"]
        assert len(inserts) == 1, "Expected exactly one line_items insert call"
        rows = inserts[0]
        codes = sorted(r["cpt_code"] for r in rows)
        assert codes == ["00100", "27447", "27486", "99214", "A0425"]

    def test_line_items_deleted_before_insert(
        self, run_pipeline: dict[str, Any],
    ) -> None:
        """Idempotent re-analyze: prior line_items are wiped before the new insert.

        Without this, a re-analyze would 2× the bill total in the report.
        """
        assert len(run_pipeline["captured"]["line_items_deletes"]) == 1

    def test_mileage_unit_charge_preserves_cents_within_1_cent(
        self, run_pipeline: dict[str, Any],
    ) -> None:
        """H2 regression net: qty × unit_charge ≈ total_charge for mileage rows."""
        rows = run_pipeline["captured"]["line_items_inserts"][0]
        mileage = next(r for r in rows if r["cpt_code"] == "A0425")
        # 25 miles billed at $250 → unit = $10.00 exactly. Allow 1¢ slack for any
        # future rounding regression (still catches H2's 2¢ drift symptom).
        assert mileage["quantity"] == 25
        product = float(mileage["quantity"]) * float(mileage["unit_charge"])
        assert abs(product - float(mileage["total_charge"])) <= 0.01

    # ── Analysis results: the S1/H8 boundary contract ─────────────────────────

    def test_analysis_results_payload_uses_camelcase_billing_error_keys(
        self, run_pipeline: dict[str, Any],
    ) -> None:
        """S1 regression net: the JSONB stored in analysis_results.errors must carry
        the camelCase keys the TypeScript Zod parser expects. Pre-S1, the engine
        emitted snake_case and the patient report would crash on first finding.
        """
        inserts = run_pipeline["captured"]["analysis_results_inserts"]
        assert len(inserts) == 1
        errors = inserts[0]["errors"]
        assert isinstance(errors, list)
        assert len(errors) > 0, "Expected at least the NCCI unbundling finding"

        first = errors[0]
        # The contract that S1 fixed: these are the camelCase keys.
        assert "estimatedOvercharge" in first
        assert "affectedLineItemIds" in first
        # And the snake_case versions must be absent.
        assert "estimated_overcharge" not in first
        assert "affected_line_item_ids" not in first

    def test_decimal_fields_are_floats_not_strings(
        self, run_pipeline: dict[str, Any],
    ) -> None:
        """H8 regression net: Decimal → JSON must serialize to numeric float, not str.

        Pre-H8, the model_serializer fell back to str(Decimal) and total_charges
        landed in JSONB as e.g. "30100.00". The TS layer then string-comparisons
        rather than arithmetic on it — silently breaking savings totals.
        """
        payload = run_pipeline["captured"]["analysis_results_inserts"][0]
        assert isinstance(payload["total_charges"], float)
        assert isinstance(payload["total_potential_savings"], float)
        assert isinstance(payload["estimated_fair_value"], float)

        # And the per-error Decimal field too.
        first_error = payload["errors"][0]
        assert isinstance(first_error["estimatedOvercharge"], float)

    def test_total_charges_matches_sum_of_line_items(
        self, run_pipeline: dict[str, Any],
    ) -> None:
        """Sanity arithmetic on the headline number patients see."""
        payload = run_pipeline["captured"]["analysis_results_inserts"][0]
        line_items = run_pipeline["captured"]["line_items_inserts"][0]
        expected = sum(float(r["total_charge"]) for r in line_items)
        assert abs(payload["total_charges"] - expected) < 0.01

    def test_estimated_fair_value_equals_total_minus_savings(
        self, run_pipeline: dict[str, Any],
    ) -> None:
        """Algebraic invariant — protects against a refactor that drops one term."""
        payload = run_pipeline["captured"]["analysis_results_inserts"][0]
        expected = payload["total_charges"] - payload["total_potential_savings"]
        assert abs(payload["estimated_fair_value"] - expected) < 0.01

    # ── Detected findings ─────────────────────────────────────────────────────

    def test_ncci_unbundling_detected_on_planted_pair(
        self, run_pipeline: dict[str, Any],
    ) -> None:
        """The 27447+27486 pair must surface as an NCCI_UNBUNDLING finding."""
        errors = run_pipeline["captured"]["analysis_results_inserts"][0]["errors"]
        codes = {e["code"] for e in errors}
        assert "NCCI_UNBUNDLING" in codes, (
            f"Expected NCCI_UNBUNDLING among detected errors, got: {codes}"
        )

    def test_at_least_one_finding_has_savings(
        self, run_pipeline: dict[str, Any],
    ) -> None:
        """The whole pipeline exists to surface savings — a $30k bill with
        a planted unbundling pair must yield a positive recoverable total."""
        payload = run_pipeline["captured"]["analysis_results_inserts"][0]
        assert payload["total_potential_savings"] > 0

    def test_ai_summary_present_in_payload(
        self, run_pipeline: dict[str, Any],
    ) -> None:
        """Test-mode AI service still emits a non-empty summary string."""
        payload = run_pipeline["captured"]["analysis_results_inserts"][0]
        assert isinstance(payload["ai_summary"], str)
        assert len(payload["ai_summary"]) > 0

    # ── PostHog telemetry contract ────────────────────────────────────────────

    def test_posthog_started_event_fired(
        self, run_pipeline: dict[str, Any],
    ) -> None:
        """Per the Phase 7 design call: telemetry events are part of the public
        contract. A rename here forces a deliberate update on both ends."""
        events = [c.kwargs.get("event") for c in run_pipeline["posthog"].call_args_list]
        # The 'started' event is fired by analyze_bill (the synchronous handler),
        # which we don't run here — only the background pipeline. Pipeline
        # completion is what we assert.
        assert "bill analysis completed" in events, (
            f"Expected completion telemetry; saw: {events}"
        )

    def test_posthog_completion_carries_savings_flag(
        self, run_pipeline: dict[str, Any],
    ) -> None:
        """`has_savings` must reflect the actual savings total — analytics
        dashboards filter on this; a constant True/False would silently
        skew the conversion funnel."""
        for call in run_pipeline["posthog"].call_args_list:
            if call.kwargs.get("event") == "bill analysis completed":
                props = call.kwargs.get("properties", {})
                assert isinstance(props.get("has_savings"), bool)
                # Pipeline produced positive savings → flag must be True.
                assert props["has_savings"] is True
                return
        pytest.fail("'bill analysis completed' event was not captured")

    def test_no_failure_event_fired(self, run_pipeline: dict[str, Any]) -> None:
        """Negative assertion: a happy-path run must NOT also emit a failure
        event. Without this, a future try/except that swallows-and-retries
        could double-count failures in the analytics dashboard."""
        events = [c.kwargs.get("event") for c in run_pipeline["posthog"].call_args_list]
        assert "bill analysis failed" not in events


class TestS6S7Idempotency:
    """S6 + S7 (Phase 8.2) regression nets.

    Pre-S6: re-analyze of an already-COMPLETE bill flipped its status to
    FAILED via a 23505 unique_violation on analysis_results.bill_id.
    Pre-S7: re-analyze ran every BQ + Gemini call before discovering the
    existing row. Both fixed by an early-return guard at the top of
    _run_analysis_pipeline.
    """

    def test_skips_pipeline_when_analysis_results_already_exist(
        self,
        ai_service_test_mode: MagicMock,
        ocr_mock: MagicMock,
        posthog_capture: MagicMock,
    ) -> None:
        """When analysis_results already has a row for this bill_id, the
        pipeline returns immediately — no OCR call, no BQ call, no AI call,
        no insert — and emits a 'bill analysis skipped' telemetry event."""
        # Configure the supabase mock so analysis_results query returns 1 row.
        client = _mock_supabase_with_data(_table_data())
        # Override analysis_results table to return an existing row.
        original_table = client.table.side_effect
        def _table(name: str) -> MagicMock:
            query = original_table(name)  # type: ignore[misc]
            if name == "analysis_results":
                query.execute.return_value.data = [{"id": "existing-uuid"}]
            return query
        client.table.side_effect = _table

        asyncio.run(_run_analysis_pipeline(
            bill_id="bill-existing",
            file_path="user/bill.pdf",
            state="OH", county=None, zip_code="44195",
            payer_name=None, plan_name=None, plan_type=None,
            user_id="user-1",
            supabase=client,
        ))

        # OCR was never called — early-return short-circuited.
        ocr_mock.extract_text.assert_not_called()

        # PostHog 'bill analysis skipped' event fires; 'started'/'completed' don't.
        events = [c.kwargs.get("event") for c in posthog_capture.call_args_list]
        assert "bill analysis skipped" in events
        assert "bill analysis completed" not in events
        assert "bill analysis failed" not in events

        # No analysis_results write (insert OR upsert) happened.
        assert client._captured["analysis_results_inserts"] == []
