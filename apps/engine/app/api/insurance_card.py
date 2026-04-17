"""Insurance card extraction endpoint.

Accepts an image of an insurance card (JPEG, PNG, or PDF scan) and uses
Claude's vision capability to extract structured plan data. Returns all
identifiable fields with confidence indicators so the frontend can highlight
any fields that need user review.

Claude sees the card image directly — no intermediate OCR step. This is more
accurate than Vision OCR + text parsing because Claude understands spatial
layout and field labels in context (e.g. distinguishing "Member ID" from
"Group #" from "Rx BIN" when they appear next to each other on the card).
"""

import base64
import logging
import json
import re

import anthropic
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict

from app.core.dependencies import get_anthropic_client

router = APIRouter(prefix="/insurance-card", tags=["insurance-card"])
logger = logging.getLogger(__name__)

# Maximum image size — insurance card photos are small; reject anything huge
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


class InsuranceCardExtraction(BaseModel):
    """Structured fields extracted from an insurance card image.

    Each field is None when not found on the card. The 'confident' flag is
    False when Claude found a plausible value but was uncertain (e.g. a number
    that could be either a member ID or group number). The frontend should
    highlight low-confidence fields for user review.
    """
    model_config = ConfigDict(strict=True)

    payer_name: str | None
    plan_name: str | None
    member_id: str | None
    group_id: str | None
    # Inferred from card context: commercial/medicare/medicaid/tricare/self_pay
    plan_type: str | None
    # False when a field was populated but Claude was uncertain about it
    confident: bool
    # Plain-English note if anything was ambiguous or missing
    note: str | None


_EXTRACTION_PROMPT = """You are reading an insurance card image. Extract the following fields exactly as printed on the card.

Return ONLY a JSON object with these exact keys:
{
  "payer_name": "Insurance company name (e.g. 'Blue Cross Blue Shield of California')",
  "plan_name": "Plan or product name (e.g. 'PPO Gold', 'HMO Select', 'Medicare Advantage'). Look for labels like Plan, Product, Coverage, or Network.",
  "member_id": "The member/subscriber ID number. Look for labels: Member ID, Member #, ID, Subscriber ID. This is NOT the Group #, NOT the Rx BIN, NOT the PCN, NOT the phone number.",
  "group_id": "The group number. Look for labels: Group, Group #, Grp, Employer Group.",
  "plan_type": "One of: commercial, medicare, medicaid, tricare, self_pay. Infer from the card — e.g. 'Medicare' or 'Medicaid' in the company name or plan name.",
  "confident": true or false — set false if you were uncertain about any field,
  "note": "Optional plain-English note if anything was ambiguous, missing, or if multiple numbers appeared that could be the member ID."
}

Rules:
- If a field is not visible on the card, use null.
- Do not invent values. Only return what you can read.
- The member_id is almost always labeled explicitly. If you see several ID-like numbers, pick the one labeled 'Member' or 'ID' or 'Subscriber'.
- Return ONLY the JSON object — no explanation, no markdown, no surrounding text."""


@router.post(
    "/extract",
    response_model=InsuranceCardExtraction,
    status_code=status.HTTP_200_OK,
)
async def extract_insurance_card(
    image: UploadFile = File(..., description="Insurance card image (JPEG, PNG, or WebP)"),
    client: anthropic.Anthropic = Depends(get_anthropic_client),
) -> InsuranceCardExtraction:
    """Extract structured insurance plan data from a card photo.

    The image is sent directly to Claude's vision API. No PHI is stored —
    this endpoint is stateless and returns only the extracted fields.
    """
    # Validate content type
    content_type = image.content_type or ""
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported image type '{content_type}'. Use JPEG, PNG, or WebP.",
        )

    # Read and size-check the image
    image_bytes = await image.read()
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image exceeds 5 MB limit.",
        )

    # Base64-encode for Claude's vision API
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    logger.info(
        "Extracting insurance card data from %s (%d bytes)",
        image.filename or "upload",
        len(image_bytes),
    )

    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",  # Haiku is fast + cheap for structured extraction
            max_tokens=512,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": content_type,
                                "data": image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": _EXTRACTION_PROMPT,
                        },
                    ],
                }
            ],
        )
    except anthropic.APIError as exc:
        logger.error("Claude API error during card extraction: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Card extraction service unavailable. Please try again.",
        ) from exc

    raw_text = message.content[0].text if message.content else ""
    logger.debug("Claude raw extraction response: %s", raw_text[:500])

    # Parse JSON from Claude's response — strip any accidental markdown fences
    json_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text.strip(), flags=re.MULTILINE)
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        logger.warning("Claude returned non-JSON during card extraction: %s", raw_text[:200])
        # Return empty extraction rather than a 500 — user can fill in manually
        return InsuranceCardExtraction(
            payer_name=None,
            plan_name=None,
            member_id=None,
            group_id=None,
            plan_type=None,
            confident=False,
            note="Could not read the card clearly. Please fill in the fields manually.",
        )

    # Normalise plan_type to our enum values
    raw_type = (data.get("plan_type") or "").lower()
    plan_type_map = {
        "commercial": "commercial",
        "medicare": "medicare",
        "medicaid": "medicaid",
        "tricare": "tricare",
        "self_pay": "self_pay",
        "self-pay": "self_pay",
        "self pay": "self_pay",
    }
    plan_type = plan_type_map.get(raw_type, "commercial" if raw_type else None)

    return InsuranceCardExtraction(
        payer_name=data.get("payer_name") or None,
        plan_name=data.get("plan_name") or None,
        member_id=data.get("member_id") or None,
        group_id=data.get("group_id") or None,
        plan_type=plan_type,
        confident=bool(data.get("confident", True)),
        note=data.get("note") or None,
    )
