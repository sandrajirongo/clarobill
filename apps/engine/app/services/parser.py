"""Line item parser — converts raw OCR text into structured LineItem records.

Extracts CPT codes, charges, dates, and modifiers from unstructured bill text.
Supports both single-line formats (traditional provider bills) and multi-line
formats (insurance EOBs where the charge appears on a separate line from the
CPT code).
"""

import logging
import re
from dataclasses import dataclass
from datetime import date

logger = logging.getLogger(__name__)

# CPT code: exactly 5 digits at a word boundary
_CPT_CODE_PATTERN = re.compile(r"\b(\d{5})\b")
# Optional modifier: 2-char alphanumeric code immediately after CPT code
_MODIFIER_PATTERN = re.compile(r"\b\d{5}\s+([A-Z0-9]{2})\b")
# Dollar amount: requires exactly 2 decimal places to avoid matching date fragments
# (e.g. 11/14/25 would only match 11 without the decimal requirement)
_AMOUNT_PATTERN = re.compile(r"\$?([\d,]+\.\d{2})\b")
_DATE_PATTERN = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")

# How many lines after the CPT code line to search for a charge amount
_LOOKAHEAD_LINES = 3


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
    """Parses raw OCR text into structured line items.

    Handles both traditional provider bill format (CPT + description + charge
    on one line) and insurance EOB format (CPT on one line, charge on the
    next 1-3 lines).
    """

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
        # Track processed line indices to avoid duplicate line items when the
        # same CPT code appears multiple times (e.g. in EOB totals rows)
        processed_line_indices: set[int] = set()

        for i, line in enumerate(lines):
            if i in processed_line_indices:
                continue

            cpt_match = _CPT_CODE_PATTERN.search(line)
            if not cpt_match:
                continue

            cpt_code = cpt_match.group(1)

            # Extract optional modifier from the CPT code line
            modifier: str | None = None
            mod_match = _MODIFIER_PATTERN.search(line)
            if mod_match:
                modifier = mod_match.group(1)

            # Try to find a charge on the same line first, then look ahead
            charge = self._find_charge_in_window(lines, i)
            if charge is None:
                logger.debug("No charge found for CPT %s at line %d — skipping", cpt_code, i)
                continue

            # Extract service date from CPT line or the surrounding window
            service_date = self._find_date_in_window(lines, i) or fallback_date

            # Build description from the CPT code line (strip CPT code, modifier,
            # amounts, and date patterns so we're left with readable text)
            description = self._extract_description(line, cpt_match.end())

            processed_line_indices.add(i)
            line_items.append(ParsedLineItem(
                cpt_code=cpt_code,
                description=description,
                service_date=service_date,
                quantity=1,
                unit_charge=charge,
                total_charge=charge,
                modifier=modifier,
                diagnosis_pointers=[],
            ))

        logger.info("Parser extracted %d line items from %d lines", len(line_items), len(lines))
        return line_items

    def _find_charge_in_window(self, lines: list[str], start: int) -> float | None:
        """Search for a dollar amount on the CPT line and up to LOOKAHEAD_LINES below.

        Requires exactly 2 decimal places to avoid matching date fragments.
        """
        for j in range(start, min(start + _LOOKAHEAD_LINES + 1, len(lines))):
            amount_match = _AMOUNT_PATTERN.search(lines[j])
            if amount_match:
                try:
                    return float(amount_match.group(1).replace(",", ""))
                except ValueError:
                    continue
        return None

    def _find_date_in_window(self, lines: list[str], start: int) -> date | None:
        """Search for a date in the CPT line and up to LOOKAHEAD_LINES around it."""
        for j in range(max(0, start - 1), min(start + _LOOKAHEAD_LINES + 1, len(lines))):
            parsed = self._extract_date(lines[j])
            if parsed is not None:
                return parsed
        return None

    @staticmethod
    def _extract_description(line: str, cpt_end: int) -> str:
        """Extract readable description text from the portion of the line after the CPT code.

        Strips out dates, dollar amounts, and stray punctuation so the result
        is a clean human-readable label.
        """
        text = line[cpt_end:]
        # Remove dates
        text = _DATE_PATTERN.sub("", text)
        # Remove dollar amounts
        text = _AMOUNT_PATTERN.sub("", text)
        # Remove parenthesised remark numbers like (1) (2)
        text = re.sub(r"\(\d+\)", "", text)
        # Remove the word "on" which often precedes a date in EOBs
        text = re.sub(r"\bon\b", "", text, flags=re.IGNORECASE)
        text = text.strip(" \t-–/")
        return text if text else f"CPT {line.split()[0] if line.split() else 'code'}"

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
