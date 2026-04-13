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

# Procedure code: 5-digit CPT codes or HCPCS Level II codes (letter + 4 digits, e.g. A0425)
_PROCEDURE_CODE_PATTERN = re.compile(r"\b(\d{5}|[A-Z]\d{4})\b")
# Optional modifier: 2-char alphanumeric code immediately after the procedure code
_MODIFIER_PATTERN = re.compile(r"\b(?:\d{5}|[A-Z]\d{4})\s+([A-Z0-9]{2})\b")
# Mileage quantity — "12 miles", "12.0 mi", "8 MI" — searched near ambulance mileage codes
_MILEAGE_PATTERN = re.compile(r"\b(\d{1,4}(?:\.\d)?)\s*(?:miles?|mi)\b", re.IGNORECASE)
# Dollar amount: requires exactly 2 decimal places to avoid matching date fragments
# (e.g. 11/14/25 would only match 11 without the decimal requirement)
_AMOUNT_PATTERN = re.compile(r"\$?([\d,]+\.\d{2})\b")
_DATE_PATTERN = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")

# Anesthesia time patterns — searched near anesthesia CPT codes (00100–01999)
# "45 min" / "45 minutes" / "120 MIN"
_ANES_MINUTES_PATTERN = re.compile(r"\b(\d{1,3})\s*min(?:utes?)?\b", re.IGNORECASE)
# Duration in H:MM format where hours <= 6 (distinguishes "1:30" duration from "08:15" clock time)
_ANES_DURATION_HM_PATTERN = re.compile(r"\b([0-6]):([0-5]\d)\b")
# Start/end time pair — "Start: 08:15  End: 09:00" or "IN: 08:15  OUT: 09:30"
_ANES_START_END_PATTERN = re.compile(
    r"(?:start|begin|in|incision)[:\s]+(\d{1,2}):(\d{2})"
    r".{0,40}"
    r"(?:end|stop|out|close)[:\s]+(\d{1,2}):(\d{2})",
    re.IGNORECASE,
)

# How many lines after the CPT code line to search for a charge amount
_LOOKAHEAD_LINES = 3

# NPI patterns — used by extract_npi(), separate from the line-item parse flow.
# Primary: explicit "NPI:" / "NPI #" label immediately preceding the 10-digit number.
_NPI_LABEL_PATTERN = re.compile(r"\bNPI[:\s#]+(\d{10})\b", re.IGNORECASE)
# Fallback: 10-digit number within 60 characters of a provider-identifying keyword.
# Covers formats like "Billing Provider  1234567893" where the label is absent.
_NPI_CONTEXT_PATTERN = re.compile(
    r"(?:billing|provider|facility|physician)\b.{0,60}\b(\d{10})\b",
    re.IGNORECASE,
)


def _validate_npi_luhn(npi: str) -> bool:
    """Validate a 10-digit NPI using the CMS Luhn check.

    CMS prepends "80840" to the 10-digit NPI to form a 15-digit string,
    then applies the standard Luhn algorithm. A checksum divisible by 10
    indicates a valid NPI.

    Known valid NPI for testing: 1234567893 (checksum = 70).
    """
    digits = "80840" + npi
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def _is_anesthesia_code(cpt_code: str) -> bool:
    """Return True for CPT codes in the anesthesia range 00100–01999."""
    try:
        return 100 <= int(cpt_code) <= 1999
    except ValueError:
        return False


# Ambulance HCPCS codes for which mileage quantity should be extracted.
# A0425 = ground mileage; A0435 = fixed-wing air mileage; A0436 = rotary-wing air mileage.
_AMBULANCE_MILEAGE_CODES: frozenset[str] = frozenset({"A0425", "A0435", "A0436"})


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
    # Anesthesia time in minutes — populated only for codes in the 00100–01999 range.
    # None means time was not found in the OCR text, not that the procedure had no time.
    anesthesia_minutes: int | None = None


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

            code_match = _PROCEDURE_CODE_PATTERN.search(line)
            if not code_match:
                continue

            cpt_code = code_match.group(1)

            # Extract optional modifier from the procedure code line
            modifier: str | None = None
            mod_match = _MODIFIER_PATTERN.search(line)
            if mod_match:
                modifier = mod_match.group(1)

            # Try to find a charge on the same line first, then look ahead
            charge = self._find_charge_in_window(lines, i)
            if charge is None:
                logger.debug("No charge found for code %s at line %d — skipping", cpt_code, i)
                continue

            # Extract service date from the code line or the surrounding window
            service_date = self._find_date_in_window(lines, i) or fallback_date

            # Build description from the code line (strip code, modifier,
            # amounts, and date patterns so we're left with readable text)
            description = self._extract_description(line, code_match.end())

            # Extract anesthesia time for codes in the 00100–01999 range
            anesthesia_minutes: int | None = None
            if _is_anesthesia_code(cpt_code):
                anesthesia_minutes = self._find_anesthesia_minutes(lines, i)

            # Extract mileage for ambulance per-mile codes.
            # Sets quantity to the number of miles and unit_charge to the per-mile rate,
            # enabling the rules engine to compare unit_charge directly against the AFS
            # per-mile benchmark rather than the total transport charge.
            quantity = 1
            unit_charge = charge
            if cpt_code in _AMBULANCE_MILEAGE_CODES:
                miles = self._find_mileage_quantity(lines, i)
                if miles is not None and miles > 1:
                    quantity = miles
                    unit_charge = round(charge / miles, 2)

            processed_line_indices.add(i)
            line_items.append(ParsedLineItem(
                cpt_code=cpt_code,
                description=description,
                service_date=service_date,
                quantity=quantity,
                unit_charge=unit_charge,
                total_charge=charge,
                modifier=modifier,
                diagnosis_pointers=[],
                anesthesia_minutes=anesthesia_minutes,
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

    def _find_anesthesia_minutes(self, lines: list[str], start: int) -> int | None:
        """Extract anesthesia duration in minutes from the text around an anesthesia CPT code.

        Tries three formats in order of reliability:
          1. Start/end clock times  — "Start: 08:15  End: 09:45" → 90 min
          2. Explicit minutes       — "45 min" / "120 minutes"
          3. H:MM duration          — "1:30" → 90 min (only H <= 6 to avoid clock times)

        Searches the CPT line and up to LOOKAHEAD_LINES below it.
        """
        window = "\n".join(lines[start : min(start + _LOOKAHEAD_LINES + 1, len(lines))])

        # 1. Start/end clock pair — most reliable when present
        se_match = _ANES_START_END_PATTERN.search(window)
        if se_match:
            start_h, start_m, end_h, end_m = (int(x) for x in se_match.groups())
            total_start = start_h * 60 + start_m
            total_end = end_h * 60 + end_m
            duration = total_end - total_start
            if duration > 0:
                return duration

        # 2. Explicit minute value
        min_match = _ANES_MINUTES_PATTERN.search(window)
        if min_match:
            minutes = int(min_match.group(1))
            if 1 <= minutes <= 600:  # 1 min – 10 hours: sane range
                return minutes

        # 3. H:MM duration format (hours capped at 6 to avoid clock-time false positives)
        hm_match = _ANES_DURATION_HM_PATTERN.search(window)
        if hm_match:
            hours, mins = int(hm_match.group(1)), int(hm_match.group(2))
            total = hours * 60 + mins
            if total > 0:
                return total

        return None

    def _find_mileage_quantity(self, lines: list[str], start: int) -> int | None:
        """Extract statute miles from the text around an ambulance mileage code.

        Matches patterns like "12 miles", "12.0 mi", "8 MI". Rounds fractional
        values to the nearest whole mile. Returns None when no mileage is found,
        which causes the caller to leave quantity=1 and use total_charge for
        the outlier comparison instead of unit_charge.
        """
        window = "\n".join(lines[start : min(start + _LOOKAHEAD_LINES + 1, len(lines))])
        match = _MILEAGE_PATTERN.search(window)
        if not match:
            return None
        miles = round(float(match.group(1)))
        # Sanity bounds: 1–999 statute miles covers all realistic ambulance transports
        if 1 <= miles <= 999:
            return miles
        return None

    def extract_npi(self, raw_text: str) -> str | None:
        """Extract and validate the billing provider NPI from OCR text.

        Tries two strategies in order:
          1. Explicit label  — "NPI: 1234567893", "NPI# 1234567893"
          2. Context keyword — 10-digit number within 60 chars of "billing",
             "provider", "facility", or "physician"

        Both require the candidate to pass the CMS Luhn check before returning.
        This filters out phone numbers and other 10-digit OCR noise.

        Args:
            raw_text: Full text from OCR extraction.

        Returns:
            First Luhn-valid 10-digit NPI found, or None.
        """
        for match in _NPI_LABEL_PATTERN.finditer(raw_text):
            candidate = match.group(1)
            if _validate_npi_luhn(candidate):
                return candidate

        for match in _NPI_CONTEXT_PATTERN.finditer(raw_text):
            candidate = match.group(1)
            if _validate_npi_luhn(candidate):
                return candidate

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
