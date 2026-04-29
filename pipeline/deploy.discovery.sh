#!/usr/bin/env bash
# Deploy the annual MRF discovery Cloud Run Job + Cloud Scheduler trigger.
#
# Run once to create the job and schedule. Re-run to update the image after
# code changes; idempotent (job is upserted via try-create-then-update).
#
# Schedule: 02:00 UTC on January 15 every year, timed for after CMS's
# January-1 chargemaster re-publication deadline so the discovery picks up
# every hospital's freshest URLs and any newly-certified facilities.
#
# Manual triggers (when needed):
#   gcloud run jobs execute clarobill-mrf-discovery --region us-central1
#
# Prerequisites:
#   gcloud auth login
#   gcloud config set project clarobill-prd
#   Artifact Registry repo `clarobill-pipeline` exists (created via deploy.sh)
#   Secret `google-places-api-key` exists in Secret Manager with a clean key
#     (see docs/decisions/2026-04-28-google-places-cost-design.md for setup)
#   clarobill-pipeline-sa has secretmanager.secretAccessor on that secret
#     (see docs/gcp-architecture.md One-Time Setup Checklist step 7)
#
# Usage:
#   bash pipeline/deploy.discovery.sh

set -euo pipefail

PROJECT="clarobill-prd"
REGION="us-central1"
REPO="us-central1-docker.pkg.dev/${PROJECT}/clarobill-pipeline"
IMAGE="${REPO}/mrf-discovery:latest"
PIPELINE_SA="clarobill-pipeline-sa@${PROJECT}.iam.gserviceaccount.com"
SCHEDULER_SA="clarobill-scheduler-sa@${PROJECT}.iam.gserviceaccount.com"

JOB_NAME="clarobill-mrf-discovery"
# Bi-annual schedule (decided 2026-04-29 in Phase 4 design Q3): hospitals
# republish their chargemasters in February and August, so the discovery
# pipeline runs both times to catch each publication wave.
SCHEDULE_FEB_NAME="clarobill-mrf-discovery-feb"
SCHEDULE_AUG_NAME="clarobill-mrf-discovery-aug"
SCHEDULE_FEB_CRON="0 2 1 2 *"  # 02:00 UTC on February 1 every year
SCHEDULE_AUG_CRON="0 2 1 8 *"  # 02:00 UTC on August 1 every year

echo "==> Building and pushing image (${IMAGE})..."
echo "    Build context is the repo root so the Docker COPY paths can find"
echo "    scripts/mrf_discovery/ which lives outside the pipeline/ directory."
echo "    A temp cloudbuild.yaml is generated to point Cloud Build at our"
echo "    custom Dockerfile path — gcloud builds submit doesn't accept a"
echo "    --file/--dockerfile flag directly."
CB_TMP="$(mktemp -t cloudbuild-discovery.XXXXXX.yaml)"
trap 'rm -f "${CB_TMP}"' EXIT
cat > "${CB_TMP}" <<EOF
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-f', 'pipeline/Dockerfile.discovery', '-t', '${IMAGE}', '.']
images:
  - '${IMAGE}'
EOF
gcloud builds submit \
  --config "${CB_TMP}" \
  --project "${PROJECT}" \
  .

# Task timeout: 8 hours. The 2026-04-29 real run completed Stage 1-3 in ~3.5
# hours including the ~30-minute Tier 3 paid sweep; 8h gives headroom for
# slow hospitals, retries, and Year-2+ growth without auto-aborting.
echo "==> Creating/updating Cloud Run Job ${JOB_NAME}..."
gcloud run jobs create "${JOB_NAME}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --service-account "${PIPELINE_SA}" \
  --task-timeout 28800 \
  --max-retries 0 \
  --memory 4Gi \
  --cpu 2 \
  --set-env-vars "GCP_PROJECT_ID=${PROJECT},BIGQUERY_DATASET=hospital_prices,GCS_MRF_STAGING_BUCKET=mrf-staging,GCS_MRF_ARCHIVE_BUCKET=mrf-archive-clarobill-prd" \
  --project "${PROJECT}" \
  2>/dev/null || \
gcloud run jobs update "${JOB_NAME}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --service-account "${PIPELINE_SA}" \
  --task-timeout 28800 \
  --max-retries 0 \
  --memory 4Gi \
  --cpu 2 \
  --set-env-vars "GCP_PROJECT_ID=${PROJECT},BIGQUERY_DATASET=hospital_prices,GCS_MRF_STAGING_BUCKET=mrf-staging,GCS_MRF_ARCHIVE_BUCKET=mrf-archive-clarobill-prd" \
  --project "${PROJECT}"

echo "==> Granting scheduler SA permission to invoke the discovery job..."
gcloud run jobs add-iam-policy-binding "${JOB_NAME}" \
  --region "${REGION}" \
  --member "serviceAccount:${SCHEDULER_SA}" \
  --role "roles/run.jobsExecutor" \
  --project "${PROJECT}"

_create_or_update_schedule() {
  local name="$1"
  local cron="$2"
  local description="$3"
  echo "==> Creating/updating Cloud Scheduler trigger ${name} (${cron})..."
  gcloud scheduler jobs create http "${name}" \
    --location "${REGION}" \
    --schedule "${cron}" \
    --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT}/jobs/${JOB_NAME}:run" \
    --http-method POST \
    --oauth-service-account-email "${SCHEDULER_SA}" \
    --description "${description}" \
    --project "${PROJECT}" \
    2>/dev/null || \
  gcloud scheduler jobs update http "${name}" \
    --location "${REGION}" \
    --schedule "${cron}" \
    --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT}/jobs/${JOB_NAME}:run" \
    --http-method POST \
    --oauth-service-account-email "${SCHEDULER_SA}" \
    --description "${description}" \
    --project "${PROJECT}"
}

_create_or_update_schedule "${SCHEDULE_FEB_NAME}" "${SCHEDULE_FEB_CRON}" \
  "MRF discovery — February run (catches Jan 1 republish wave)"
_create_or_update_schedule "${SCHEDULE_AUG_NAME}" "${SCHEDULE_AUG_CRON}" \
  "MRF discovery — August run (catches mid-year republish wave)"

echo ""
echo "==> Discovery pipeline deployed."
echo "    Job:        ${JOB_NAME}"
echo "    Schedule 1: ${SCHEDULE_FEB_NAME}  (${SCHEDULE_FEB_CRON} — Feb 1 02:00 UTC)"
echo "    Schedule 2: ${SCHEDULE_AUG_NAME}  (${SCHEDULE_AUG_CRON} — Aug 1 02:00 UTC)"
echo "    Image:      ${IMAGE}"
echo ""
echo "    Manual trigger (uses default args — full annual run, \$450 ceiling):"
echo "      gcloud run jobs execute ${JOB_NAME} --region ${REGION}"
echo ""
echo "    Manual trigger with custom args (e.g. start from a specific stage):"
echo "      gcloud run jobs execute ${JOB_NAME} --region ${REGION} \\"
echo "        --args=--start-stage=stage3_tier3,--run-id=<existing-run-id>"
echo ""
echo "    Verify schedule next-run time:"
echo "      gcloud scheduler jobs describe ${SCHEDULE_NAME} --location ${REGION}"
