"""Bill analysis API routes."""

import logging
import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from supabase import Client

from app.core.dependencies import get_ai_analysis_service, get_email_service, get_supabase_client
from app.models.bill import (
    AnalyzeAccepted,
    AnalyzeRequest,
    BillingError,
    BillingErrorCode,
    ErrorSeverity,
    ReportGenerated,
    ReportRequest,
)
from app.services.ai_analysis import AiAnalysisService
from app.services.email_service import EmailService
from app.services.ocr import OcrExtractionError, OcrService
from app.services.parser import BillParser, ParsedLineItem
from app.services.report_generator import ReportGenerator
from app.services.rules_engine import DetectedError, RulesEngine

router = APIRouter(prefix="/bills", tags=["bills"])
logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)


@router.post("/{bill_id}/analyze", response_model=AnalyzeAccepted, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("10/hour")  # OCR + AI calls are expensive — 10 analyses per hour per IP
async def analyze_bill(
    request: Request,
    bill_id: str,
    body: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    supabase: Client = Depends(get_supabase_client),
) -> AnalyzeAccepted:
    """Accept a bill for analysis and process it asynchronously.

    Returns 202 Accepted immediately. The bill status in the database is updated
    as processing progresses. The frontend polls GET /api/bills/{billId} for status.
    """
    if body.bill_id != bill_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="bill_id mismatch")

    # Mark the bill as in OCR processing so the frontend shows progress
    supabase.table("bills").update({"status": "ocr_processing"}).eq("id", bill_id).execute()

    background_tasks.add_task(_run_analysis_pipeline, bill_id, body.file_path, supabase)

    return AnalyzeAccepted()


async def _run_analysis_pipeline(bill_id: str, file_path: str, supabase: Client) -> None:
    """Full analysis pipeline — runs in the background after accepting the request.

    Steps:
      1. Download file from Supabase Storage
      2. OCR extraction
      3. Line item parsing
      4. Rules engine
      5. AI analysis (Claude)
      6. Persist results and update bill status
    """
    try:
        # 1. Download file bytes from Storage
        file_response = supabase.storage.from_("bills").download(file_path)
        file_bytes: bytes = file_response

        # Derive MIME type from file path extension
        mime_type = _mime_type_from_path(file_path)

        # 2. OCR
        supabase.table("bills").update({"status": "ocr_processing"}).eq("id", bill_id).execute()
        ocr_service = OcrService()
        raw_text = await ocr_service.extract_text(file_bytes, mime_type)

        # 3. Parse line items
        supabase.table("bills").update({"status": "analyzing"}).eq("id", bill_id).execute()
        logger.info("OCR raw text for bill %s:\n%s", bill_id, raw_text)
        parser = BillParser()
        parsed_items = parser.parse(raw_text, bill_date=date.today())

        # Persist line items to the database
        line_item_rows = [
            {
                "id": str(uuid.uuid4()),
                "bill_id": bill_id,
                "cpt_code": item.cpt_code,
                "description": item.description,
                "service_date": item.service_date.isoformat(),
                "quantity": item.quantity,
                "unit_charge": float(item.unit_charge),
                "total_charge": float(item.total_charge),
                "modifier": item.modifier,
                "diagnosis_pointers": item.diagnosis_pointers,
            }
            for item in parsed_items
        ]
        if line_item_rows:
            supabase.table("line_items").insert(line_item_rows).execute()

        # 4. Load reference data and run rules engine
        ncci_pairs = _load_ncci_pairs(supabase)
        medicare_rates = _load_medicare_rates(supabase, [item.cpt_code for item in parsed_items])
        engine = RulesEngine(ncci_edit_pairs=ncci_pairs, medicare_rates=medicare_rates)
        detected_errors = engine.run(parsed_items)

        # Map detected errors to line item IDs
        line_item_ids = [row["id"] for row in line_item_rows]
        billing_errors = _map_errors_to_line_items(detected_errors, line_item_ids)

        # 5. AI summary via Claude
        ai_service = get_ai_analysis_service()
        ai_summary = await ai_service.generate_bill_summary(billing_errors, parsed_items)

        # 6. Persist analysis results
        total_charges = sum(Decimal(str(item.total_charge)) for item in parsed_items)
        total_savings = sum(e.estimated_overcharge for e in billing_errors)
        estimated_fair = total_charges - total_savings

        supabase.table("analysis_results").insert({
            "id": str(uuid.uuid4()),
            "bill_id": bill_id,
            "errors": [e.model_dump() for e in billing_errors],
            "total_charges": float(total_charges),
            "estimated_fair_value": float(estimated_fair),
            "total_potential_savings": float(total_savings),
            "ai_summary": ai_summary,
            "dispute_letter_url": None,
            "report_url": None,
        }).execute()

        supabase.table("bills").update({"status": "complete"}).eq("id", bill_id).execute()
        logger.info("Analysis complete for bill %s — %d errors found", bill_id, len(billing_errors))

    except OcrExtractionError as exc:
        logger.error("OCR failed for bill %s: %s", bill_id, exc)
        supabase.table("bills").update({"status": "failed"}).eq("id", bill_id).execute()
    except Exception as exc:
        logger.exception("Unexpected error in analysis pipeline for bill %s: %s", bill_id, exc)
        supabase.table("bills").update({"status": "failed"}).eq("id", bill_id).execute()


def _mime_type_from_path(file_path: str) -> str:
    extension = file_path.rsplit(".", 1)[-1].lower()
    return {"pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(
        extension, "application/octet-stream"
    )


def _load_ncci_pairs(supabase: Client) -> dict[str, set[str]]:
    """Load active NCCI edit pairs from the database."""
    response = supabase.table("ncci_edit_pairs").select("column_one_code,column_two_code").is_("deletion_date", "null").execute()
    pairs: dict[str, set[str]] = {}
    for row in response.data:
        pairs.setdefault(row["column_one_code"], set()).add(row["column_two_code"])
    return pairs


def _load_medicare_rates(supabase: Client, cpt_codes: list[str]) -> dict[str, Decimal]:
    """Load Medicare non-facility rates for the given CPT codes."""
    if not cpt_codes:
        return {}
    response = (
        supabase.table("medicare_fee_schedule")
        .select("cpt_code,non_facility_rate")
        .in_("cpt_code", list(set(cpt_codes)))
        .order("year", desc=True)
        .execute()
    )
    # Take the most recent rate per CPT code (ordered by year desc)
    rates: dict[str, Decimal] = {}
    for row in response.data:
        if row["cpt_code"] not in rates:
            rates[row["cpt_code"]] = Decimal(str(row["non_facility_rate"]))
    return rates


def _map_errors_to_line_items(
    detected_errors: list[DetectedError],
    line_item_ids: list[str],
) -> list[BillingError]:
    """Convert rules engine DetectedErrors to BillingError models using real UUIDs."""
    result: list[BillingError] = []
    for error in detected_errors:
        affected_ids = [
            line_item_ids[i] for i in error.affected_indices if i < len(line_item_ids)
        ]
        result.append(BillingError(
            code=BillingErrorCode(error.code),
            severity=ErrorSeverity(error.severity),
            affected_line_item_ids=affected_ids,
            description=error.description,
            estimated_overcharge=error.estimated_overcharge,
            medicare_benchmark_rate=error.medicare_benchmark_rate,
        ))
    return result


@router.post("/{bill_id}/report", response_model=ReportGenerated, status_code=status.HTTP_200_OK)
@limiter.limit("5/hour")  # PDF generation + email — tighter limit than analysis
async def generate_report(
    request: Request,
    bill_id: str,
    body: ReportRequest,
    supabase: Client = Depends(get_supabase_client),
    ai_service: AiAnalysisService = Depends(get_ai_analysis_service),
    email_service: EmailService = Depends(get_email_service),
) -> ReportGenerated:
    """Generate the full PDF report and dispute letter, then email them to the patient.

    Called by the Next.js webhook after a successful Stripe payment.
    Idempotent — safe to call more than once for the same bill.
    """
    # Load the bill and existing analysis
    bill_row = supabase.table("bills").select("id,file_name,file_path,user_id").eq("id", bill_id).single().execute()
    if not bill_row.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bill not found.")

    analysis_row = (
        supabase.table("analysis_results")
        .select("id,errors,ai_summary,report_url")
        .eq("bill_id", bill_id)
        .single()
        .execute()
    )
    if not analysis_row.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found.")

    # Idempotency — don't regenerate if already done
    if analysis_row.data.get("report_url"):
        logger.info("Report already generated for bill %s, skipping", bill_id)
        return ReportGenerated()

    # Reload parsed line items from DB
    items_row = (
        supabase.table("line_items")
        .select("cpt_code,description,service_date,quantity,unit_charge,total_charge,modifier,diagnosis_pointers")
        .eq("bill_id", bill_id)
        .execute()
    )
    line_items = [
        ParsedLineItem(
            cpt_code=r["cpt_code"],
            description=r["description"],
            service_date=date.fromisoformat(r["service_date"]),
            quantity=r["quantity"],
            unit_charge=float(r["unit_charge"]),
            total_charge=float(r["total_charge"]),
            modifier=r["modifier"],
            diagnosis_pointers=r["diagnosis_pointers"],
        )
        for r in items_row.data
    ]

    # Reconstruct BillingError list from stored JSONB
    billing_errors = [
        BillingError(
            code=BillingErrorCode(e["code"]),
            severity=ErrorSeverity(e["severity"]),
            affected_line_item_ids=e["affected_line_item_ids"],
            description=e["description"],
            estimated_overcharge=Decimal(str(e["estimated_overcharge"])),
            medicare_benchmark_rate=Decimal(str(e["medicare_benchmark_rate"])) if e.get("medicare_benchmark_rate") else None,
        )
        for e in analysis_row.data["errors"]
    ]

    file_name: str = bill_row.data["file_name"]
    user_id: str = bill_row.data["user_id"]
    ai_summary: str = analysis_row.data["ai_summary"]

    # Generate dispute letter and PDFs
    dispute_letter_text = await ai_service.generate_dispute_letter(billing_errors, line_items, file_name)
    generator = ReportGenerator()
    report_pdf = generator.generate_report_pdf(billing_errors, line_items, file_name, ai_summary)
    dispute_pdf = generator.generate_dispute_letter_pdf(dispute_letter_text)

    # Upload PDFs to Supabase Storage (private bucket: 'reports')
    report_path = f"{user_id}/{bill_id}/report.pdf"
    dispute_path = f"{user_id}/{bill_id}/dispute-letter.pdf"
    supabase.storage.from_("reports").upload(report_path, report_pdf, {"content-type": "application/pdf", "upsert": "true"})
    supabase.storage.from_("reports").upload(dispute_path, dispute_pdf, {"content-type": "application/pdf", "upsert": "true"})

    # Store storage paths in analysis_results
    supabase.table("analysis_results").update({
        "report_url": report_path,
        "dispute_letter_url": dispute_path,
    }).eq("bill_id", bill_id).execute()

    # Send email with both PDFs attached
    email_service.send_report_email(
        to_email=body.user_email,
        bill_file_name=file_name,
        report_pdf=report_pdf,
        dispute_letter_pdf=dispute_pdf,
    )

    logger.info("Report generated and emailed for bill %s", bill_id)
    return ReportGenerated()
