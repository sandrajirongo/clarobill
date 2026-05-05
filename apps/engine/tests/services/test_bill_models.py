"""Tests for the wire shape of BillingError and AnalysisResult.

These guard the engine→web contract. Phase 1 of the 2026-05-04 bug-fix
campaign added an alias_generator on BillingError so model_dump emits
camelCase to match the TypeScript BillingError. The frontend's Zod schema
in packages/shared accepts both shapes during migration; once the SQL
backfill rewrites legacy snake_case rows, the snake fallback is dead.
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models.bill import (
    AnalysisResult,
    AnalyzeRequest,
    BillingError,
    BillingErrorCode,
    ErrorSeverity,
    PlanType,
)


@pytest.fixture
def sample_error() -> BillingError:
    return BillingError(
        code=BillingErrorCode.PRICE_OUTLIER,
        severity=ErrorSeverity.CRITICAL,
        affected_line_item_ids=["li-1", "li-2"],
        description="CPT 99214 billed at 3x Medicare rate",
        estimated_overcharge=Decimal("250.50"),
        medicare_benchmark_rate=Decimal("50.25"),
    )


def test_billing_error_dumps_camel_case_with_by_alias(sample_error: BillingError) -> None:
    dumped = sample_error.model_dump(by_alias=True, mode="json")

    # Camel keys present
    assert "affectedLineItemIds" in dumped
    assert "estimatedOvercharge" in dumped
    assert "medicareBenchmarkRate" in dumped

    # Snake keys NOT present — this is the contract that prevents the
    # patient-results page from rendering $undefined.toFixed(2).
    assert "affected_line_item_ids" not in dumped
    assert "estimated_overcharge" not in dumped
    assert "medicare_benchmark_rate" not in dumped

    # Decimal serialiser still applied
    assert dumped["estimatedOvercharge"] == 250.50
    assert dumped["medicareBenchmarkRate"] == 50.25


def test_billing_error_dumps_snake_without_alias(sample_error: BillingError) -> None:
    """Without by_alias=True, the dump uses Python field names. This protects
    callers that explicitly opt out of the camel contract — though after Phase 1
    no caller in the codebase does (Phase 6 retires the snake path entirely)."""
    dumped = sample_error.model_dump()
    assert "affected_line_item_ids" in dumped
    assert "affectedLineItemIds" not in dumped


def test_billing_error_round_trip_camel(sample_error: BillingError) -> None:
    """model_validate accepts the camelCase shape and reconstructs the model.

    strict=False is required because the JSONB-emitted form has plain
    strings (for the StrEnums) and floats (for Decimal). The read-back
    path in _do_generate_report uses the same relaxation.
    """
    dumped = sample_error.model_dump(by_alias=True, mode="json")
    rebuilt = BillingError.model_validate(dumped, strict=False)
    assert rebuilt == sample_error


def test_billing_error_round_trip_snake(sample_error: BillingError) -> None:
    """model_validate also accepts legacy snake_case input via populate_by_name=True.

    This is what lets the read-back path (`_do_generate_report`) tolerate JSONB
    rows persisted before the alias_generator change.
    """
    legacy_snake = {
        "code": "PRICE_OUTLIER",
        "severity": "critical",
        "affected_line_item_ids": ["li-1", "li-2"],
        "description": "CPT 99214 billed at 3x Medicare rate",
        "estimated_overcharge": 250.50,
        "medicare_benchmark_rate": 50.25,
    }
    rebuilt = BillingError.model_validate(legacy_snake, strict=False)
    assert rebuilt.affected_line_item_ids == ["li-1", "li-2"]
    assert rebuilt.estimated_overcharge == Decimal("250.5")


def test_billing_error_strict_construction_still_blocks_silent_coercion() -> None:
    """Default `strict=True` on the model still rejects type-loose input.

    This guards against regression: the strict=False relaxation is opt-in for
    the JSONB read path only. Code that constructs a BillingError directly
    (e.g. _map_errors_to_line_items) must still pass the right Python types,
    or Pydantic raises — which is the Rule 5 contract.
    """
    with pytest.raises(ValidationError):
        BillingError.model_validate({
            "code": "PRICE_OUTLIER",  # str instead of BillingErrorCode
            "severity": "critical",
            "affectedLineItemIds": [],
            "description": "",
            "estimatedOvercharge": 0,
            "medicareBenchmarkRate": None,
        })  # default strict=True — must reject string→enum coercion


def test_billing_error_known_keys_after_dump_match_zod_schema(
    sample_error: BillingError,
) -> None:
    """Regression net: if a future commit adds a field to BillingError without
    updating the shared Zod schema, this test flags it explicitly. The expected
    set MUST stay in sync with packages/shared/src/schemas/bill.ts."""
    dumped = sample_error.model_dump(by_alias=True, mode="json")
    expected_keys = {
        "code",
        "severity",
        "affectedLineItemIds",
        "description",
        "estimatedOvercharge",
        "medicareBenchmarkRate",
    }
    assert set(dumped.keys()) == expected_keys


def test_billing_error_rejects_negative_overcharge() -> None:
    # Pydantic strict mode does not enforce ge=0 unless declared on the field.
    # This test documents the current contract — overcharge can be any Decimal.
    # Phase 3 (H8) tightens this with Field(ge=0). This test will be updated then.
    e = BillingError(
        code=BillingErrorCode.PRICE_OUTLIER,
        severity=ErrorSeverity.CRITICAL,
        affected_line_item_ids=[],
        description="",
        estimated_overcharge=Decimal("-1"),
        medicare_benchmark_rate=None,
    )
    assert e.estimated_overcharge == Decimal("-1")


def test_billing_error_rejects_unknown_code() -> None:
    with pytest.raises(ValidationError):
        BillingError.model_validate({
            "code": "NOT_A_CODE",
            "severity": "critical",
            "affectedLineItemIds": [],
            "description": "",
            "estimatedOvercharge": 0,
            "medicareBenchmarkRate": None,
        })


# ─── AnalysisResult ───────────────────────────────────────────────────────────


@pytest.fixture
def sample_analysis() -> AnalysisResult:
    return AnalysisResult(
        id="a-1",
        bill_id="b-1",
        errors=[],
        total_charges=Decimal("1234.56"),
        estimated_fair_value=Decimal("789.00"),
        total_potential_savings=Decimal("445.56"),
        ai_summary="summary",
        dispute_letter_url=None,
        report_url=None,
        created_at="2026-05-04T00:00:00Z",
    )


def test_analysis_result_serializes_decimals_as_floats(
    sample_analysis: AnalysisResult,
) -> None:
    """H8 contract: Decimal fields dump as JSON numbers, not stringified Decimals.

    Without the field_serializers added in this commit, `model_dump(mode="json")`
    emits {"total_charges": "1234.56"} — a string — which the TS `totalCharges:
    number` contract silently accepts but downstream Number() coercion treats
    as NaN under any locale that disagrees on the decimal separator. Latent
    footgun until anyone wires AnalysisResult into a response_model=.
    """
    # by_alias=True mirrors the production dump path (matches the camelCase
    # contract introduced for BillingError in Phase 1.2).
    dumped = sample_analysis.model_dump(by_alias=True, mode="json")
    assert dumped["totalCharges"] == 1234.56
    assert dumped["estimatedFairValue"] == 789.0
    assert dumped["totalPotentialSavings"] == 445.56
    # Type assertion: each must be a Python float (or int, which JSON treats
    # as a number) — never a str.
    assert isinstance(dumped["totalCharges"], float)
    assert isinstance(dumped["estimatedFairValue"], float)
    assert isinstance(dumped["totalPotentialSavings"], float)

    # Also confirm via the snake-case dump that the serializer fires regardless
    # of alias usage — guards against a future contributor reaching for the
    # snake form and getting back a stringified Decimal.
    snake_dumped = sample_analysis.model_dump(mode="json")
    assert isinstance(snake_dumped["total_charges"], float)
    assert isinstance(snake_dumped["estimated_fair_value"], float)
    assert isinstance(snake_dumped["total_potential_savings"], float)


# ─── AnalyzeRequest validators (H10) ──────────────────────────────────────────

_VALID_REQUEST_BASE: dict[str, object] = {
    "bill_id": "b-1",
    "file_path": "u-1/b-1/bill.pdf",
    "user_id": "u-1",
}


def test_analyze_request_accepts_minimal_valid_input() -> None:
    """All optional fields can be omitted — engine falls back to national defaults."""
    req = AnalyzeRequest.model_validate(_VALID_REQUEST_BASE)
    assert req.state is None
    assert req.zip_code is None
    assert req.plan_type is None


def test_analyze_request_accepts_well_formed_optional_fields() -> None:
    req = AnalyzeRequest.model_validate({
        **_VALID_REQUEST_BASE,
        "state": "CALIFORNIA",
        "county": "LOS ANGELES",
        "zip_code": "94143",
        "payer_name": "Aetna",
        "plan_name": "PPO",
        "plan_type": "commercial",
    })
    assert req.state == "CALIFORNIA"
    assert req.zip_code == "94143"
    assert req.plan_type is PlanType.COMMERCIAL


def test_analyze_request_rejects_lowercase_state() -> None:
    """The engine downstream expects uppercase CMS state names — validate at the boundary."""
    with pytest.raises(ValidationError):
        AnalyzeRequest.model_validate({**_VALID_REQUEST_BASE, "state": "california"})


def test_analyze_request_rejects_zip_with_letters() -> None:
    with pytest.raises(ValidationError):
        AnalyzeRequest.model_validate({**_VALID_REQUEST_BASE, "zip_code": "9414X"})


def test_analyze_request_rejects_short_zip() -> None:
    with pytest.raises(ValidationError):
        AnalyzeRequest.model_validate({**_VALID_REQUEST_BASE, "zip_code": "9414"})


def test_analyze_request_rejects_zip_with_extension() -> None:
    """ZIP+4 ('94143-1234') is not accepted — engine only uses the 5-digit prefix."""
    with pytest.raises(ValidationError):
        AnalyzeRequest.model_validate({**_VALID_REQUEST_BASE, "zip_code": "94143-1234"})


def test_analyze_request_rejects_unknown_plan_type() -> None:
    with pytest.raises(ValidationError):
        AnalyzeRequest.model_validate({**_VALID_REQUEST_BASE, "plan_type": "platinum"})


def test_analyze_request_rejects_empty_payer_name() -> None:
    with pytest.raises(ValidationError):
        AnalyzeRequest.model_validate({**_VALID_REQUEST_BASE, "payer_name": ""})


def test_analysis_result_dumps_camel_case(sample_analysis: AnalysisResult) -> None:
    """The alias_generator on AnalysisResult mirrors the one on BillingError —
    consumers always see the same casing convention."""
    dumped = sample_analysis.model_dump(by_alias=True, mode="json")
    assert "billId" in dumped
    assert "totalCharges" in dumped
    assert "estimatedFairValue" in dumped
    assert "totalPotentialSavings" in dumped
    assert "aiSummary" in dumped
    assert "disputeLetterUrl" in dumped
    assert "reportUrl" in dumped
    assert "createdAt" in dumped
    assert "bill_id" not in dumped
    assert "total_charges" not in dumped
