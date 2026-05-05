"""Curated allowlist of clinically-redundant CPT pairs (non-NCCI).

Why this list exists
--------------------
CMS NCCI PTP catches the strict procedure-to-procedure bundling rules CMS
publishes. But many billing-error patterns commercial payers routinely deny
are NOT formal NCCI edits — they are payer-policy redundancies. Examples:

  - Two OB ultrasounds same encounter (transabdominal + transvaginal) when
    both are not medically necessary.
  - ABO + Rh blood typing billed as two separate codes when they are
    routinely ordered together as one "type and Rh" panel.
  - Venipuncture + minimal-level E&M when the E&M was the only reason for
    the blood draw.

CMS does not formally bundle these in NCCI, but most commercial payer
medical-policy documents will deny them when billed without justification.
ClaroBill flags them as **REDUNDANT_CLINICAL_PAIR** with **warning**
severity and hedged language ("ask the hospital to justify"), distinct from
the **critical** NCCI_UNBUNDLING flag.

Curation criteria (mandatory for every entry)
---------------------------------------------
1. **Not in NCCI PTP.** Verified against `data/ncci/2026/mcr/ccipra-v321r0-f4.txt`
   in both directions. If a pair is in NCCI in either direction, NCCI handles
   it — do NOT add it here.
2. **Documented payer policy.** Every entry must cite a specific reason this
   pair is commonly denied (clinical redundancy, panel-vs-component, etc.).
3. **No diagnosis-dependent pairs.** If "redundant" depends on the diagnosis
   code (e.g. "PSA total + free PSA only redundant when total is normal"),
   leave it out — false positives erode user trust.
4. **No bilateral/anatomical-distinct cases.** If the pair has a legitimate
   reason to be billed together (e.g. bilateral procedures), document the
   suppression modifier.
5. **Same service date only.** Different dates = different encounters =
   different medical-necessity context.

Adding a new pair
-----------------
- Verify it's not in NCCI: `grep -E "^<a>\s+<b>|^<b>\s+<a>" data/ncci/2026/mcr/ccipra-v321r0-f4.txt`
- Add an entry to REDUNDANT_PAIRS below with all four fields populated.
- Add a test case in tests/services/test_rules_engine.py mirroring the
  existing REDUNDANT_CLINICAL_PAIR tests.
- Update docs/architecture/rules-engine.md if adding a new category.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RedundantPair:
    """One curated payer-policy redundant CPT pair.

    Both code_a and code_b must be present on the same service date with no
    suppression_modifier on either to fire the rule.
    """

    code_a: str
    code_b: str
    category: str  # 'ob_ultrasound' | 'lab_panel' | 'em_with_procedure'
    rationale: str
    # Modifiers that justify billing both codes (e.g. 59 for distinct sites).
    # Empty frozenset means no override — pair is always redundant if both
    # present same date.
    suppression_modifiers: frozenset[str]
    payer_policy_note: str


# --- The curated list -------------------------------------------------------
# Last updated: 2026-04-29. NCCI verification batch run against the 2026 v3.21
# MCR PTP files. See docs/decisions/2026-04-29-redundant-clinical-pairs-rule.md
# for the design and curation rationale.
REDUNDANT_PAIRS: tuple[RedundantPair, ...] = (
    # --- OB ultrasound family ---
    # CPT 76817 (transvaginal) is commonly ordered alongside one of the
    # transabdominal codes during the same OB visit. Most payer medical
    # policies expect one approach (transabdominal OR transvaginal) per
    # encounter unless there is a specific clinical reason — modifier 59
    # (distinct anatomic site, e.g. twin pregnancy) overrides.
    RedundantPair(
        code_a="76801",
        code_b="76817",
        category="ob_ultrasound",
        rationale="OB ultrasound transabdominal first trimester complete + transvaginal "
                  "are typically performed as alternatives, not together, unless distinct "
                  "anatomical findings justify both.",
        suppression_modifiers=frozenset({"59", "XS"}),
        payer_policy_note="Most commercial payers (Aetna, BCBS, UHC) bundle into one "
                          "approach per encounter absent documentation of distinct sites.",
    ),
    RedundantPair(
        code_a="76805",
        code_b="76817",
        category="ob_ultrasound",
        rationale="OB ultrasound transabdominal after first trimester + transvaginal "
                  "billed same encounter is typically redundant.",
        suppression_modifiers=frozenset({"59", "XS"}),
        payer_policy_note="ACOG guidelines describe transvaginal as a complement to "
                          "transabdominal only when transabdominal is non-diagnostic.",
    ),
    RedundantPair(
        code_a="76815",
        code_b="76817",
        category="ob_ultrasound",
        rationale="Limited OB ultrasound + transvaginal same encounter is rarely justified — "
                  "if transvaginal is performed, it usually supplants the limited study.",
        suppression_modifiers=frozenset({"59", "XS"}),
        payer_policy_note="Limited (76815) is typically performed when complete is not "
                          "indicated; pairing with transvaginal suggests one is redundant.",
    ),
    RedundantPair(
        code_a="76817",
        code_b="76819",
        category="ob_ultrasound",
        rationale="Transvaginal OB + biophysical profile billed same encounter overlaps "
                  "fetal-assessment scope already included in the BPP.",
        suppression_modifiers=frozenset({"59", "XS"}),
        payer_policy_note="BPP (76819) includes ultrasound assessment of fetal well-being; "
                          "separately billing 76817 is generally considered redundant.",
    ),
    # --- Lab panels ---
    # ABO + Rh are functionally one test ("type and Rh") in clinical practice.
    # Some labs bill them as two CPTs but most payer policies treat them as a
    # bundle.
    RedundantPair(
        code_a="86900",
        code_b="86901",
        category="lab_panel",
        rationale="ABO blood typing + Rh typing are routinely ordered together as a "
                  "single 'type and Rh' panel; billing them as separate CPTs is a "
                  "common payer-policy redundancy.",
        suppression_modifiers=frozenset(),  # no override — these are functionally one test
        payer_policy_note="Many commercial payers (Anthem, Cigna) explicitly bundle ABO+Rh "
                          "into a single line item even though CMS NCCI does not.",
    ),
    RedundantPair(
        code_a="82565",
        code_b="82550",
        category="lab_panel",
        rationale="Creatinine quantitative + creatine kinase ordered same encounter "
                  "without a clinical indication (e.g. rhabdomyolysis) is treated as a "
                  "redundant order under many payer policies.",
        suppression_modifiers=frozenset(),
        payer_policy_note="When ordered together routinely (not in the context of "
                          "muscle/cardiac injury workup), payers may deny one as not "
                          "medically necessary.",
    ),
    # --- E&M with procedure ---
    # Venipuncture (36415) is bundled into all E&M services per CPT guidelines
    # when the venipuncture is the routine specimen-collection step for labs
    # ordered during the visit. Modifier 25 on the E&M is the override.
    RedundantPair(
        code_a="36415",
        code_b="99211",
        category="em_with_procedure",
        rationale="Venipuncture for routine lab draw is bundled into a minimal-level "
                  "E&M visit when the E&M is the only reason for the encounter.",
        suppression_modifiers=frozenset({"25"}),  # 25 on the E&M = separately identifiable
        payer_policy_note="CPT guidelines: routine venipuncture associated with a lab "
                          "drawn during the visit is included in the E&M code unless the "
                          "E&M is separately identifiable (modifier 25).",
    ),
)


def find_pair(code_a: str, code_b: str) -> RedundantPair | None:
    """Return the RedundantPair entry covering (code_a, code_b), order-insensitive.

    Returns None if the pair is not in the curated list.
    """
    for pair in REDUNDANT_PAIRS:
        if {pair.code_a, pair.code_b} == {code_a, code_b}:
            return pair
    return None


def all_codes_in_pairs() -> frozenset[str]:
    """Return every CPT code referenced by any pair in the list.

    Used by the rules engine to short-circuit detection when no relevant code
    is present on the bill.
    """
    codes: set[str] = set()
    for pair in REDUNDANT_PAIRS:
        codes.add(pair.code_a)
        codes.add(pair.code_b)
    return frozenset(codes)
