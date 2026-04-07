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


class RulesEngine:
    """Runs all billing rules against a parsed bill."""

    def __init__(
        self,
        ncci_edit_pairs: dict[str, set[str]],
        medicare_rates: dict[str, Decimal],
        outlier_threshold: float = 2.0,
    ) -> None:
        """
        Args:
            ncci_edit_pairs: Map of column_one_code → set of column_two_codes.
                             Loaded from the ncci_edit_pairs table.
            medicare_rates:  Map of cpt_code → non_facility_rate.
                             Loaded from the medicare_fee_schedule table.
            outlier_threshold: A charge is flagged as an outlier when it exceeds
                               the Medicare rate by this multiplier (default: 2x).
        """
        self._ncci_pairs = ncci_edit_pairs
        self._medicare_rates = medicare_rates
        self._outlier_threshold = outlier_threshold

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
                errors.append(DetectedError(
                    code="PRICE_OUTLIER",
                    severity="warning",
                    affected_indices=[index],
                    description=(
                        f"CPT {item.cpt_code} was billed at ${charge:.2f}, which is "
                        f"{charge / medicare_rate:.1f}x the Medicare benchmark of "
                        f"${medicare_rate:.2f}. Consider requesting an itemized bill."
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
