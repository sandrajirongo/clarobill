"""AI analysis service — generates patient-facing report content.

Produces two outputs:
  1. Bill summary  — plain-English explanation of errors (runs during analysis)
  2. Dispute letter — formal letter the patient can send to the provider (runs after payment)

Primary model: Gemini 2.0 Flash via Vertex AI (Google Cloud).
Fallback model: Claude Sonnet via Anthropic API.

The fallback activates on any Gemini failure (API error, rate limit, service unavailable).
If both providers fail the exception propagates — the caller marks the bill as FAILED
rather than delivering degraded output to a paying user.

Both providers use credentials already configured for the deployment:
  - Gemini:  Application Default Credentials (same as Cloud Vision + BigQuery)
  - Claude:  ANTHROPIC_API_KEY environment variable

All AI calls are funneled through this module. Test mode returns fixture text.
"""

import asyncio
import logging
from datetime import date

import anthropic
import vertexai
from vertexai.generative_models import GenerationConfig, GenerativeModel

from app.core.config import settings
from app.models.bill import BillingError
from app.services.parser import ParsedLineItem

logger = logging.getLogger(__name__)

_GEMINI_MODEL = "gemini-2.0-flash-001"


def _build_recipient_block(
    hospital_name: str | None,
    hospital_city: str | None,
    hospital_state: str | None,
    hospital_zip: str | None,
) -> str:
    """Build the recipient address block for a dispute letter.

    Combines whatever provider info we have into a USPS-shaped block:

        {hospital_name}
        Billing Department
        {city}, {state}  {zip}

    Each line is omitted gracefully when its source field is missing.
    When hospital_name is missing we fall back to a clear placeholder
    rather than a silent empty string — the patient can see what's
    expected and edit the DOCX before sending.

    Pre-2026-04-30 this was inlined and only used hospital_name; address
    fields were extracted from the bill but discarded. Sandra reported
    the resulting letters had a `[PROVIDER NAME AND ADDRESS]` placeholder
    even when the address was clearly visible in the bill OCR.
    """
    lines: list[str] = []
    if hospital_name:
        lines.append(hospital_name)
    else:
        lines.append("[PROVIDER NAME]")
    lines.append("Billing Department")

    # City/state/ZIP go on a single USPS-style line. Build it from whatever
    # subset we have rather than emitting an empty line — a bill that lists
    # only the state still produces a usable, partially-populated address.
    address_parts: list[str] = []
    if hospital_city:
        address_parts.append(hospital_city)
    if hospital_state:
        if address_parts:
            address_parts[-1] = f"{address_parts[-1]}, {hospital_state}"
        else:
            address_parts.append(hospital_state)
    if hospital_zip:
        address_parts.append(hospital_zip)
    if address_parts:
        # Two spaces between state and ZIP per USPS convention; otherwise
        # comma-separated.
        if hospital_state and hospital_zip and len(address_parts) >= 2:
            tail = address_parts.pop()  # ZIP
            lines.append(f"{address_parts[0]}  {tail}")
        else:
            lines.append(", ".join(address_parts))
    return "\n".join(lines)


class AiAnalysisService:
    """Generates patient-facing content from billing error analysis.

    Gemini 2.0 Flash is the primary provider. Claude Sonnet is the fallback.
    Test mode bypasses all API calls and returns fixture text.
    """

    def __init__(self, client: anthropic.AsyncAnthropic, test_mode: bool = False) -> None:
        self._client = client
        self._test_mode = test_mode
        # Only initialise Vertex AI when a project is configured — avoids failures
        # in test environments where GCP credentials are not present.
        if settings.gcp_project_id:
            vertexai.init(project=settings.gcp_project_id, location=settings.vertex_ai_location)

    async def _call_gemini(self, prompt: str, max_tokens: int) -> str:
        """Call Gemini via Vertex AI.

        The Vertex AI generative model SDK is synchronous; the call is wrapped in
        asyncio.to_thread so it does not block the event loop.

        Raises if the candidate did not finish cleanly (MAX_TOKENS, SAFETY,
        RECITATION, etc.) so the caller's fallback path activates instead of
        delivering a truncated mid-sentence response. Sandra hit this once with
        a dispute letter that cut off in Dispute 4 because Gemini stopped
        mid-stream and `response.text` returned the partial output silently.
        """
        def _sync() -> str:
            model = GenerativeModel(_GEMINI_MODEL)
            response = model.generate_content(
                prompt,
                generation_config=GenerationConfig(
                    max_output_tokens=max_tokens,
                    temperature=0.3,
                ),
            )
            candidate = response.candidates[0] if response.candidates else None
            finish_reason = getattr(candidate, "finish_reason", None)
            # finish_reason 1 == STOP (the only clean termination). Anything
            # else (MAX_TOKENS=2, SAFETY=3, RECITATION=4, OTHER=5) means the
            # output is truncated or otherwise unsafe to ship as-is.
            if finish_reason is not None and int(finish_reason) != 1:
                raise RuntimeError(
                    f"Gemini stopped with finish_reason={finish_reason} "
                    f"(not STOP); output likely truncated"
                )
            return str(response.text)

        return await asyncio.to_thread(_sync)

    async def generate_bill_summary(
        self,
        errors: list[BillingError],
        line_items: list[ParsedLineItem],
    ) -> str:
        """Generate a plain-English summary of billing errors for the patient.

        Args:
            errors: Detected billing errors from the rules engine.
            line_items: Parsed line items from the bill.

        Returns:
            2-3 sentence summary suitable for a non-expert patient.
        """
        if self._test_mode:
            return self._fixture_summary(errors)

        if not errors:
            return (
                "We reviewed your bill and did not find any obvious billing errors. "
                "Consider requesting an itemized statement from your provider to verify all charges."
            )

        total_overcharge = sum(e.estimated_overcharge for e in errors)
        error_descriptions = "\n".join(f"- {e.description}" for e in errors)

        prompt = (
            "You are helping a patient understand potential errors in their medical bill. "
            "Write 2-3 plain-English sentences summarizing what was found and how much the patient might save. "
            "Use plain prose only — no Markdown, no bold, no headers, no bullet points, no emojis. "
            f"Total potential overcharge: ${total_overcharge:.2f}.\n\n"
            f"Issues found:\n{error_descriptions}"
        )

        # Primary: Gemini
        try:
            text = await self._call_gemini(prompt, max_tokens=300)
            logger.info("Generated bill summary via Gemini (%d chars)", len(text))
            return text
        except Exception as exc:
            logger.warning(
                "Gemini call failed generating bill summary (%s: %s) — falling back to Claude",
                type(exc).__name__, exc,
            )

        # Fallback: Claude — propagates on failure so the caller can mark the bill FAILED
        message = await self._client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        # Claude returns list[TextBlock | ToolUseBlock]. We never request tool use,
        # so the first block is always a TextBlock — narrow explicitly so mypy is happy.
        first_block = message.content[0] if message.content else None
        text = first_block.text if isinstance(first_block, anthropic.types.TextBlock) else ""
        logger.info("Generated bill summary via Claude fallback (%d chars)", len(text))
        return text

    async def generate_dispute_letter(
        self,
        errors: list[BillingError],
        line_items: list[ParsedLineItem],
        bill_file_name: str,
        hospital_name: str | None = None,
        hospital_city: str | None = None,
        hospital_state: str | None = None,
        hospital_zip: str | None = None,
        payer_name: str | None = None,
        patient_name: str | None = None,
        patient_dob: str | None = None,
        member_id: str | None = None,
    ) -> str:
        """Generate a formal dispute letter the patient can send to their provider.

        Args:
            errors: Detected billing errors from the rules engine.
            line_items: Parsed line items from the bill.
            bill_file_name: Original file name — used to identify the bill in the letter.
            hospital_name: Provider name extracted from the bill, if available.
            hospital_city: Provider city extracted from the bill, if available.
            hospital_state: Provider state (2-letter) extracted from the bill, if available.
            hospital_zip: Provider ZIP extracted from the bill, if available.
            payer_name: Insurer name from user verification, if available.
            patient_name: Patient full name from profile_members, if available.
            patient_dob: Patient date of birth (ISO yyyy-mm-dd) from profile_members, if available.
            member_id: Insurance member ID from insurance_plans, if available.

        Returns:
            Plain-text dispute letter with no Markdown formatting, ready for DOCX conversion.
        """
        if not errors:
            return ""

        if self._test_mode:
            return self._fixture_dispute_letter(
                errors,
                patient_name=patient_name,
                patient_dob=patient_dob,
                member_id=member_id,
            )

        total_overcharge = sum(e.estimated_overcharge for e in errors)
        error_list = "\n".join(
            f"- {e.code}: {e.description} (estimated overcharge: ${e.estimated_overcharge:.2f})"
            for e in errors
        )
        line_item_summary = "\n".join(
            f"  - CPT {item.cpt_code}: {item.description}, ${item.total_charge:.2f}, "
            f"date {item.service_date}"
            for item in line_items[:20]
        )

        recipient_line = _build_recipient_block(
            hospital_name=hospital_name,
            hospital_city=hospital_city,
            hospital_state=hospital_state,
            hospital_zip=hospital_zip,
        )
        insurer_line = (
            f"Insurance: {payer_name}" if payer_name else ""
        )
        patient_name_value = patient_name if patient_name else "[YOUR NAME]"
        patient_dob_value = patient_dob if patient_dob else "[YOUR DATE OF BIRTH]"
        member_id_value = member_id if member_id else "[YOUR MEMBER ID]"
        # Format: "April 25, 2026". Server runs in UTC on Cloud Run; a one-day
        # drift versus the user's local date is acceptable for a dispute letter.
        today = date.today()
        today_value = f"{today.strftime('%B')} {today.day}, {today.year}"

        prompt = (
            "You are a medical billing advocate helping a patient write a formal dispute letter "
            "to their healthcare provider. Write a professional, firm, and specific dispute letter "
            "based on the billing errors below.\n\n"
            "CRITICAL FORMATTING RULES — follow exactly:\n"
            "- Plain text only. No Markdown. No asterisks, no pound signs, no dashes as bullets.\n"
            "- Separate every section with a blank line.\n"
            "- Label each dispute item as 'Dispute 1:', 'Dispute 2:', etc. on its own line, "
            "followed by a blank line, then the detail paragraph.\n"
            "- No bold, no italics, no underline, no lists.\n\n"
            "Letter structure (use exactly this order):\n"
            f"1. Today's date (already filled in — use as-is): {today_value}\n"
            f"2. Recipient block (already filled in — use as-is):\n{recipient_line}\n"
            "3. Subject line: Re: Billing Dispute — [bill reference]\n"
            "4. Salutation: Dear Billing Department,\n"
            "5. Opening paragraph (1-2 sentences citing the total disputed amount)\n"
            "6. One section per billing error, each starting with 'Dispute N:'\n"
            "7. Closing paragraph requesting itemized bill and corrected statement within 30 days\n"
            f"8. Closing: Sincerely,\n\n{patient_name_value}\n{patient_dob_value}\n{insurer_line}\n"
            f"   Member ID: {member_id_value}\n\n"
            f"Bill reference: {bill_file_name}\n"
            f"Total disputed amount: ${total_overcharge:.2f}\n\n"
            f"Billing errors found:\n{error_list}\n\n"
            f"Line items on the bill:\n{line_item_summary}"
        )

        # max_tokens=4096: gives the model generous headroom for a 10-error
        # letter with full provider/patient blocks, a real opening, ~250 tok
        # per dispute paragraph, closing, and signature. Gemini 2.0 Flash
        # supports up to 8192 output tokens, so 4096 is safe.
        # 2500 was the prior value but Sandra hit a mid-Dispute-4 cutoff on a
        # 4-error letter (~700 tokens of actual output) — the issue was not
        # the cap but Gemini stopping early without setting finish_reason=STOP.
        # `_call_gemini` now raises on non-STOP finishes so the Claude
        # fallback handles those cases; this ceiling is the guaranteed-budget
        # for clean Gemini runs.
        _LETTER_MAX_TOKENS = 4096

        # Primary: Gemini
        try:
            text = await self._call_gemini(prompt, max_tokens=_LETTER_MAX_TOKENS)
            logger.info("Generated dispute letter via Gemini (%d chars)", len(text))
            return text
        except Exception as exc:
            logger.warning(
                "Gemini call failed generating dispute letter (%s: %s) — falling back to Claude",
                type(exc).__name__, exc,
            )

        # Fallback: Claude — propagates on failure so the caller can mark the bill FAILED
        message = await self._client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=_LETTER_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        # Claude returns list[TextBlock | ToolUseBlock]. We never request tool use,
        # so the first block is always a TextBlock — narrow explicitly so mypy is happy.
        first_block = message.content[0] if message.content else None
        text = first_block.text if isinstance(first_block, anthropic.types.TextBlock) else ""
        logger.info("Generated dispute letter via Claude fallback (%d chars)", len(text))
        return text

    @staticmethod
    def _fixture_summary(errors: list[BillingError]) -> str:
        if not errors:
            return "No billing errors were found in your bill."
        total = sum(e.estimated_overcharge for e in errors)
        return (
            f"We found {len(errors)} potential billing issue(s) in your bill totalling "
            f"${total:.2f} in possible overcharges. "
            "Review the findings below and consider contacting your provider."
        )

    @staticmethod
    def _fixture_dispute_letter(
        errors: list[BillingError],
        *,
        patient_name: str | None = None,
        patient_dob: str | None = None,
        member_id: str | None = None,
    ) -> str:
        total = sum(e.estimated_overcharge for e in errors)
        name_line = patient_name if patient_name else "[YOUR NAME]"
        dob_line = patient_dob if patient_dob else "[YOUR DATE OF BIRTH]"
        member_line = member_id if member_id else "[YOUR MEMBER ID]"
        today = date.today()
        today_line = f"{today.strftime('%B')} {today.day}, {today.year}"
        return (
            f"{today_line}\n\nBilling Department,\n\n"
            "I am writing to formally dispute charges on my recent medical bill.\n\n"
            f"Total disputed amount: ${total:.2f}\n\n"
            "Please provide an itemized bill and corrected statement within 30 days.\n\n"
            f"Sincerely,\n{name_line}\n{dob_line}\nMember ID: {member_line}"
        )
