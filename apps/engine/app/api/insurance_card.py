"""Insurance card extraction — GCV OCR + Claude text parsing.

Two-stage pipeline used by production document scanning systems:
  1. Google Cloud Vision document_text_detection → raw OCR text (~0.5s)
  2. Claude Sonnet text API → structured JSON from OCR text (~1-2s)

This is more reliable than sending the raw image to Claude Vision because:
- GCV is purpose-built for dense printed text on cards (handles glare, plastic sheen)
- The text API never fails due to image quality — only the OCR step sees the image
- Combined latency ~2-3s vs 8-15s for vision inference on a high-res frame
"""

import json
import logging
import re

import anthropic
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict

from app.core.dependencies import get_async_anthropic_client
from app.services.ocr import OcrExtractionError, OcrService

router = APIRouter(prefix="/insurance-card", tags=["insurance-card"])
logger = logging.getLogger(__name__)

# The frontend crops to the card region before sending, so images are small.
# Keep the limit generous for upload-a-photo fallback.
MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}


class InsuranceCardExtraction(BaseModel):
    """Structured fields extracted from an insurance card.

    Each field is None when not found. confident=False signals the frontend
    to highlight fields for user review.
    """

    model_config = ConfigDict(strict=True)

    payer_name: str | None
    plan_name: str | None
    member_id: str | None
    group_id: str | None
    plan_type: str | None
    confident: bool
    note: str | None


_PARSE_PROMPT = """\
Parse the OCR text below from a health insurance card. Return ONLY a valid JSON object — \
no explanation, no markdown fences.

Required keys:
  "payer_name"  — Insurance company name. e.g. Aetna, Blue Cross Blue Shield, UnitedHealthcare, \
Humana, Cigna, Molina, Kaiser, Anthem, BCBS, Centene. null if not present.
  "plan_name"   — Specific plan/product name. Look for Plan, Product, Coverage, Network labels. \
null if not separately labeled.
  "member_id"   — Member/subscriber ID. Labels: Member ID, Member #, ID #, Subscriber ID, Mbr ID. \
NOT Group #, NOT Rx BIN, NOT PCN, NOT RxGrp. null if not present.
  "group_id"    — Group/employer number. Labels: Group, Group #, Grp #. null if not present.
  "plan_type"   — Exactly one of: commercial, medicare, medicaid, tricare, self_pay.
                  medicare  → card mentions Medicare, CMS, or Medicare Advantage
                  medicaid  → card mentions Medicaid, CHIP, Medi-Cal, TennCare, AHCCCS, or any state Medicaid brand
                  tricare   → card mentions TRICARE, Military Health System, DoD
                  self_pay  → no insurer name
                  commercial → all employer/marketplace/ACA plans from private insurers
  "confident"   — true if all values are clear and unambiguous, false if any were uncertain
  "note"        — brief description of ambiguity, or null

Rules:
- Use null (never empty string) for fields not found in the text
- "plan_type" is always one of the 5 values, never null

OCR text extracted from card:
{ocr_text}"""

_ASSISTANT_PREFILL = "{"


def _normalise_plan_type(raw: str) -> str:
    s = raw.lower().strip()
    exact: dict[str, str] = {
        "commercial": "commercial",
        "medicare": "medicare",
        "medicaid": "medicaid",
        "tricare": "tricare",
        "self_pay": "self_pay",
        "self-pay": "self_pay",
        "self pay": "self_pay",
    }
    if s in exact:
        return exact[s]
    if "medicare" in s:
        return "medicare"
    if "medicaid" in s or "chip" in s or "medi-cal" in s or "tenncare" in s or "ahcccs" in s:
        return "medicaid"
    if "tricare" in s or "military" in s:
        return "tricare"
    if "self" in s:
        return "self_pay"
    return "commercial"


@router.post(
    "/extract",
    response_model=InsuranceCardExtraction,
    status_code=status.HTTP_200_OK,
)
async def extract_insurance_card(
    image: UploadFile = File(..., description="Cropped insurance card image (JPEG, PNG, or WebP)"),
    client: anthropic.AsyncAnthropic = Depends(get_async_anthropic_client),
) -> InsuranceCardExtraction:
    """Extract structured insurance plan data from a card photo.

    Uses Google Cloud Vision for OCR, then Claude text API for field parsing.
    No PHI is stored — this endpoint is stateless.
    """
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

    logger.info(
        "Insurance card extraction: %s (%d bytes)",
        image.filename or "upload",
        len(image_bytes),
    )

    # ── Stage 1: Google Cloud Vision OCR ─────────────────────────────────────
    try:
        ocr = OcrService()
        raw_text = await ocr.extract_text(image_bytes, content_type)
    except OcrExtractionError as exc:
        logger.error("GCV OCR failed for insurance card: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not read text from the card. Ensure the card is well-lit, flat, and in focus.",
        ) from exc

    logger.info("GCV extracted %d characters from card", len(raw_text))
    logger.debug("Card OCR text: %.400s", raw_text)

    # ── Stage 2: Claude text API parses the OCR output ────────────────────────
    try:
        message = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            messages=[
                {
                    "role": "user",
                    "content": _PARSE_PROMPT.format(ocr_text=raw_text),
                },
                {
                    "role": "assistant",
                    "content": _ASSISTANT_PREFILL,
                },
            ],
        )
    except anthropic.APIError as exc:
        logger.error("Claude API error parsing card OCR text: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Card parsing service unavailable. Please try again.",
        ) from exc

    first_block = message.content[0] if message.content else None
    continuation = first_block.text if isinstance(first_block, anthropic.types.TextBlock) else ""
    raw_json = re.sub(r"\s*```\s*$", "", (_ASSISTANT_PREFILL + (continuation or "}")).strip())

    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        logger.warning("Claude returned non-JSON for card: %.200s", raw_json)
        return InsuranceCardExtraction(
            payer_name=None,
            plan_name=None,
            member_id=None,
            group_id=None,
            plan_type="commercial",
            confident=False,
            note="Could not parse fields automatically. Please fill in manually.",
        )

    raw_type = str(data.get("plan_type") or "")
    return InsuranceCardExtraction(
        payer_name=data.get("payer_name") or None,
        plan_name=data.get("plan_name") or None,
        member_id=data.get("member_id") or None,
        group_id=data.get("group_id") or None,
        plan_type=_normalise_plan_type(raw_type) if raw_type else None,
        confident=bool(data.get("confident", True)),
        note=data.get("note") or None,
    )
