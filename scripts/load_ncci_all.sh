#!/usr/bin/env bash
# load_ncci_all.sh — Full NCCI data load across all available years.
#
# Loads every MUE file found under data/ncci/{year}/mcd/ and data/ncci/{year}/mcr/,
# plus the 2026 PTP files. Each file is upserted — re-running is always safe,
# existing rows are updated in place, no data is deleted before inserting.
#
# Pre-requisites:
#   1. Migrations 20260420000017 through 20260420000020 applied to your Supabase DB.
#      Run each SQL file in your Supabase dashboard → SQL Editor.
#   2. Environment variables set:
#        export SUPABASE_URL=https://<your-project>.supabase.co
#        export SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
#   3. Python deps installed:  pip install supabase
#
# Usage (from repo root):
#   bash scripts/load_ncci_all.sh

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="$REPO_ROOT/data/ncci"
SCRIPTS_DIR="$REPO_ROOT/scripts"

# ── Env check ────────────────────────────────────────────────────────────────
if [[ -z "${SUPABASE_URL:-}" || -z "${SUPABASE_SERVICE_ROLE_KEY:-}" ]]; then
  echo "Error: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set." >&2
  echo ""
  echo "Get them from: Supabase dashboard → Settings → API → Service Role key"
  echo "Then run:"
  echo "  export SUPABASE_URL=https://<your-project>.supabase.co"
  echo "  export SUPABASE_SERVICE_ROLE_KEY=<service-role-key>"
  exit 1
fi

PTP_LOADER="python3 $SCRIPTS_DIR/load_ncci_edits.py"
MUE_LOADER="python3 $SCRIPTS_DIR/load_mue_limits.py"

ERRORS=0

run_loader() {
  # Runs a loader command. On failure: prints an error and increments ERRORS
  # but does NOT abort the overall load. One bad file should not stop the rest.
  if ! "$@"; then
    echo "  ERROR: loader failed — $*" >&2
    ERRORS=$((ERRORS + 1))
  fi
}

echo "============================================================"
echo " NCCI Full Load — $(date '+%Y-%m-%d %H:%M')"
echo " Data root: $DATA_DIR"
echo "============================================================"

# ── PTP edit pairs (2026 only) ────────────────────────────────────────────────
# CMS PTP files are cumulative — every historically-active pair is listed with
# its own effective_date/deletion_date. Only the latest quarterly file is needed.
# Upsert is sufficient: existing rows are updated in place. No delete needed.
echo ""
echo "── PTP Edits (Q1 2026, payer_type=medicare) ─────────────────"

for svc_type in practitioner outpatient dme; do
  case "$svc_type" in
    practitioner) label="PractitionerServices" ;;
    outpatient)   label="OutpatientHospitalServices" ;;
    dme)          label="DMEServices" ;;
  esac
  file="$DATA_DIR/2026/mcd/MCD-PTP-${label}-Effective_01012026.txt"
  if [[ -f "$file" ]]; then
    echo ""
    echo "  PTP $svc_type → $(basename "$file")"
    run_loader $PTP_LOADER --file "$file" --service-type "$svc_type" --payer-type medicare
  else
    echo "  WARNING: PTP file not found: $file" >&2
  fi
done

# ── MUE limits — MCR (Medicare, with Adjudication Indicator) ─────────────────
echo ""
echo "── MUE: Medicare (MCR CSV files, all years) ─────────────────"

for year_dir in "$DATA_DIR"/*/mcr; do
  [[ -d "$year_dir" ]] || continue
  year=$(basename "$(dirname "$year_dir")")
  for svc_type in practitioner outpatient dme; do
    case "$svc_type" in
      practitioner) pattern="*Practitioner*" ;;
      outpatient)   pattern="*OutpatientHospital*" ;;
      dme)          pattern="*DME*" ;;
    esac
    # Sort so base file loads first, then revisions (_R1, -REPLACEMENT) overwrite
    while IFS= read -r -d $'\0' file; do
      echo ""
      echo "  MUE medicare/$svc_type [$year] → $(basename "$file")"
      run_loader $MUE_LOADER --file "$file" --service-type "$svc_type" --payer-type medicare
    done < <(find "$year_dir" -maxdepth 1 -name "*.csv" -name "$pattern" -print0 | sort -z)
  done
done

# ── MUE limits — MCD (Medicaid, no Adjudication Indicator) ───────────────────
echo ""
echo "── MUE: Medicaid (MCD TXT files, all years) ─────────────────"

for year_dir in "$DATA_DIR"/*/mcd; do
  [[ -d "$year_dir" ]] || continue
  year=$(basename "$(dirname "$year_dir")")
  for svc_type in practitioner outpatient dme; do
    case "$svc_type" in
      practitioner) pattern="*MUE*Practitioner*" ;;
      outpatient)   pattern="*MUE*OutpatientHospital*" ;;
      dme)          pattern="*MUE*DME*" ;;
    esac
    while IFS= read -r -d $'\0' file; do
      echo ""
      echo "  MUE medicaid/$svc_type [$year] → $(basename "$file")"
      run_loader $MUE_LOADER --file "$file" --service-type "$svc_type" --payer-type medicaid
    done < <(find "$year_dir" -maxdepth 1 \( -iname "*.txt" \) -name "$pattern" -print0 | sort -z)
  done
done

echo ""
echo "============================================================"
if [[ $ERRORS -eq 0 ]]; then
  echo " Done. All files loaded successfully."
else
  echo " Done with $ERRORS error(s). Check output above for details." >&2
fi
echo "============================================================"

exit $((ERRORS > 0 ? 1 : 0))
