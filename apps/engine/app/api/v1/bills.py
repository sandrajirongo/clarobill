"""Bill analysis API routes."""

import logging
import uuid
from collections import Counter
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from google.cloud import bigquery
from slowapi import Limiter
from slowapi.util import get_remote_address
from supabase import Client

from app.core.config import settings
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
        _run_analysis_pipeline,
        bill_id, body.file_path, body.state, body.county, body.zip_code,
        body.payer_name, body.plan_name, body.plan_type, supabase,
    )

    return AnalyzeAccepted()


async def _run_analysis_pipeline(
    bill_id: str,
    file_path: str,
    state: str | None,
    county: str | None,
    zip_code: str | None,
    payer_name: str | None,
    plan_name: str | None,
    plan_type: str | None,
    supabase: Client,
) -> None:
    """Full analysis pipeline — runs in the background after accepting the request.

    Steps:
      1. Download file from Supabase Storage
      2. OCR extraction
      3. Line item parsing
      4. Rules engine (all rules, including negotiated rate if payer/plan provided)
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

        # 3. Parse line items and attempt NPI extraction
        supabase.table("bills").update({"status": "analyzing"}).eq("id", bill_id).execute()
        logger.info("OCR raw text for bill %s:\n%s", bill_id, raw_text)
        parser = BillParser()
        parsed_items = parser.parse(raw_text, bill_date=date.today())

        # Best-effort NPI and name extraction — stored for hospital charge lookup.
        # Both are optional; the pipeline continues without them.
        hospital_npi = parser.extract_npi(raw_text)
        hospital_name = parser.extract_hospital_name(raw_text)
        if hospital_npi:
            logger.info("Extracted NPI %s from bill %s", hospital_npi, bill_id)
        if hospital_name:
            logger.info("Extracted hospital name '%s' from bill %s", hospital_name, bill_id)
        # Persist all confirmed identity fields — hospital from OCR, payer/plan from user
        identity_update: dict = {}
        if hospital_npi:
            identity_update["hospital_npi"] = hospital_npi
        if hospital_name:
            identity_update["hospital_name"] = hospital_name
        if payer_name:
            identity_update["payer_name"] = payer_name
        if plan_name:
            identity_update["plan_name"] = plan_name
        if plan_type:
            identity_update["plan_type"] = plan_type
        if identity_update:
            supabase.table("bills").update(identity_update).eq("id", bill_id).execute()

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
        service_type, payer_type = _derive_ncci_context(cpt_codes, plan_type)
        ncci_pairs = _load_ncci_pairs(supabase, service_type, payer_type, rate_date)
        mue_limits = _load_mue_limits(supabase, cpt_codes, service_type, payer_type, rate_date)
        medicare_rates = _load_medicare_rates(supabase, cpt_codes, locality_code, rate_date)
        non_payable_codes = _load_non_payable_codes(supabase, cpt_codes, rate_date)
        hcpcs_non_payable, hcpcs_termination_dates = _load_hcpcs_code_data(
            supabase, cpt_codes, rate_date
        )
        non_payable_codes.update(hcpcs_non_payable)
        anesthesia_cf = _load_anesthesia_cf(supabase, locality_code, rate_date)
        anesthesia_base_units = _load_anesthesia_base_units(supabase, cpt_codes, rate_date.year)
        opps_rates = _load_opps_rates(supabase, cpt_codes, locality_code, rate_date)
        ambulance_rates = _load_ambulance_rates(
            supabase, cpt_codes, locality_code, zip_code, rate_date
        )
        bq = _build_bq_client()
        hospital_charges = _load_hospital_charges(bq, cpt_codes, hospital_npi, hospital_name)
        negotiated_charges = _load_negotiated_charges(bq, cpt_codes, hospital_npi, hospital_name, payer_name, plan_name)
        engine = RulesEngine(
            ncci_edit_pairs=ncci_pairs,
            medicare_rates=medicare_rates,
            non_payable_codes=non_payable_codes,
            anesthesia_cf=anesthesia_cf,
            anesthesia_base_units=anesthesia_base_units,
            opps_rates=opps_rates,
            ambulance_rates=ambulance_rates,
            hcpcs_termination_dates=hcpcs_termination_dates,
            hospital_charges=hospital_charges,
            negotiated_charges=negotiated_charges,
            mue_limits=mue_limits,
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


def _derive_ncci_context(cpt_codes: list[str], plan_type: str | None) -> tuple[str, str]:
    """Determine the NCCI service_type and payer_type to use for a given bill.

    service_type: inferred from the code set present on the bill.
      'dme'          — any HCPCS Level II code in the A/E/K/L/S range (DME/supply codes)
      'practitioner' — default; covers the vast majority of professional/physician bills

    payer_type: maps the patient's insurance type to the CMS NCCI file to query.
      'medicare'  — plan_type is 'medicare' or unknown/commercial (Medicare NCCI is the
                    national floor standard and the only payer-specific file currently loaded)
      'medicaid'  — plan_type is 'medicaid' (CMS national MCD files apply; when state-specific
                    Medicaid edits are loaded they will use payer_type='medicaid')

    Note: outpatient hospital service type is not yet auto-detected. OPPS-billed facility
    claims can be distinguished by the presence of revenue codes, which are not extracted
    by the current parser. Default 'practitioner' is conservative — PTP edits for
    practitioner services are a valid floor for outpatient facility bills.
    """
    # DME detection: HCPCS Level II alpha codes that are supply/equipment categories
    dme_prefixes = ("A0", "A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9",
                    "E0", "E1", "K0", "L0", "L1", "L2", "L3", "L4", "L5", "L6",
                    "L7", "L8", "L9")
    has_dme = any(
        c and any(c.startswith(p) for p in dme_prefixes)
        for c in cpt_codes
    )
    service_type = "dme" if has_dme else "practitioner"

    payer_type = "medicaid" if plan_type == "medicaid" else "medicare"

    return service_type, payer_type


def _load_ncci_pairs(
    supabase: Client,
    service_type: str = "practitioner",
    payer_type: str = "medicare",
    service_date: date | None = None,
) -> dict[str, set[str]]:
    """Load NCCI PTP edit pairs active on service_date.

    Filters to pairs whose effective_date <= service_date and deletion_date is
    null or after service_date, so historical bills use the edits in force at
    the time of service rather than today's rules.
    """
    query = (
        supabase.table("ncci_edit_pairs")
        .select("column_one_code,column_two_code")
        .eq("service_type", service_type)
        .eq("payer_type", payer_type)
    )
    if service_date is not None:
        query = (
            query
            .lte("effective_date", service_date.isoformat())
            .or_(f"deletion_date.is.null,deletion_date.gte.{service_date.isoformat()}")
        )
    else:
        query = query.is_("deletion_date", "null")

    response = query.execute()
    pairs: dict[str, set[str]] = {}
    for row in response.data:
        pairs.setdefault(row["column_one_code"], set()).add(row["column_two_code"])
    return pairs


def _load_mue_limits(
    supabase: Client,
    cpt_codes: list[str],
    service_type: str = "practitioner",
    payer_type: str = "medicare",
    service_date: date | None = None,
) -> dict[str, tuple[int, int]]:
    """Load CMS MUE limits for the CPT codes on this bill.

    Returns a map of hcpcs_code → (mue_value, adjudication_indicator).

    Uses the most recent quarterly release whose effective_date is on or before
    service_date, so a bill from 2022 gets the 2022 MUE values, not the current
    ones. Falls back to any available row when service_date is not provided.
    """
    if not cpt_codes:
        return {}

    query = (
        supabase.table("ncci_mue_limits")
        .select("hcpcs_code,mue_value,adjudication_indicator,effective_date")
        .in_("hcpcs_code", list(set(cpt_codes)))
        .eq("service_type", service_type)
        .eq("payer_type", payer_type)
    )
    if service_date is not None:
        query = query.lte("effective_date", service_date.isoformat())

    # Order by code then effective_date descending so the first occurrence of
    # each code is the most recent quarterly release in effect on service_date.
    response = (
        query
        .order("hcpcs_code")
        .order("effective_date", desc=True)
        .execute()
    )

    result: dict[str, tuple[int, int]] = {}
    for row in response.data:
        code = row["hcpcs_code"]
        if code not in result:
            result[code] = (int(row["mue_value"]), int(row["adjudication_indicator"]))
    return result


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


def _load_hcpcs_code_data(
    supabase: Client,
    cpt_codes: list[str],
    rate_date: date = date(2026, 1, 1),
) -> tuple[dict[str, str], dict[str, date]]:
    """Return non-payable status and termination dates for HCPCS Level II codes on the bill.

    Queries cms_hcpcs_codes for any alpha-prefixed codes (A-Z followed by 4 digits)
    and returns two mappings:

    non_payable: hcpc → proc_stat-equivalent key for merging into non_payable_codes:
        'I'  ← coverage_code 'I' (not payable by Medicare) — critical
        'N'  ← coverage_code 'M' or 'S' (non-covered / non-covered by statute) — warning
        'B'  ← pricing_indicator '00' with no explicit coverage code (not separately
                priced by Part B — bundled or Part A only) — critical

    termination_dates: hcpc → last valid date. Only codes whose termination_date is
        not null are included. The rules engine uses this to flag service dates that
        fall after the termination date.

    Uses the most recent quarterly release with effective_from ≤ rate_date.
    """
    hcpcs_level2 = [c for c in set(cpt_codes) if c and not c[0].isdigit()]
    if not hcpcs_level2:
        return {}, {}

    response = (
        supabase.table("cms_hcpcs_codes")
        .select("hcpc,pricing_indicator,coverage_code,termination_date")
        .in_("hcpc", hcpcs_level2)
        .lte("effective_from", rate_date.isoformat())
        .order("effective_from", desc=True)
        .execute()
    )

    # One row per hcpc: take the most recent (first due to desc ordering)
    seen: set[str] = set()
    non_payable: dict[str, str] = {}
    termination_dates: dict[str, date] = {}

    for row in response.data:
        hcpc = row["hcpc"]
        if hcpc in seen:
            continue
        seen.add(hcpc)

        coverage = (row.get("coverage_code") or "").strip()
        pricing = (row.get("pricing_indicator") or "").strip()
        term_raw = row.get("termination_date")

        # Map HCPCS coverage codes to the proc_stat keys the rules engine understands
        if coverage == "I":
            non_payable[hcpc] = "I"
        elif coverage in ("M", "S"):
            non_payable[hcpc] = "N"
        elif pricing == "00":
            # Not separately priced by Part B (bundled, Part A only, etc.)
            non_payable[hcpc] = "B"

        if term_raw:
            try:
                termination_dates[hcpc] = date.fromisoformat(term_raw)
            except ValueError:
                pass

    return non_payable, termination_dates


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


def _resolve_ambulance_rural_indicator(
    supabase: Client,
    zip_code: str | None,
    rate_date: date,
) -> str:
    """Resolve the rural/urban designation for a ZIP code from the AFS ZIP5 table.

    Returns:
        ''  = urban    (default when ZIP is unknown or not found)
        'R' = rural
        'B' = super rural

    Uses the most recent ZIP5 release with effective_from <= rate_date.
    Falls back to '' (urban) on any lookup failure so the engine still runs.
    """
    if not zip_code:
        return ""

    zip5 = zip_code.strip()[:5]
    if len(zip5) < 5 or not zip5.isdigit():
        return ""

    response = (
        supabase.table("cms_ambulance_zip_locality")
        .select("rural_indicator")
        .eq("zip5", zip5)
        .lte("effective_from", rate_date.isoformat())
        .order("effective_from", desc=True)
        .limit(1)
        .execute()
    )
    if not response.data:
        logger.warning(
            "ZIP %s not found in ambulance ZIP table (effective_from<=%s) — using urban rate.",
            zip5,
            rate_date,
        )
        return ""
    return response.data[0]["rural_indicator"] or ""


def _load_ambulance_rates(
    supabase: Client,
    cpt_codes: list[str],
    locality_code: str,
    zip_code: str | None,
    rate_date: date,
) -> dict[str, Decimal]:
    """Load CMS Ambulance Fee Schedule benchmarks for any ambulance codes on the bill.

    Resolves the applicable rate tier (urban / rural / super-rural) using the
    patient's ZIP code. Falls back to the urban rate when ZIP is unavailable.

    locality_code is the 7-char code from _resolve_locality():
      carrier = locality_code[:5]   (e.g. '01112')
      locality = locality_code[5:]  (e.g. '05')

    Returns an empty dict if no A04xx codes are on the bill or the table has no
    data for this carrier/locality — this disables the ambulance outlier rule
    rather than emitting false flags.

    Args:
        supabase: Authenticated Supabase client.
        cpt_codes: List of CPT/HCPC codes from the parsed bill.
        locality_code: 7-char CMS MAC locality code from _resolve_locality().
        zip_code: Patient's 5-digit ZIP code for rural indicator resolution.
        rate_date: Representative service date from the bill's line items.
    """
    # Ambulance HCPCS codes are A04xx — filter out all standard CPT codes
    ambulance_codes = [c for c in set(cpt_codes) if c.startswith("A04")]
    if not ambulance_codes:
        return {}

    # Use national default when locality couldn't be resolved
    if locality_code == "0000000":
        logger.warning(
            "Ambulance rate lookup: locality unknown — no benchmark available for this bill."
        )
        return {}

    carrier = locality_code[:5]
    locality = locality_code[5:]
    rate_date_str = rate_date.isoformat()

    response = (
        supabase.table("cms_ambulance_rates")
        .select("hcpc,urban_rate,rural_rate,super_rural_rate")
        .in_("hcpc", ambulance_codes)
        .eq("carrier", carrier)
        .eq("locality", locality)
        .lte("effective_from", rate_date_str)
        .order("effective_from", desc=True)
        .execute()
    )

    if not response.data:
        return {}

    # Take the most recent available entry per HCPC code (≤ service date)
    latest: dict[str, dict] = {}
    for row in response.data:
        if row["hcpc"] not in latest:
            latest[row["hcpc"]] = row

    rural_indicator = _resolve_ambulance_rural_indicator(supabase, zip_code, rate_date)

    rates: dict[str, Decimal] = {}
    for hcpc, row in latest.items():
        if rural_indicator == "B" and row["super_rural_rate"] is not None:
            rate_value = row["super_rural_rate"]
        elif rural_indicator == "R" and row["rural_rate"] is not None:
            rate_value = row["rural_rate"]
        else:
            # Urban default (also used when rural/super-rural rate is null for this code)
            rate_value = row["urban_rate"]

        if rate_value is not None and float(rate_value) > 0:
            rates[hcpc] = Decimal(str(rate_value)).quantize(Decimal("0.01"))

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


def _build_bq_client() -> bigquery.Client | None:
    """Build a BigQuery client using Application Default Credentials.

    Returns None when gcp_project_id is not configured (local dev without GCP
    access), which causes hospital charge lookup to be skipped gracefully.
    On Cloud Run the runtime SA (clarobill-vision-sa) provides credentials
    automatically via ADC — no key file needed.
    """
    if not settings.gcp_project_id:
        return None
    try:
        return bigquery.Client(project=settings.gcp_project_id)
    except Exception as exc:
        logger.warning("Could not build BigQuery client — hospital charge lookup disabled: %s", exc)
        return None


def _load_hospital_charges(
    bq: bigquery.Client | None,
    cpt_codes: list[str],
    hospital_npi: str | None,
    hospital_name: str | None,
) -> dict[str, Decimal]:
    """Load the hospital's published gross charges for the CPT codes on the bill.

    Queries BigQuery hospital_charges using:
      1. NPI match (exact) — preferred; always unambiguous.
      2. Name match (LIKE on hospital_directory) — fallback when NPI unavailable.
         Only used when exactly one hospital matches, to avoid returning charges
         for the wrong facility.

    Returns an empty dict when: BigQuery not configured, no hospital identified,
    no match found, or name is ambiguous. The rules engine skips the hospital
    charge outlier rule when the dict is empty.
    """
    if bq is None or not cpt_codes:
        return {}
    if not hospital_npi and not hospital_name:
        return {}

    dataset = f"{settings.gcp_project_id}.{settings.bigquery_dataset}"
    unique_codes = list(set(cpt_codes))

    # 1. NPI match — exact and unambiguous
    if hospital_npi:
        return _query_charges_by_npi(bq, dataset, unique_codes, hospital_npi)

    # 2. Name match — resolve NPI from hospital_directory first
    assert hospital_name is not None
    npi = _resolve_npi_by_name(bq, dataset, hospital_name)
    if npi is None:
        logger.info("Hospital name '%s' matched 0 or >1 hospitals — skipping charge lookup", hospital_name)
        return {}
    return _query_charges_by_npi(bq, dataset, unique_codes, npi)


def _query_charges_by_npi(
    bq: bigquery.Client,
    dataset: str,
    cpt_codes: list[str],
    hospital_npi: str,
) -> dict[str, Decimal]:
    """Query hospital_charges for a specific NPI, returning gross charge per CPT code.

    Takes the highest gross_charge per code when a hospital has multiple rows for
    the same code (e.g. different settings or payer rows with different charges).
    The gross charge is the hospital's own maximum list price — billing above it
    is an unambiguous error regardless of which specific row was used for billing.
    """
    query = f"""
        SELECT code, MAX(gross_charge) AS gross_charge
        FROM `{dataset}.hospital_charges`
        WHERE hospital_npi = @npi
          AND code IN UNNEST(@codes)
          AND gross_charge IS NOT NULL
          AND gross_charge > 0
        GROUP BY code
    """
    job_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("npi", "STRING", hospital_npi),
        bigquery.ArrayQueryParameter("codes", "STRING", cpt_codes),
    ])
    try:
        rows = list(bq.query(query, job_config=job_config).result())
    except Exception as exc:
        logger.warning("BigQuery hospital charge lookup failed for NPI %s: %s", hospital_npi, exc)
        return {}
    return {row["code"]: Decimal(str(row["gross_charge"])).quantize(Decimal("0.01")) for row in rows}


def _resolve_npi_by_name(
    bq: bigquery.Client,
    dataset: str,
    hospital_name: str,
) -> str | None:
    """Resolve a hospital_npi from hospital_directory by fuzzy name match.

    Returns the NPI only when exactly one hospital matches, preventing charges
    from the wrong facility being returned when names are ambiguous.
    Uses a case-insensitive LIKE match on a cleaned version of the name.
    """
    # Use the name as-is for the LIKE pattern — BigQuery LOWER() handles case
    name_pattern = f"%{hospital_name.strip().lower()}%"
    query = f"""
        SELECT hospital_npi, COUNT(*) AS match_count
        FROM `{dataset}.hospital_directory`
        WHERE LOWER(hospital_name) LIKE @name_pattern
          AND hospital_npi IS NOT NULL
        GROUP BY hospital_npi
    """
    job_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("name_pattern", "STRING", name_pattern),
    ])
    try:
        rows = list(bq.query(query, job_config=job_config).result())
    except Exception as exc:
        logger.warning("BigQuery name lookup failed for '%s': %s", hospital_name, exc)
        return None
    if len(rows) == 1:
        return str(rows[0]["hospital_npi"])
    return None


def _load_negotiated_charges(
    bq: bigquery.Client | None,
    cpt_codes: list[str],
    hospital_npi: str | None,
    hospital_name: str | None,
    payer_name: str | None,
    plan_name: str | None,
) -> dict[str, Decimal]:
    """Load the insurer-specific contracted rate for each CPT code on this bill.

    Queries hospital_charges WHERE hospital_npi matches AND payer_name/plan_name
    match the patient's confirmed insurance plan. Returns the MAX(negotiated_charge)
    per code when multiple rows match (e.g. different settings or negotiated_type values).

    Returns empty dict when:
      - BigQuery not configured
      - No CPT codes on the bill
      - Hospital not identified (no NPI and no resolvable name)
      - Payer or plan not provided (user skipped insurance confirmation)
      - No matching rows found in hospital_charges for this payer/plan combination
        (hospital may not have published per-payer rates, or MRF uses different names)

    The rules engine skips NEGOTIATED_RATE_EXCEEDED when this returns empty.
    """
    if bq is None or not cpt_codes:
        return {}
    if not payer_name or not plan_name:
        return {}
    if not hospital_npi and not hospital_name:
        return {}

    dataset = f"{settings.gcp_project_id}.{settings.bigquery_dataset}"
    unique_codes = list(set(cpt_codes))

    # Resolve NPI if only name is available — same logic as hospital charge lookup
    npi = hospital_npi
    if not npi:
        assert hospital_name is not None
        npi = _resolve_npi_by_name(bq, dataset, hospital_name)
        if npi is None:
            logger.info(
                "Hospital name '%s' matched 0 or >1 hospitals — skipping negotiated rate lookup",
                hospital_name,
            )
            return {}

    # LIKE match on payer/plan — MRF data uses various naming conventions.
    # Use the user-entered value as a substring search (case-insensitive).
    # Only return rates when negotiated_type is 'negotiated' or 'derived' —
    # 'percentage' rates are multipliers of another rate and cannot be directly
    # compared to billed charges without additional context.
    payer_pattern = f"%{payer_name.strip().lower()}%"
    plan_pattern = f"%{plan_name.strip().lower()}%"

    query = f"""
        SELECT code, MAX(negotiated_charge) AS negotiated_charge
        FROM `{dataset}.hospital_charges`
        WHERE hospital_npi = @npi
          AND LOWER(payer_name) LIKE @payer_pattern
          AND LOWER(plan_name) LIKE @plan_pattern
          AND code IN UNNEST(@codes)
          AND negotiated_charge IS NOT NULL
          AND negotiated_charge > 0
          AND negotiated_type IN ('negotiated', 'derived')
        GROUP BY code
    """
    job_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("npi", "STRING", npi),
        bigquery.ScalarQueryParameter("payer_pattern", "STRING", payer_pattern),
        bigquery.ScalarQueryParameter("plan_pattern", "STRING", plan_pattern),
        bigquery.ArrayQueryParameter("codes", "STRING", unique_codes),
    ])
    try:
        rows = list(bq.query(query, job_config=job_config).result())
    except Exception as exc:
        logger.warning(
            "BigQuery negotiated rate lookup failed for NPI %s / payer '%s' / plan '%s': %s",
            npi, payer_name, plan_name, exc,
        )
        return {}

    if not rows:
        logger.info(
            "No negotiated rates found for NPI %s / payer '%s' / plan '%s' — "
            "hospital may not publish per-payer rates or names don't match MRF data.",
            npi, payer_name, plan_name,
        )
        return {}

    logger.info(
        "Loaded %d negotiated rates for NPI %s / payer '%s' / plan '%s'",
        len(rows), npi, payer_name, plan_name,
    )
    return {row["code"]: Decimal(str(row["negotiated_charge"])).quantize(Decimal("0.01")) for row in rows}


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
