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
            "Summarize the following billing issues in 2-3 plain-English sentences. "
            "Be specific about what was found and how much the patient might save. "
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
    ) -> str:
        """Generate a formal dispute letter the patient can send to their provider.

        Args:
            errors: Detected billing errors from the rules engine.
            line_items: Parsed line items from the bill.
            bill_file_name: Original file name — used to identify the bill in the letter.

        Returns:
            Full text of a formal dispute letter (Markdown formatting).
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
        # Build a summary of the line items for reference
        line_item_summary = "\n".join(
            f"  - CPT {item.cpt_code}: {item.description}, ${item.total_charge:.2f}, "
            f"date {item.service_date}"
            for item in line_items[:20]  # Cap at 20 items to stay within token budget
        )

        prompt = (
            "You are a medical billing advocate helping a patient write a formal dispute letter "
            "to their healthcare provider. Write a professional, firm, and specific dispute letter "
            "based on the billing errors below.\n\n"
            "Instructions:\n"
            "- Address it to 'Billing Department' (the patient will add the provider name)\n"
            "- Include a placeholder [YOUR NAME] and [YOUR DATE OF BIRTH] for the patient to fill in\n"
            "- Reference each specific error with CPT codes and dates\n"
            "- Cite the total disputed amount\n"
            "- Request an itemized bill and a corrected statement within 30 days\n"
            "- Keep it under 400 words\n"
            "- Use formal letter format with today's date as [DATE]\n\n"
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
