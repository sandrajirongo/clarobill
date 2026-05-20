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
DISCOVERY_IMAGE="${REPO}/mrf-discovery:latest"
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
  --substitutions="_IMAGE=${IMAGE},_DISCOVERY_IMAGE=${DISCOVERY_IMAGE}" \
  --project "${PROJECT}" \
  .

# Task timeout: 16 hours (57600s) — applied uniformly across all jobs.
# All jobs default to 6 tasks. Each task reads CLOUD_RUN_TASK_INDEX and
# processes its shard (hospitals[index::6]). Parallelism defaults to 0
# (unlimited) so all 6 tasks run concurrently.
echo "==> Creating/updating clarobill-mrf-scraper Cloud Run Job..."
gcloud run jobs create clarobill-mrf-scraper \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --service-account "${PIPELINE_SA}" \
  --tasks 6 \
  --task-timeout 57600 \
  --max-retries 0 \
  --memory 8Gi \
  --cpu 2 \
  --set-env-vars "GCP_PROJECT_ID=${PROJECT},BIGQUERY_DATASET=hospital_prices,GCS_MRF_STAGING_BUCKET=mrf-staging,GCS_MRF_ARCHIVE_BUCKET=clarobill-mrf-archive-uscentral" \
  --project "${PROJECT}" \
  2>/dev/null || \
gcloud run jobs update clarobill-mrf-scraper \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --service-account "${PIPELINE_SA}" \
  --tasks 6 \
  --task-timeout 57600 \
  --max-retries 0 \
  --memory 8Gi \
  --cpu 2 \
  --set-env-vars "GCP_PROJECT_ID=${PROJECT},BIGQUERY_DATASET=hospital_prices,GCS_MRF_STAGING_BUCKET=mrf-staging,GCS_MRF_ARCHIVE_BUCKET=clarobill-mrf-archive-uscentral" \
  --project "${PROJECT}"

echo "==> Creating/updating clarobill-mrf-parser Cloud Run Job..."
gcloud run jobs create clarobill-mrf-parser \
  --image "${IMAGE}" \
  --command "python,parse_hospital_mrfs.py" \
  --region "${REGION}" \
  --service-account "${PIPELINE_SA}" \
  --tasks 6 \
  --task-timeout 57600 \
  --max-retries 0 \
  --memory 8Gi \
  --cpu 2 \
  --set-env-vars "GCP_PROJECT_ID=${PROJECT},BIGQUERY_DATASET=hospital_prices,GCS_MRF_STAGING_BUCKET=mrf-staging,GCS_MRF_ARCHIVE_BUCKET=clarobill-mrf-archive-uscentral" \
  --project "${PROJECT}" \
  2>/dev/null || \
gcloud run jobs update clarobill-mrf-parser \
  --image "${IMAGE}" \
  --command "python,parse_hospital_mrfs.py" \
  --region "${REGION}" \
  --service-account "${PIPELINE_SA}" \
  --tasks 6 \
  --task-timeout 57600 \
  --max-retries 0 \
  --memory 8Gi \
  --cpu 2 \
  --set-env-vars "GCP_PROJECT_ID=${PROJECT},BIGQUERY_DATASET=hospital_prices,GCS_MRF_STAGING_BUCKET=mrf-staging,GCS_MRF_ARCHIVE_BUCKET=clarobill-mrf-archive-uscentral" \
  --project "${PROJECT}"

# ---------------------------------------------------------------------------
# Discovery pipeline — full + stage-specific jobs (annual, uses mrf-discovery image)
# ---------------------------------------------------------------------------
DISCOVERY_IMAGE="us-central1-docker.pkg.dev/${PROJECT}/clarobill-pipeline/mrf-discovery:latest"
DISCOVERY_SA="${PIPELINE_SA}"
DISCOVERY_ENVVARS="GCP_PROJECT_ID=${PROJECT},BIGQUERY_DATASET=hospital_prices,GCS_MRF_STAGING_BUCKET=mrf-staging,GCS_MRF_ARCHIVE_BUCKET=clarobill-mrf-archive-uscentral,DISCOVERY_RUN_ID="

# Helper: create-or-update a discovery stage job.
# Usage: _create_or_update_discovery_job <job-name> <start-stage> <stop-stage> <memory>
#
# Uses gcloud run jobs replace with a YAML manifest instead of --args so that
# args are passed as a proper list. The gcloud --args flag treats the value as
# a comma-separated list and rejects duplicate tokens — which breaks stage1 and
# stage4 where --start-stage and --stop-after are the same value.
_create_or_update_discovery_job() {
  local name="$1"
  local start="$2"
  local stop="$3"
  local mem="$4"
  echo "==> Creating/updating ${name}..."
  local tmpfile
  tmpfile=$(mktemp /tmp/discovery-job-XXXX.yaml)
  cat > "${tmpfile}" <<YAML
apiVersion: run.googleapis.com/v1
kind: Job
metadata:
  name: ${name}
  namespace: ${PROJECT}
  labels:
    cloud.googleapis.com/location: ${REGION}
spec:
  template:
    spec:
      taskCount: 6
      template:
        spec:
          serviceAccountName: ${DISCOVERY_SA}
          timeoutSeconds: "57600"
          maxRetries: 0
          containers:
          - image: ${DISCOVERY_IMAGE}
            command:
            - python
            args:
            - /app/scripts/discover_mrf_pipeline.py
            - --project
            - ${PROJECT}
            - --start-stage
            - ${start}
            - --stop-after
            - ${stop}
            env:
            - name: GCP_PROJECT_ID
              value: "${PROJECT}"
            - name: BIGQUERY_DATASET
              value: hospital_prices
            - name: GCS_MRF_STAGING_BUCKET
              value: mrf-staging
            - name: GCS_MRF_ARCHIVE_BUCKET
              value: clarobill-mrf-archive-uscentral
            - name: DISCOVERY_RUN_ID
              value: ""
            resources:
              limits:
                cpu: "2"
                memory: ${mem}
YAML
  gcloud run jobs replace "${tmpfile}" --region "${REGION}" --project "${PROJECT}"
  rm -f "${tmpfile}"
}

# Full pipeline (annual Feb 15 run — all stages including paid Tier 3).
# Run-id is auto-generated if DISCOVERY_RUN_ID env var is not set on the job.
echo "==> Creating/updating clarobill-mrf-discovery-annual (full pipeline)..."
gcloud run jobs create clarobill-mrf-discovery-annual \
  --image "${DISCOVERY_IMAGE}" \
  --command "python" \
  --args "/app/scripts/discover_mrf_pipeline.py,--project,${PROJECT}" \
  --region "${REGION}" \
  --service-account "${DISCOVERY_SA}" \
  --tasks 6 \
  --task-timeout 57600 \
  --max-retries 0 \
  --memory 4Gi \
  --cpu 2 \
  --set-env-vars "${DISCOVERY_ENVVARS}" \
  --project "${PROJECT}" \
  2>/dev/null || \
gcloud run jobs update clarobill-mrf-discovery-annual \
  --image "${DISCOVERY_IMAGE}" \
  --command "python" \
  --args "/app/scripts/discover_mrf_pipeline.py,--project,${PROJECT}" \
  --region "${REGION}" \
  --service-account "${DISCOVERY_SA}" \
  --tasks 6 \
  --task-timeout 57600 \
  --max-retries 0 \
  --memory 4Gi \
  --cpu 2 \
  --set-env-vars "${DISCOVERY_ENVVARS}" \
  --project "${PROJECT}"

# Stage-specific jobs for partial re-runs.
# All require DISCOVERY_RUN_ID to be set on the job before execution (except Stage 1,
# which generates a fresh run_id when DISCOVERY_RUN_ID is empty).
# Update run_id after each annual run:
#   gcloud run jobs update <job> --update-env-vars DISCOVERY_RUN_ID=<new-id> --region us-central1
_create_or_update_discovery_job clarobill-mrf-discovery-stage1 stage1_cms      stage1_cms      4Gi
_create_or_update_discovery_job clarobill-mrf-discovery-stage2 stage2_pos      stage2_wikidata 4Gi
_create_or_update_discovery_job clarobill-mrf-discovery-stage3 stage3_tier1    stage3_tier3    4Gi
_create_or_update_discovery_job clarobill-mrf-discovery-stage4 stage4_mrf_urls stage4_mrf_urls 4Gi

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
echo "    Manual trigger (6 tasks by default — all run concurrently):"
echo "      gcloud run jobs execute clarobill-mrf-scraper --region ${REGION}"
echo "      gcloud run jobs execute clarobill-mrf-parser  --region ${REGION}"
echo "      gcloud run jobs execute clarobill-mrf-discovery-stage4 \\"
echo "        --update-env-vars DISCOVERY_RUN_ID=<run-id> --region ${REGION}"
