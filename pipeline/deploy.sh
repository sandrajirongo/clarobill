#!/usr/bin/env bash
# Deploy the MRF pipeline image and Cloud Run Jobs.
#
# Run once to set up the pipeline. Re-run to update the image after code changes.
#
# Prerequisites:
#   gcloud auth login
#   gcloud config set project clarobill-prd
#   Artifact Registry repo: clarobill-pipeline (create once if needed)
#     gcloud artifacts repositories create clarobill-pipeline \
#       --repository-format=docker --location=us-central1
#
# Usage:
#   bash pipeline/deploy.sh

set -euo pipefail

PROJECT="clarobill-prd"
REGION="us-central1"
REPO="us-central1-docker.pkg.dev/${PROJECT}/clarobill-pipeline"
IMAGE="${REPO}/mrf-pipeline:latest"
PIPELINE_SA="clarobill-pipeline-sa@${PROJECT}.iam.gserviceaccount.com"

echo "==> Building and pushing image..."
# Build context is repo root (.) because the Dockerfile COPYs from
# pipeline/* AND scripts/mrf_discovery/* — both sibling directories need
# to be in scope. Sending only pipeline/ as context (the original deploy.sh
# behaviour) made Docker resolve `COPY pipeline/requirements.txt` to a
# missing path. The cloudbuild.yaml sibling specifies the Dockerfile path
# explicitly so we can keep the Dockerfile co-located with pipeline code.
# Run from repo root: `bash pipeline/deploy.sh`
gcloud builds submit \
  --config=pipeline/cloudbuild.yaml \
  --substitutions="_IMAGE=${IMAGE}" \
  --project "${PROJECT}" \
  .

# Task timeout: 4 hours (14400s) handles ~3,100 hospitals comfortably.
# Scaling path when hospital count grows (target ~18,000 = 6x current):
#   Use --tasks N + --parallelism N to shard work across N task instances.
#   Each task reads CLOUD_RUN_TASK_INDEX and processes hospitals[index::N].
#   At N=6 tasks, each handles ~3,000 hospitals — same wall-clock time as today.
#   Both scraper and parser need to be updated to support task sharding.
echo "==> Creating/updating clarobill-mrf-scraper Cloud Run Job..."
gcloud run jobs create clarobill-mrf-scraper \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --service-account "${PIPELINE_SA}" \
  --task-timeout 129600 \
  --max-retries 0 \
  --memory 8Gi \
  --cpu 2 \
  --set-env-vars "GCP_PROJECT_ID=${PROJECT},BIGQUERY_DATASET=hospital_prices,GCS_MRF_STAGING_BUCKET=mrf-staging,GCS_MRF_ARCHIVE_BUCKET=mrf-archive-clarobill-prd" \
  --project "${PROJECT}" \
  2>/dev/null || \
gcloud run jobs update clarobill-mrf-scraper \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --service-account "${PIPELINE_SA}" \
  --task-timeout 129600 \
  --max-retries 0 \
  --memory 8Gi \
  --cpu 2 \
  --set-env-vars "GCP_PROJECT_ID=${PROJECT},BIGQUERY_DATASET=hospital_prices,GCS_MRF_STAGING_BUCKET=mrf-staging,GCS_MRF_ARCHIVE_BUCKET=mrf-archive-clarobill-prd" \
  --project "${PROJECT}"

echo "==> Creating/updating clarobill-mrf-parser Cloud Run Job..."
gcloud run jobs create clarobill-mrf-parser \
  --image "${IMAGE}" \
  --command "python,parse_hospital_mrfs.py" \
  --region "${REGION}" \
  --service-account "${PIPELINE_SA}" \
  --task-timeout 129600 \
  --max-retries 0 \
  --memory 8Gi \
  --cpu 2 \
  --set-env-vars "GCP_PROJECT_ID=${PROJECT},BIGQUERY_DATASET=hospital_prices,GCS_MRF_STAGING_BUCKET=mrf-staging,GCS_MRF_ARCHIVE_BUCKET=mrf-archive-clarobill-prd" \
  --project "${PROJECT}" \
  2>/dev/null || \
gcloud run jobs update clarobill-mrf-parser \
  --image "${IMAGE}" \
  --command "python,parse_hospital_mrfs.py" \
  --region "${REGION}" \
  --service-account "${PIPELINE_SA}" \
  --task-timeout 129600 \
  --max-retries 0 \
  --memory 8Gi \
  --cpu 2 \
  --set-env-vars "GCP_PROJECT_ID=${PROJECT},BIGQUERY_DATASET=hospital_prices,GCS_MRF_STAGING_BUCKET=mrf-staging,GCS_MRF_ARCHIVE_BUCKET=mrf-archive-clarobill-prd" \
  --project "${PROJECT}"

# Grant Cloud Scheduler SA permission to invoke both jobs
SCHEDULER_SA="clarobill-scheduler-sa@${PROJECT}.iam.gserviceaccount.com"
echo "==> Granting scheduler SA run.jobsExecutor on both jobs..."
gcloud run jobs add-iam-policy-binding clarobill-mrf-scraper \
  --region "${REGION}" \
  --member "serviceAccount:${SCHEDULER_SA}" \
  --role "roles/run.jobsExecutor" \
  --project "${PROJECT}"

gcloud run jobs add-iam-policy-binding clarobill-mrf-parser \
  --region "${REGION}" \
  --member "serviceAccount:${SCHEDULER_SA}" \
  --role "roles/run.jobsExecutor" \
  --project "${PROJECT}"

echo "==> Creating/updating Cloud Scheduler jobs..."

# 2026-04-30 cadence change (see docs/decisions/2026-04-30-pipeline-cadence.md):
# MRFs change at most twice per year per CMS rule, so weekly polling was wasteful.
# New schedule:
#   - Annual scrape + parse on Feb 15 (matches annual discovery; gives hospitals
#     6 weeks past Jan 1 republish deadline to fix any errors before we crawl).
#   - Mid-year safety scrape + parse on Aug 15 (catches the ~10% of hospitals
#     that republish in summer).
# The legacy weekly schedules are deleted at the bottom of this script.
_create_or_update_schedule() {
  local name="$1"
  local cron="$2"
  local target_job="$3"
  local description="$4"
  echo "==> Creating/updating Cloud Scheduler trigger ${name} (${cron})..."
  gcloud scheduler jobs create http "${name}" \
    --location "${REGION}" \
    --schedule "${cron}" \
    --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT}/jobs/${target_job}:run" \
    --http-method POST \
    --oauth-service-account-email "${SCHEDULER_SA}" \
    --description "${description}" \
    --project "${PROJECT}" \
    2>/dev/null || \
  gcloud scheduler jobs update http "${name}" \
    --location "${REGION}" \
    --schedule "${cron}" \
    --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT}/jobs/${target_job}:run" \
    --http-method POST \
    --oauth-service-account-email "${SCHEDULER_SA}" \
    --description "${description}" \
    --project "${PROJECT}"
}

# Scraper: annual Feb 15 + mid-year Aug 15.
_create_or_update_schedule \
  "clarobill-mrf-scraper-annual" \
  "0 2 15 2 *" \
  "clarobill-mrf-scraper" \
  "MRF scraper — ANNUAL Feb 15 02:00 UTC (full chargemaster refresh)"
_create_or_update_schedule \
  "clarobill-mrf-scraper-midyear" \
  "0 2 15 8 *" \
  "clarobill-mrf-scraper" \
  "MRF scraper — MID-YEAR Aug 15 02:00 UTC (catches summer republishers)"

# Parser: 4 hours after each scraper, same dates.
_create_or_update_schedule \
  "clarobill-mrf-parser-annual" \
  "0 6 15 2 *" \
  "clarobill-mrf-parser" \
  "MRF parser — ANNUAL Feb 15 06:00 UTC (4h after annual scraper)"
_create_or_update_schedule \
  "clarobill-mrf-parser-midyear" \
  "0 6 15 8 *" \
  "clarobill-mrf-parser" \
  "MRF parser — MID-YEAR Aug 15 06:00 UTC (4h after mid-year scraper)"

# Delete the legacy weekly schedules so they don't double-trigger alongside
# the new annual/mid-year schedules. Idempotent — silent if already gone.
for old in clarobill-mrf-scraper-weekly clarobill-mrf-parser-weekly; do
  echo "==> Removing legacy weekly schedule ${old} if present..."
  gcloud scheduler jobs delete "${old}" \
    --location "${REGION}" --project "${PROJECT}" --quiet 2>/dev/null || true
done

echo ""
echo "==> Pipeline deployed."
echo "    Scraper annual:    Feb 15 02:00 UTC"
echo "    Scraper mid-year:  Aug 15 02:00 UTC"
echo "    Parser annual:     Feb 15 06:00 UTC"
echo "    Parser mid-year:   Aug 15 06:00 UTC"
echo ""
echo "    Manual trigger — single task (small fleet test):"
echo "      gcloud run jobs execute clarobill-mrf-scraper --region ${REGION}"
echo "      gcloud run jobs execute clarobill-mrf-parser  --region ${REGION}"
echo ""
echo "    Manual trigger — 6 parallel tasks (for ~13,989 hospitals, ~4h wall-clock):"
echo "      gcloud run jobs execute clarobill-mrf-scraper --tasks 6 --region ${REGION}"
echo "      gcloud run jobs execute clarobill-mrf-parser  --tasks 6 --region ${REGION}"
echo "    Note: parallelism defaults to 0 (unlimited) — all 6 tasks run concurrently."
