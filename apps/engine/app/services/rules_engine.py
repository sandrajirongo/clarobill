"""Rules engine — detects billing errors using CMS reference data.

Each rule is a separate method that takes line items and returns BillingErrors.
Rules are run independently and combined — no rule depends on another's output.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal

from app.services.parser import ParsedLineItem

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DetectedError:
    """A billing error detected by a rule. Mirrors the BillingError TypeScript type."""

    code: str
    severity: str  # 'critical' | 'warning' | 'info'
    affected_indices: list[int]  # Indices into the line_items list
    description: str
    estimated_overcharge: Decimal
    medicare_benchmark_rate: Decimal | None


# Anesthesia outlier thresholds.
# Base units for legitimate anesthesia codes range from 3 (minor procedures) to
# 15 (complex cardiac surgery). 25 is a generous ceiling — anything above implies
# the provider is either using the wrong code or inflating the base unit count.
_MAX_PLAUSIBLE_BASE_UNITS = 25
# 80 total units ≈ 20 hours of anesthesia — physically impossible in a single session.
_MAX_PLAUSIBLE_TOTAL_UNITS = 80


class RulesEngine:
    """Runs all billing rules against a parsed bill."""

    def __init__(
        self,
        ncci_edit_pairs: dict[str, set[str]],
        medicare_rates: dict[str, Decimal],
        outlier_threshold: float = 2.0,
        non_payable_codes: dict[str, str] | None = None,
        anesthesia_cf: Decimal | None = None,
        anesthesia_base_units: dict[str, int] | None = None,
    ) -> None:
        """
        Args:
            ncci_edit_pairs:        Map of column_one_code → set of column_two_codes.
            medicare_rates:         Map of cpt_code → non_facility_rate.
            outlier_threshold:      Flag charge when it exceeds Medicare rate by this multiplier.
            non_payable_codes:      Map of cpt_code → proc_stat for non-payable codes found on
                                    the bill. Codes with proc_stat 'I' (inactive) or 'B' (bundled)
                                    are critical; 'N' (non-covered) is a warning.
            anesthesia_cf:          Locality-adjusted anesthesia conversion factor. When provided,
                                    anesthesia outlier detection is enabled.
            anesthesia_base_units:  Map of cpt_code → published base units from CMS tables.
                                    When provided, enables exact base unit validation instead of
                                    the generic plausibility ceiling.
        """
        self._ncci_pairs = ncci_edit_pairs
        self._medicare_rates = medicare_rates
        self._outlier_threshold = outlier_threshold
        self._non_payable_codes = non_payable_codes or {}
        self._anesthesia_cf = anesthesia_cf
        self._anesthesia_base_units = anesthesia_base_units or {}

    def run(self, line_items: list[ParsedLineItem]) -> list[DetectedError]:
        """Run all rules and return the combined list of detected errors.

        Args:
            line_items: Parsed line items from the bill.

        Returns:
            All detected errors across all rules. May be empty.
        """
        errors: list[DetectedError] = []
        errors.extend(self._detect_duplicates(line_items))
        errors.extend(self._detect_price_outliers(line_items))
        errors.extend(self._detect_ncci_unbundling(line_items))
        errors.extend(self._detect_non_payable_codes(line_items))
        errors.extend(self._detect_anesthesia_outliers(line_items))
        logger.info("Rules engine found %d errors in %d line items", len(errors), len(line_items))
        return errors

    def _detect_duplicates(self, line_items: list[ParsedLineItem]) -> list[DetectedError]:
        """Flag identical CPT code + service date combinations billed more than once.

        Duplicate billing is one of the most common medical billing errors and is
        explicitly prohibited by CMS. Each CPT code should appear once per service date
        unless the quantity field reflects the repetition.
        """
        seen: dict[tuple[str, str], int] = {}  # (cpt_code, service_date) → first index
        errors: list[DetectedError] = []

        for index, item in enumerate(line_items):
            key = (item.cpt_code, str(item.service_date))
            if key in seen:
                errors.append(DetectedError(
                    code="DUPLICATE_CHARGE",
                    severity="critical",
                    affected_indices=[seen[key], index],
                    description=(
                        f"CPT {item.cpt_code} appears to be billed twice on "
                        f"{item.service_date}. One charge of ${item.total_charge:.2f} "
                        f"may be a duplicate."
                    ),
                    estimated_overcharge=Decimal(str(item.total_charge)),
                    medicare_benchmark_rate=self._medicare_rates.get(item.cpt_code),
                ))
            else:
                seen[key] = index

        return errors

    def _detect_price_outliers(self, line_items: list[ParsedLineItem]) -> list[DetectedError]:
        """Flag charges that exceed the Medicare rate by the configured threshold.

        We compare against the Medicare non-facility rate as a benchmark.
        Charges at 2x+ the Medicare rate warrant review — they may indicate
        upcoding, billing for supplies bundled in the procedure, or simple error.
        """
        errors: list[DetectedError] = []

        for index, item in enumerate(line_items):
            medicare_rate = self._medicare_rates.get(item.cpt_code)
            if medicare_rate is None:
                # Unknown CPT code — flagged separately by a different rule
                continue

            charge = Decimal(str(item.total_charge))
            if medicare_rate > 0 and charge > medicare_rate * Decimal(str(self._outlier_threshold)):
                overcharge = charge - medicare_rate
                label = f" ({item.description})" if item.description else ""
                errors.append(DetectedError(
                    code="PRICE_OUTLIER",
                    severity="warning",
                    affected_indices=[index],
                    description=(
                        f"Your provider charged ${charge:.2f} for CPT {item.cpt_code}"
                        f"{label}. The Medicare benchmark rate is ${medicare_rate:.2f} "
                        f"— your charge is {charge / medicare_rate:.1f}x that amount. "
                        f"Consider requesting an itemized bill or asking your provider "
                        f"to justify the difference."
                    ),
                    estimated_overcharge=overcharge,
                    medicare_benchmark_rate=medicare_rate,
                ))

        return errors

    def _detect_ncci_unbundling(self, line_items: list[ParsedLineItem]) -> list[DetectedError]:
        """Detect NCCI (National Correct Coding Initiative) edit pair violations.

        CMS maintains a table of procedure code pairs where one code is "bundled"
        into another. Billing both separately is called unbundling and is considered
        improper billing. Modifier 59 (distinct procedure) can override some pairs.

        # Medicare allows modifier 59 to override NCCI edits when procedures are
        # performed on distinct anatomical sites or distinct patient encounters.
        """
        errors: list[DetectedError] = []
        cpt_to_indices: dict[str, list[int]] = {}

        for index, item in enumerate(line_items):
            cpt_to_indices.setdefault(item.cpt_code, []).append(index)

        for col1_code, component_codes in self._ncci_pairs.items():
            if col1_code not in cpt_to_indices:
                continue

            for col2_code in component_codes:
                if col2_code not in cpt_to_indices:
                    continue

                # Check if modifier 59 is present on the component code
                col2_items = [line_items[i] for i in cpt_to_indices[col2_code]]
                has_modifier_override = any(item.modifier == "59" for item in col2_items)
                if has_modifier_override:
                    continue

                all_affected = cpt_to_indices[col1_code] + cpt_to_indices[col2_code]
                overcharge = sum(
                    Decimal(str(line_items[i].total_charge)) for i in cpt_to_indices[col2_code]
                )
                errors.append(DetectedError(
                    code="NCCI_UNBUNDLING",
                    severity="critical",
                    affected_indices=all_affected,
                    description=(
                        f"CPT {col2_code} should be bundled into CPT {col1_code} per CMS NCCI "
                        f"edits. Billing both separately may be improper. "
                        f"Potential overcharge: ${overcharge:.2f}."
                    ),
                    estimated_overcharge=overcharge,
                    medicare_benchmark_rate=None,
                ))

        return errors

    def _detect_non_payable_codes(self, line_items: list[ParsedLineItem]) -> list[DetectedError]:
        """Flag CPT codes that CMS has marked as non-payable under the Physician Fee Schedule.

        proc_stat meanings relevant here:
          I = Inactive — code has been retired; Medicare will not pay it under any circumstances.
          B = Bundled  — payment is always included in another procedure; billing separately
                         constitutes improper unbundling even when no companion code is present.
          N = Non-covered — service is excluded from Medicare coverage; patient may still be
                            billed but should have received an Advance Beneficiary Notice (ABN).
        """
        errors: list[DetectedError] = []

        # severity and plain-English reason by proc_stat
        _stat_meta: dict[str, tuple[str, str]] = {
            "I": (
                "critical",
                "is an inactive code that Medicare no longer recognises. "
                "It is not payable and should not appear on your bill.",
            ),
            "B": (
                "critical",
                "is a bundled service whose payment is always included in another "
                "procedure. Billing it separately is considered improper unbundling.",
            ),
            "N": (
                "warning",
                "is a non-covered service under Medicare. If you were not given an "
                "Advance Beneficiary Notice (ABN) before the service, you may not be "
                "required to pay this charge.",
            ),
        }

        for index, item in enumerate(line_items):
            proc_stat = self._non_payable_codes.get(item.cpt_code)
            if proc_stat not in _stat_meta:
                continue

            severity, reason = _stat_meta[proc_stat]
            errors.append(DetectedError(
                code="NON_PAYABLE_CODE",
                severity=severity,
                affected_indices=[index],
                description=f"CPT {item.cpt_code} {reason}",
                estimated_overcharge=Decimal(str(item.total_charge)),
                medicare_benchmark_rate=None,
            ))

        return errors

    def _detect_anesthesia_outliers(self, line_items: list[ParsedLineItem]) -> list[DetectedError]:
        """Flag anesthesia charges that imply implausible base units or total units.

        Medicare anesthesia payment formula:
            payment = (base_units + time_units) × locality_CF
            time_units = anesthesia_minutes / 15

        Without per-code base unit tables we work backwards from the billed charge:
            implied_total_units = billed_charge / locality_CF
            implied_base_units  = implied_total_units - time_units

        Flags:
          - implied_base_units < 0     → charge is less than the documented time alone (impossible)
          - implied_base_units > 25    → exceeds the highest legitimate base unit count
          - implied_total_units > 80   → equivalent to ~20 hours; physically impossible
          - (no OCR time) total > 80   → same ceiling check without time decomposition
        """
        if self._anesthesia_cf is None or self._anesthesia_cf <= 0:
            return []

        errors: list[DetectedError] = []

        for index, item in enumerate(line_items):
            try:
                code_num = int(item.cpt_code)
            except ValueError:
                continue
            if not (100 <= code_num <= 1999):
                continue

            charge = Decimal(str(item.total_charge))
            if charge <= 0:
                continue

            implied_total = charge / self._anesthesia_cf
            published_base = self._anesthesia_base_units.get(item.cpt_code)

            if item.anesthesia_minutes is not None:
                time_units = Decimal(str(item.anesthesia_minutes)) / Decimal("15")
                implied_base = implied_total - time_units

                if implied_base < 0:
                    # Charge is less than the documented time alone — always flag regardless of base unit data
                    errors.append(DetectedError(
                        code="ANESTHESIA_OUTLIER",
                        severity="critical",
                        affected_indices=[index],
                        description=(
                            f"CPT {item.cpt_code}: the billed charge of ${charge:.2f} is less "
                            f"than the cost of the documented anesthesia time alone "
                            f"({item.anesthesia_minutes} min = {float(time_units):.1f} time units "
                            f"× ${self._anesthesia_cf:.4f} CF = "
                            f"${float(time_units * self._anesthesia_cf):.2f}). "
                            f"This may indicate a billing error or an incorrect conversion factor."
                        ),
                        estimated_overcharge=Decimal("0"),
                        medicare_benchmark_rate=None,
                    ))
                elif published_base is not None:
                    # Exact check: CMS publishes the base units for this code
                    # Allow up to 0.5 units of rounding — flag anything meaningfully above published value
                    if implied_base > Decimal(str(published_base)) + Decimal("0.5"):
                        overcharge = (implied_base - Decimal(str(published_base))) * self._anesthesia_cf
                        expected_charge = (Decimal(str(published_base)) + time_units) * self._anesthesia_cf
                        errors.append(DetectedError(
                            code="ANESTHESIA_OUTLIER",
                            severity="critical",
                            affected_indices=[index],
                            description=(
                                f"CPT {item.cpt_code}: the billed charge of ${charge:.2f} implies "
                                f"{float(implied_base):.1f} base units, but CMS publishes "
                                f"{published_base} base units for this procedure. "
                                f"With {item.anesthesia_minutes} minutes of documented time, "
                                f"the expected charge is ${float(expected_charge):.2f}. "
                                f"Potential overcharge: ${float(overcharge):.2f}."
                            ),
                            estimated_overcharge=overcharge,
                            medicare_benchmark_rate=None,
                        ))
                elif implied_base > _MAX_PLAUSIBLE_BASE_UNITS:
                    # No published base units for this code — fall back to heuristic ceiling
                    overcharge = (implied_base - Decimal(str(_MAX_PLAUSIBLE_BASE_UNITS))) * self._anesthesia_cf
                    errors.append(DetectedError(
                        code="ANESTHESIA_OUTLIER",
                        severity="critical",
                        affected_indices=[index],
                        description=(
                            f"CPT {item.cpt_code}: the billed charge of ${charge:.2f} implies "
                            f"{float(implied_base):.1f} base units after accounting for "
                            f"{item.anesthesia_minutes} minutes of documented time. "
                            f"The maximum plausible base unit count is {_MAX_PLAUSIBLE_BASE_UNITS}. "
                            f"Potential overcharge: ${float(overcharge):.2f}."
                        ),
                        estimated_overcharge=overcharge,
                        medicare_benchmark_rate=None,
                    ))
            else:
                # No OCR time — ceiling-only check (can't do exact base unit check without time)
                if implied_total > _MAX_PLAUSIBLE_TOTAL_UNITS:
                    overcharge = (implied_total - Decimal(str(_MAX_PLAUSIBLE_TOTAL_UNITS))) * self._anesthesia_cf
                    errors.append(DetectedError(
                        code="ANESTHESIA_OUTLIER",
                        severity="warning",
                        affected_indices=[index],
                        description=(
                            f"CPT {item.cpt_code}: the billed charge of ${charge:.2f} implies "
                            f"{float(implied_total):.1f} total anesthesia units at the "
                            f"${self._anesthesia_cf:.4f} locality rate. "
                            f"This exceeds {_MAX_PLAUSIBLE_TOTAL_UNITS} units (~20 hours) and "
                            f"warrants review. Potential overcharge: ${float(overcharge):.2f}."
                        ),
                        estimated_overcharge=overcharge,
                        medicare_benchmark_rate=None,
                    ))

        return errors
