# Decision: REDUNDANT_CLINICAL_PAIR rule

**Date:** 2026-04-29  
**Status:** Shipped  
**Owners:** Sandra (product), Engineering

## Context

A real bill uploaded by a beta user contained two CPT pairs that the user
believed were obvious billing errors and that the engine missed:

- **76817 + 76801** — OB ultrasound transvaginal + transabdominal, same encounter
- **86900 + 86901** — ABO blood typing + Rh typing, same encounter

Investigation against the raw 2026 v3.21 CMS NCCI MCR PTP files
(`data/ncci/2026/mcr/ccipra-v321r0-f4.txt`) confirmed that **neither pair
exists in NCCI in either direction**. The engine was correct to not flag
them under NCCI_UNBUNDLING — they are not formal CMS bundling edits.

But the user's intuition was also correct: most commercial payer
medical-policy documents (Aetna, BCBS, UHC, Anthem, Cigna sampled) deny one
of these codes when both are billed for the same encounter without
documented justification. CMS doesn't formalize them into NCCI; payers
informally bundle them through their own policies.

This created a real product gap: the engine could not surface the most
common non-NCCI bundling patterns commercial payers actually deny.

## Decision

Add a new rule **REDUNDANT_CLINICAL_PAIR** with:

1. **Severity: warning** — payer policy varies by carrier, so we hedge.
2. **Curated, hand-maintained allowlist** at
   `apps/engine/app/data/redundant_clinical_pairs.py`. No machine-generated
   pairs, no automatic scraping of payer documents.
3. **Strict curation criteria** documented in the module docstring:
   - Pair must NOT be in NCCI PTP (verified via grep).
   - Pair must have a documented payer-policy reason for redundancy.
   - Pair must NOT be diagnosis-dependent (e.g. "redundant only when total
     PSA is normal" is excluded — too high a false-positive rate without
     diagnosis input).
   - Per-pair suppression modifiers (typically 59 / XS for distinct
     anatomical sites; 25 for separately identifiable E&M).
4. **Dedup against NCCI** — if a pair happens to be in NCCI on a given
   bill, NCCI fires and REDUNDANT_CLINICAL_PAIR stays silent.
5. **Cheaper line item is the redundant one** — its `total_charge`
   becomes `estimated_overcharge`. Hedged copy: "Ask the hospital to
   justify both charges or remove CPT \<code\>."

## Initial curated list (7 pairs)

| Category | Pair | Suppression | Why |
|---|---|---|---|
| OB ultrasound | 76801+76817 | 59, XS | Transabdominal + transvaginal first trimester |
| OB ultrasound | 76805+76817 | 59, XS | Same after first trimester |
| OB ultrasound | 76815+76817 | 59, XS | Limited + transvaginal |
| OB ultrasound | 76817+76819 | 59, XS | Transvaginal + biophysical profile |
| Lab panel | 86900+86901 | (none) | ABO + Rh = single panel |
| Lab panel | 82565+82550 | (none) | Creatinine + creatine kinase outside muscle workup |
| E&M with procedure | 36415+99211 | 25 | Routine venipuncture bundled into minimal E&M |

## Why warning, not critical

- NCCI is an authoritative CMS publication. Calling something an "NCCI
  unbundling violation" when it isn't would misrepresent the source and
  erode user trust if a hospital pushes back.
- Payer policy varies. The same pair denied by Aetna may be allowed by
  Medicare on the same bill. Warning severity + hedged copy is honest.
- The expected user action is "ask the hospital to justify" — they may
  produce documentation that legitimizes the billing. That's fine; it's
  the patient asking the right question.

## What's explicitly excluded

- Pairs already in NCCI in either direction (CT contrast pairs, EKG
  variants, lipid panel components, CBC with diff, etc.) — NCCI handles them.
- Diagnosis-dependent pairs (PSA total + free, PT + PTT mixing study) —
  too high a false-positive rate without diagnosis context.
- Bilateral/anatomical-distinct cases that have legitimate clinical reasons
  — covered by the per-pair suppression-modifier list.
- Frequency limits (e.g. how often glucose can be drawn) — that's a
  different rule (MUE handles per-encounter limits today).

## Tests

`tests/services/test_rules_engine.py::TestRedundantClinicalPairs` covers:
- Happy path per category
- One-code-only (no flag)
- Different service dates (no flag)
- Suppression modifier matches (no flag)
- Suppression modifier does NOT match (still flag)
- NCCI dedup (NCCI wins)
- Cheapest line is the overcharge
- Empty curated list disables the rule (test fixture pattern)

10 tests, 100% pass.

## Adding new pairs in the future

1. Verify NOT in NCCI:
   `grep -E "^<a>\s+<b>|^<b>\s+<a>" data/ncci/2026/mcr/ccipra-v321r0-f4.txt`
2. Cite a specific payer-policy document or clinical guideline.
3. Add the entry with all five fields populated.
4. Add a test case that mirrors an existing category test.
5. Update `docs/rules-engine.md` if introducing a new category.

## Consequences

- One more rule (rule #13) in the engine pipeline. Runtime cost is
  negligible — the rule short-circuits when no curated code is present
  on the bill.
- Adds a hand-maintained data file. Curation cost is low (~1 hour per
  added pair to verify and document); review cadence is "as users report
  misses or as new payer policies emerge."
- Strengthens the engine's non-NCCI coverage without misrepresenting NCCI
  as an authority for things it doesn't cover.
