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

# ── PTP edit pairs — MCD (Medicaid) ──────────────────────────────────────────
# CMS PTP files are cumulative snapshots. Only the latest quarterly file per
# service type is needed — all historically-active pairs are included with their
# own effective_date/deletion_date. Upsert is sufficient; no delete needed.
echo ""
echo "── PTP Edits: Medicaid (MCD files, all years) ───────────────"

for year_dir in "$DATA_DIR"/*/mcd; do
  [[ -d "$year_dir" ]] || continue
  year=$(basename "$(dirname "$year_dir")")
  for svc_type in practitioner outpatient dme; do
    case "$svc_type" in
      practitioner) pattern="MCD-PTP-PractitionerServices*" ;;
      outpatient)   pattern="MCD-PTP-OutpatientHospitalServices*" ;;
      dme)          pattern="MCD-PTP-DMEServices*" ;;
    esac
    while IFS= read -r -d $'\0' file; do
      echo ""
      echo "  PTP medicaid/$svc_type [$year] → $(basename "$file")"
      run_loader $PTP_LOADER --file "$file" --service-type "$svc_type" --payer-type medicaid
    done < <(find "$year_dir" -maxdepth 1 -iname "$pattern" -print0 | sort -z)
  done
done

# ── PTP edit pairs — MCR (Medicare) ──────────────────────────────────────────
# CMS Medicare PTP files use a different naming convention and 7-column format.
# Files are split across f1–f4 per version — load all of them sorted so the
# latest version (highest v-number) loads last and overwrites earlier data.
# Naming: ccioph-v{ver}r0-f{n}.txt (outpatient), ccipra-v{ver}r0-f{n}.txt (practitioner)
echo ""
echo "── PTP Edits: Medicare (MCR files, all years) ───────────────"

for year_dir in "$DATA_DIR"/*/mcr; do
  [[ -d "$year_dir" ]] || continue
  year=$(basename "$(dirname "$year_dir")")
  for svc_type in practitioner outpatient dme; do
    case "$svc_type" in
      practitioner) prefix="ccipra" ;;
      outpatient)   prefix="ccioph" ;;
      dme)          prefix="ccidme" ;;
    esac
    while IFS= read -r -d $'\0' file; do
      echo ""
      echo "  PTP medicare/$svc_type [$year] → $(basename "$file")"
      run_loader $PTP_LOADER --file "$file" --service-type "$svc_type" --payer-type medicare
    done < <(find "$year_dir" -maxdepth 1 -iname "${prefix}*.txt" -print0 | sort -z)
  done
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
    done < <(find "$year_dir" -maxdepth 1 -iname "*.txt" -iname "$pattern" -print0 | sort -z)
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
