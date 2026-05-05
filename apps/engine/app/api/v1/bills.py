"""Bill analysis API routes."""

import asyncio
import logging
import uuid
from collections import Counter
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from google.cloud import bigquery
from slowapi import Limiter
from slowapi.util import get_remote_address
from supabase import Client

from app.core.config import settings
from app.core.dependencies import get_ai_analysis_service, get_email_service, get_supabase_client
from app.core.posthog_client import posthog_client
from app.core.supabase_helpers import as_optional_row, as_rows
from app.models.bill import (
    AnalyzeAccepted,
    AnalyzeRequest,
    BillingError,
    BillingErrorCode,
    BillStatus,
    ErrorSeverity,
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
    supabase.table("bills").update({"status": BillStatus.OCR_PROCESSING}).eq("id", bill_id).execute()

    posthog_client.capture(
        distinct_id=body.user_id,
        event="bill analysis started",
        properties={
            "bill_id": bill_id,
            "has_payer_info": bool(body.payer_name),
            "plan_type": body.plan_type,
        },
    )

    background_tasks.add_task(
        _run_analysis_pipeline,
        bill_id, body.file_path, body.state, body.county, body.zip_code,
        body.payer_name, body.plan_name, body.plan_type, body.user_id, supabase,
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
    user_id: str,
    supabase: Client,
) -> None:
    """Full analysis pipeline — runs in the background after accepting the request.

    Steps:
      1. Download file from Supabase Storage
      2. OCR extraction
      3. Line item parsing
      4. Rules engine (all rules, including negotiated rate if payer/plan provided)
      5. AI analysis (Gemini primary, Claude fallback)
      6. Persist results and update bill status
    """
    logger.info("Processing bill %s for user %s", bill_id, user_id)
    try:
        # S6+S7 (Phase 8.2): re-analyze idempotency.
        #
        # Pre-S6 the pipeline always did `analysis_results.insert(...)`. On a
        # second analyze for the same bill_id, Postgres rejected with a
        # 23505 unique_violation (analysis_results.bill_id is UNIQUE).
        # Supabase-py raised, the broad except below caught it, and the bill
        # was marked FAILED — destroying user-visible state for an analysis
        # that had already succeeded.
        #
        # S7: even setting that aside, the prior pipeline ran every BQ +
        # Gemini call before discovering the existing analysis_results row.
        # A flapping retry could rack up real BQ on-demand spend + Vertex AI
        # tokens on every iteration with zero idempotency gate.
        #
        # Early-return: if a COMPLETE analysis_results row already exists,
        # log a 'bill analysis skipped' PostHog event and return without I/O.
        existing = (
            supabase.table("analysis_results")
            .select("id")
            .eq("bill_id", bill_id)
            .limit(1)
            .execute()
        )
        if as_rows(existing.data):
            logger.info(
                "Bill %s already has analysis_results — skipping pipeline (idempotency)",
                bill_id,
            )
            posthog_client.capture(
                distinct_id=user_id,
                event="bill analysis skipped",
                properties={"bill_id": bill_id, "reason": "already_complete"},
            )
            return

        # 1. Download file bytes from Storage
        file_response = supabase.storage.from_("bills").download(file_path)
        file_bytes: bytes = file_response

        # Derive MIME type from file path extension
        mime_type = _mime_type_from_path(file_path)

        # 2. OCR
        supabase.table("bills").update({"status": BillStatus.OCR_PROCESSING}).eq("id", bill_id).execute()
        ocr_service = OcrService()
        raw_text = await ocr_service.extract_text(file_bytes, mime_type)

        # 3. Parse line items and attempt NPI extraction
        supabase.table("bills").update({"status": BillStatus.ANALYZING}).eq("id", bill_id).execute()
        parser = BillParser()
        parsed_items = parser.parse(raw_text, bill_date=date.today())

        if not parsed_items:
            # OCR extracted text but found no CPT line items. The document is
            # likely a summary statement, an EOB, or a bill format the parser
            # does not yet recognise. Mark as FAILED so the user is told to
            # upload an itemised bill rather than seeing a misleading
            # "no errors found" COMPLETE result.
            logger.warning("Parser found 0 line items in bill %s — marking FAILED", bill_id)
            supabase.table("bills").update({"status": BillStatus.FAILED}).eq("id", bill_id).execute()
            posthog_client.capture(
                distinct_id=user_id,
                event="bill analysis failed",
                properties={"bill_id": bill_id, "failure_reason": "no_line_items_parsed"},
            )
            return

        # Best-effort NPI, name, and address extraction for hospital charge lookup.
        # All are optional; the pipeline continues without them.
        # NPI is exact and unambiguous — used directly when present.
        # Name + address are used for progressive directory matching when NPI is absent.
        # hospital_state/hospital_zip come from the OCR bill header (2-letter state code
        # and 5-digit ZIP), NOT from the user-submitted state/zip which are the patient's
        # location and stored in a different format (full CMS state name).
        hospital_npi = parser.extract_npi(raw_text)
        hospital_name = parser.extract_hospital_name(raw_text)
        # Capture the city too — needed for the dispute-letter recipient block.
        # Pre-2026-04-30 this discarded the city via `_, state, zip`; the letter
        # ended up with a `[PROVIDER NAME AND ADDRESS]` placeholder.
        hospital_city, hospital_state, hospital_zip = parser.extract_hospital_address(raw_text)
        # M14 (Phase 8.6): hospital identity (name + address) is bill content
        # — log at INFO only IDs/counts, push name/address logs to DEBUG.
        # Cloud Logging retains INFO+ beyond ClaroBill's PHI window; DEBUG
        # is suppressed in prod by default.
        if hospital_npi:
            logger.info("Extracted NPI from bill %s", bill_id)
            logger.debug("Bill %s NPI value: %s", bill_id, hospital_npi)
        if hospital_name:
            logger.info(
                "Extracted hospital identity for bill %s (state=%s zip=%s)",
                bill_id, hospital_state, hospital_zip,
            )
            logger.debug(
                "Bill %s hospital name='%s' city='%s'",
                bill_id, hospital_name, hospital_city,
            )
        # Persist all confirmed identity fields — hospital from OCR, payer/plan from user
        identity_update: dict[str, str] = {}
        if hospital_npi:
            identity_update["hospital_npi"] = hospital_npi
        if hospital_name:
            identity_update["hospital_name"] = hospital_name
        if hospital_city:
            identity_update["hospital_city"] = hospital_city
        if hospital_state:
            identity_update["hospital_state"] = hospital_state
        if hospital_zip:
            identity_update["hospital_zip"] = hospital_zip
        if payer_name:
            identity_update["payer_name"] = payer_name
        if plan_name:
            identity_update["plan_name"] = plan_name
        if plan_type:
            identity_update["plan_type"] = plan_type
        if identity_update:
            supabase.table("bills").update(identity_update).eq("id", bill_id).execute()

        # Persist line items to the database
        line_item_rows: list[dict[str, Any]] = [
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
        # Clear any prior line_items for this bill before inserting fresh rows.
        # An out-of-band re-analyze (operator script, manual retry) would
        # otherwise duplicate every line — total_charges would be 2-3× the real
        # bill, and the report's "Line Items" table would list each CPT twice.
        # The production happy path inserts once and never re-runs analyze, so
        # this delete is a no-op on first analysis.
        supabase.table("line_items").delete().eq("bill_id", bill_id).execute()
        if line_item_rows:
            supabase.table("line_items").insert(line_item_rows).execute()

        # 4. Load reference data and run rules engine.
        #
        # Reference data is loaded per CMS quarter so that line items on opposite
        # sides of a quarterly release boundary (e.g. Dec 31 / Jan 1) are each
        # benchmarked against the rates in effect on their own service date rather
        # than a single "majority date" chosen for the whole bill.
        #
        # When the same CPT code appears in two different quarters (rare but possible),
        # the later quarter's rates take precedence in the merged dict. This is the
        # correct behaviour: the later quarter's release supersedes the earlier one
        # and the rate delta between adjacent quarters is always small.
        cpt_codes = [item.cpt_code for item in parsed_items]
        dominant_rate_date = _derive_rate_date(parsed_items)
        locality_code = _resolve_locality(supabase, state, county, dominant_rate_date.year)
        logger.info(
            "Using dominant_rate_date=%s locality_code=%s for bill %s (state=%s county=%s)",
            dominant_rate_date, locality_code, bill_id, state, county,
        )
        service_type, payer_type = _derive_ncci_context(cpt_codes, plan_type)
        # If the bill was identified as coming from a hospital, treat it as an outpatient
        # facility claim for pricing benchmarks. Revenue codes (the definitive signal) are
        # not extracted by the parser, so a confirmed hospital_name is the best available
        # proxy. This drives the commercial rate multiplier selection in PRICE_OUTLIER
        # (outpatient hospital: 2.64× Medicare vs physician: 1.40× Medicare).
        if hospital_name and service_type == "practitioner":
            service_type = "outpatient"
        ncci_service_types = list({service_type, "practitioner", "outpatient"})

        # Group parsed_items by CMS quarter. Most bills have a single quarter; cross-quarter
        # bills get per-quarter reference data so minority-date codes aren't mis-benchmarked.
        quarter_to_codes: dict[date, list[str]] = {}
        for item in parsed_items:
            q = _quarter_date(item.service_date)
            quarter_to_codes.setdefault(q, []).append(item.cpt_code)

        ncci_pairs: dict[str, set[str]] = {}
        mue_limits: dict[str, tuple[int, int]] = {}
        medicare_rates: dict[str, Decimal] = {}
        non_payable_codes: dict[str, str] = {}
        hcpcs_termination_dates: dict[str, date] = {}
        opps_rates: dict[str, Decimal] = {}
        ambulance_rates: dict[str, Decimal] = {}
        # Anesthesia base units are year-keyed (not quarter-keyed) — track loaded years.
        anesthesia_base_units: dict[str, int] = {}
        loaded_years: set[int] = set()
        # Anesthesia CF is a scalar — load once from the dominant quarter.
        anesthesia_cf = _load_anesthesia_cf(supabase, locality_code, dominant_rate_date)

        for q_date in sorted(quarter_to_codes):
            q_codes = quarter_to_codes[q_date]
            ncci_pairs.update(
                _load_ncci_pairs(supabase, q_codes, ncci_service_types, payer_type, q_date)
            )
            mue_limits.update(
                _load_mue_limits(supabase, q_codes, service_type, payer_type, q_date)
            )
            medicare_rates.update(
                _load_medicare_rates(supabase, q_codes, locality_code, q_date)
            )
            q_non_payable = _load_non_payable_codes(supabase, q_codes, q_date)
            non_payable_codes.update(q_non_payable)
            q_hcpcs_np, q_hcpcs_term = _load_hcpcs_code_data(supabase, q_codes, q_date)
            non_payable_codes.update(q_hcpcs_np)
            hcpcs_termination_dates.update(q_hcpcs_term)
            opps_rates.update(
                _load_opps_rates(supabase, q_codes, locality_code, q_date)
            )
            ambulance_rates.update(
                _load_ambulance_rates(supabase, q_codes, locality_code, zip_code, q_date)
            )
            if q_date.year not in loaded_years:
                anesthesia_base_units.update(
                    _load_anesthesia_base_units(supabase, q_codes, q_date.year)
                )
                loaded_years.add(q_date.year)

        if len(quarter_to_codes) > 1:
            logger.info(
                "Cross-quarter bill %s: loaded reference data for %d distinct quarters %s",
                bill_id, len(quarter_to_codes), sorted(quarter_to_codes),
            )
        bq = _build_bq_client()
        # SF2 (Phase 8.2): track BQ-backed sources that failed to load so the
        # report can surface a BENCHMARK_UNAVAILABLE finding. Pre-SF2 a
        # transient BQ outage silently returned {} and the patient saw "no
        # anomalies" with no indication the engine never reached the table.
        bq_unavailable_sources: list[str] = []

        def _safe_load(name: str, loader: Callable[[], dict[str, Decimal]]) -> dict[str, Decimal]:
            try:
                return loader()
            except Exception as exc:
                logger.warning(
                    "BQ benchmark source %r unavailable for bill %s: %s",
                    name, bill_id, exc,
                )
                bq_unavailable_sources.append(name)
                return {}

        # Use the earliest service date year so we never compare against pricing
        # published after the services were actually rendered.
        service_year = min(item.service_date.year for item in parsed_items)
        hospital_charges = _safe_load(
            "hospital_gross",
            lambda: _load_hospital_charges(
                bq, cpt_codes, hospital_npi, hospital_name, service_year,
                hospital_state, hospital_zip,
            ),
        )
        negotiated_charges = _safe_load(
            "negotiated_rate",
            lambda: _load_negotiated_charges(
                bq, cpt_codes, hospital_npi, hospital_name, payer_name, plan_name,
                service_year, hospital_state, hospital_zip,
            ),
        )
        # Load the hospital-wide ceiling rate as a fallback for codes where the
        # exact payer/plan rate could not be matched (e.g. MRF naming mismatch).
        negotiated_ceiling = _safe_load(
            "negotiated_ceiling",
            lambda: _load_negotiated_ceiling(
                bq, cpt_codes, hospital_npi, hospital_name, service_year,
                hospital_state, hospital_zip,
            ),
        )
        engine = RulesEngine(
            ncci_edit_pairs=ncci_pairs,
            medicare_rates=medicare_rates,
            plan_type=plan_type,
            service_type=service_type,
            non_payable_codes=non_payable_codes,
            anesthesia_cf=anesthesia_cf,
            anesthesia_base_units=anesthesia_base_units,
            opps_rates=opps_rates,
            ambulance_rates=ambulance_rates,
            hcpcs_termination_dates=hcpcs_termination_dates,
            hospital_charges=hospital_charges,
            negotiated_charges=negotiated_charges,
            negotiated_ceiling=negotiated_ceiling,
            mue_limits=mue_limits,
        )
        detected_errors = engine.run(parsed_items)

        # Map detected errors to line item IDs
        line_item_ids: list[str] = [str(row["id"]) for row in line_item_rows]
        billing_errors = _map_errors_to_line_items(detected_errors, line_item_ids)

        # SF2 (Phase 8.2): if any BQ-backed benchmark source was unavailable,
        # surface a single BENCHMARK_UNAVAILABLE finding so the report tells
        # the patient explicitly that those checks couldn't run. Without
        # this, the patient sees a clean report and assumes nothing is
        # wrong — even though the engine never reached the data.
        if bq_unavailable_sources:
            sources_label = ", ".join(sorted(set(bq_unavailable_sources)))
            billing_errors.append(BillingError(
                code=BillingErrorCode.BENCHMARK_UNAVAILABLE,
                severity=ErrorSeverity.INFO,
                affected_line_item_ids=[],
                description=(
                    f"We couldn't reach the hospital-charge benchmark for this bill "
                    f"({sources_label}). Other findings on this report still apply, "
                    f"but the missing benchmark means a real overcharge could go "
                    f"unflagged. Please retry analysis later for the most complete "
                    f"results."
                ),
                estimated_overcharge=Decimal("0"),
                benchmark_rate=None,
                benchmark_source=None,
            ))

        # 5. AI summary (Gemini primary, Claude fallback)
        ai_service = get_ai_analysis_service()
        ai_summary = await ai_service.generate_bill_summary(billing_errors, parsed_items)

        # 6. Persist analysis results.
        #
        # `total_potential_savings` is the realistic recoverable headline, not a
        # sum of every rule firing. Multiple rules often fire on the same line
        # item from different angles (PRICE_OUTLIER vs commercial benchmark,
        # HOSPITAL_CHARGE_OUTLIER vs the hospital's own gross, and
        # NEGOTIATED_CEILING_EXCEEDED vs the hospital's max negotiated rate).
        # All three are the SAME billed dollar — a patient can't recover three
        # times. We group findings by the tuple of line items they affect and
        # take the MAX overcharge per group, then sum across groups. The full
        # list of individual findings is still persisted on `errors` for the
        # report and dispute letter to render.
        total_charges = sum(Decimal(str(item.total_charge)) for item in parsed_items)
        savings_groups: dict[tuple[str, ...], Decimal] = {}
        for idx, e in enumerate(billing_errors):
            # Bill-wide findings (no affected line items) get a unique key so
            # they aren't collapsed with each other.
            key = tuple(sorted(e.affected_line_item_ids)) if e.affected_line_item_ids else (f"__bill__{idx}",)
            current = savings_groups.get(key, Decimal("0"))
            if e.estimated_overcharge > current:
                savings_groups[key] = e.estimated_overcharge
        total_savings = sum(savings_groups.values(), Decimal("0"))
        estimated_fair = total_charges - total_savings

        # S6 (Phase 8.2): upsert on bill_id so a force-re-analyze (operator
        # script bypassing the early-return guard above by clearing prior
        # analysis_results) doesn't fail the UNIQUE constraint. Each
        # call replaces the row entirely; downstream consumers always see
        # a single row per bill_id.
        supabase.table("analysis_results").upsert({
            "id": str(uuid.uuid4()),
            "bill_id": bill_id,
            # by_alias=True emits camelCase keys to match the TS BillingError
            # contract; mode="json" applies the field_serializer for Decimal→float.
            "errors": [e.model_dump(by_alias=True, mode="json") for e in billing_errors],
            "total_charges": float(total_charges),
            "estimated_fair_value": float(estimated_fair),
            "total_potential_savings": float(total_savings),
            "ai_summary": ai_summary,
            "dispute_letter_url": None,
            "report_url": None,
        }, on_conflict="bill_id").execute()

        supabase.table("bills").update({"status": BillStatus.COMPLETE}).eq("id", bill_id).execute()
        logger.info("Analysis complete for bill %s — %d errors found", bill_id, len(billing_errors))
        posthog_client.capture(
            distinct_id=user_id,
            event="bill analysis completed",
            properties={
                "bill_id": bill_id,
                "errors_found": len(billing_errors),
                "has_savings": float(total_savings) > 0,
                "line_item_count": len(parsed_items),
                "has_payer_info": bool(payer_name),
            },
        )

    except OcrExtractionError as exc:
        logger.error("OCR failed for bill %s: %s", bill_id, exc)
        supabase.table("bills").update({"status": BillStatus.FAILED}).eq("id", bill_id).execute()
        posthog_client.capture(
            distinct_id=user_id,
            event="bill analysis failed",
            properties={"bill_id": bill_id, "failure_reason": "ocr_failed"},
        )
    except Exception as exc:
        logger.exception("Unexpected error in analysis pipeline for bill %s: %s", bill_id, exc)
        supabase.table("bills").update({"status": BillStatus.FAILED}).eq("id", bill_id).execute()
        # M23 (Phase 8.6): tag the failure with exception_type so PostHog
        # can distinguish a wave of FAILED-from-BQ-outage from a wave of
        # FAILED-from-programmer-bug. Pre-M23 every catastrophe became
        # "pipeline_error" with no class info.
        posthog_client.capture(
            distinct_id=user_id,
            event="bill analysis failed",
            properties={
                "bill_id": bill_id,
                "failure_reason": "pipeline_error",
                "exception_type": type(exc).__name__,
            },
        )


def _mime_type_from_path(file_path: str) -> str:
    extension = file_path.rsplit(".", 1)[-1].lower()
    return {"pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(
        extension, "application/octet-stream"
    )


def _quarter_date(d: date) -> date:
    """Return the first day of the CMS quarter containing d.

    CMS releases reference data quarterly: Jan 1, Apr 1, Jul 1, Oct 1.
    Any service date within a quarter maps to that quarter's release date,
    which is used as the upper-bound for effective_from queries.
    """
    quarter_month = ((d.month - 1) // 3) * 3 + 1
    return date(d.year, quarter_month, 1)


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

    Note: 'outpatient' service type is not returned here — the caller overrides to
    'outpatient' when a confirmed hospital_name is present. Revenue codes (the definitive
    facility/professional split signal) are not extracted by the current parser, so
    hospital_name is the best available proxy.
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
    cpt_codes: list[str],
    service_types: list[str] | None = None,
    payer_type: str = "medicare",
    service_date: date | None = None,
) -> dict[str, set[str]]:
    """Load NCCI PTP edit pairs active on service_date for the CPT codes on this bill.

    Filters to pairs whose effective_date <= service_date and deletion_date is
    null or after service_date, so historical bills use the edits in force at
    the time of service rather than today's rules.

    Filters by column_one_code IN (cpt_codes) so only pairs relevant to this
    bill's codes are fetched. Without this filter the query would match 2M+ rows
    and PostgREST would return only the first 1000 — making unbundling detection
    effectively non-functional for any specific bill's code pairs.

    Queries all relevant service_types simultaneously. Both 'practitioner' and
    'outpatient' are always included because outpatient hospital service type is
    not reliably auto-detected (requires revenue code parsing not yet implemented).
    Querying both is safe — the column_one_code filter keeps the result small.
    """
    if not cpt_codes:
        return {}

    unique_codes = list(set(cpt_codes))
    effective_service_types = list(set(service_types or ["practitioner", "outpatient"]))

    query = (
        supabase.table("ncci_edit_pairs")
        .select("column_one_code,column_two_code")
        .in_("service_type", effective_service_types)
        .eq("payer_type", payer_type)
        .in_("column_one_code", unique_codes)
    )
    if service_date is not None:
        query = (
            query
            .lte("effective_date", service_date.isoformat())
            .or_(f"deletion_date.is.null,deletion_date.gte.{service_date.isoformat()}")
        )
    else:
        query = query.is_("deletion_date", "null")

    # 10,000 is well above any realistic bill size. Without an explicit limit PostgREST
    # silently caps at 1,000 — and because the result is non-empty (some pairs are always
    # returned), the empty-result warning never fires. We'd silently miss pairs.
    response = query.limit(10000).execute()
    rows = as_rows(response.data)
    pairs: dict[str, set[str]] = {}
    for row in rows:
        pairs.setdefault(row["column_one_code"], set()).add(row["column_two_code"])

    if len(rows) >= 10000:
        logger.warning(
            "NCCI pairs result hit the 10000-row limit for service_types=%s payer_type=%s "
            "cpt_codes=%s — some pairs may be silently missing. Consider paginating.",
            effective_service_types, payer_type, unique_codes,
        )
    elif not pairs:
        logger.warning(
            "No NCCI pairs found for service_types=%s payer_type=%s service_date=%s "
            "cpt_codes=%s — NCCI_UNBUNDLING detection disabled for this bill.",
            effective_service_types, payer_type, service_date, unique_codes,
        )

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
    for row in as_rows(response.data):
        code = row["hcpcs_code"]
        if code not in result:
            result[code] = (int(row["mue_value"]), int(row["adjudication_indicator"]))

    if not result:
        logger.warning(
            "No MUE limits found for cpt_codes=%s service_type=%s payer_type=%s service_date=%s "
            "— MUE_EXCEEDED detection disabled for this bill.",
            list(set(cpt_codes)), service_type, payer_type, service_date,
        )

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

    # Fetch RVU components — pick the most recent quarterly release ≤ service date.
    # Base (no-modifier) rows may have modifier=NULL or modifier='' depending on
    # which loader run produced the data. Match both to be safe.
    indicators_resp = (
        supabase.table("cms_pfs_indicators")
        .select("hcpc,rvu_work,nfac_pe_rvu,rvu_mp,nfac_total_rvu,conv_fact,proc_stat")
        .in_("hcpc", unique_codes)
        .or_("modifier.is.null,modifier.eq.")
        .eq("proc_stat", "A")
        .lte("effective_from", rate_date_str)
        .order("effective_from", desc=True)
        .execute()
    )

    # Take the most recent available entry per HCPC code (≤ service date)
    indicators: dict[str, dict[str, Any]] = {}
    for row in as_rows(indicators_resp.data):
        if row["hcpc"] not in indicators:
            indicators[row["hcpc"]] = row

    if not indicators:
        logger.warning(
            "No Medicare rates found for cpt_codes=%s locality=%s rate_date=%s — "
            "PRICE_OUTLIER detection disabled for this bill. "
            "Check that these codes exist in cms_pfs_indicators with proc_stat='A' "
            "and effective_from <= %s.",
            unique_codes, locality_code, rate_date_str, rate_date_str,
        )
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

    locality_rows = as_rows(locality_resp.data)
    if locality_rows:
        gpci = locality_rows[0]
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
        .or_("modifier.is.null,modifier.eq.")
        .lte("effective_from", rate_date.isoformat())
        .order("effective_from", desc=True)
        .execute()
    )
    result: dict[str, str] = {}
    for row in as_rows(response.data):
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

    for row in as_rows(response.data):
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
    for row in as_rows(response.data):
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
        .or_("modifier.is.null,modifier.eq.")
        .eq("locality_code", locality_code)
        .lte("effective_from", rate_date.isoformat())
        .order("effective_from", desc=True)
        .execute()
    )

    # Take the most recent available entry per code (≤ service date)
    rates: dict[str, Decimal] = {}
    for row in as_rows(response.data):
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
    rows = as_rows(response.data)
    if not rows:
        logger.warning(
            "ZIP %s not found in ambulance ZIP table (effective_from<=%s) — using urban rate.",
            zip5,
            rate_date,
        )
        return ""
    indicator = rows[0]["rural_indicator"]
    return str(indicator) if indicator else ""


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

    ambulance_rows = as_rows(response.data)
    if not ambulance_rows:
        return {}

    # Take the most recent available entry per HCPC code (≤ service date)
    latest: dict[str, dict[str, Any]] = {}
    for row in ambulance_rows:
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
        rows = as_rows(response.data)
        if rows:
            return str(rows[0]["locality_code"])

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
    rows = as_rows(response.data)
    if rows:
        return str(rows[0]["locality_code"])

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
    rows = as_rows(response.data)
    if rows:
        return str(rows[0]["locality_code"])

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
    rows = as_rows(response.data)
    if not rows:
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
    return Decimal(str(rows[0]["non_qualifying_cf"]))


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
    service_year: int,
    hospital_state: str | None = None,
    hospital_zip: str | None = None,
) -> dict[str, Decimal]:
    """Load the hospital's published gross charges for the CPT codes on the bill.

    Queries hospital_charges_latest using the closest pricing year <= service_year:
      1. NPI match (exact) — preferred; always unambiguous.
      2. Name match (progressive) — fallback when NPI unavailable. Uses state and
         zip (extracted from OCR bill header) to disambiguate same-name hospitals
         before falling back to name-only. Returns empty if still ambiguous.

    Returns an empty dict when: BigQuery not configured, no hospital identified,
    no match found, or name is unresolvably ambiguous. The rules engine skips the
    hospital charge outlier rule when the dict is empty.
    """
    if bq is None or not cpt_codes:
        return {}
    if not hospital_npi and not hospital_name:
        return {}

    dataset = f"{settings.gcp_project_id}.{settings.bigquery_dataset}"
    unique_codes = list(set(cpt_codes))

    if hospital_npi:
        return _query_charges_by_npi(bq, dataset, unique_codes, hospital_npi, service_year)

    if hospital_name is None:
        return {}
    npi = _resolve_npi_by_name(bq, dataset, hospital_name, hospital_state, hospital_zip)
    if npi is None:
        return {}
    return _query_charges_by_npi(bq, dataset, unique_codes, npi, service_year)


def _query_charges_by_npi(
    bq: bigquery.Client,
    dataset: str,
    cpt_codes: list[str],
    hospital_npi: str,
    service_year: int,
) -> dict[str, Decimal]:
    """Query hospital_charges_latest for a specific NPI, returning gross charge per CPT code.

    Selects the closest pricing year <= service_year via a window function, then takes
    MAX(gross_charge) per code across all settings/payer rows for that year.
    The gross charge is the hospital's own maximum list price — billing above it
    is an unambiguous error regardless of which specific row was used for billing.
    """
    # `dataset` is an engine config value (settings.bigquery_dataset), never user
    # input. All user-provided values flow through ScalarQueryParameter below.
    query = f"""
        SELECT code, MAX(gross_charge) AS gross_charge
        FROM (
          SELECT code, gross_charge,
            DENSE_RANK() OVER (PARTITION BY code ORDER BY pricing_effective_year DESC) AS yr_rank
          FROM `{dataset}.hospital_charges_latest`
          WHERE hospital_npi = @npi
            AND code IN UNNEST(@codes)
            AND pricing_effective_year <= @service_year
            AND gross_charge IS NOT NULL
            AND gross_charge > 0
        )
        WHERE yr_rank = 1
        GROUP BY code
    """  # noqa: S608
    job_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("npi", "STRING", hospital_npi),
        bigquery.ArrayQueryParameter("codes", "STRING", cpt_codes),
        bigquery.ScalarQueryParameter("service_year", "INT64", service_year),
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
    hospital_state: str | None = None,
    hospital_zip: str | None = None,
) -> str | None:
    """Resolve a hospital NPI from hospital_directory using progressive address matching.

    Tries up to three passes in decreasing specificity, returning the NPI on the
    first pass that yields exactly one match. A no-match is always preferable to a
    wrong-hospital match — charge data from the wrong facility produces false findings.

      Pass 1: name + state + zip   — resolves same-name same-state variants (e.g. two
                                     St. Mary's hospitals in Ohio, different cities/ZIPs)
      Pass 2: name + state         — resolves same-name hospitals in different states
      Pass 3: name only            — safe only when the name is nationally unique

    Only passes for which the required address fields are available are attempted.
    state and zip are extracted from the OCR bill header (hospital_directory stores
    2-letter state codes; zip is a 5-digit string).
    """
    name_substr = hospital_name.strip()

    # Build pass list from most to least specific based on available address fields.
    # Each entry is (label, state_value, zip_value) — None means "skip this field".
    # zip_code pass is included in the logic but hospital_directory.zip_code is
    # currently unpopulated — it requires a one-time NPPES backfill (npiregistry.cms.hhs.gov).
    # Once loaded, Pass 1 will activate automatically.
    passes: list[tuple[str, str | None, str | None]] = []
    if hospital_state and hospital_zip:
        passes.append(("name+state+zip", hospital_state, hospital_zip))
    if hospital_state:
        passes.append(("name+state", hospital_state, None))
    passes.append(("name", None, None))

    # Strip apostrophes from both sides so "Saint Michael's" and "Saint Michaels"
    # variants match. Different directory feeds use different conventions.
    base_where = (
        "CONTAINS_SUBSTR(REPLACE(hospital_name, \"'\", ''), REPLACE(@name_substr, \"'\", ''))\n"
        "          AND hospital_npi IS NOT NULL"
    )

    for label, state, zip_code in passes:
        conditions = base_where
        params: list[bigquery.ScalarQueryParameter] = [
            bigquery.ScalarQueryParameter("name_substr", "STRING", name_substr),
        ]
        if state:
            conditions += "\n          AND state = @state"
            params.append(bigquery.ScalarQueryParameter("state", "STRING", state))
        if zip_code:
            conditions += "\n          AND zip_code = @zip_code"
            params.append(bigquery.ScalarQueryParameter("zip_code", "STRING", zip_code))

        # `dataset` is from engine config; `conditions` is built from fixed string
        # templates with ScalarQueryParameter placeholders — no user input interpolated.
        query = f"SELECT hospital_npi FROM `{dataset}.hospital_directory` WHERE {conditions}"  # noqa: S608
        try:
            rows = list(bq.query(query, job_config=bigquery.QueryJobConfig(query_parameters=params)).result())
        except Exception as exc:
            logger.warning("Hospital NPI lookup (%s) failed for '%s': %s", label, hospital_name, exc)
            return None

        if not rows:
            continue

        # Always validate against hospital_charges before returning. A
        # directory row that points at an NPI with no pricing data is
        # effectively the wrong match — using it produces zero hospital
        # findings even when a real match exists under a sibling NPI.
        # This catches: apostrophe / casing variants where the directory
        # query picks the wrong row, stale NPIs from facility transfers,
        # and sibling clinics that share a name with the inpatient hospital.
        candidate_npis = [str(r["hospital_npi"]) for r in rows]
        active_npis = _filter_npis_with_charges(bq, dataset, candidate_npis)

        # H15 (Phase 8.3): if the presence-check itself errored (returned
        # None as a sentinel rather than empty list — distinct from "no
        # NPIs found"), abort the resolution. Pre-H15, [] on exception
        # silently fell through to the broader pass which could resolve
        # to a wrong-hospital NPI.
        if active_npis is None:
            logger.warning(
                "Hospital '%s' %s: charges presence check unavailable; "
                "aborting NPI resolution rather than falling back to a "
                "broader pass that may match the wrong hospital",
                hospital_name, label,
            )
            return None

        if len(active_npis) == 1:
            npi = active_npis[0]
            logger.info(
                "Hospital '%s' resolved via %s → NPI %s (%d directory rows, 1 with charge data)",
                hospital_name, label, npi, len(rows),
            )
            return npi

        logger.debug(
            "Hospital '%s' %s: %d directory rows, %d with charge data — narrowing to next pass",
            hospital_name, label, len(rows), len(active_npis),
        )

    logger.info(
        "Hospital '%s' (state=%s zip=%s) unresolved — 0 or >1 matches on all passes, skipping charge lookup",
        hospital_name, hospital_state, hospital_zip,
    )
    return None


def _filter_npis_with_charges(
    bq: bigquery.Client,
    dataset: str,
    candidate_npis: list[str],
) -> list[str] | None:
    """Return the subset of candidate NPIs that have at least one row in
    hospital_charges. Used by `_resolve_npi_by_name` to disambiguate when the
    directory has stale duplicates (e.g. Saint Michael's Medical Center NJ
    appears twice in `hospital_directory` — only NPI 1568825545 has pricing).

    H15 (Phase 8.3): returns None on BQ exception to distinguish "presence
    check unavailable" from "no NPIs found". Pre-H15 returned [] on
    exception, which the caller treated as "narrow to next pass" — and
    the next (broader) pass could resolve to a wrong-hospital NPI when
    only a transient outage was responsible.
    """
    if not candidate_npis:
        return []
    query = f"""
        SELECT DISTINCT hospital_npi
        FROM `{dataset}.hospital_charges`
        WHERE hospital_npi IN UNNEST(@npis)
    """  # noqa: S608
    job_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ArrayQueryParameter("npis", "STRING", candidate_npis),
    ])
    try:
        rows = list(bq.query(query, job_config=job_config).result())
    except Exception as exc:
        logger.warning("hospital_charges presence check failed for %d NPIs: %s", len(candidate_npis), exc)
        return None
    return [str(r["hospital_npi"]) for r in rows]


def _resolve_payer_aliases(
    bq: bigquery.Client,
    dataset: str,
    payer_name: str,
) -> list[str]:
    """Return all known MRF alias strings for the payer group that matches payer_name.

    Looks up the canonical payer_group by matching payer_name against the alias
    column (case-insensitive substring), then returns all aliases for that group.
    This lets the negotiated rate query use exact IN() matching rather than CONTAINS_SUBSTR,
    covering all known MRF naming variations for the same insurer.

    Returns an empty list when:
      - The payer_name_aliases table doesn't exist yet (table not seeded)
      - No canonical group matches the provided name

    Falls back gracefully — the caller should fall back to CONTAINS_SUBSTR when
    this returns empty.
    """
    # H14 + M17 (Phase 8.3): make the alias match deterministic + safer.
    #
    # Pre-H14: bidirectional CONTAINS_SUBSTR with no length floor +
    # LIMIT 1 with no ORDER BY meant a 2-letter alias from any
    # payer_group could match an arbitrary user-supplied payer_name longer
    # than 2 chars, AND the LIMIT 1 was non-deterministic across runs.
    # Effect: "Aetna" could match payer_group="AT&T" because alias "at"
    # is a substring of "aetna" — wrong-hospital negotiated rates fed to
    # the rules engine.
    #
    # Fix: drop the reverse direction (`@payer_name` contains `alias`)
    # AND add `LENGTH(alias) >= 4` floor on the forward direction. Add
    # `ORDER BY LENGTH(alias) DESC, payer_group` so the longest, then
    # alphabetically-first alias wins — deterministic. The empty-result
    # case still triggers the substring fallback at the call site.
    #
    # `dataset` is engine config; @payer_name is parameterized.
    lookup_query = f"""
        SELECT payer_group
        FROM `{dataset}.payer_name_aliases`
        WHERE CONTAINS_SUBSTR(@payer_name, alias)
          AND LENGTH(alias) >= 4
        ORDER BY LENGTH(alias) DESC, payer_group
        LIMIT 1
    """  # noqa: S608
    try:
        rows = list(bq.query(
            lookup_query,
            job_config=bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("payer_name", "STRING", payer_name),
            ]),
        ).result())
    except Exception:
        # Table doesn't exist yet or query failed — return empty to trigger fallback
        return []

    if not rows:
        return []

    payer_group = rows[0]["payer_group"]

    alias_query = f"""
        SELECT alias
        FROM `{dataset}.payer_name_aliases`
        WHERE payer_group = @payer_group
    """  # noqa: S608
    try:
        alias_rows = list(bq.query(
            alias_query,
            job_config=bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("payer_group", "STRING", payer_group),
            ]),
        ).result())
    except Exception:
        return []

    return [str(row["alias"]) for row in alias_rows]


def _load_negotiated_charges(
    bq: bigquery.Client | None,
    cpt_codes: list[str],
    hospital_npi: str | None,
    hospital_name: str | None,
    payer_name: str | None,
    plan_name: str | None,
    service_year: int,
    hospital_state: str | None = None,
    hospital_zip: str | None = None,
) -> dict[str, Decimal]:
    """Load the insurer-specific contracted rate for each CPT code on this bill.

    Queries hospital_charges_latest with the closest pricing year <= service_year.
    Returns MAX(negotiated_charge) per code when multiple rows match (e.g. different
    settings or negotiated_type values for the same year).

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

    npi = hospital_npi
    if not npi:
        if hospital_name is None:
            return {}
        npi = _resolve_npi_by_name(bq, dataset, hospital_name, hospital_state, hospital_zip)
        if npi is None:
            return {}

    payer_substr = payer_name.strip()
    plan_substr = plan_name.strip()

    # Attempt 1: join against payer_name_aliases for exact normalized matching.
    # The alias table maps raw MRF payer strings → canonical payer_group, letting
    # us query with IN (all aliases for this group) rather than a substring search.
    # This eliminates false misses where the user types "Blue Cross" but the MRF
    # uses "Anthem Blue Cross Blue Shield of California".
    aliases = _resolve_payer_aliases(bq, dataset, payer_substr)
    if aliases:
        query = f"""
            SELECT code, MAX(negotiated_charge) AS negotiated_charge
            FROM (
              SELECT code, negotiated_charge,
                DENSE_RANK() OVER (PARTITION BY code ORDER BY pricing_effective_year DESC) AS yr_rank
              FROM `{dataset}.hospital_charges_latest`
              WHERE hospital_npi = @npi
                AND payer_name IN UNNEST(@payer_aliases)
                AND CONTAINS_SUBSTR(plan_name, @plan_substr)
                AND code IN UNNEST(@codes)
                AND pricing_effective_year <= @service_year
                AND negotiated_charge IS NOT NULL
                AND negotiated_charge > 0
                AND negotiated_type IN ('negotiated', 'derived')
            )
            WHERE yr_rank = 1
            GROUP BY code
        """  # noqa: S608
        job_config = bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("npi", "STRING", npi),
            bigquery.ArrayQueryParameter("payer_aliases", "STRING", aliases),
            bigquery.ScalarQueryParameter("plan_substr", "STRING", plan_substr),
            bigquery.ArrayQueryParameter("codes", "STRING", unique_codes),
            bigquery.ScalarQueryParameter("service_year", "INT64", service_year),
        ])
    else:
        # Attempt 2: substring fallback when the payer_name_aliases table is empty
        # or the user-provided name has no canonical alias. CONTAINS_SUBSTR is
        # case-insensitive and safe against LIKE metacharacters.
        query = f"""
            SELECT code, MAX(negotiated_charge) AS negotiated_charge
            FROM (
              SELECT code, negotiated_charge,
                DENSE_RANK() OVER (PARTITION BY code ORDER BY pricing_effective_year DESC) AS yr_rank
              FROM `{dataset}.hospital_charges_latest`
              WHERE hospital_npi = @npi
                AND CONTAINS_SUBSTR(payer_name, @payer_substr)
                AND CONTAINS_SUBSTR(plan_name, @plan_substr)
                AND code IN UNNEST(@codes)
                AND pricing_effective_year <= @service_year
                AND negotiated_charge IS NOT NULL
                AND negotiated_charge > 0
                AND negotiated_type IN ('negotiated', 'derived')
            )
            WHERE yr_rank = 1
            GROUP BY code
        """  # noqa: S608
        job_config = bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("npi", "STRING", npi),
            bigquery.ScalarQueryParameter("payer_substr", "STRING", payer_substr),
            bigquery.ScalarQueryParameter("plan_substr", "STRING", plan_substr),
            bigquery.ArrayQueryParameter("codes", "STRING", unique_codes),
            bigquery.ScalarQueryParameter("service_year", "INT64", service_year),
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


def _load_negotiated_ceiling(
    bq: bigquery.Client | None,
    cpt_codes: list[str],
    hospital_npi: str | None,
    hospital_name: str | None,
    service_year: int,
    hospital_state: str | None = None,
    hospital_zip: str | None = None,
) -> dict[str, Decimal]:
    """Load the hospital-wide maximum negotiated rate per CPT code.

    Queries MAX(max_negotiated) across all payers at this hospital for each code,
    using the closest pricing year <= service_year via a window function.
    max_negotiated is extracted from the hospital's MRF standard_charges level —
    it represents the highest dollar amount any insurer has contracted to pay for
    that procedure at that facility.

    Used as a fallback when the exact payer/plan negotiated rate cannot be matched.
    A billed charge above this ceiling exceeds what any insurer pays — a meaningful
    benchmark even without knowing the patient's specific plan rate.

    Returns empty dict when:
      - BigQuery not configured
      - No CPT codes on the bill
      - Hospital not identified
      - No max_negotiated values loaded for this hospital's codes (hospital may
        only publish gross charges, or the MRF parser did not extract this field)
    """
    if bq is None or not cpt_codes:
        return {}
    if not hospital_npi and not hospital_name:
        return {}

    dataset = f"{settings.gcp_project_id}.{settings.bigquery_dataset}"
    unique_codes = list(set(cpt_codes))

    npi = hospital_npi
    if not npi:
        if hospital_name is None:
            return {}
        npi = _resolve_npi_by_name(bq, dataset, hospital_name, hospital_state, hospital_zip)
        if npi is None:
            return {}

    query = f"""
        SELECT code, MAX(max_negotiated) AS ceiling_rate
        FROM (
          SELECT code, max_negotiated,
            DENSE_RANK() OVER (PARTITION BY code ORDER BY pricing_effective_year DESC) AS yr_rank
          FROM `{dataset}.hospital_charges_latest`
          WHERE hospital_npi = @npi
            AND code IN UNNEST(@codes)
            AND pricing_effective_year <= @service_year
            AND max_negotiated IS NOT NULL
            AND max_negotiated > 0
        )
        WHERE yr_rank = 1
        GROUP BY code
    """  # noqa: S608
    job_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("npi", "STRING", npi),
        bigquery.ArrayQueryParameter("codes", "STRING", unique_codes),
        bigquery.ScalarQueryParameter("service_year", "INT64", service_year),
    ])
    try:
        rows = list(bq.query(query, job_config=job_config).result())
    except Exception as exc:
        logger.warning("BigQuery negotiated ceiling lookup failed for NPI %s: %s", npi, exc)
        return {}

    if not rows:
        return {}

    result = {row["code"]: Decimal(str(row["ceiling_rate"])).quantize(Decimal("0.01")) for row in rows}
    logger.info("Loaded %d negotiated ceiling rates for NPI %s", len(result), npi)
    return result


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
            benchmark_rate=error.benchmark_rate,
            benchmark_source=error.benchmark_source,
        ))
    return result


@router.post("/{bill_id}/report", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("5/hour")  # PDF generation + email — tighter limit than analysis
async def generate_report(
    request: Request,
    bill_id: str,
    body: ReportRequest,
    background_tasks: BackgroundTasks,
    supabase: Client = Depends(get_supabase_client),
    ai_service: AiAnalysisService = Depends(get_ai_analysis_service),
    email_service: EmailService = Depends(get_email_service),
) -> dict[str, str]:
    """Kick off report + dispute letter generation as a background task.

    Returns 202 immediately so the caller (checkout route) never times out
    waiting for a 30-60s synchronous response. The frontend polls for
    report_url to appear in the analysis record.

    Idempotency: skips if a valid file already exists in storage.
    If report_url is set but the file is missing (stale from a crashed run),
    regenerates rather than returning a broken download.
    """
    bill_row = supabase.table("bills").select(
        "id,file_name,file_path,user_id,hospital_name,hospital_city,hospital_state,hospital_zip,"
        "payer_name,plan_name,profile_member_id"
    ).eq("id", bill_id).single().execute()
    bill_data = as_optional_row(bill_row.data)
    if not bill_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bill not found.")
    if bill_data["user_id"] != body.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized.")

    analysis_row = (
        supabase.table("analysis_results")
        .select("id,errors,ai_summary,report_url")
        .eq("bill_id", bill_id)
        .single()
        .execute()
    )
    analysis_data = as_optional_row(analysis_row.data)
    if not analysis_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found.")

    user_id: str = bill_data["user_id"]
    existing_url: str | None = analysis_data.get("report_url")

    # Idempotency: skip only if the file actually exists in storage.
    # create_signed_url always succeeds regardless of whether the file exists;
    # list() is the only way to confirm the object is actually present.
    if existing_url:
        try:
            folder = f"{user_id}/{bill_id}"
            listing = supabase.storage.from_("reports").list(folder) or []
            present = {f["name"] for f in listing}
            if "report.pdf" in present:
                logger.info("Report already exists in storage for bill %s, skipping", bill_id)
                return {"status": "already_done"}
        except Exception as exc:
            logger.warning("Storage list probe failed for bill %s — will regenerate: %s", bill_id, exc)
        # File is absent despite report_url being set — clear stale URL and regenerate
        logger.info("report_url set for bill %s but file missing — will regenerate", bill_id)
        supabase.table("analysis_results").update(
            {"report_url": None, "dispute_letter_url": None}
        ).eq("bill_id", bill_id).execute()

    background_tasks.add_task(
        _do_generate_report,
        bill_id=bill_id,
        body=body,
        bill_data=bill_data,
        analysis_data=analysis_data,
        supabase=supabase,
        ai_service=ai_service,
        email_service=email_service,
    )
    logger.info("Report generation queued for bill %s", bill_id)
    posthog_client.capture(
        distinct_id=user_id,
        event="report generation requested",
        properties={"bill_id": bill_id},
    )
    return {"status": "processing"}


async def _do_generate_report(
    bill_id: str,
    body: ReportRequest,
    bill_data: dict[str, Any],
    analysis_data: dict[str, Any],
    supabase: Client,
    ai_service: AiAnalysisService,
    email_service: EmailService,
) -> None:
    """Background task: generate PDF + DOCX, upload to storage, email the patient."""
    user_id: str = bill_data["user_id"]
    try:
        file_name: str = bill_data["file_name"]
        hospital_name: str | None = bill_data.get("hospital_name")
        hospital_city: str | None = bill_data.get("hospital_city")
        hospital_state: str | None = bill_data.get("hospital_state")
        hospital_zip: str | None = bill_data.get("hospital_zip")
        payer_name: str | None = bill_data.get("payer_name")
        plan_name: str | None = bill_data.get("plan_name")
        profile_member_id: str | None = bill_data.get("profile_member_id")
        ai_summary: str = analysis_data["ai_summary"]

        # Pull patient identity for the dispute letter closing block.
        # Falls back to bracketed placeholders inside generate_dispute_letter
        # when any field is missing — never ask the user to retype data we have.
        patient_name: str | None = None
        patient_dob: str | None = None
        member_id: str | None = None
        if profile_member_id:
            member_row = (
                supabase.table("profile_members")
                .select("full_name,date_of_birth")
                .eq("id", profile_member_id)
                .single()
                .execute()
            )
            member_data = as_optional_row(member_row.data)
            if member_data:
                pn = member_data.get("full_name")
                patient_name = str(pn) if pn else None
                dob_raw = member_data.get("date_of_birth")
                patient_dob = str(dob_raw) if dob_raw else None

            if payer_name and plan_name:
                plan_row = (
                    supabase.table("insurance_plans")
                    .select("member_id")
                    .eq("profile_member_id", profile_member_id)
                    .eq("payer_name", payer_name)
                    .eq("plan_name", plan_name)
                    .limit(1)
                    .execute()
                )
                plan_rows = as_rows(plan_row.data)
                if plan_rows:
                    raw_member_id = plan_rows[0].get("member_id")
                    member_id = str(raw_member_id) if raw_member_id else None

        items_row = (
            supabase.table("line_items")
            .select("cpt_code,description,service_date,quantity,unit_charge,total_charge,modifier,diagnosis_pointers")
            .eq("bill_id", bill_id)
            .execute()
        )
        line_items = [
            ParsedLineItem(
                cpt_code=str(r["cpt_code"]),
                description=str(r["description"]),
                service_date=date.fromisoformat(str(r["service_date"])),
                quantity=int(r["quantity"]),
                unit_charge=float(r["unit_charge"]),
                total_charge=float(r["total_charge"]),
                modifier=str(r["modifier"]) if r["modifier"] is not None else None,
                diagnosis_pointers=list(r["diagnosis_pointers"]) if r["diagnosis_pointers"] else [],
            )
            for r in as_rows(items_row.data)
        ]

        # `model_validate` honours both snake_case (legacy rows) and
        # camelCase (current contract via alias_generator + populate_by_name).
        # This is what makes the JSONB backfill rewrite a forward-only operation
        # — the read path tolerates either shape during migration.
        # strict=False allows JSONB primitives to coerce: str→StrEnum, float→Decimal.
        # The model is normally strict (no silent coercion at construction time);
        # for self-emitted JSONB round-trip this is the correct relaxation.
        billing_errors = [
            BillingError.model_validate(e, strict=False) for e in analysis_data["errors"]
        ]

        generator = ReportGenerator()
        loop = asyncio.get_running_loop()
        dispute_letter_text, report_pdf = await asyncio.gather(
            ai_service.generate_dispute_letter(
                billing_errors, line_items, file_name,
                hospital_name=hospital_name,
                hospital_city=hospital_city,
                hospital_state=hospital_state,
                hospital_zip=hospital_zip,
                payer_name=payer_name,
                patient_name=patient_name, patient_dob=patient_dob,
                member_id=member_id,
            ),
            loop.run_in_executor(
                None,
                lambda: generator.generate_report_pdf(billing_errors, line_items, file_name, ai_summary),
            ),
        )
        dispute_docx = generator.generate_dispute_letter_docx(dispute_letter_text)

        report_path = f"{user_id}/{bill_id}/report.pdf"
        dispute_path = f"{user_id}/{bill_id}/dispute-letter.docx"
        docx_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        # Parallel uploads — supabase-py is sync, so each upload would otherwise
        # block ~1-2s on Supabase round-trip. Running both in threads cuts ~1s
        # off the path between "PDF/DOCX bytes ready" and "URLs visible to the
        # dashboard."
        await asyncio.gather(
            loop.run_in_executor(
                None,
                lambda: supabase.storage.from_("reports").upload(
                    report_path, report_pdf,
                    {"content-type": "application/pdf", "upsert": "true"},
                ),
            ),
            loop.run_in_executor(
                None,
                lambda: supabase.storage.from_("reports").upload(
                    dispute_path, dispute_docx,
                    {"content-type": docx_mime, "upsert": "true"},
                ),
            ),
        )

        supabase.table("analysis_results").update({
            "report_url": report_path,
            "dispute_letter_url": dispute_path,
        }).eq("bill_id", bill_id).execute()

        email_service.send_report_email(
            to_email=body.user_email,
            bill_file_name=file_name,
            report_pdf=report_pdf,
            dispute_letter_docx=dispute_docx,
        )
        logger.info("Report generated and emailed for bill %s", bill_id)
        posthog_client.capture(
            distinct_id=user_id,
            event="report generated",
            properties={"bill_id": bill_id},
        )

    except Exception as exc:
        logger.exception("Report generation background task failed for bill %s", bill_id)
        # M23 (Phase 8.6): tag exception_type so failures are
        # distinguishable in PostHog.
        posthog_client.capture(
            distinct_id=user_id,
            event="report generation failed",
            properties={"bill_id": bill_id, "exception_type": type(exc).__name__},
        )
