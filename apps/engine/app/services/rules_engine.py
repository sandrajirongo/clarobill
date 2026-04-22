"""Rules engine — detects billing errors using CMS reference data.

Each rule is a separate method that takes line items and returns BillingErrors.
Rules are run independently and combined — no rule depends on another's output.
"""

import logging
from dataclasses import dataclass
from datetime import date
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


# Price outlier thresholds by plan type.
# Medicare/Medicaid: the Medicare rate IS the payment ceiling — flag anything above 1.05× (rounding tolerance).
# Commercial: negotiated rates run 1.2–1.6× Medicare; flag above 1.8× to avoid false positives on normal bills.
# TRICARE/self_pay: tracks Medicare closely; flag above 1.2× to catch egregious overcharges.
_PRICE_OUTLIER_THRESHOLDS: dict[str, float] = {
    "medicare":   1.05,
    "medicaid":   1.05,
    "commercial": 1.80,
    "tricare":    1.20,
    "self_pay":   1.20,
}
_PRICE_OUTLIER_DEFAULT_THRESHOLD = 1.80

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
        plan_type: str | None = None,
        medicare_outlier_threshold: float = 1.8,
        exact_price_threshold: float = 1.1,
        non_payable_codes: dict[str, str] | None = None,
        anesthesia_cf: Decimal | None = None,
        anesthesia_base_units: dict[str, int] | None = None,
        opps_rates: dict[str, Decimal] | None = None,
        ambulance_rates: dict[str, Decimal] | None = None,
        hcpcs_termination_dates: dict[str, date] | None = None,
        hospital_charges: dict[str, Decimal] | None = None,
        negotiated_charges: dict[str, Decimal] | None = None,
        mue_limits: dict[str, tuple[int, int]] | None = None,
    ) -> None:
        """
        Args:
            ncci_edit_pairs:            Map of column_one_code → set of column_two_codes.
            medicare_rates:             Map of cpt_code → non_facility_rate.
            medicare_outlier_threshold: Flag charge when it exceeds the Medicare benchmark by this
                                        multiplier. Default 1.8 = flag anything more than 80% over
                                        Medicare. Used for PRICE_OUTLIER, FACILITY_CHARGE_OUTLIER,
                                        and AMBULANCE_CHARGE_OUTLIER. Set higher than exact_price_
                                        threshold because Medicare rates are a floor signal, not a
                                        maximum — commercial payers routinely reimburse at 1.2–2.5×
                                        Medicare, so a low threshold generates false positives on
                                        every normal commercial bill. 1.8× exceeds the maximum
                                        expected commercial markup (~1.5×) while still catching
                                        egregious overcharges.
            exact_price_threshold:      Flag charge when it exceeds an exact agreed/published price
                                        by this multiplier. Default 1.1 = flag anything more than
                                        10% over the benchmark. Used for HOSPITAL_CHARGE_OUTLIER
                                        (hospital's own chargemaster) and NEGOTIATED_RATE_EXCEEDED
                                        (insurer-specific contracted rate). These benchmarks are
                                        the actual agreed or published price, so there is no
                                        insurance-type ambiguity — 10% tolerance handles minor
                                        rounding and unit-charge-vs-total-charge discrepancies.
            non_payable_codes:          Map of cpt_code → proc_stat for non-payable codes found on
                                        the bill. Codes with proc_stat 'I' (inactive) or 'B' (bundled)
                                        are critical; 'N' (non-covered) is a warning.
            anesthesia_cf:              Locality-adjusted anesthesia conversion factor. When provided,
                                        anesthesia outlier detection is enabled.
            anesthesia_base_units:      Map of cpt_code → published base units from CMS tables.
                                        When provided, enables exact base unit validation instead of
                                        the generic plausibility ceiling.
            opps_rates:                 Map of hcpc → OPPS facility payment cap for the resolved
                                        locality. When provided, enables facility charge outlier
                                        detection for hospital outpatient bills.
            ambulance_rates:            Map of hcpc → applicable Medicare ambulance rate (urban,
                                        rural, or super-rural) for the patient's ZIP code. When
                                        provided, enables ambulance charge outlier detection.
            hcpcs_termination_dates:    Map of hcpc → last valid date from cms_hcpcs_codes.
                                        When provided, enables detection of terminated HCPCS
                                        Level II codes billed after their termination date.
            hospital_charges:           Map of cpt_code → hospital's own published gross charge
                                        from their MRF price transparency file. When provided,
                                        enables hospital charge outlier detection.
            negotiated_charges:         Map of cpt_code → the specific negotiated rate contracted
                                        between the hospital and the patient's insurer/plan, from
                                        the MRF price transparency file. When provided, enables
                                        the negotiated rate exceeded detection — the strongest
                                        price benchmark available.
            mue_limits:                 Map of hcpcs_code → (mue_value, adjudication_indicator).
                                        mue_value: max allowed units per line (or per claim/date for
                                        indicator 1). adjudication_indicator: 0=unknown, 1=claim edit,
                                        2=DOS policy (hard denial), 3=DOS clinical (documentable).
                                        When provided, enables MUE violation detection.
        """
        self._ncci_pairs = ncci_edit_pairs
        self._medicare_rates = medicare_rates
        self._plan_type = plan_type
        self._medicare_outlier_threshold = medicare_outlier_threshold
        self._exact_price_threshold = exact_price_threshold
        self._non_payable_codes = non_payable_codes or {}
        self._anesthesia_cf = anesthesia_cf
        self._anesthesia_base_units = anesthesia_base_units or {}
        self._opps_rates = opps_rates or {}
        self._ambulance_rates = ambulance_rates or {}
        self._hcpcs_termination_dates = hcpcs_termination_dates or {}
        self._hospital_charges = hospital_charges or {}
        self._negotiated_charges = negotiated_charges or {}
        self._mue_limits = mue_limits or {}

    def run(self, line_items: list[ParsedLineItem]) -> list[DetectedError]:
        """Run all rules and return the combined list of detected errors.

        Args:
            line_items: Parsed line items from the bill.

        Returns:
            All detected errors across all rules. May be empty.
        """
        errors: list[DetectedError] = []

        duplicate_errors = self._detect_duplicates(line_items)
        errors.extend(duplicate_errors)

        # The second index in each DUPLICATE_CHARGE error is the line item being disputed
        # entirely. Flagging that same item as additionally overpriced (PRICE_OUTLIER,
        # FACILITY_CHARGE_OUTLIER, etc.) double-counts the charge and inflates potential
        # savings beyond what is achievable. Suppress all other rule errors whose affected
        # indices are exclusively duplicate instances.
        duplicate_indices: set[int] = {
            e.affected_indices[1]
            for e in duplicate_errors
            if len(e.affected_indices) >= 2
        }

        def _without_duplicates(rule_errors: list[DetectedError]) -> list[DetectedError]:
            if not duplicate_indices:
                return rule_errors
            return [
                e for e in rule_errors
                if not all(i in duplicate_indices for i in e.affected_indices)
            ]

        errors.extend(_without_duplicates(self._detect_price_outliers(line_items)))
        errors.extend(self._detect_ncci_unbundling(line_items))
        errors.extend(_without_duplicates(self._detect_non_payable_codes(line_items)))
        errors.extend(_without_duplicates(self._detect_anesthesia_outliers(line_items)))
        errors.extend(_without_duplicates(self._detect_facility_outliers(line_items)))
        errors.extend(_without_duplicates(self._detect_ambulance_outliers(line_items)))
        errors.extend(_without_duplicates(self._detect_terminated_codes(line_items)))
        errors.extend(_without_duplicates(self._detect_hospital_charge_outliers(line_items)))
        errors.extend(_without_duplicates(self._detect_negotiated_rate_exceeded(line_items)))
        errors.extend(_without_duplicates(self._detect_mue_violations(line_items)))
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
        """Flag charges that exceed the Medicare benchmark rate by a plan-type-aware threshold.

        Threshold varies by insurance type because the Medicare rate means different things:
          - Medicare/Medicaid patients: the Medicare rate is the payment ceiling (1.05× tolerance)
          - Commercial: negotiated rates are 1.2–1.6× Medicare; flag above 1.8×
          - TRICARE/self_pay: tracks Medicare closely; flag above 1.2×
        """
        threshold = Decimal(str(
            _PRICE_OUTLIER_THRESHOLDS.get(self._plan_type or "", _PRICE_OUTLIER_DEFAULT_THRESHOLD)
        ))
        errors: list[DetectedError] = []

        for index, item in enumerate(line_items):
            medicare_rate = self._medicare_rates.get(item.cpt_code)
            if medicare_rate is None:
                # Unknown CPT code — flagged separately by a different rule
                continue

            charge = Decimal(str(item.total_charge))
            if medicare_rate > 0 and charge > medicare_rate * threshold:
                overcharge = charge - medicare_rate
                label = f" ({item.description})" if item.description else ""
                if self._plan_type in ("medicare", "medicaid"):
                    benchmark_context = (
                        f"The Medicare rate of ${medicare_rate:.2f} is the maximum reimbursable "
                        f"amount for this service — your charge of ${charge:.2f} exceeds it."
                    )
                else:
                    benchmark_context = (
                        f"The Medicare benchmark rate is ${medicare_rate:.2f} "
                        f"— your charge is {charge / medicare_rate:.1f}× that amount."
                    )
                errors.append(DetectedError(
                    code="PRICE_OUTLIER",
                    severity="warning",
                    affected_indices=[index],
                    description=(
                        f"Your provider charged ${charge:.2f} for CPT {item.cpt_code}"
                        f"{label}. {benchmark_context} "
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
                    (Decimal(str(line_items[i].total_charge)) for i in cpt_to_indices[col2_code]),
                    Decimal("0"),
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
            # Level II HCPCS codes start with a letter; CPT codes are all digits.
            code_label = "CPT" if item.cpt_code and item.cpt_code[0].isdigit() else "HCPCS"
            errors.append(DetectedError(
                code="NON_PAYABLE_CODE",
                severity=severity,
                affected_indices=[index],
                description=f"{code_label} {item.cpt_code} {reason}",
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

    # Ambulance HCPCS codes covered by the CMS Ambulance Fee Schedule.
    # All are A-prefix HCPCS Level II codes (not matched by the 5-digit CPT pattern).
    _AMBULANCE_CODES: frozenset[str] = frozenset({
        "A0425",  # Ground mileage, per statute mile
        "A0426",  # ALS non-emergency, level 1
        "A0427",  # ALS emergency, level 1
        "A0428",  # BLS non-emergency
        "A0429",  # BLS emergency
        "A0430",  # Fixed-wing air transport
        "A0431",  # Rotary-wing (helicopter) transport
        "A0432",  # ALS non-emergency, level 2
        "A0433",  # Advanced ALS (specialty)
        "A0434",  # Specialty care transport
        "A0435",  # Fixed-wing air mileage, per statute mile
        "A0436",  # Rotary-wing air mileage, per statute mile
    })

    def _detect_ambulance_outliers(self, line_items: list[ParsedLineItem]) -> list[DetectedError]:
        """Flag ambulance charges that exceed the CMS Ambulance Fee Schedule rate.

        The AFS publishes locality-adjusted rates with three tiers:
          urban, rural, and super-rural.
        The applicable rate is pre-selected by _load_ambulance_rates() in bills.py
        based on the patient's ZIP code. When ZIP is unknown, the urban (lowest)
        rate is used as a conservative benchmark.

        Uses the medicare_outlier_threshold multiplier (1.8× by default).
        Disabled when ambulance_rates is not loaded (no AFS data for the locality).
        """
        if not self._ambulance_rates:
            return []

        errors: list[DetectedError] = []

        for index, item in enumerate(line_items):
            if item.cpt_code not in self._AMBULANCE_CODES:
                continue

            benchmark = self._ambulance_rates.get(item.cpt_code)
            if benchmark is None or benchmark <= 0:
                continue

            # For per-mile codes (A0425, A0435, A0436): when mileage was parsed,
            # compare the per-mile unit_charge against the AFS per-mile benchmark.
            # When mileage is unknown (quantity=1), compare total_charge — only
            # a wildly inflated total will trigger, which is intentionally conservative.
            is_mileage_code = item.cpt_code in {"A0425", "A0435", "A0436"}
            if is_mileage_code and item.quantity > 1:
                billed = Decimal(str(item.unit_charge))
                charge_label = f"${billed:.2f}/mile ({item.quantity} miles billed)"
            else:
                billed = Decimal(str(item.total_charge))
                charge_label = f"${billed:.2f}"

            if billed > benchmark * Decimal(str(self._medicare_outlier_threshold)):
                overcharge = (billed - benchmark) * Decimal(str(item.quantity))
                label = f" ({item.description})" if item.description else ""
                errors.append(DetectedError(
                    code="AMBULANCE_CHARGE_OUTLIER",
                    severity="warning",
                    affected_indices=[index],
                    description=(
                        f"Your provider charged {charge_label} for ambulance service "
                        f"{item.cpt_code}{label}. The Medicare Ambulance Fee Schedule "
                        f"benchmark for your area is ${benchmark:.2f} — your charge is "
                        f"{billed / benchmark:.1f}x that amount. Ambulance billing errors "
                        f"are among the most common in healthcare. Consider requesting an "
                        f"itemized bill and contacting the provider to review the charge."
                    ),
                    estimated_overcharge=overcharge,
                    medicare_benchmark_rate=benchmark,
                ))

        return errors

    def _detect_terminated_codes(self, line_items: list[ParsedLineItem]) -> list[DetectedError]:
        """Flag HCPCS Level II codes billed after their CMS termination date.

        CMS terminates codes when they are replaced, consolidated, or withdrawn.
        Billing a terminated code for a service that occurred after the termination
        date means the provider used an invalid code — the claim will typically be
        denied by Medicare and most commercial payers.  The correct current code
        should have been used instead.

        Only HCPCS Level II codes are checked (alpha-prefix, e.g. A0425, J1234).
        CPT codes are covered by the proc_stat field in cms_pfs_indicators.
        """
        if not self._hcpcs_termination_dates:
            return []

        errors: list[DetectedError] = []

        for index, item in enumerate(line_items):
            term_date = self._hcpcs_termination_dates.get(item.cpt_code)
            if term_date is None:
                continue
            if item.service_date <= term_date:
                continue
            errors.append(DetectedError(
                code="TERMINATED_CODE_BILLED",
                severity="critical",
                affected_indices=[index],
                description=(
                    f"HCPCS {item.cpt_code} was terminated by CMS effective {term_date} "
                    f"and is no longer a valid billing code. The service date on this claim "
                    f"is {item.service_date}, which is after the termination date. This claim "
                    f"line will likely be denied — ask your provider which current code should "
                    f"have been used."
                ),
                estimated_overcharge=Decimal(str(item.total_charge)),
                medicare_benchmark_rate=None,
            ))

        return errors

    def _detect_hospital_charge_outliers(self, line_items: list[ParsedLineItem]) -> list[DetectedError]:
        """Flag charges that exceed the hospital's own published gross charge.

        Hospitals are required by CMS price transparency rules to publish their
        gross (chargemaster) rate for every procedure. Billing above that rate
        means the patient was charged more than the hospital's own list price —
        an unambiguous billing error regardless of insurance or payer.

        Uses the exact_price_threshold multiplier (1.1 by default = flag anything
        more than 10% over the published price). Disabled when hospital_charges is
        not loaded (hospital not in our database or NPI/name could not be matched).
        """
        if not self._hospital_charges:
            return []

        errors: list[DetectedError] = []

        for index, item in enumerate(line_items):
            gross_charge = self._hospital_charges.get(item.cpt_code)
            if gross_charge is None or gross_charge <= 0:
                continue

            charge = Decimal(str(item.total_charge))
            if charge > gross_charge * Decimal(str(self._exact_price_threshold)):
                overcharge = charge - gross_charge
                label = f" ({item.description})" if item.description else ""
                errors.append(DetectedError(
                    code="HOSPITAL_CHARGE_OUTLIER",
                    severity="critical",
                    affected_indices=[index],
                    description=(
                        f"Your provider charged ${charge:.2f} for CPT {item.cpt_code}"
                        f"{label}, but this hospital's own published price list "
                        f"(CMS price transparency file) shows a gross charge of "
                        f"${gross_charge:.2f}. You were billed "
                        f"${overcharge:.2f} more than the hospital's own listed price."
                    ),
                    estimated_overcharge=overcharge,
                    medicare_benchmark_rate=gross_charge,
                ))

        return errors

    def _detect_negotiated_rate_exceeded(self, line_items: list[ParsedLineItem]) -> list[DetectedError]:
        """Flag charges that exceed the patient's insurer-specific contracted rate.

        This is the strongest price benchmark in the engine. The negotiated rate is the
        exact dollar amount the patient's insurer agreed to pay this hospital for each
        procedure. Billing above it means the patient is being charged outside the terms
        of the insurance contract — the hospital cannot collect more than its contracted
        rate from an in-network patient.

        Data source: hospital_charges BigQuery table, filtered to the patient's
        payer_name and plan_name. The rate is loaded by _load_negotiated_charges()
        in bills.py before the engine runs.

        Disabled when negotiated_charges is empty (insurer not identified, plan not
        matched in MRF data, or hospital not in our database).
        """
        if not self._negotiated_charges:
            return []

        errors: list[DetectedError] = []

        for index, item in enumerate(line_items):
            negotiated_rate = self._negotiated_charges.get(item.cpt_code)
            if negotiated_rate is None or negotiated_rate <= 0:
                continue

            charge = Decimal(str(item.total_charge))
            if charge > negotiated_rate * Decimal(str(self._exact_price_threshold)):
                overcharge = charge - negotiated_rate
                label = f" ({item.description})" if item.description else ""
                errors.append(DetectedError(
                    code="NEGOTIATED_RATE_EXCEEDED",
                    severity="critical",
                    affected_indices=[index],
                    description=(
                        f"Your provider charged ${charge:.2f} for CPT {item.cpt_code}"
                        f"{label}. Your insurance plan's contracted rate at this hospital "
                        f"for this procedure is ${negotiated_rate:.2f} — a difference of "
                        f"${overcharge:.2f}. In-network providers cannot bill above their "
                        f"contracted rate. This may be a billing error or an improper "
                        f"balance-billing attempt."
                    ),
                    estimated_overcharge=overcharge,
                    medicare_benchmark_rate=negotiated_rate,
                ))

        return errors

    def _detect_facility_outliers(self, line_items: list[ParsedLineItem]) -> list[DetectedError]:
        """Flag facility charges that exceed the CMS OPPS payment cap for the locality.

        The OPPS cap is the amount Medicare pays for a procedure in a hospital outpatient
        setting. Charges significantly above this cap warrant review — the patient's
        cost-sharing is based on the billed charge, not just the Medicare payment amount.
        Uses the medicare_outlier_threshold multiplier (1.8× by default).
        """
        if not self._opps_rates:
            return []

        errors: list[DetectedError] = []

        for index, item in enumerate(line_items):
            opps_cap = self._opps_rates.get(item.cpt_code)
            if opps_cap is None or opps_cap <= 0:
                continue

            charge = Decimal(str(item.total_charge))
            if charge > opps_cap * Decimal(str(self._medicare_outlier_threshold)):
                overcharge = charge - opps_cap
                label = f" ({item.description})" if item.description else ""
                errors.append(DetectedError(
                    code="FACILITY_CHARGE_OUTLIER",
                    severity="warning",
                    affected_indices=[index],
                    description=(
                        f"Your facility charged ${charge:.2f} for CPT {item.cpt_code}"
                        f"{label}. The Medicare OPPS payment cap for this procedure "
                        f"in your area is ${opps_cap:.2f} — your charge is "
                        f"{charge / opps_cap:.1f}x that amount. Consider requesting "
                        f"an itemised bill and asking the facility to review the charge."
                    ),
                    estimated_overcharge=overcharge,
                    medicare_benchmark_rate=opps_cap,
                ))

        return errors

    def _detect_mue_violations(self, line_items: list[ParsedLineItem]) -> list[DetectedError]:
        """Flag line items where the billed quantity exceeds the CMS Medically Unlikely Edit limit.

        MUE limits define the maximum units of a given HCPCS/CPT code that can be billed
        on a single claim line or per date of service. Exceeding these limits is a strong
        indicator of quantity inflation or billing error.

        Adjudication indicator determines how the check is applied and what severity to assign:
          1 = Claim Edit: sum all lines with same code+date; total must not exceed the MUE value.
          2 = Date of Service Edit (Policy): each individual line must not exceed MUE — hard denial.
          3 = Date of Service Edit (Clinical): each line must not exceed MUE, but medical
              documentation can override — flag as warning rather than critical.
          0 = Unknown (MCD files omit this field): treat like indicator 2 conservatively.
        """
        if not self._mue_limits:
            return []

        errors: list[DetectedError] = []

        # Build index: (cpt_code, service_date_str) → [indices]
        code_date_indices: dict[tuple[str, str], list[int]] = {}
        for index, item in enumerate(line_items):
            key = (item.cpt_code, str(item.service_date))
            code_date_indices.setdefault(key, []).append(index)

        already_flagged: set[tuple[str, str]] = set()

        for index, item in enumerate(line_items):
            limit = self._mue_limits.get(item.cpt_code)
            if limit is None:
                continue

            mue_value, adj_indicator = limit
            if mue_value == 0:
                # mue_value of 0 means "not separately payable" — flag every occurrence
                errors.append(DetectedError(
                    code="MUE_EXCEEDED",
                    severity="critical",
                    affected_indices=[index],
                    description=(
                        f"CPT {item.cpt_code} has a CMS MUE value of 0, meaning it is "
                        f"not separately payable under any circumstances. "
                        f"Billing this code is considered improper."
                    ),
                    estimated_overcharge=Decimal(str(item.total_charge)),
                    medicare_benchmark_rate=None,
                ))
                continue

            key = (item.cpt_code, str(item.service_date))

            if adj_indicator == 1:
                # Claim Edit: compare the sum of all quantities for this code+date
                if key in already_flagged:
                    continue
                already_flagged.add(key)
                all_indices = code_date_indices[key]
                total_qty = sum(line_items[i].quantity for i in all_indices)
                if total_qty <= mue_value:
                    continue
                excess = total_qty - mue_value
                avg_unit = sum(
                    Decimal(str(line_items[i].unit_charge)) for i in all_indices
                ) / len(all_indices)
                overcharge = avg_unit * excess
                errors.append(DetectedError(
                    code="MUE_EXCEEDED",
                    severity="critical",
                    affected_indices=all_indices,
                    description=(
                        f"CPT {item.cpt_code} was billed for a combined total of {total_qty} units "
                        f"on {item.service_date}. The CMS Medically Unlikely Edit limit is "
                        f"{mue_value} units per claim. The excess {excess} unit(s) are unlikely "
                        f"to be reimbursed. Potential overcharge: ${float(overcharge):.2f}."
                    ),
                    estimated_overcharge=overcharge,
                    medicare_benchmark_rate=None,
                ))
            else:
                # Indicators 0, 2, 3: check each line individually
                qty = item.quantity
                if qty <= mue_value:
                    continue
                excess = qty - mue_value
                overcharge = Decimal(str(item.unit_charge)) * excess
                # Indicator 2 (policy) = hard denial → critical
                # Indicator 3 (clinical) = can be overridden with documentation → warning
                # Indicator 0 (unknown) = treat conservatively as critical
                severity = "warning" if adj_indicator == 3 else "critical"
                doc_note = (
                    " With supporting clinical documentation, this may be justified."
                    if adj_indicator == 3 else ""
                )
                errors.append(DetectedError(
                    code="MUE_EXCEEDED",
                    severity=severity,
                    affected_indices=[index],
                    description=(
                        f"CPT {item.cpt_code} was billed for {qty} units on {item.service_date}. "
                        f"The CMS Medically Unlikely Edit limit is {mue_value} units per date of "
                        f"service. The excess {excess} unit(s) are unlikely to be "
                        f"reimbursed.{doc_note} "
                        f"Potential overcharge: ${float(overcharge):.2f}."
                    ),
                    estimated_overcharge=overcharge,
                    medicare_benchmark_rate=None,
                ))

        return errors
