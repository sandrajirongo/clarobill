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
# Annual + quarterly schedule (decided 2026-04-30 — see
# docs/decisions/2026-04-30-pipeline-cadence.md):
#
#   - Annual full discovery on Feb 15 (gives hospitals 6 weeks past the
#     Jan 1 CMS republish deadline to fix any errors before we crawl).
#   - Quarterly gap-fill on the 15th of Feb / May / Aug / Nov — re-runs
#     only the hospitals where validated_mrf_urls is still NULL after the
#     prior pass. The Feb 15 quarterly anchor coincides with the annual
#     run; same job, same date, --gap-fill-only is implicit on the annual
#     run because it sweeps everyone.
#   - Tier 3 (PAID Google Places) only runs in the annual; quarterly
#     gap-fills skip it via --gap-fill-only without --include-tier3.
SCHEDULE_ANNUAL_NAME="clarobill-mrf-discovery-annual"
SCHEDULE_QUARTERLY_NAME="clarobill-mrf-discovery-quarterly"
SCHEDULE_ANNUAL_CRON="0 2 15 2 *"          # 02:00 UTC, Feb 15
SCHEDULE_QUARTERLY_CRON="0 2 15 5,8,11 *"  # 02:00 UTC, May/Aug/Nov 15
# Note: Feb 15 is intentionally NOT in the quarterly cron — the annual run
# on Feb 15 already covers everyone, including the gap-fill cohort.

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
# Why split --command and --args:
#   The Dockerfile's CMD bakes in everything as args. When a user passes
#   --args at execute time, Cloud Run REPLACES the args portion entirely.
#   If the script path is part of args, that override accidentally drops
#   the script — the container runs `python --start-stage=...` and crashes
#   with no Python output (this happened in execution g66ns on 2026-04-30).
#   Putting the script path in --command keeps it stable across overrides;
#   the orchestrator's argparse handles --project's default itself so an
#   override that drops --project is safe.
gcloud run jobs create "${JOB_NAME}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --service-account "${PIPELINE_SA}" \
  --task-timeout 28800 \
  --max-retries 0 \
  --memory 4Gi \
  --cpu 2 \
  --command "python,/app/scripts/discover_mrf_pipeline.py" \
  --args "--project,${PROJECT}" \
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
  --command "python,/app/scripts/discover_mrf_pipeline.py" \
  --args "--project,${PROJECT}" \
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
  local body="$4"  # JSON body for the run request — controls --args overrides
  echo "==> Creating/updating Cloud Scheduler trigger ${name} (${cron})..."
  gcloud scheduler jobs create http "${name}" \
    --location "${REGION}" \
    --schedule "${cron}" \
    --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT}/jobs/${JOB_NAME}:run" \
    --http-method POST \
    --oauth-service-account-email "${SCHEDULER_SA}" \
    --description "${description}" \
    --message-body "${body}" \
    --project "${PROJECT}" \
    2>/dev/null || \
  gcloud scheduler jobs update http "${name}" \
    --location "${REGION}" \
    --schedule "${cron}" \
    --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT}/jobs/${JOB_NAME}:run" \
    --http-method POST \
    --oauth-service-account-email "${SCHEDULER_SA}" \
    --description "${description}" \
    --message-body "${body}" \
    --project "${PROJECT}"
}

# Annual: no --args override — runs every stage including Tier 3 (paid).
_create_or_update_schedule "${SCHEDULE_ANNUAL_NAME}" "${SCHEDULE_ANNUAL_CRON}" \
  "MRF discovery — ANNUAL Feb 15 full run (Stages 1-4, includes Tier 3 paid sweep)" \
  "{}"

# Quarterly gap-fill: pass --gap-fill-only via container args override.
# Cloud Scheduler --message-body JSON shape for run-jobs override:
#   { "overrides": { "containerOverrides": [{ "args": ["--gap-fill-only"] }] } }
_create_or_update_schedule "${SCHEDULE_QUARTERLY_NAME}" "${SCHEDULE_QUARTERLY_CRON}" \
  "MRF discovery — QUARTERLY gap-fill (May/Aug/Nov 15) — only hospitals still missing URLs, free stages only" \
  '{"overrides":{"containerOverrides":[{"args":["--gap-fill-only"]}]}}'

# Old Feb 1 + Aug 1 schedules are superseded — delete them if they exist
# from earlier deploys so they don't double-trigger.
for old in clarobill-mrf-discovery-feb clarobill-mrf-discovery-aug; do
  echo "==> Removing legacy schedule ${old} if present..."
  gcloud scheduler jobs delete "${old}" \
    --location "${REGION}" --project "${PROJECT}" --quiet 2>/dev/null || true
done

echo ""
echo "==> Discovery pipeline deployed."
echo "    Job:           ${JOB_NAME}"
echo "    Annual run:    ${SCHEDULE_ANNUAL_NAME}    (${SCHEDULE_ANNUAL_CRON} — Feb 15 02:00 UTC)"
echo "    Quarterly:     ${SCHEDULE_QUARTERLY_NAME} (${SCHEDULE_QUARTERLY_CRON} — May/Aug/Nov 15 02:00 UTC)"
echo "    Image:         ${IMAGE}"
echo ""
echo "    Manual triggers:"
echo "      # Full annual run (Stages 1-4 + Tier 3 paid)"
echo "      gcloud run jobs execute ${JOB_NAME} --region ${REGION}"
echo ""
echo "      # Gap-fill (free stages only, skips Tier 3)"
echo "      gcloud run jobs execute ${JOB_NAME} --region ${REGION} --args=--gap-fill-only"
echo ""
echo "      # Re-run only Tier 3 with a fresh budget on a specific run"
echo "      gcloud run jobs execute ${JOB_NAME} --region ${REGION} \\"
echo "        --args=--start-stage=stage3_tier3,--run-id=<existing-run-id>"
echo ""
echo "      # Re-run only Stage 4 (URL crawler) on an existing run"
echo "      gcloud run jobs execute ${JOB_NAME} --region ${REGION} \\"
echo "        --args=--start-stage=stage4_mrf_urls,--run-id=<existing-run-id>"
echo ""
echo "    Verify schedule next-run times:"
echo "      gcloud scheduler jobs describe ${SCHEDULE_ANNUAL_NAME}    --location ${REGION}"
echo "      gcloud scheduler jobs describe ${SCHEDULE_QUARTERLY_NAME} --location ${REGION}"
