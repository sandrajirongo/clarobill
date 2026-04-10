"""Bill analysis API routes."""

import logging
import uuid
from collections import Counter
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

    background_tasks.add_task(
        _run_analysis_pipeline, bill_id, body.file_path, body.state, body.county, supabase
    )

    return AnalyzeAccepted()


async def _run_analysis_pipeline(
    bill_id: str,
    file_path: str,
    state: str | None,
    county: str | None,
    supabase: Client,
) -> None:
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
        cpt_codes = [item.cpt_code for item in parsed_items]
        rate_date = _derive_rate_date(parsed_items)
        locality_code = _resolve_locality(supabase, state, county, rate_date.year)
        logger.info(
            "Using rate_date=%s locality_code=%s for bill %s (state=%s county=%s)",
            rate_date, locality_code, bill_id, state, county,
        )
        ncci_pairs = _load_ncci_pairs(supabase)
        medicare_rates = _load_medicare_rates(supabase, cpt_codes, locality_code, rate_date)
        non_payable_codes = _load_non_payable_codes(supabase, cpt_codes, rate_date)
        anesthesia_cf = _load_anesthesia_cf(supabase, locality_code, rate_date)
        anesthesia_base_units = _load_anesthesia_base_units(supabase, cpt_codes, rate_date.year)
        opps_rates = _load_opps_rates(supabase, cpt_codes, locality_code, rate_date)
        engine = RulesEngine(
            ncci_edit_pairs=ncci_pairs,
            medicare_rates=medicare_rates,
            non_payable_codes=non_payable_codes,
            anesthesia_cf=anesthesia_cf,
            anesthesia_base_units=anesthesia_base_units,
            opps_rates=opps_rates,
        )
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


def _derive_rate_date(parsed_items: list[ParsedLineItem]) -> date:
    """Determine the CMS fee schedule release date to use for benchmarking.

    Uses the most common service date across all line items. If dates are tied,
    the most recent wins. Falls back to today if no dates were parsed (e.g. OCR
    failed to extract dates).

    The engine queries cms_pfs_indicators and cms_opps_cap with
    effective_from <= rate_date, so this date is used to pick the most recent
    quarterly release that was in effect when the service was rendered. For
    example, a service date of 2024-02-15 picks the 2024-01-01 (JANR) release,
    while 2024-05-10 picks the 2024-04-01 release.
    """
    dates = [item.service_date for item in parsed_items if item.service_date is not None]
    if not dates:
        return date.today()
    counts: Counter[date] = Counter(dates)
    # Most frequent date; break ties by preferring the most recent
    return max(counts, key=lambda d: (counts[d], d))


def _load_ncci_pairs(supabase: Client) -> dict[str, set[str]]:
    """Load active NCCI edit pairs from the database."""
    response = supabase.table("ncci_edit_pairs").select("column_one_code,column_two_code").is_("deletion_date", "null").execute()
    pairs: dict[str, set[str]] = {}
    for row in response.data:
        pairs.setdefault(row["column_one_code"], set()).add(row["column_two_code"])
    return pairs


def _load_medicare_rates(
    supabase: Client,
    cpt_codes: list[str],
    locality_code: str = "0000000",
    rate_date: date = date(2026, 1, 1),
) -> dict[str, Decimal]:
    """Compute Medicare non-facility rates for the given CPT codes.

    Rates are derived from the CMS PFS indicators (RVU components + conversion
    factor) adjusted by the GPCI values for the given locality.

    For the national rate (locality '0000000'), all GPCIs are 1.0, so:
        national_rate = nfac_total_rvu * conv_fact

    For a locality-adjusted rate:
        rate = (rvu_work * gpci_work + nfac_pe_rvu * gpci_pe + rvu_mp * gpci_mp) * conv_fact

    Only codes with proc_stat='A' (actively priced via RVU formula) are returned.
    Codes without a rate entry — or with zero total RVU — are excluded so the
    rules engine skips them rather than emitting false outlier flags.

    Args:
        supabase: Authenticated Supabase client.
        cpt_codes: List of CPT/HCPC codes from the parsed bill.
        locality_code: CMS MAC locality code for GPCI adjustment.
                       Defaults to '0000000' (national, all GPCIs = 1.0).
        rate_date: The representative service date derived from the bill's line items.
                   Queries use effective_from <= rate_date so the most recent quarterly
                   release in effect on that date is used automatically.
    """
    if not cpt_codes:
        return {}

    unique_codes = list(set(cpt_codes))
    rate_date_str = rate_date.isoformat()

    # Fetch RVU components — pick the most recent quarterly release ≤ service date
    indicators_resp = (
        supabase.table("cms_pfs_indicators")
        .select("hcpc,rvu_work,nfac_pe_rvu,rvu_mp,nfac_total_rvu,conv_fact,proc_stat")
        .in_("hcpc", unique_codes)
        .eq("modifier", "")
        .eq("proc_stat", "A")
        .lte("effective_from", rate_date_str)
        .order("effective_from", desc=True)
        .execute()
    )

    # Take the most recent available entry per HCPC code (≤ service date)
    indicators: dict[str, dict] = {}
    for row in indicators_resp.data:
        if row["hcpc"] not in indicators:
            indicators[row["hcpc"]] = row

    if not indicators:
        return {}

    # Fetch GPCI values — year-based (GPCI values do not change mid-year)
    locality_resp = (
        supabase.table("cms_localities")
        .select("gpci_work,gpci_pe,gpci_mp")
        .eq("locality_code", locality_code)
        .lte("year", rate_date.year)
        .order("year", desc=True)
        .limit(1)
        .execute()
    )

    if locality_resp.data:
        gpci = locality_resp.data[0]
        gpci_work = Decimal(str(gpci["gpci_work"]))
        gpci_pe   = Decimal(str(gpci["gpci_pe"]))
        gpci_mp   = Decimal(str(gpci["gpci_mp"]))
    else:
        # Fall back to national (1.0) if locality not found
        gpci_work = gpci_pe = gpci_mp = Decimal("1.0")
        logger.warning("Locality %s not found — using national GPCIs (1.0)", locality_code)

    rates: dict[str, Decimal] = {}
    for hcpc, row in indicators.items():
        cf = Decimal(str(row["conv_fact"]))
        if cf == 0:
            continue
        if gpci_work == gpci_pe == gpci_mp == Decimal("1.0"):
            # Shortcut: use the pre-summed national total
            rate = Decimal(str(row["nfac_total_rvu"])) * cf
        else:
            rate = (
                Decimal(str(row["rvu_work"])) * gpci_work
                + Decimal(str(row["nfac_pe_rvu"])) * gpci_pe
                + Decimal(str(row["rvu_mp"])) * gpci_mp
            ) * cf
        if rate > 0:
            rates[hcpc] = rate.quantize(Decimal("0.01"))

    return rates


def _load_non_payable_codes(
    supabase: Client,
    cpt_codes: list[str],
    rate_date: date = date(2026, 1, 1),
) -> dict[str, str]:
    """Return a map of cpt_code → proc_stat for any non-payable codes on the bill.

    Only codes with proc_stat in ('I', 'B', 'N') are returned:
      I = Inactive, B = Bundled (not separately payable), N = Non-covered.
    Codes not present in cms_pfs_indicators are ignored — we only flag what we
    can confirm, not codes we simply don't recognise.
    """
    if not cpt_codes:
        return {}
    response = (
        supabase.table("cms_pfs_indicators")
        .select("hcpc,proc_stat")
        .in_("hcpc", list(set(cpt_codes)))
        .in_("proc_stat", ["I", "B", "N"])
        .eq("modifier", "")
        .lte("effective_from", rate_date.isoformat())
        .order("effective_from", desc=True)
        .execute()
    )
    result: dict[str, str] = {}
    for row in response.data:
        if row["hcpc"] not in result:
            result[row["hcpc"]] = row["proc_stat"]
    return result


def _load_anesthesia_base_units(
    supabase: Client,
    cpt_codes: list[str],
    rate_year: int = 2026,
) -> dict[str, int]:
    """Return published CMS base units for any anesthesia codes on the bill.

    Uses the closest available vintage ≤ the bill year (CMS released tables in
    2018 and 2022; a 2020 bill uses the 2018 table, a 2023 bill uses 2022).

    Only anesthesia codes (00100–01999) are returned — other codes are ignored.
    Returns an empty dict if the table has not been loaded, which causes the
    rules engine to fall back to the heuristic base unit ceiling.
    """
    anes_codes = [c for c in set(cpt_codes) if c.isdigit() and 100 <= int(c) <= 1999]
    if not anes_codes:
        return {}

    response = (
        supabase.table("cms_anesthesia_base_units")
        .select("cpt_code,base_units,effective_year")
        .in_("cpt_code", anes_codes)
        .lte("effective_year", rate_year)
        .order("effective_year", desc=True)
        .execute()
    )

    # Take the most recent available entry per code (≤ bill year)
    result: dict[str, int] = {}
    for row in response.data:
        if row["cpt_code"] not in result:
            result[row["cpt_code"]] = int(row["base_units"])
    return result


def _load_opps_rates(
    supabase: Client,
    cpt_codes: list[str],
    locality_code: str = "0000000",
    rate_date: date = date(2026, 1, 1),
) -> dict[str, Decimal]:
    """Load OPPS facility payment caps for the given CPT codes and locality.

    Returns a map of hcpc → facility_price using the no-modifier (modifier='') rows,
    which represent the standard outpatient facility payment cap. Uses the most recent
    quarterly release with effective_from <= service date. Returns an empty dict if
    the table has no data for this locality, which disables the facility outlier rule.

    Args:
        supabase: Authenticated Supabase client.
        cpt_codes: List of CPT/HCPC codes from the parsed bill.
        locality_code: 7-char CMS MAC locality code from _resolve_locality().
        rate_date: Representative service date derived from the bill's line items.
    """
    if not cpt_codes:
        return {}

    response = (
        supabase.table("cms_opps_cap")
        .select("hcpc,facility_price")
        .in_("hcpc", list(set(cpt_codes)))
        .eq("modifier", "")
        .eq("locality_code", locality_code)
        .lte("effective_from", rate_date.isoformat())
        .order("effective_from", desc=True)
        .execute()
    )

    # Take the most recent available entry per code (≤ service date)
    rates: dict[str, Decimal] = {}
    for row in response.data:
        hcpc = row["hcpc"]
        if hcpc not in rates and row["facility_price"] is not None:
            rates[hcpc] = Decimal(str(row["facility_price"]))

    return rates


def _resolve_locality(
    supabase: Client,
    state: str | None,
    county: str | None,
    rate_year: int = 2026,
) -> str:
    """Resolve a CMS 7-digit locality code from the patient's state, county, and bill year.

    Uses year <= rate_year so the closest available vintage is used automatically
    when the exact year isn't loaded (e.g. a 2019 bill uses the 2020 table).

    Lookup order:
      1. Exact county match (most specific)
      2. REST OF STATE fallback for the state
      3. STATEWIDE entry for the state
      4. National default '0000000' (all GPCIs = 1.0)

    Returns '0000000' if state is not provided or no match is found at any level.
    """
    if not state:
        return "0000000"

    state_upper = state.strip().upper()

    # 1. Exact county match
    if county:
        county_upper = county.strip().upper()
        for suffix in (" COUNTY", " CNTY"):
            if county_upper.endswith(suffix):
                county_upper = county_upper[: -len(suffix)].strip()

        response = (
            supabase.table("cms_county_locality")
            .select("locality_code")
            .eq("state", state_upper)
            .eq("county_name", county_upper)
            .lte("year", rate_year)
            .order("year", desc=True)
            .limit(1)
            .execute()
        )
        if response.data:
            return str(response.data[0]["locality_code"])

    # 2. REST OF STATE fallback
    response = (
        supabase.table("cms_county_locality")
        .select("locality_code")
        .eq("state", state_upper)
        .eq("is_rest_of_state", True)
        .lte("year", rate_year)
        .order("year", desc=True)
        .limit(1)
        .execute()
    )
    if response.data:
        return str(response.data[0]["locality_code"])

    # 3. STATEWIDE entry
    response = (
        supabase.table("cms_county_locality")
        .select("locality_code")
        .eq("state", state_upper)
        .eq("is_statewide", True)
        .lte("year", rate_year)
        .order("year", desc=True)
        .limit(1)
        .execute()
    )
    if response.data:
        return str(response.data[0]["locality_code"])

    # 4. National default
    logger.warning(
        "Could not resolve locality for state=%s county=%s year<=%d — using national default.",
        state,
        county,
        rate_year,
    )
    return "0000000"


def _load_anesthesia_cf(
    supabase: Client,
    locality_code: str = "0000000",
    rate_date: date = date(2026, 1, 1),
) -> Decimal | None:
    """Load the locality-adjusted anesthesia conversion factor.

    Derives contractor and locality_number from the 7-char locality_code.
    Falls back to the synthetic NATIONAL row when locality_code is '0000000'.
    Uses effective_from <= rate_date so the most recent quarterly release in
    effect on the service date is used, including mid-year corrections.

    Returns None if the table has not been loaded yet, which disables the
    anesthesia outlier rule rather than using a hardcoded fallback.
    """
    if locality_code == "0000000":
        contractor, locality_number = "NATL", "NATL"
    else:
        # locality_code = contractor (5 chars) + locality_number (2 chars)
        contractor = locality_code[:5]
        locality_number = locality_code[5:]

    response = (
        supabase.table("cms_anesthesia_cf")
        .select("non_qualifying_cf")
        .eq("contractor", contractor)
        .eq("locality_number", locality_number)
        .lte("effective_from", rate_date.isoformat())
        .order("effective_from", desc=True)
        .limit(1)
        .execute()
    )
    if not response.data:
        # Try national fallback if the specific locality doesn't have an anesthesia CF
        if contractor != "NATL":
            return _load_anesthesia_cf(supabase, "0000000", rate_date)
        logger.warning(
            "Anesthesia CF not found for contractor=%s locality=%s effective_from<=%s — "
            "anesthesia outlier detection disabled.",
            contractor,
            locality_number,
            rate_date,
        )
        return None
    return Decimal(str(response.data[0]["non_qualifying_cf"]))


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
