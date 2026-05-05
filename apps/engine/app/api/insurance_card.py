"""Insurance card field extraction via AI vision.

Accepts a cropped card image (JPEG/PNG/WebP from the frontend), extracts structured
insurance plan fields, and returns typed data. The image is never stored — this
endpoint is stateless.

Primary model: Gemini 2.0 Flash via Vertex AI (multimodal).
Fallback model: Claude Sonnet via Anthropic API.

The fallback activates on any Gemini failure. If both providers fail a 502 is returned.
"""

import asyncio
import base64
import json
import logging
from typing import Annotated, Literal, cast

import anthropic
from anthropic.types import TextBlock
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from vertexai.generative_models import GenerativeModel, Part

from app.core.config import settings
from app.core.posthog_client import posthog_client
from app.models.bill import PlanType

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
    """Structured fields extracted from an insurance card.

    T3 + T4 (Phase 8.1): plan_type is a closed set; the engine emits
    camelCase via alias_generator so the web layer can parse via Zod
    rather than hand-translating each field.
    """

    model_config = ConfigDict(
        strict=True,
        alias_generator=to_camel,
        populate_by_name=True,
    )

    payer_name: str | None
    plan_name: str | None
    member_id: str | None
    group_id: str | None
    # strict=False on the field allows raw strings to coerce into the
    # PlanType StrEnum at construction time. The model-level strict=True
    # still applies to every other field. Mirrors the AnalyzeRequest
    # pattern from H10.
    plan_type: Annotated[PlanType, Field(strict=False)] | None
    rx_bin: str | None
    rx_pcn: str | None
    rx_group: str | None
    confident: bool
    note: str | None


def _parse_ai_response(raw_text: str) -> dict[str, object]:
    """Strip optional markdown code fences and parse JSON from an AI response.

    H16 (Phase 8.3): defensive against malformed fences. Pre-H16 a response
    of just "```" (no newline, no closing fence) raised IndexError on the
    `split("\\n", 1)[1]` access — and the caller's try/except only caught
    JSONDecodeError + ValueError, so the IndexError escaped as a raw 500
    with no PostHog telemetry. Now any opening fence is stripped via
    removeprefix + closing fence stripped via rstrip, with NO indexing
    operations that could raise.
    """
    text = raw_text.strip()
    if text.startswith("```"):
        # Drop opening fence + optional language tag (e.g. ```json).
        # If there's a newline after the fence, drop everything up to it.
        text = text.removeprefix("```")
        if "\n" in text:
            text = text.split("\n", 1)[1]
        # Drop trailing closing fence; rstrip handles any number of
        # trailing backticks + whitespace.
        text = text.rstrip("`").strip()
    return json.loads(text)  # type: ignore[no-any-return]


def _gemini_extract_sync(image_bytes: bytes, mime_type: str) -> str:
    """Synchronous Gemini vision call — run via asyncio.to_thread."""
    model = GenerativeModel("gemini-2.0-flash-001")
    image_part = Part.from_data(data=image_bytes, mime_type=mime_type)
    response = model.generate_content([image_part, _EXTRACT_PROMPT])
    return str(response.text)


async def _extract_via_gemini(image_bytes: bytes, mime_type: str) -> str:
    return await asyncio.to_thread(_gemini_extract_sync, image_bytes, mime_type)


@router.post(
    "/extract",
    response_model=InsuranceCardExtraction,
    status_code=status.HTTP_200_OK,
)
async def extract_insurance_card(
    image: UploadFile = File(..., description="Insurance card photo (JPEG, PNG, or WebP)"),  # noqa: B008
) -> InsuranceCardExtraction:
    """Extract structured insurance plan data from a card photo.

    Tries Gemini 2.0 Flash vision first; falls back to Claude Sonnet on any
    Gemini failure. Returns 502 only when both providers fail.
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

    logger.info("Card extraction: %s (%d bytes)", image.filename or "upload", len(image_bytes))

    # Primary: Gemini vision
    raw_text: str | None = None
    provider: str = "gemini"
    try:
        raw_text = await _extract_via_gemini(image_bytes, content_type)
        logger.info("Card extracted via Gemini")
    except Exception as exc:
        logger.warning(
            "Gemini vision failed (%s: %s) — falling back to Claude",
            type(exc).__name__, exc,
        )

    # Fallback: Claude vision
    if raw_text is None:
        provider = "claude"
        try:
            raw_text = await asyncio.to_thread(_extract_via_claude_sync, image_bytes, content_type)
            logger.info("Card extracted via Claude fallback")
        except Exception as exc:
            logger.error("Both vision providers failed for card extraction: %s", exc)
            posthog_client.capture(
                distinct_id="anonymous",
                event="insurance card extraction failed",
                properties={"$process_person_profile": False},
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not read the card. Ensure it is well-lit and try again.",
            ) from exc

    try:
        data = _parse_ai_response(raw_text)
    # H16 (Phase 8.3): widened from (JSONDecodeError, ValueError) to
    # Exception. The parse step is small and the failure mode is bounded
    # — any error here means we couldn't recover the AI's JSON, regardless
    # of the specific exception class.
    except Exception as exc:
        logger.error("Failed to parse AI card extraction response: %s", raw_text[:200])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not parse card data. Please try again.",
        ) from exc

    def _str(key: str) -> str | None:
        val = data.get(key)
        return str(val) if val else None

    # T3 fix (Phase 8.1): plan_type is a closed set. If the AI returned a
    # value outside PlanType (e.g. "PPO", "Choice POS I"), pass None so
    # the user picks from the closed set in the UI rather than silently
    # defaulting to "commercial" (which routed wrong rule benchmarks).
    raw_plan_type = _str("plan_type")
    valid_plan_types = {pt.value for pt in PlanType}
    plan_type_value: PlanType | None = (
        PlanType(raw_plan_type) if raw_plan_type in valid_plan_types else None
    )

    result = InsuranceCardExtraction(
        payer_name=_str("payer_name"),
        plan_name=_str("plan_name"),
        member_id=_str("member_id"),
        group_id=_str("group_id"),
        plan_type=plan_type_value,
        rx_bin=_str("rx_bin"),
        rx_pcn=_str("rx_pcn"),
        rx_group=_str("rx_group"),
        confident=bool(data.get("confident", False)),
        note=_str("note"),
    )
    posthog_client.capture(
        distinct_id="anonymous",
        event="insurance card extracted",
        properties={
            "$process_person_profile": False,
            "provider": provider,
            "confident": result.confident,
            "plan_type": result.plan_type,
        },
    )
    return result


def _extract_via_claude_sync(image_bytes: bytes, mime_type: str) -> str:
    """Synchronous Claude vision call — run via asyncio.to_thread."""
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
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
                            mime_type,
                        ),
                        "data": base64.standard_b64encode(image_bytes).decode(),
                    },
                },
                {"type": "text", "text": _EXTRACT_PROMPT},
            ],
        }],
    )
    first_block = response.content[0]
    if not isinstance(first_block, TextBlock):
        raise ValueError(f"Unexpected Claude response block type: {type(first_block)}")
    return first_block.text
