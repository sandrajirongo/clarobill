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
            hospital_name: Provider name extracted from the bill or user input, if available.
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

        recipient_line = (
            f"{hospital_name}\nBilling Department" if hospital_name
            else "Billing Department\n[PROVIDER NAME AND ADDRESS]"
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

        # Primary: Gemini
        try:
            text = await self._call_gemini(prompt, max_tokens=800)
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
            max_tokens=800,
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
