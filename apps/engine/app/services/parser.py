"""Line item parser — converts raw OCR text into structured LineItem records.

Extracts CPT codes, charges, dates, and modifiers from unstructured bill text.
Supports both single-line formats (traditional provider bills) and multi-line
formats (insurance EOBs where the charge appears on a separate line from the
CPT code), as well as column-interleaved OCR output produced by Google Vision
when processing structured table PDFs.
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
# ISO 8601 format: YYYY-MM-DD — checked before the MM/DD pattern to avoid partial matches
_ISO_DATE_PATTERN = re.compile(r"\b(\d{4})[/-](\d{1,2})[/-](\d{1,2})\b")

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

# Lines matching this pattern are summary/totals rows — their dollar amounts must not
# be assigned to individual CPT codes during column-interleaved sequence matching.
_SUMMARY_LINE_PATTERN = re.compile(
    r"\b(total|subtotal|balance|payment|insurance|amount\s*due|co[- ]?pay|"
    r"deductible|adjustment|remittance|billed\s*to)\b",
    re.IGNORECASE,
)

# How many lines after the CPT code line to search for a charge amount
_LOOKAHEAD_LINES = 3

# Hospital name detection — keywords that identify a line as a hospital/facility name.
# Ordered roughly by specificity: "hospital" is almost always the name, "clinic" less so.
_HOSPITAL_KEYWORDS = re.compile(
    r"\b(hospital|medical center|medical group|health system|healthcare|health care|"
    r"cancer center|surgical center|surgery center|rehabilitation|rehab center|"
    r"urgent care|community health|children'?s|pediatric|memorial|clinic)\b",
    re.IGNORECASE,
)
# Patterns to strip from a candidate name line before returning it.
_NOISE_PATTERNS = [
    re.compile(r"\b\d{5}(?:-\d{4})?\b"),          # ZIP codes
    re.compile(r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b"),  # Phone numbers
    re.compile(r"\b(suite|ste|floor|fl|room|rm)\s*\d+\b", re.IGNORECASE),  # Suite/floor numbers
    re.compile(r"[,|]\s*$"),                        # Trailing commas or pipes
]

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

    Handles three OCR output layouts:
      1. Row-major (traditional): CPT + description + charge on one line.
      2. Multi-line EOB: CPT on one line, charge on the next 1-3 lines.
      3. Column-interleaved: Vision OCR returns a PDF table column-by-column —
         all CPT codes appear first, then descriptions, then charges. Proximity
         search fails here; a sequence-based fallback associates the nth CPT
         code with the nth unconsumed charge amount in document order.
    """

    def parse(self, raw_text: str, bill_date: date | None = None) -> list[ParsedLineItem]:
        """Parse OCR text into a list of structured line items.

        Args:
            raw_text: Full text from OCR extraction.
            bill_date: Fallback date if service dates can't be parsed.

        Returns:
            List of parsed line items in document order. Empty if no CPT codes found.
        """
        lines = raw_text.splitlines()
        fallback_date = bill_date or date.today()
        processed_line_indices: set[int] = set()

        # Accumulate as (line_idx, item) so we can sort into document order at the end,
        # regardless of whether items came from pass-1 proximity or pass-2 sequence matching.
        pending: list[tuple[int, ParsedLineItem]] = []
        # Lines whose dollar amounts were consumed by pass-1 proximity matching.
        consumed_amount_lines: set[int] = set()
        # CPT code lines that had no nearby charge — queued for pass-2 sequence matching.
        unmatched: list[tuple[int, str, str | None]] = []  # (line_idx, cpt_code, modifier)

        for i, line in enumerate(lines):
            if i in processed_line_indices:
                continue

            code_match = _PROCEDURE_CODE_PATTERN.search(line)
            if not code_match:
                continue

            cpt_code = code_match.group(1)

            # Exclude ZIP codes: "San Francisco, CA 94143" — the state abbreviation
            # immediately before a 5-digit number identifies it as a ZIP, not a CPT code.
            if re.search(r",\s*[A-Z]{2}\s+$", line[: code_match.start()]):
                continue

            # Extract optional modifier from the procedure code line
            modifier: str | None = None
            mod_match = _MODIFIER_PATTERN.search(line)
            if mod_match:
                modifier = mod_match.group(1)

            # Try to find a charge on the same line first, then look ahead
            charge, charge_line = self._find_charge_in_window(lines, i)
            if charge is None:
                # No charge found within proximity — save for sequence-based fallback.
                # This is the normal outcome for column-interleaved table OCR output.
                logger.debug("No charge found for code %s at line %d — queuing for fallback", cpt_code, i)
                unmatched.append((i, cpt_code, modifier))
                processed_line_indices.add(i)
                continue

            consumed_amount_lines.add(charge_line)

            service_date = self._find_date_in_window(lines, i) or fallback_date
            description = self._extract_description(line, code_match.end())

            anesthesia_minutes: int | None = None
            if _is_anesthesia_code(cpt_code):
                anesthesia_minutes = self._find_anesthesia_minutes(lines, i)

            quantity = 1
            unit_charge = charge
            if cpt_code in _AMBULANCE_MILEAGE_CODES:
                miles = self._find_mileage_quantity(lines, i)
                if miles is not None and miles > 1:
                    quantity = miles
                    unit_charge = round(charge / miles, 2)

            processed_line_indices.add(i)
            pending.append((i, ParsedLineItem(
                cpt_code=cpt_code,
                description=description,
                service_date=service_date,
                quantity=quantity,
                unit_charge=unit_charge,
                total_charge=charge,
                modifier=modifier,
                diagnosis_pointers=[],
                anesthesia_minutes=anesthesia_minutes,
            )))

        # Pass 2: sequence-based matching for column-interleaved codes
        if unmatched:
            fallback_items = self._resolve_column_interleaved(
                lines, unmatched, consumed_amount_lines, fallback_date
            )
            pending.extend(fallback_items)

        # Restore document order — pass-1 row-major items at the bottom of the bill
        # (e.g. the last two row-major items in a hybrid bill) would otherwise appear
        # before the column-interleaved items that physically precede them on the page.
        pending.sort(key=lambda x: x[0])
        line_items = [item for _, item in pending]

        logger.info("Parser extracted %d line items from %d lines", len(line_items), len(lines))
        return line_items

    def _find_charge_in_window(self, lines: list[str], start: int) -> tuple[float, int] | tuple[None, None]:
        """Search for a dollar amount on the CPT line and up to LOOKAHEAD_LINES below.

        Takes the LAST match on the line — on bills with unit-rate + total-charge columns
        (the most common real-world format), the rightmost dollar amount is always the
        total charge. Using .search() (first match) would capture the unit rate instead.

        Returns:
            (charge_value, line_index) when found, (None, None) when not found.
        """
        for j in range(start, min(start + _LOOKAHEAD_LINES + 1, len(lines))):
            matches = _AMOUNT_PATTERN.findall(lines[j])
            if matches:
                try:
                    return float(matches[-1].replace(",", "")), j
                except ValueError:
                    continue
        return None, None

    def _resolve_column_interleaved(
        self,
        lines: list[str],
        unmatched: list[tuple[int, str, str | None]],
        consumed_lines: set[int],
        fallback_date: date,
    ) -> list[tuple[int, ParsedLineItem]]:
        """Associate unmatched CPT codes with charges via document-order sequence matching.

        Google Vision OCR processes structured table PDFs column-by-column rather than
        row-by-row. All CPT codes appear in a block, followed by descriptions, followed
        by charges — so charges are 8+ lines from their codes and proximity search misses
        them entirely. This method collects all unconsumed, non-summary dollar amounts
        in document order and maps the nth amount to the nth unmatched CPT code.

        The search for available charges stops at the first summary/total line that
        appears after the last unmatched CPT code. This prevents footer amounts (the
        standalone "$9,579.00" line under "TOTAL CHARGES" in a payment summary section)
        from being picked up and assigned to individual codes.
        """
        # Stop collecting charges at the first summary line that follows the last CPT code.
        # "TOTAL CHARGES\n$9,579.00" — the $9,579 line appears on its own with no keyword,
        # so line-level filtering alone misses it. The boundary stops collection before it.
        last_unmatched_line = unmatched[-1][0]
        upper_bound = len(lines)
        for j in range(last_unmatched_line + 1, len(lines)):
            # Require a dollar amount on the same line as the summary keyword so that
            # column headers like "TOTAL CHARGES" (no amount) don't set the boundary
            # before the actual charge values that follow them in column-interleaved output.
            if _SUMMARY_LINE_PATTERN.search(lines[j]) and _AMOUNT_PATTERN.search(lines[j]):
                upper_bound = j
                break

        # One charge per line (last match) from non-consumed, non-summary lines,
        # up to the boundary established above.
        available: list[tuple[int, float]] = []
        for j, line in enumerate(lines):
            if j >= upper_bound:
                break
            if j in consumed_lines:
                continue
            if _SUMMARY_LINE_PATTERN.search(line):
                continue
            matches = _AMOUNT_PATTERN.findall(line)
            if not matches:
                continue
            try:
                available.append((j, float(matches[-1].replace(",", ""))))
            except ValueError:
                pass

        if len(available) < len(unmatched):
            logger.warning(
                "Column-interleaved fallback: %d unmatched codes but only %d available charges "
                "— %d code(s) will be dropped",
                len(unmatched), len(available), len(unmatched) - len(available),
            )

        result: list[tuple[int, ParsedLineItem]] = []
        for idx, (line_idx, cpt_code, modifier) in enumerate(unmatched):
            if idx >= len(available):
                break

            _, charge = available[idx]
            line = lines[line_idx]
            code_match = _PROCEDURE_CODE_PATTERN.search(line)

            service_date = self._find_date_in_window(lines, line_idx) or fallback_date
            description = self._extract_description(
                line, code_match.end() if code_match else len(line)
            )

            anesthesia_minutes: int | None = None
            if _is_anesthesia_code(cpt_code):
                anesthesia_minutes = self._find_anesthesia_minutes(lines, line_idx)

            quantity = 1
            unit_charge = charge
            if cpt_code in _AMBULANCE_MILEAGE_CODES:
                miles = self._find_mileage_quantity(lines, line_idx)
                if miles is not None and miles > 1:
                    quantity = miles
                    unit_charge = round(charge / miles, 2)

            result.append((line_idx, ParsedLineItem(
                cpt_code=cpt_code,
                description=description,
                service_date=service_date,
                quantity=quantity,
                unit_charge=unit_charge,
                total_charge=charge,
                modifier=modifier,
                diagnosis_pointers=[],
                anesthesia_minutes=anesthesia_minutes,
            )))

        return result

    def _find_date_in_window(self, lines: list[str], start: int) -> date | None:
        """Search for a service date near the CPT code line.

        Two-phase search:
        1. ±LOOKAHEAD_LINES around the current line — covers inline dates and dates
           on the immediately adjacent line.
        2. Global backwards scan through all preceding lines — covers section-header
           format where a single date appears above a block of multiple line items.
           Without this, only the first code under a date header gets the correct date;
           all subsequent codes in the block fall back to today, breaking duplicate
           detection and rate_date accuracy for all reference data loaders.
        """
        for j in range(max(0, start - _LOOKAHEAD_LINES), min(start + _LOOKAHEAD_LINES + 1, len(lines))):
            parsed = self._extract_date(lines[j])
            if parsed is not None:
                return parsed
        # Phase 2: scan backwards from just before the phase-1 window to find a section-header date.
        # Start at max(0, start - LOOKAHEAD_LINES) - 1 so we don't re-scan lines phase 1 covered,
        # and never go negative (negative indices would wrap to the end of the list).
        phase2_start = max(0, start - _LOOKAHEAD_LINES) - 1
        for j in range(phase2_start, -1, -1):
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

    def extract_hospital_name(self, raw_text: str) -> str | None:
        """Extract the hospital or facility name from the top of the OCR text.

        Scans the first 20 lines for the line most likely to be the facility
        name — one that contains a hospital-identifying keyword (e.g. "hospital",
        "medical center", "health system"). Returns the first match after
        stripping ZIP codes, phone numbers, and other noise.

        Returns None when no credible facility name is found, which causes the
        hospital charge lookup to skip the name-based fallback rather than
        querying with a bad search term.

        Args:
            raw_text: Full text from OCR extraction.

        Returns:
            Cleaned facility name string, or None.
        """
        lines = raw_text.splitlines()
        for line in lines[:20]:
            if not _HOSPITAL_KEYWORDS.search(line):
                continue
            name = line.strip()
            for pattern in _NOISE_PATTERNS:
                name = pattern.sub("", name).strip()
            if len(name) >= 5:
                return name
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
        """Extract the first date found in a line, or None.

        Tries ISO 8601 (YYYY-MM-DD) first — OCR fixture text and some EMR exports
        use this format, and the MM/DD pattern cannot match it (year is 4 digits).
        Falls back to MM/DD/YYYY (most US medical bills).
        """
        iso = _ISO_DATE_PATTERN.search(line)
        if iso:
            try:
                year, month, day = int(iso.group(1)), int(iso.group(2)), int(iso.group(3))
                return date(year, month, day)
            except ValueError:
                pass

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
