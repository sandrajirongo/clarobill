"""Pydantic models for bill analysis request/response shapes.

These mirror the TypeScript types in packages/shared/src/types/bill.ts.
When either changes, update both.
"""

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
    MUE_EXCEEDED = "MUE_EXCEEDED"


class LineItem(BaseModel):
    model_config = ConfigDict(strict=True)

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
    model_config = ConfigDict(strict=True)

    code: BillingErrorCode
    severity: ErrorSeverity
    affected_line_item_ids: list[str]
    description: str
    estimated_overcharge: Decimal
    # Medicare benchmark rate for comparison; None when not applicable
    medicare_benchmark_rate: Decimal | None


class AnalysisResult(BaseModel):
    model_config = ConfigDict(strict=True)

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
    state: str | None = None
    county: str | None = None
    zip_code: str | None = None
    # Insurance plan confirmed by user at verification time.
    # Used to query the hospital's MRF for the exact negotiated rate per CPT code.
    # Both must be provided to enable NEGOTIATED_RATE_EXCEEDED detection.
    payer_name: str | None = None
    plan_name: str | None = None
    # Insurance programme type — controls which NCCI edit set is loaded.
    # Values: 'medicare' | 'medicaid' | 'commercial' | 'tricare' | 'self_pay' | None
    plan_type: str | None = None


class AnalyzeAccepted(BaseModel):
    """Immediate response — the engine processes asynchronously."""

    accepted: Literal[True] = True


class ReportRequest(BaseModel):
    """Payload to trigger post-payment report generation and email delivery."""

    model_config = ConfigDict(strict=True)

    user_email: str
    user_id: str


class ReportGenerated(BaseModel):
    """Response confirming report was generated and emailed."""

    generated: Literal[True] = True


class EngineErrorCode(StrEnum):
    OCR_FAILED = "OCR_FAILED"
    INVALID_CPT_CODE = "INVALID_CPT_CODE"
    ANALYSIS_FAILED = "ANALYSIS_FAILED"
    RATE_LIMIT = "RATE_LIMIT"


class EngineError(BaseModel):
    model_config = ConfigDict(strict=True)

    code: EngineErrorCode
    detail: str
