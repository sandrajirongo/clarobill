"""Insurance card extraction via Claude Sonnet vision.

Accepts a cropped card image (1200×756 JPEG from the frontend), sends it to
Claude Sonnet with a structured extraction prompt, and returns typed insurance
plan fields. The image is never stored — this endpoint is stateless.
"""

import base64
import json
import logging
from typing import Literal, cast

from anthropic import Anthropic
from anthropic.types import TextBlock
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict

from app.core.config import settings

router = APIRouter(prefix="/insurance-card", tags=["insurance-card"])
logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}

_EXTRACT_PROMPT = """
Extract all insurance card fields from this image.
Return ONLY a JSON object with these exact keys:

- payer_name: insurance company name (string or null)
- plan_name: plan or product name such as "Choice POS I", "HMO Gold", etc. (string or null)
- member_id: member or subscriber ID number (string or null)
- group_id: group number (string or null)
- plan_type: one of "commercial", "medicare", "medicaid", "tricare", "self_pay"
- rx_bin: pharmacy BIN number, typically labeled BIN or RxBIN (string or null)
- rx_pcn: pharmacy PCN number (string or null)
- rx_group: pharmacy group number, distinct from the medical group number (string or null)
- confident: true if you could clearly read payer_name or member_id, false otherwise
- note: brief note if confidence is low, null otherwise

Return only the JSON object. No markdown, no explanation."""


class InsuranceCardExtraction(BaseModel):
    """Structured fields extracted from an insurance card."""

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


@router.post(
    "/extract",
    response_model=InsuranceCardExtraction,
    status_code=status.HTTP_200_OK,
)
async def extract_insurance_card(
    image: UploadFile = File(..., description="Insurance card photo (JPEG, PNG, or WebP)"),  # noqa: B008
) -> InsuranceCardExtraction:
    """Extract structured insurance plan data from a card photo using Claude vision."""
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

    logger.info("Card extraction: %s (%d bytes)", image.filename or "upload", len(image_bytes))

    try:
        client = Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            messages=[{
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
                            "data": base64.standard_b64encode(image_bytes).decode(),
                        },
                    },
                    {"type": "text", "text": _EXTRACT_PROMPT},
                ],
            }],
        )
    except Exception as exc:
        logger.error("Claude vision error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not read the card. Ensure it is well-lit and try again.",
        ) from exc

    first_block = response.content[0]
    if not isinstance(first_block, TextBlock):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unexpected response format. Please try again.",
        )
    raw_text = first_block.text.strip()

    # Strip markdown code fences if the model wraps the JSON
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        data: dict[str, object] = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse Claude response: %s", raw_text)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not parse card data. Please try again.",
        ) from exc

    def _str(key: str) -> str | None:
        val = data.get(key)
        return str(val) if val else None

    return InsuranceCardExtraction(
        payer_name=_str("payer_name"),
        plan_name=_str("plan_name"),
        member_id=_str("member_id"),
        group_id=_str("group_id"),
        plan_type=_str("plan_type") or "commercial",
        rx_bin=_str("rx_bin"),
        rx_pcn=_str("rx_pcn"),
        rx_group=_str("rx_group"),
        confident=bool(data.get("confident", False)),
        note=_str("note"),
    )
