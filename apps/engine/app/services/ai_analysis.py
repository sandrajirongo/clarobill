"""AI analysis service — uses Claude to generate patient-facing report content.

Produces two outputs:
  1. Bill summary  — plain-English explanation of errors (runs during analysis)
  2. Dispute letter — formal letter the patient can send to the provider (runs after payment)

All Claude calls are funneled through this module. Test mode returns fixture text.
"""

import logging
from decimal import Decimal

import anthropic

from app.models.bill import BillingError
from app.services.parser import ParsedLineItem

logger = logging.getLogger(__name__)


class AiAnalysisService:
    """Generates patient-facing content from billing error analysis using Claude."""

    def __init__(self, client: anthropic.AsyncAnthropic, test_mode: bool = False) -> None:
        self._client = client
        self._test_mode = test_mode

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

        message = await self._client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )

        text = message.content[0].text if message.content else ""
        logger.info("Generated bill summary (%d chars)", len(text))
        return text

    async def generate_dispute_letter(
        self,
        errors: list[BillingError],
        line_items: list[ParsedLineItem],
        bill_file_name: str,
        hospital_name: str | None = None,
        payer_name: str | None = None,
    ) -> str:
        """Generate a formal dispute letter the patient can send to their provider.

        Args:
            errors: Detected billing errors from the rules engine.
            line_items: Parsed line items from the bill.
            bill_file_name: Original file name — used to identify the bill in the letter.
            hospital_name: Provider name extracted from the bill or user input, if available.
            payer_name: Insurer name from user verification, if available.

        Returns:
            Plain-text dispute letter with no Markdown formatting, ready for DOCX conversion.
        """
        if not errors:
            return ""

        if self._test_mode:
            return self._fixture_dispute_letter(errors)

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
            "1. Today's date as [DATE]\n"
            f"2. Recipient block (already filled in — use as-is):\n{recipient_line}\n"
            "3. Subject line: Re: Billing Dispute — [bill reference]\n"
            "4. Salutation: Dear Billing Department,\n"
            "5. Opening paragraph (1-2 sentences citing the total disputed amount)\n"
            "6. One section per billing error, each starting with 'Dispute N:'\n"
            "7. Closing paragraph requesting itemized bill and corrected statement within 30 days\n"
            f"8. Closing: Sincerely,\n\n[YOUR NAME]\n[YOUR DATE OF BIRTH]\n{insurer_line}\n"
            "   Member ID: [YOUR MEMBER ID]\n\n"
            f"Bill reference: {bill_file_name}\n"
            f"Total disputed amount: ${total_overcharge:.2f}\n\n"
            f"Billing errors found:\n{error_list}\n\n"
            f"Line items on the bill:\n{line_item_summary}"
        )

        message = await self._client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )

        text = message.content[0].text if message.content else ""
        logger.info("Generated dispute letter (%d chars)", len(text))
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
    def _fixture_dispute_letter(errors: list[BillingError]) -> str:
        total = sum(e.estimated_overcharge for e in errors)
        return (
            "[DATE]\n\nBilling Department,\n\n"
            "I am writing to formally dispute charges on my recent medical bill.\n\n"
            f"Total disputed amount: ${total:.2f}\n\n"
            "Please provide an itemized bill and corrected statement within 30 days.\n\n"
            "Sincerely,\n[YOUR NAME]"
        )
