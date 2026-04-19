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
import json
import logging
import re
from typing import Literal, cast

import anthropic
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict

from app.core.dependencies import get_async_anthropic_client

router = APIRouter(prefix="/insurance-card", tags=["insurance-card"])
logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


class InsuranceCardExtraction(BaseModel):
    """Structured fields extracted from an insurance card image.

    Each field is None when not found on the card. The 'confident' flag is
    False when Claude found a plausible value but was uncertain. The frontend
    should highlight low-confidence fields for user review.
    """
    model_config = ConfigDict(strict=True)

    payer_name: str | None
    plan_name: str | None
    member_id: str | None
    group_id: str | None
    plan_type: str | None
    confident: bool
    note: str | None


# The user message instructs what to extract; the assistant prefill (`{`) forces
# Claude to start its response as a JSON object — no markdown fences possible.
_USER_PROMPT = """You are extracting structured data from a health insurance card photo.

Return ONLY a valid JSON object with these exact keys (no explanation, no markdown):

{
  "payer_name": "Insurance company name printed on the card. Examples: Aetna, Blue Cross Blue Shield, UnitedHealthcare, Humana, Cigna, Molina Healthcare, Kaiser Permanente, Anthem, BCBS. null if not visible.",
  "plan_name": "Specific plan or product name. Labels to look for: Plan, Product, Coverage, Network, Program. Examples: PPO Gold, HMO Select, Medicare Advantage Plus, Medicaid Managed Care, BlueCare. null if not labeled separately.",
  "member_id": "Member or subscriber ID. Labels: Member ID, Member #, ID #, Subscriber ID, Mbr ID. NOT the Group #, NOT Rx BIN, NOT PCN, NOT phone number. null if not visible.",
  "group_id": "Group or employer group number. Labels: Group, Group #, Grp #, Employer Group. null if not visible.",
  "plan_type": "MUST be exactly one of: commercial, medicare, medicaid, tricare, self_pay. Choose using these rules: 'medicare' if card shows Medicare, CMS, or Medicare Advantage. 'medicaid' if card shows Medicaid, CHIP, Medi-Cal, Healthy Families, ACCESS, AHCCCS, TennCare, or any state Medicaid program name. 'tricare' if card shows TRICARE, Military Health System, VA, or DoD. 'self_pay' if the card has no insurer name. 'commercial' for all employer/marketplace/ACA plans including HMO, PPO, EPO, POS plans from private insurers.",
  "confident": true,
  "note": null
}

Rules:
- Use null (not empty string "") for any field not found on the card
- Set "confident" to false if ANY field value was uncertain or ambiguous
- "plan_type" must be exactly one of the 5 values — never null
- "note" should describe any ambiguity or explain why confident is false"""

_ASSISTANT_PREFILL = "{"


def _normalise_plan_type(raw: str) -> str:
    """Map Claude's plan_type output to one of our 5 canonical values.

    Claude is instructed to return exact values but may deviate, especially
    when card text is ambiguous. We use substring matching as a fallback.
    """
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

    # Substring fallback — handles "medicare advantage", "medicaid hmo", "tricare prime", etc.
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
    image: UploadFile = File(..., description="Insurance card image (JPEG, PNG, or WebP)"),
    client: anthropic.AsyncAnthropic = Depends(get_async_anthropic_client),
) -> InsuranceCardExtraction:
    """Extract structured insurance plan data from a card photo.

    The image is sent directly to Claude's vision API. No PHI is stored —
    this endpoint is stateless and returns only the extracted fields.
    """
    content_type = image.content_type or ""
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported image type '{content_type}'. Use JPEG, PNG, or WebP.",
        )

    image_bytes = await image.read()
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image exceeds 5 MB limit. Please use a photo under 5 MB.",
        )

    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    logger.info(
        "Extracting insurance card data from %s (%d bytes)",
        image.filename or "upload",
        len(image_bytes),
    )

    try:
        message = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=768,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": cast(
                                    Literal["image/jpeg", "image/png", "image/gif", "image/webp"],
                                    content_type,
                                ),
                                "data": image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": _USER_PROMPT,
                        },
                    ],
                },
                # Prefill forces Claude to begin its response as a JSON object,
                # eliminating any risk of markdown fences or explanatory prose.
                {
                    "role": "assistant",
                    "content": _ASSISTANT_PREFILL,
                },
            ],
        )
    except anthropic.APIError as exc:
        logger.error("Claude API error during card extraction: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Card extraction service unavailable. Please try again.",
        ) from exc

    # Claude continues from the prefill "{" — prepend it back before parsing
    first_block = message.content[0] if message.content else None
    continuation = first_block.text if isinstance(first_block, anthropic.types.TextBlock) else ""
    raw_text = _ASSISTANT_PREFILL + (continuation or "}")
    logger.debug("Claude raw extraction response: %s", raw_text[:600])

    # Strip any trailing markdown fences Claude might still add after the JSON
    json_text = re.sub(r"\s*```\s*$", "", raw_text.strip())

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        logger.warning("Claude returned non-JSON during card extraction: %s", raw_text[:300])
        return InsuranceCardExtraction(
            payer_name=None,
            plan_name=None,
            member_id=None,
            group_id=None,
            plan_type="commercial",
            confident=False,
            note="Could not read the card clearly. Please fill in the fields manually.",
        )

    raw_type = str(data.get("plan_type") or "")
    plan_type: str | None = _normalise_plan_type(raw_type) if raw_type else None

    return InsuranceCardExtraction(
        payer_name=data.get("payer_name") or None,
        plan_name=data.get("plan_name") or None,
        member_id=data.get("member_id") or None,
        group_id=data.get("group_id") or None,
        plan_type=plan_type,
        confident=bool(data.get("confident", True)),
        note=data.get("note") or None,
    )
