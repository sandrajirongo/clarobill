"""Line item parser — converts raw OCR text into structured LineItem records.

Extracts CPT codes, charges, dates, and modifiers from unstructured bill text.
"""

import logging
import re
from dataclasses import dataclass
from datetime import date

logger = logging.getLogger(__name__)

# CPT codes are 5 digits, optionally followed by a modifier (2 alphanumeric chars)
_CPT_PATTERN = re.compile(r"\b(\d{5})\b(?:\s+([A-Z0-9]{2}))?\s+(.+?)\s+\$?([\d,]+\.?\d{0,2})")
_DATE_PATTERN = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")


@dataclass(frozen=True)
class ParsedLineItem:
    """Structured line item extracted from OCR text. Immutable by design."""

    cpt_code: str
    description: str
    service_date: date
    quantity: int
    unit_charge: float
    total_charge: float
    modifier: str | None
    diagnosis_pointers: list[str]


class BillParser:
    """Parses raw OCR text into structured line items."""

    def parse(self, raw_text: str, bill_date: date | None = None) -> list[ParsedLineItem]:
        """Parse OCR text into a list of structured line items.

        Args:
            raw_text: Full text from OCR extraction.
            bill_date: Fallback date if service dates can't be parsed.

        Returns:
            List of parsed line items. Empty if no CPT codes found.
        """
        lines = raw_text.splitlines()
        line_items: list[ParsedLineItem] = []
        fallback_date = bill_date or date.today()

        for line in lines:
            parsed = self._parse_line(line, fallback_date)
            if parsed is not None:
                line_items.append(parsed)

        logger.info("Parser extracted %d line items from %d text lines", len(line_items), len(lines))
        return line_items

    def _parse_line(self, line: str, fallback_date: date) -> ParsedLineItem | None:
        """Attempt to extract a line item from a single text line.

        Returns None if the line doesn't contain a CPT code pattern.
        """
        match = _CPT_PATTERN.search(line)
        if not match:
            return None

        cpt_code = match.group(1)
        modifier = match.group(2)  # May be None
        description = match.group(3).strip()
        charge_str = match.group(4).replace(",", "")

        try:
            charge = float(charge_str)
        except ValueError:
            logger.warning("Could not parse charge '%s' for CPT %s", charge_str, cpt_code)
            return None

        # Try to find a date in the same line; fall back to the bill date
        service_date = self._extract_date(line) or fallback_date

        return ParsedLineItem(
            cpt_code=cpt_code,
            description=description,
            service_date=service_date,
            quantity=1,
            unit_charge=charge,
            total_charge=charge,
            modifier=modifier,
            diagnosis_pointers=[],
        )

    @staticmethod
    def _extract_date(line: str) -> date | None:
        """Extract the first date found in a line, or None."""
        match = _DATE_PATTERN.search(line)
        if not match:
            return None
        try:
            month, day, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
            if year < 100:
                year += 2000
            return date(year, month, day)
        except ValueError:
            return None
