"""Insurance card extraction via Google Document AI Health Insurance Card Parser.

Document AI's Health Insurance Card Processor is purpose-built for extracting
structured data from insurance cards. It returns typed entities (member_id,
insurance_company, group_number, plan_name, etc.) directly — no OCR + LLM chain
needed. This is the same technology used by hospital intake systems and benefits
verification platforms.

Setup: create a HEALTH_INSURANCE_CARD_PROCESSOR processor in GCP Document AI
console (console.cloud.google.com/ai/document-ai/processors), then set
DOCUMENT_AI_PROCESSOR_ID in the engine .env. Location must be "us".
"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from google.cloud import documentai_v1 as documentai
from google.oauth2 import service_account
from pydantic import BaseModel, ConfigDict

from app.core.config import settings

router = APIRouter(prefix="/insurance-card", tags=["insurance-card"])
logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/tiff"}


class InsuranceCardExtraction(BaseModel):
    """Structured fields extracted from an insurance card.

    confident=False signals the frontend to highlight all fields for user review.
    """

    model_config = ConfigDict(strict=True)

    payer_name: str | None
    plan_name: str | None
    member_id: str | None
    group_id: str | None
    plan_type: str | None
    rx_bin: str | None
    rx_pcn: str | None
    rx_group: str | None
    confident: bool
    note: str | None


def _build_documentai_client() -> documentai.DocumentProcessorServiceClient:
    if settings.google_credentials_json:
        info = json.loads(settings.google_credentials_json)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        return documentai.DocumentProcessorServiceClient(credentials=creds)
    return documentai.DocumentProcessorServiceClient()


def _get_project_id() -> str:
    if settings.gcp_project_id:
        return settings.gcp_project_id
    if settings.google_credentials_json:
        return json.loads(settings.google_credentials_json).get("project_id", "")
    if settings.google_application_credentials:
        return json.loads(Path(settings.google_application_credentials).read_text()).get("project_id", "")
    return ""


def _normalise_plan_type(company: str, plan: str, raw_type: str) -> str:
    """Infer our 5-value plan_type enum from Document AI entity text."""
    combined = f"{company} {plan} {raw_type}".lower()
    if "medicare" in combined:
        return "medicare"
    if any(k in combined for k in ("medicaid", "medi-cal", "chip", "tenncare", "ahcccs", "access")):
        return "medicaid"
    if any(k in combined for k in ("tricare", "military", "va health", "champva")):
        return "tricare"
    if "self" in combined and "pay" in combined:
        return "self_pay"
    return "commercial"


def _entity_map(document: documentai.Document) -> dict[str, str]:
    """Return a flat {entity_type: mention_text} dict from all document entities."""
    result: dict[str, str] = {}
    for entity in document.entities:
        text = (entity.mention_text or "").strip()
        if text:
            result[entity.type_] = text
    return result


@router.post(
    "/extract",
    response_model=InsuranceCardExtraction,
    status_code=status.HTTP_200_OK,
)
async def extract_insurance_card(
    image: UploadFile = File(..., description="Insurance card photo (JPEG, PNG, or WebP)"),
) -> InsuranceCardExtraction:
    """Extract structured insurance plan data from a card photo using Document AI."""
    if not settings.document_ai_processor_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Insurance card scanning is not configured. Contact support.",
        )

    content_type = image.content_type or ""
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported image type. Use JPEG, PNG, or WebP.",
        )

    image_bytes = await image.read()
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image exceeds 10 MB limit.",
        )

    project_id = _get_project_id()
    if not project_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GCP project not configured. Set GCP_PROJECT_ID.",
        )

    processor_name = (
        f"projects/{project_id}"
        f"/locations/{settings.document_ai_location}"
        f"/processors/{settings.document_ai_processor_id}"
    )

    logger.info(
        "Document AI card extraction: %s (%d bytes) processor=%s",
        image.filename or "upload",
        len(image_bytes),
        settings.document_ai_processor_id,
    )

    try:
        client = _build_documentai_client()
        request = documentai.ProcessRequest(
            name=processor_name,
            raw_document=documentai.RawDocument(content=image_bytes, mime_type=content_type),
        )
        result = client.process_document(request=request)
        document = result.document
    except Exception as exc:
        logger.error("Document AI error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not read the card. Ensure it is well-lit and in focus, then try again.",
        ) from exc

    entities = _entity_map(document)
    logger.info("Document AI entities: %s", list(entities.keys()))
    logger.debug("Document AI entity values: %s", entities)

    company   = entities.get("insurance_company", "")
    plan_name = entities.get("plan_name", "")
    raw_type  = entities.get("plan_type", "")
    member_id = entities.get("member_id") or entities.get("subscriber_id", "")
    group_id  = entities.get("group_number") or entities.get("group_name", "")

    plan_type = _normalise_plan_type(company, plan_name, raw_type)

    # confident = True if we extracted at least the insurer or member ID
    confident = bool(company or member_id)
    note = None
    if not confident:
        note = "Could not extract key fields. Please fill in manually."

    return InsuranceCardExtraction(
        payer_name=company or None,
        plan_name=plan_name or None,
        member_id=member_id or None,
        group_id=group_id or None,
        plan_type=plan_type,
        rx_bin=entities.get("rx_bin") or None,
        rx_pcn=entities.get("rx_pcn") or None,
        rx_group=entities.get("rx_group") or None,
        confident=confident,
        note=note,
    )
