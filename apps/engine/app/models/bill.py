"""Pydantic models for bill analysis request/response shapes.

These mirror the TypeScript types in packages/shared/src/types/bill.ts.
When either changes, update both.
"""

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer
from pydantic.alias_generators import to_camel


class BillStatus(StrEnum):
    UPLOADING = "uploading"
    OCR_PROCESSING = "ocr_processing"
    ANALYZING = "analyzing"
    COMPLETE = "complete"
    FAILED = "failed"


class ErrorSeverity(StrEnum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class PlanType(StrEnum):
    """Insurance programme type — mirrors PlanType in packages/shared/src/types/bill.ts.

    Controls which NCCI edit set the rules engine loads (medicare vs. medicaid)
    and which PRICE_OUTLIER threshold applies (commercial = 1.8x, medicare = 1.05x,
    self_pay/tricare = 1.2x).
    """

    COMMERCIAL = "commercial"
    MEDICARE = "medicare"
    MEDICAID = "medicaid"
    TRICARE = "tricare"
    SELF_PAY = "self_pay"


class BillingErrorCode(StrEnum):
    DUPLICATE_CHARGE = "DUPLICATE_CHARGE"
    PRICE_OUTLIER = "PRICE_OUTLIER"
    NCCI_UNBUNDLING = "NCCI_UNBUNDLING"
    INVALID_CPT_CODE = "INVALID_CPT_CODE"
    UPCODING = "UPCODING"
    MISSING_MODIFIER = "MISSING_MODIFIER"
    DATE_INCONSISTENCY = "DATE_INCONSISTENCY"
    NON_PAYABLE_CODE = "NON_PAYABLE_CODE"
    TERMINATED_CODE_BILLED = "TERMINATED_CODE_BILLED"
    ANESTHESIA_OUTLIER = "ANESTHESIA_OUTLIER"
    FACILITY_CHARGE_OUTLIER = "FACILITY_CHARGE_OUTLIER"
    AMBULANCE_CHARGE_OUTLIER = "AMBULANCE_CHARGE_OUTLIER"
    HOSPITAL_CHARGE_OUTLIER = "HOSPITAL_CHARGE_OUTLIER"
    NEGOTIATED_RATE_EXCEEDED = "NEGOTIATED_RATE_EXCEEDED"
    NEGOTIATED_CEILING_EXCEEDED = "NEGOTIATED_CEILING_EXCEEDED"
    MUE_EXCEEDED = "MUE_EXCEEDED"
    REDUNDANT_CLINICAL_PAIR = "REDUNDANT_CLINICAL_PAIR"


class Bill(BaseModel):
    """Mirrors TypeScript `Bill` in packages/shared/src/types/bill.ts.

    Phase 8 T2: introduced so the Pydantic↔Zod parity test can assert
    that every field on the TS shape exists on the Pydantic side.
    Pre-T2 the parity test silently skipped Bill — T1 (missing
    hospital_city/state/zip) demonstrated the gap was real.
    """

    model_config = ConfigDict(
        strict=True,
        alias_generator=to_camel,
        populate_by_name=True,
    )

    id: str
    user_id: str
    # User-supplied label; falls back to file_name when null
    display_name: str | None
    file_name: str
    file_path: str
    file_size: int = Field(ge=0)
    mime_type: Literal["application/pdf", "image/jpeg", "image/png"]
    status: BillStatus
    # OCR-extracted provider identity — confirmed during pre-analysis verification
    hospital_npi: str | None
    hospital_name: str | None
    # OCR-extracted provider address (migration 20260430000022). Powers the
    # dispute-letter recipient block + BigQuery hospital-name disambiguation.
    hospital_city: str | None
    hospital_state: str | None
    hospital_zip: str | None
    # Insurance confirmed by user at verification time — denormalized from insurance_plans
    profile_member_id: str | None
    payer_name: str | None
    plan_name: str | None
    plan_type: PlanType | None
    # Timestamp when the user completed pre-analysis verification
    confirmed_at: str | None
    created_at: str
    updated_at: str


class LineItem(BaseModel):
    # Matches BillingError + AnalysisResult: alias_generator = camelCase to
    # align with the TS LineItem contract. populate_by_name lets engine code
    # construct via snake_case Python field names.
    model_config = ConfigDict(
        strict=True,
        alias_generator=to_camel,
        populate_by_name=True,
    )

    id: str
    bill_id: str
    cpt_code: str
    description: str
    service_date: date
    quantity: int = Field(ge=1)
    unit_charge: Decimal = Field(ge=0)
    total_charge: Decimal = Field(ge=0)
    modifier: str | None
    diagnosis_pointers: list[str]


class BillingError(BaseModel):
    # alias_generator + populate_by_name + by_alias dump → emits camelCase
    # to match the TS BillingError contract while still letting the engine
    # construct instances with the snake_case Python field names. The
    # frontend's Zod schema accepts both shapes during the migration window
    # (Phase 1 of the 2026-05-04 bug-fix campaign); once the SQL backfill
    # rewrites legacy rows, the snake fallback in Zod becomes dead code.
    model_config = ConfigDict(
        strict=True,
        alias_generator=to_camel,
        populate_by_name=True,
    )

    code: BillingErrorCode
    severity: ErrorSeverity
    affected_line_item_ids: list[str]
    description: str
    estimated_overcharge: Decimal
    # Medicare benchmark rate for comparison; None when not applicable
    medicare_benchmark_rate: Decimal | None

    @field_serializer("estimated_overcharge")
    def _ser_overcharge(self, v: Decimal) -> float:
        return float(v)

    @field_serializer("medicare_benchmark_rate")
    def _ser_benchmark(self, v: Decimal | None) -> float | None:
        return float(v) if v is not None else None


class AnalysisResult(BaseModel):
    # alias_generator + by_alias dump → camelCase wire shape, matching the
    # BillingError contract from Phase 1. Kept consistent so any future
    # response_model=AnalysisResult endpoint produces the right key set.
    model_config = ConfigDict(
        strict=True,
        alias_generator=to_camel,
        populate_by_name=True,
    )

    id: str
    bill_id: str
    errors: list[BillingError]
    total_charges: Decimal
    estimated_fair_value: Decimal
    total_potential_savings: Decimal
    ai_summary: str
    dispute_letter_url: str | None
    report_url: str | None
    created_at: str

    # Match the BillingError pattern: emit Decimal as float so JSON consumers
    # (TS frontend, Supabase JSONB, future response_model=) see numbers, not
    # quoted strings. Without these, model_dump_json() emits the Decimal as
    # a string and breaks the TS `number` contract — H8 of the bug-fix campaign.
    @field_serializer("total_charges")
    def _ser_total_charges(self, v: Decimal) -> float:
        return float(v)

    @field_serializer("estimated_fair_value")
    def _ser_fair_value(self, v: Decimal) -> float:
        return float(v)

    @field_serializer("total_potential_savings")
    def _ser_savings(self, v: Decimal) -> float:
        return float(v)


# ─── API Request / Response ────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    """Payload from the Next.js frontend when triggering bill analysis."""

    model_config = ConfigDict(strict=True)

    bill_id: str
    file_path: str
    user_id: str
    # Optional geography for GPCI-adjusted rate benchmarking.
    # state: uppercase CMS state name (e.g. "CALIFORNIA")
    # county: county name without "County" suffix (e.g. "LOS ANGELES")
    # zip_code: 5-digit ZIP code used for ambulance rural/urban indicator lookup
    #
    # Constraints (H10 fix, 2026-05-04): the engine downstream of this request
    # type-checks state ∈ uppercase CMS names, ZIP ∈ 5 digits, plan_type ∈ a
    # closed set. Pre-fix, ANY string passed validation and silently routed to
    # NCCI / PRICE_OUTLIER paths that produced wrong findings.
    state: Annotated[str, Field(pattern=r"^[A-Z][A-Z\s]{1,49}$")] | None = None
    county: Annotated[str, Field(min_length=1, max_length=80)] | None = None
    zip_code: Annotated[str, Field(pattern=r"^\d{5}$")] | None = None
    # Insurance plan confirmed by user at verification time.
    # Used to query the hospital's MRF for the exact negotiated rate per CPT code.
    # Both must be provided to enable NEGOTIATED_RATE_EXCEEDED detection.
    payer_name: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    plan_name: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    # Insurance programme type — controls which NCCI edit set is loaded.
    # `strict=False` per-field allows the JSON string ("commercial") to coerce
    # into the StrEnum value at the FastAPI request boundary; the model-level
    # strict=True still applies to every other field. Without this, FastAPI
    # would reject every legitimate analyze request.
    plan_type: Annotated[PlanType, Field(strict=False)] | None = None


class AnalyzeAccepted(BaseModel):
    """Immediate response — the engine processes asynchronously."""

    accepted: Literal[True] = True


class ReportRequest(BaseModel):
    """Payload to trigger post-payment report generation and email delivery."""

    model_config = ConfigDict(strict=True)

    user_email: str
    user_id: str


