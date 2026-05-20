#!/usr/bin/env bash
# Create and configure gs://clarobill-mrf-archive-uscentral — the immutable historical
# archive of every hospital MRF file we have ever downloaded.
#
# Bucket name note: GCS bucket names are globally unique across all of GCP, so
# the unsuffixed `mrf-archive` was already taken. We use the product-prefix
# convention (`clarobill-mrf-archive-uscentral`) matching the actual bucket
# created for this project.
#
# Layout:
#   gs://clarobill-mrf-archive-uscentral/pricing-year={year}/{npi-or-uuid}/{sha256_first16}.{ext}
#   gs://clarobill-mrf-archive-uscentral/pricing-year={year}/{npi-or-uuid}/{sha256_first16}.meta.json
#
# Why a separate bucket from mrf-staging:
#   - mrf-staging holds ephemeral working files for the weekly scraper/parser.
#   - mrf-archive holds immutable evidence behind dispute letters, retained
#     forever. Mixing the two in one bucket makes lifecycle policies dangerous.
#
# Storage class: COLDLINE
#   - Files are written once, read rarely (only when re-parsing or re-auditing
#     a historical bill). Coldline at $0.004/GB-mo vs Standard at $0.020/GB-mo
#     is a 5x saving for our access pattern.
#   - First-byte latency is millisecond-class; only retrieval cost is higher.
#   - 30-day minimum storage duration (we never delete anyway, so irrelevant).
#
# Why "soft delete" stays at the default 7 days, not zero:
#   Soft delete protects against accidental deletion (operator error, malicious
#   service-account compromise). 7 days is the GCP default and adds zero cost
#   on objects we never delete in the first place.
#
# Why versioning is enabled:
#   If we ever overwrite an archive object (we shouldn't, but bugs happen),
#   versioning preserves the original. Combined with Object Lock-equivalent
#   IAM (no service account has storage.objects.delete), this is belt-and-
#   suspenders evidence preservation.
#
# Usage:
#   bash scripts/mrf_discovery/setup_archive_bucket.sh           # dry run (default)
#   APPLY=1 bash scripts/mrf_discovery/setup_archive_bucket.sh   # actually create

set -euo pipefail

PROJECT="${GCP_PROJECT_ID:-clarobill-prd}"
BUCKET="clarobill-mrf-archive-uscentral"
LOCATION="US"             # multi-region — same as BigQuery dataset, no egress cost on cross-service reads
STORAGE_CLASS="COLDLINE"
PIPELINE_SA="clarobill-pipeline-sa@${PROJECT}.iam.gserviceaccount.com"

APPLY="${APPLY:-0}"

run() {
    if [[ "${APPLY}" == "1" ]]; then
        echo ">>> $*"
        eval "$@"
    else
        echo "[dry-run] $*"
    fi
}

echo "==> Project:      ${PROJECT}"
echo "==> Bucket:       gs://${BUCKET}"
echo "==> Location:     ${LOCATION}"
echo "==> Storage:      ${STORAGE_CLASS}"
echo "==> Pipeline SA:  ${PIPELINE_SA}"
if [[ "${APPLY}" != "1" ]]; then
    echo "==> Mode:         DRY RUN (set APPLY=1 to execute)"
fi
echo ""

if gcloud storage buckets describe "gs://${BUCKET}" --project "${PROJECT}" >/dev/null 2>&1; then
    echo "==> Bucket already exists, will reconfigure (idempotent)."
else
    echo "==> Creating bucket gs://${BUCKET}..."
    run gcloud storage buckets create "gs://${BUCKET}" \
        --project "${PROJECT}" \
        --location "${LOCATION}" \
        --default-storage-class "${STORAGE_CLASS}" \
        --uniform-bucket-level-access \
        --public-access-prevention
fi

echo "==> Enabling object versioning..."
run gcloud storage buckets update "gs://${BUCKET}" \
    --project "${PROJECT}" \
    --versioning

echo "==> Setting labels..."
run gcloud storage buckets update "gs://${BUCKET}" \
    --project "${PROJECT}" \
    --update-labels=purpose=mrf-historical-archive,owner=clarobill-pipeline,immutable=true

# Lifecycle rule: NoncurrentTimeBeforeTransition + DELETE on noncurrent versions
# only after 90 days. Live (current) versions never expire — that is the whole
# point of this bucket. The noncurrent cleanup just prevents an unbounded version
# graveyard if a buggy archiver ever overwrites the same object repeatedly.
LIFECYCLE_TMP="$(mktemp -t mrf-archive-lifecycle.XXXXXX.json)"
cat > "${LIFECYCLE_TMP}" <<'JSON'
{
  "lifecycle": {
    "rule": [
      {
        "action": { "type": "Delete" },
        "condition": {
          "daysSinceNoncurrentTime": 90,
          "numNewerVersions": 5
        }
      }
    ]
  }
}
JSON
echo "==> Applying lifecycle rule (delete noncurrent versions older than 90d, keep last 5)..."
run gcloud storage buckets update "gs://${BUCKET}" \
    --project "${PROJECT}" \
    --lifecycle-file "${LIFECYCLE_TMP}"
[[ "${APPLY}" == "1" ]] && rm -f "${LIFECYCLE_TMP}" || echo "    (lifecycle JSON kept at ${LIFECYCLE_TMP} for inspection)"

# IAM: pipeline SA gets objectCreator (write) + objectViewer (read) but NOT
# objectAdmin — the absence of objects.delete is the immutability guarantee.
# If we ever need to clean up, a human with bucketAdmin can do it explicitly.
echo "==> Granting roles to pipeline SA..."
run gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
    --project "${PROJECT}" \
    --member "serviceAccount:${PIPELINE_SA}" \
    --role "roles/storage.objectCreator"

run gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
    --project "${PROJECT}" \
    --member "serviceAccount:${PIPELINE_SA}" \
    --role "roles/storage.objectViewer"

echo ""
echo "==> Done."
if [[ "${APPLY}" != "1" ]]; then
    echo "    This was a DRY RUN — no changes were made."
    echo "    To apply, re-run with APPLY=1:"
    echo "      APPLY=1 bash scripts/mrf_discovery/setup_archive_bucket.sh"
else
    echo "    Bucket gs://${BUCKET} is ready for archive writes."
    echo ""
    echo "    Verify:"
    echo "      gcloud storage buckets describe gs://${BUCKET} --project ${PROJECT}"
fi
