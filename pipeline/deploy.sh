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
gcloud builds submit \
  --tag "${IMAGE}" \
  --project "${PROJECT}" \
  pipeline/

echo "==> Creating/updating clarobill-mrf-scraper Cloud Run Job..."
gcloud run jobs create clarobill-mrf-scraper \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --service-account "${PIPELINE_SA}" \
  --task-timeout 3600 \
  --memory 512Mi \
  --cpu 1 \
  --set-env-vars "GCP_PROJECT_ID=${PROJECT},BIGQUERY_DATASET=clarobill_hospital_prices,GCS_MRF_STAGING_BUCKET=clarobill-mrf-staging" \
  --project "${PROJECT}" \
  2>/dev/null || \
gcloud run jobs update clarobill-mrf-scraper \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --service-account "${PIPELINE_SA}" \
  --task-timeout 3600 \
  --memory 512Mi \
  --cpu 1 \
  --set-env-vars "GCP_PROJECT_ID=${PROJECT},BIGQUERY_DATASET=clarobill_hospital_prices,GCS_MRF_STAGING_BUCKET=clarobill-mrf-staging" \
  --project "${PROJECT}"

echo "==> Creating/updating clarobill-mrf-parser Cloud Run Job..."
gcloud run jobs create clarobill-mrf-parser \
  --image "${IMAGE}" \
  --command "python,parse_hospital_mrfs.py" \
  --region "${REGION}" \
  --service-account "${PIPELINE_SA}" \
  --task-timeout 7200 \
  --memory 2Gi \
  --cpu 2 \
  --set-env-vars "GCP_PROJECT_ID=${PROJECT},BIGQUERY_DATASET=clarobill_hospital_prices,GCS_MRF_STAGING_BUCKET=clarobill-mrf-staging" \
  --project "${PROJECT}" \
  2>/dev/null || \
gcloud run jobs update clarobill-mrf-parser \
  --image "${IMAGE}" \
  --command "python,parse_hospital_mrfs.py" \
  --region "${REGION}" \
  --service-account "${PIPELINE_SA}" \
  --task-timeout 7200 \
  --memory 2Gi \
  --cpu 2 \
  --set-env-vars "GCP_PROJECT_ID=${PROJECT},BIGQUERY_DATASET=clarobill_hospital_prices,GCS_MRF_STAGING_BUCKET=clarobill-mrf-staging" \
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

# Scraper runs Tuesday 02:00 UTC — hospitals often update MRFs Mon/Tue after CMS deadlines.
gcloud scheduler jobs create http clarobill-mrf-scraper-weekly \
  --location "${REGION}" \
  --schedule "0 2 * * 2" \
  --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT}/jobs/clarobill-mrf-scraper:run" \
  --http-method POST \
  --oauth-service-account-email "${SCHEDULER_SA}" \
  --project "${PROJECT}" \
  2>/dev/null || \
gcloud scheduler jobs update http clarobill-mrf-scraper-weekly \
  --location "${REGION}" \
  --schedule "0 2 * * 2" \
  --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT}/jobs/clarobill-mrf-scraper:run" \
  --http-method POST \
  --oauth-service-account-email "${SCHEDULER_SA}" \
  --project "${PROJECT}"

# Parser runs Tuesday 06:00 UTC — 4 hours after scraper to let downloads complete.
gcloud scheduler jobs create http clarobill-mrf-parser-weekly \
  --location "${REGION}" \
  --schedule "0 6 * * 2" \
  --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT}/jobs/clarobill-mrf-parser:run" \
  --http-method POST \
  --oauth-service-account-email "${SCHEDULER_SA}" \
  --project "${PROJECT}" \
  2>/dev/null || \
gcloud scheduler jobs update http clarobill-mrf-parser-weekly \
  --location "${REGION}" \
  --schedule "0 6 * * 2" \
  --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT}/jobs/clarobill-mrf-parser:run" \
  --http-method POST \
  --oauth-service-account-email "${SCHEDULER_SA}" \
  --project "${PROJECT}"

echo ""
echo "==> Pipeline deployed."
echo "    Scraper:  runs Tuesdays at 02:00 UTC"
echo "    Parser:   runs Tuesdays at 06:00 UTC"
echo ""
echo "    Manual trigger (for first run / testing):"
echo "      gcloud run jobs execute clarobill-mrf-scraper --region ${REGION}"
echo "      gcloud run jobs execute clarobill-mrf-parser  --region ${REGION}"
