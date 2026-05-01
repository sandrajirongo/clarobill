"""End-to-end validation of the rules engine against real fleet data.

Anchors on Saint Michaels Medical Center (NPI 1568825545) — the most-
validated hospital in our `hospital_charges` table as of 2026-05-01.
Saint Michaels has 1,287,678 charge rows for pricing_effective_year=2024
spanning 6,535 distinct CPTs across 24 payers.

Test design:

  Synthetic bill — single line item, CPT 99214 (established office
  visit, moderate complexity), billed $850, Aetna Medicaid plan,
  service date 2024-06-01.

  Saint Michaels' actual published values for CPT 99214 (verified
  via direct BigQuery on 2026-05-01):
    gross_charge:        $683.00
    aetna_medicaid_rate: $96.84   (exact (payer, plan) match)
    max_negotiated:      $546.40  (across all payers at this hospital)
    min_negotiated:      $79.23

  Expected rule firings (with default thresholds: 1.1× exact, 1.8× medicare):

    NEGOTIATED_RATE_EXCEEDED   $850 > $96.84 × 1.1 = $106.52   FIRES
    HOSPITAL_CHARGE_OUTLIER    $850 > $683 × 1.1  = $751.30   FIRES
    NEGOTIATED_CEILING_EXCEEDED  suppressed (exact match exists)  NO
    PRICE_OUTLIER  Medicare benchmark × 1.05 (medicaid plan_type)   FIRES
                                                  if Medicare rate present

If all expected rules fire with the right benchmark math, the engine
is correctly wired against the new effective-dated `hospital_charges`
table and we're cleared to ship Phase 5 + the full fleet scrape.

Usage:
    python scripts/validate_rules_engine_against_fleet.py

Requires:
    GOOGLE_APPLICATION_CREDENTIALS pointing to the pipeline SA key, or
    `gcloud auth application-default login` already current.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

# Allow importing engine code from repo root invocation.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "apps" / "engine"))

# Ensure pydantic-settings doesn't try to read prod env vars during import.
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "stub")
os.environ.setdefault("GCP_PROJECT_ID", "clarobill-prd")
os.environ.setdefault("BIGQUERY_DATASET", "hospital_prices")

from google.cloud import bigquery

from app.services.parser import ParsedLineItem  # noqa: E402
from app.services.rules_engine import RulesEngine  # noqa: E402


# ── Test inputs (synthetic bill) ────────────────────────────────────────────

HOSPITAL_NPI = "1568825545"  # Saint Michaels Medical Center, Newark NJ
SERVICE_DATE = date(2024, 6, 1)
BILLED_CHARGE = 850.00
TEST_CPT = "99214"
TEST_PAYER = "Aetna"
TEST_PLAN = "Aetna Medicaid"


def _load_charges_for_test(bq: bigquery.Client) -> dict[str, Decimal | None]:
    """Pull the four reference rates the rules engine needs for one CPT.

    Returns a dict with: gross, exact_negotiated, max_negotiated, min_negotiated.
    Uses the new effective-dated `hospital_charges` table (the post-Phase-4
    target — what Phase 5 will switch the engine over to).
    """
    sql = """
    WITH src AS (
      SELECT *
      FROM `clarobill-prd.hospital_prices.hospital_charges`
      WHERE hospital_npi = @npi
        AND code = @code
        AND pricing_effective_year = @year
    )
    SELECT
      MAX(gross_charge)                                                  AS gross,
      MAX(IF(payer_name = @payer AND plan_name = @plan, negotiated_charge, NULL)) AS exact_negotiated,
      MAX(max_negotiated)                                                AS max_negotiated,
      MIN(NULLIF(min_negotiated, 0))                                     AS min_negotiated
    FROM src
    """
    job_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("npi", "STRING", HOSPITAL_NPI),
        bigquery.ScalarQueryParameter("code", "STRING", TEST_CPT),
        bigquery.ScalarQueryParameter("year", "INT64", SERVICE_DATE.year),
        bigquery.ScalarQueryParameter("payer", "STRING", TEST_PAYER),
        bigquery.ScalarQueryParameter("plan", "STRING", TEST_PLAN),
    ])
    row = next(iter(bq.query(sql, job_config=job_config).result()))
    return {
        "gross": Decimal(str(row["gross"])) if row["gross"] is not None else None,
        "exact_negotiated": Decimal(str(row["exact_negotiated"])) if row["exact_negotiated"] is not None else None,
        "max_negotiated": Decimal(str(row["max_negotiated"])) if row["max_negotiated"] is not None else None,
        "min_negotiated": Decimal(str(row["min_negotiated"])) if row["min_negotiated"] is not None else None,
    }


def _build_engine(charges: dict[str, Decimal | None]) -> RulesEngine:
    """Construct a RulesEngine with the loaded reference data.

    We pass empty dicts for every CMS reference table not relevant to this
    test (Medicare PFS, NCCI, OPPS, MUE, anesthesia, ambulance, HCPCS) —
    rules requiring missing data degrade to no-op. This keeps the test
    focused on the MRF-derived pricing rules, which are the ones Phase 4
    actually delivers data for.
    """
    return RulesEngine(
        ncci_edit_pairs={},
        medicare_rates={},  # PRICE_OUTLIER will not fire (degraded)
        plan_type="medicaid",
        service_type="outpatient",
        hospital_charges={TEST_CPT: charges["gross"]} if charges["gross"] else {},
        negotiated_charges={TEST_CPT: charges["exact_negotiated"]} if charges["exact_negotiated"] else {},
        negotiated_ceiling={TEST_CPT: charges["max_negotiated"]} if charges["max_negotiated"] else {},
    )


def main() -> int:
    print(f"\n{'=' * 70}")
    print("End-to-end validation: Saint Michaels Medical Center, CPT 99214")
    print(f"{'=' * 70}\n")

    bq = bigquery.Client(project="clarobill-prd")
    charges = _load_charges_for_test(bq)

    print("Reference data from hospital_charges (post-Phase-4):")
    for k, v in charges.items():
        print(f"  {k:<20} {v if v is not None else '(no data)'}")
    print()

    if charges["gross"] is None:
        print("FAIL: no gross_charge for CPT 99214 — Saint Michaels data not loaded?")
        return 2

    engine = _build_engine(charges)
    bill = ParsedLineItem(
        cpt_code=TEST_CPT,
        description="Office/outpatient visit, est patient, moderate",
        service_date=SERVICE_DATE,
        quantity=1,
        unit_charge=BILLED_CHARGE,
        total_charge=BILLED_CHARGE,
        modifier=None,
        diagnosis_pointers=[],
    )
    print(f"Synthetic bill:  CPT {TEST_CPT}  |  ${BILLED_CHARGE:.2f}  |  "
          f"{TEST_PAYER} / {TEST_PLAN}  |  {SERVICE_DATE}\n")

    errors = engine.run([bill])
    print(f"Engine returned {len(errors)} finding(s):\n")
    for err in errors:
        print(f"  [{err.severity.upper():<8}] {err.code}")
        print(f"            overcharge = ${err.estimated_overcharge:>9}")
        print(f"            {err.description[:200]}")
        if len(err.description) > 200:
            print(f"            ...")
        print()

    # Expected outcomes
    found = {e.code for e in errors}
    print("─── Expected rule firings ───")
    expectations = [
        ("HOSPITAL_CHARGE_OUTLIER",   True,  "$850 > $683 × 1.1 = $751.30"),
        ("NEGOTIATED_RATE_EXCEEDED",  True,  "$850 > $96.84 × 1.1 = $106.52  (exact Aetna Medicaid rate)"),
        ("NEGOTIATED_CEILING_EXCEEDED", False, "Suppressed because an exact (payer, plan) match exists"),
    ]
    all_pass = True
    for code, should_fire, why in expectations:
        actual = code in found
        status = "PASS" if actual == should_fire else "FAIL"
        if actual != should_fire:
            all_pass = False
        verb = "FIRED" if actual else "did not fire"
        print(f"  {status}  {code:<32} {verb:<14} | {why}")
    print()

    if all_pass:
        print("END-TO-END VALIDATION PASSED.")
        print("Rules engine wires correctly against post-Phase-4 hospital_charges.\n")
        return 0
    else:
        print("END-TO-END VALIDATION FAILED — see expected vs actual above.\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
