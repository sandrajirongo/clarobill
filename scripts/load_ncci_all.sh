#!/usr/bin/env bash
# load_ncci_all.sh — Full NCCI data refresh (PTP + MUE).
#
# Loads all 9 NCCI files from data/ncci/ into the database:
#   - 3 Medicaid PTP files  (payer_type=medicare — CMS NCCI edits apply to all payer types)
#   - 3 Medicare MUE files  (payer_type=medicare, with Adjudication Indicator)
#   - 3 Medicaid MUE files  (payer_type=medicaid, no Adjudication Indicator)
#
# Pre-requisites:
#   1. Migration 20260420000017 applied to your Supabase database (adds service_type +
#      payer_type to ncci_edit_pairs, creates ncci_mue_limits).
#   2. Environment variables set:
#        export SUPABASE_URL=https://<your-project>.supabase.co
#        export SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
#   3. Python deps installed:  pip install supabase
#
# Usage (from repo root):
#   bash scripts/load_ncci_all.sh
#
# The --replace flag deletes existing rows for each (service_type, payer_type)
# combination before inserting, so stale entries from previous loads are removed.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="$REPO_ROOT/data/ncci"
SCRIPTS_DIR="$REPO_ROOT/scripts"

# ── Env check ────────────────────────────────────────────────────────────────
if [[ -z "${SUPABASE_URL:-}" || -z "${SUPABASE_SERVICE_ROLE_KEY:-}" ]]; then
  echo "Error: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set." >&2
  echo ""
  echo "Get them from your Supabase project → Settings → API."
  echo "Then run:"
  echo "  export SUPABASE_URL=https://<your-project>.supabase.co"
  echo "  export SUPABASE_SERVICE_ROLE_KEY=<service-role-key>"
  exit 1
fi

# ── File check ───────────────────────────────────────────────────────────────
REQUIRED_FILES=(
  "MCD-PTP-PractitionerServices-Effective_01012026.txt"
  "MCD-PTP-OutpatientHospitalServices-Effective_01012026.txt"
  "MCD-PTP-DMEServices-Effective_01012026.txt"
  "MCR_MUE_PractitionerServices_Eff_04-01-2026.csv"
  "MCR_MUE_OutpatientHospitalServices_Eff_04-01-2026.csv"
  "MCR_MUE_DMESupplierServices_Eff_04-01-2026.csv"
  "MCD-MUE-PractitionerServices-Effective_01012026.txt"
  "MCD-MUE-OutpatientHospitalServices-Effective_01012026.txt"
  "MCD-MUE-DMEServices-Effective_01012026.txt"
)
missing=0
for f in "${REQUIRED_FILES[@]}"; do
  if [[ ! -f "$DATA_DIR/$f" ]]; then
    echo "Missing: $DATA_DIR/$f" >&2
    missing=1
  fi
done
if [[ $missing -eq 1 ]]; then
  echo "Error: one or more required files are missing from data/ncci/." >&2
  exit 1
fi

PTP="python $SCRIPTS_DIR/load_ncci_edits.py --replace"
MUE="python $SCRIPTS_DIR/load_mue_limits.py --replace"

echo "============================================================"
echo " NCCI Full Refresh — $(date '+%Y-%m-%d %H:%M')"
echo "============================================================"

# ── PTP edit pairs ────────────────────────────────────────────────────────────
echo ""
echo "── PTP: Practitioner (payer_type=medicare) ─────────────────"
$PTP --file "$DATA_DIR/MCD-PTP-PractitionerServices-Effective_01012026.txt" \
     --service-type practitioner --payer-type medicare

echo ""
echo "── PTP: Outpatient Hospital (payer_type=medicare) ──────────"
$PTP --file "$DATA_DIR/MCD-PTP-OutpatientHospitalServices-Effective_01012026.txt" \
     --service-type outpatient --payer-type medicare

echo ""
echo "── PTP: DME (payer_type=medicare) ──────────────────────────"
$PTP --file "$DATA_DIR/MCD-PTP-DMEServices-Effective_01012026.txt" \
     --service-type dme --payer-type medicare

# ── Medicare MUE limits (MCR, with Adjudication Indicator) ───────────────────
echo ""
echo "── MUE: Medicare Practitioner (Q2 2026) ────────────────────"
$MUE --file "$DATA_DIR/MCR_MUE_PractitionerServices_Eff_04-01-2026.csv" \
     --service-type practitioner --payer-type medicare

echo ""
echo "── MUE: Medicare Outpatient Hospital (Q2 2026) ─────────────"
$MUE --file "$DATA_DIR/MCR_MUE_OutpatientHospitalServices_Eff_04-01-2026.csv" \
     --service-type outpatient --payer-type medicare

echo ""
echo "── MUE: Medicare DME Supplier (Q2 2026) ────────────────────"
$MUE --file "$DATA_DIR/MCR_MUE_DMESupplierServices_Eff_04-01-2026.csv" \
     --service-type dme --payer-type medicare

# ── Medicaid MUE limits (MCD, no Adjudication Indicator) ─────────────────────
echo ""
echo "── MUE: Medicaid Practitioner (Q1 2026) ────────────────────"
$MUE --file "$DATA_DIR/MCD-MUE-PractitionerServices-Effective_01012026.txt" \
     --service-type practitioner --payer-type medicaid

echo ""
echo "── MUE: Medicaid Outpatient Hospital (Q1 2026) ─────────────"
$MUE --file "$DATA_DIR/MCD-MUE-OutpatientHospitalServices-Effective_01012026.txt" \
     --service-type outpatient --payer-type medicaid

echo ""
echo "── MUE: Medicaid DME (Q1 2026) ─────────────────────────────"
$MUE --file "$DATA_DIR/MCD-MUE-DMEServices-Effective_01012026.txt" \
     --service-type dme --payer-type medicaid

echo ""
echo "============================================================"
echo " Done."
echo "============================================================"
