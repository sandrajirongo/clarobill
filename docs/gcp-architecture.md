# ClaroBill — GCP Architecture Reference

This document covers every GCP service in use, the data flow between them, the
service accounts and the specific permissions each holds, and why each permission
is required. It is the authoritative reference for infrastructure setup and IAM.

---

## GCP Project

**Project ID:** `clarobill-prd`  
**Primary region:** `us-central1`

---

## Architecture Overview

```
                          ┌─────────────────────────────────┐
                          │         Cloud Scheduler          │
                          │  clarobill-mrf-scraper-weekly   │  Tue 02:00 UTC
                          │  clarobill-mrf-parser-weekly    │  Tue 06:00 UTC
                          └──────────────┬──────────────────┘
                                         │ HTTP POST (OAuth)
                                         ▼
                          ┌─────────────────────────────────┐
                          │         Cloud Run Jobs           │
                          │                                 │
                          │  clarobill-mrf-scraper          │──► scrapes hospital
                          │  clarobill-mrf-parser           │    websites & MRFs
                          └──────────┬──────────────────────┘
                                     │
                  ┌──────────────────┼──────────────────┐
                  ▼                  ▼                   ▼
        ┌──────────────┐   ┌──────────────────┐  ┌─────────────┐
        │  GCS Bucket  │   │    BigQuery       │  │  Artifact   │
        │  mrf-staging │   │ hospital_prices   │  │  Registry   │
        │              │   │                   │  │  (images)   │
        │ raw/{slug}/  │   │ hospital_directory│  └─────────────┘
        │ parsed/{npi}/│   │ hospital_charges  │
        └──────────────┘   └──────────────────┘

                          ┌─────────────────────────────────┐
                          │       Cloud Run Service          │
                          │   clarobill-engine (FastAPI)     │──► patient bill analysis
                          └──────────────────────────────────┘    OCR + rules engine
                                         ▲
                          ┌──────────────┴──────────────────┐
                          │         Cloud Build              │
                          │  trigger: engine-deploy-on-push  │
                          │  fires on push to main           │
                          │  when apps/engine/** changes     │
                          └──────────────────────────────────┘
                                         ▲
                          ┌──────────────┴──────────────────┐
                          │  GitHub: sandrajirongo/clarobill │
                          │  branch: main                    │
                          └──────────────────────────────────┘
                                         │
                          ┌──────────────▼──────────────────┐
                          │         Cloud Vision API         │
                          │         (OCR extraction)         │
                          └─────────────────────────────────┘
```

---

## Services

### 1. Cloud Run Jobs — MRF Pipeline

Two jobs share a single Docker image built from `pipeline/`. The image is stored
in Artifact Registry and referenced by digest on each deploy.

#### `clarobill-mrf-scraper`

**Purpose:** Discover and download hospital MRF (Machine Readable File) price
transparency files from hospital websites to GCS.

**What it does (per run):**
1. Reads all hospitals from `hospital_directory` BigQuery table (NPI, name, mrf_url)
2. For each hospital with an mrf_url: sends HTTP HEAD to check `Last-Modified`
3. Skips the file if `Last-Modified` matches the stored value (unchanged since last run)
4. Downloads changed/new files to `gs://mrf-staging/raw/{name_slug}/{timestamp}{.ext}`
5. Stores hospital context (name, mrf_url, state) as GCS blob metadata for the parser
6. After all downloads: bulk-updates `hospital_directory.last_modified` via BigQuery MERGE

**Env vars:**
```
GCP_PROJECT_ID=clarobill-prd
BIGQUERY_DATASET=hospital_prices
GCS_MRF_STAGING_BUCKET=mrf-staging
```

**Resources:** 4Gi memory, 2 vCPU, 4h task timeout, max-retries 0  
**Scaling:** `--tasks N` distributes hospitals by index (`hospitals[task_index::N]`)

**Runs:** Tuesdays 02:00 UTC via Cloud Scheduler. Also triggered manually before
a parser run when re-processing is needed.

---

#### `clarobill-mrf-parser`

**Purpose:** Parse downloaded MRF JSON files and load normalised charge data into
BigQuery `hospital_charges`.

**What it does (per blob in `gs://mrf-staging/raw/`):**
1. Reads hospital context from GCS blob metadata (name, mrf_url, state)
2. Extracts the hospital NPI from the MRF JSON root (authoritative — more reliable
   than the discovery-pipeline-resolved NPI in hospital_directory, which comes from
   NPPES Registry API name/state matching and may have low-confidence matches)
3. Stream-parses the CMS JSON schema v2.0.0 MRF using `hospital_mrf_utils.stream_charges_v2()`
4. Writes normalised charge rows (NPI, code, code_type, gross_charge, payer_name,
   plan_name, negotiated_charge, etc.) as NDJSON to `gs://mrf-staging/parsed/{npi}/`
5. DELETEs existing rows for this NPI from `hospital_charges` (idempotent — safe to re-run)
6. Loads the NDJSON staging blob → `hospital_charges` via BigQuery load job
7. Updates `hospital_directory.last_scraped` and backfills `hospital_npi` if null
8. Deletes the raw MRF blob (prevents double-processing if runs overlap)

**Env vars:** Same as scraper  
**Resources:** 4Gi memory, 2 vCPU, 4h task timeout, max-retries 0  
**Scaling:** Same `--tasks N` sharding as scraper (blobs distributed by index)

**Runs:** Tuesdays 06:00 UTC (4 hours after scraper to let downloads complete).

---

### 2. Cloud Scheduler

Triggers the MRF pipeline jobs on a weekly schedule. Uses HTTP POST to the
Cloud Run Jobs API with OAuth authentication.

| Job name | Schedule | Target |
|----------|----------|--------|
| `clarobill-mrf-scraper-weekly` | `0 2 * * 2` (Tue 02:00 UTC) | clarobill-mrf-scraper |
| `clarobill-mrf-parser-weekly` | `0 6 * * 2` (Tue 06:00 UTC) | clarobill-mrf-parser |

**Why Tuesdays:** Hospitals typically update their MRF files on Monday or Tuesday
after CMS quarterly deadlines. Running Tuesday morning maximises the probability
of catching fresh updates.

---

### 3. Cloud Storage — `mrf-staging`

**Bucket:** `gs://mrf-staging` (us-central1, Standard storage class)

**Layout:**
```
mrf-staging/
  raw/
    {hospital-name-slug}/
      {scraped_at_utc_iso}.json.gz     ← downloaded MRF (gzip if original was gzipped)
      {scraped_at_utc_iso}.json        ← uncompressed MRF
  parsed/
    {hospital_npi}/
      {hospital_npi}_{scraped_at}.ndjson  ← normalised charge rows for BQ load
```

**Object metadata on raw blobs:**
- `hospital_name` — human-readable name from `hospital_directory` (originally CMS PI list, enriched by POS file)
- `mrf_url` — source URL
- `state` — hospital state (for future locality filtering)

**Lifecycle:** Raw blobs are deleted by the parser after successful load.
Parsed NDJSON blobs are retained for 7 days as audit trail, then deleted by
a lifecycle rule.

---

### 4. BigQuery — `hospital_prices` dataset

**Project:** `clarobill-prd`  
**Dataset:** `hospital_prices`  
**Location:** US (multi-region)

#### Table: `hospital_directory`

Populated by the annual CMS-direct discovery pipeline (`scripts/mrf_discovery/stage*.py`).
Updated by the weekly scraper (`last_modified`) and parser (`hospital_npi`, `last_scraped`)
jobs. Pivoted on 2026-04-28 from a third-party Payerset scrape (~3,100 hospitals) to
CMS-direct discovery (~13,833 US civilian hospitals). See
`docs/decisions/2026-04-28-cms-direct-mrf-discovery.md`.

| Column | Type | Description |
|--------|------|-------------|
| hospital_npi | STRING | CMS NPI — primary lookup key for charge queries |
| hospital_name | STRING | Human-readable name |
| mrf_url | STRING | URL of the hospital's MRF file |
| state | STRING | Two-letter state abbreviation |
| last_modified | STRING | HTTP Last-Modified from most recent successful scrape |
| last_scraped | TIMESTAMP | When the parser last processed this hospital |

#### Table: `hospital_charges`

The core price transparency table. One row per procedure × payer × plan combination
per hospital. Loaded by the parser from CMS MRF v2.0.0 files.

| Column | Type | Description |
|--------|------|-------------|
| hospital_npi | STRING | Joins to hospital_directory |
| code_type | STRING | "CPT", "HCPCS", "MS-DRG", "RC", etc. |
| code | STRING | Procedure code |
| description | STRING | Procedure description from MRF |
| gross_charge | FLOAT | Chargemaster (list) price — HOSPITAL_CHARGE_OUTLIER benchmark |
| discounted_cash_price | FLOAT | Self-pay negotiated rate |
| min_negotiated | FLOAT | Minimum across all payer contracts |
| max_negotiated | FLOAT | Maximum across all payer contracts |
| payer_name | STRING | Insurer name — used for NEGOTIATED_RATE_EXCEEDED lookup |
| plan_name | STRING | Plan name — used for NEGOTIATED_RATE_EXCEEDED lookup |
| negotiated_charge | FLOAT | Exact contracted rate for this payer/plan |
| negotiated_type | STRING | "negotiated" \| "derived" \| "percentage" \| "range" |
| setting | STRING | "inpatient" \| "outpatient" \| null |
| effective_date | DATE | Date this rate became effective |
| scraped_at | TIMESTAMP | When this row was loaded |

**Query patterns used by the rules engine:**
1. `WHERE hospital_npi = ? AND code IN UNNEST(?) AND gross_charge > 0 GROUP BY code` → gross charges
2. `WHERE hospital_npi = ? AND LOWER(payer_name) LIKE ? AND LOWER(plan_name) LIKE ? AND code IN UNNEST(?) AND negotiated_type IN ('negotiated','derived')` → negotiated rates

---

### 5. Artifact Registry

#### `clarobill-pipeline`

**Repository:** `us-central1-docker.pkg.dev/clarobill-prd/clarobill-pipeline`  
**Image:** `mrf-pipeline:latest`

Stores the Docker image used by both Cloud Run Jobs. The image is built by
`gcloud builds submit` in Cloud Build and pushed here. Both jobs are updated
to use the new image digest after each build.

#### `cloud-run-source-deploy`

**Repository:** `us-central1-docker.pkg.dev/clarobill-prd/cloud-run-source-deploy`  
**Image:** `clarobill-engine:$COMMIT_SHA` and `clarobill-engine:latest`

Stores the FastAPI engine image. Built and pushed automatically by the Cloud Build
trigger on every push to main that touches `apps/engine/**`. Both a commit-SHA tag
(for rollback) and `latest` are pushed on each build.

### 6. Cloud Build — Engine Auto-Deploy Trigger

**Trigger name:** `rmgpgab-clarobill-engine-us-central1-sandrajirongo-clarobillwrs`  
**Event:** Push to branch `^main$`  
**Included files filter:** `apps/engine/**`  
**Build config:** `apps/engine/cloudbuild.yaml`  
**Repository:** `sandrajirongo/clarobill` (GitHub App connection)

**What it does on each trigger:**
1. Builds the Docker image from `apps/engine/` as the build context
2. Pushes `clarobill-engine:$COMMIT_SHA` and `clarobill-engine:latest` to `cloud-run-source-deploy`
3. Deploys `clarobill-engine:$COMMIT_SHA` to the `clarobill-engine` Cloud Run service in `us-central1`

**Rollback:** To roll back to a specific commit, deploy the commit-SHA image manually:
```bash
gcloud run services update clarobill-engine \
  --image us-central1-docker.pkg.dev/clarobill-prd/cloud-run-source-deploy/clarobill-engine:<COMMIT_SHA> \
  --region us-central1
```

---

### 6. Cloud Vision API

Used by the FastAPI engine (`clarobill-vision-sa`) for OCR extraction of
uploaded medical bills. Each bill upload triggers one or more Vision API
annotate requests (one per page for PDFs, one per image).

---

---

## Service Accounts

ClaroBill uses three service accounts, each with the minimum permissions
required for its function. No service account has project-level Owner or Editor.

---

### `clarobill-pipeline-sa`

**Email:** `clarobill-pipeline-sa@clarobill-prd.iam.gserviceaccount.com`
**Used by:**
- Cloud Run Jobs (`clarobill-mrf-scraper`, `clarobill-mrf-parser`) — weekly
- MRF discovery scripts (`scripts/mrf_discovery/stage*.py`) — currently manual; will become a Cloud Run Job (`clarobill-mrf-discovery-annual`) at Phase 3g

| Permission | Role | Why required |
|------------|------|-------------|
| Read from BigQuery | `roles/bigquery.dataViewer` on `hospital_prices` dataset | Scraper reads `hospital_directory`; discovery stages read `mrf_discovery_checkpoint` |
| Write/update BigQuery | `roles/bigquery.dataEditor` on `hospital_prices` dataset | Scraper writes MERGE updates to `hospital_directory`; parser DELETEs + loads rows into `hospital_charges`; discovery stages write to `mrf_discovery_checkpoint`, `mrf_archive_index`, `mrf_discovery_runs` |
| Run BigQuery jobs | `roles/bigquery.jobUser` on project | Required to execute queries and load jobs; without this, BigQuery API calls are rejected even with data permissions |
| Read GCS objects | `roles/storage.objectViewer` on `mrf-staging` bucket | Parser reads raw MRF blobs from `gs://mrf-staging/raw/`; discovery stages read NPPES and Places API caches |
| Write GCS objects | `roles/storage.objectCreator` on `mrf-staging` bucket | Scraper writes downloaded MRF files; parser writes NDJSON staging blobs; discovery stages write API caches |
| Delete GCS objects | `roles/storage.objectAdmin` on `mrf-staging` bucket | Parser deletes raw blobs after successful load to prevent double-processing. objectAdmin is used because objectCreator + objectViewer does not include delete; objectAdmin scoped to this bucket only. |
| Read MRF archive | `roles/storage.objectViewer` on `mrf-archive-clarobill-prd` bucket | Phase 4 parser reads archived MRFs to populate `hospital_charges` (planned). |
| Write MRF archive | `roles/storage.objectCreator` on `mrf-archive-clarobill-prd` bucket | Phase 4 scraper streams downloaded MRFs to immutable archive. **Does NOT have `objects.delete` on this bucket — that is the immutability guarantee.** |
| Read Places API key | `roles/secretmanager.secretAccessor` on secret `google-places-api-key` only | Stage 3 Tier 3 reads the Google Places API key at startup. Scoped to the single secret; does NOT grant access to other secrets in the project. |
| Call Google Places API | (no IAM role — API key auth) | Places API uses the API key, not service-account credentials. The key authorises billed calls; the SA's only role is reading the key from Secret Manager. |

**Does NOT have:** Cloud Run invoker, Scheduler invoker, Vision API access,
Supabase credentials, MRF archive delete, any cross-project permissions, or
access to any Secret Manager secret other than `google-places-api-key`.

---

### `clarobill-scheduler-sa`

**Email:** `clarobill-scheduler-sa@clarobill-prd.iam.gserviceaccount.com`  
**Used by:** Cloud Scheduler

| Permission | Role | Why required |
|------------|------|-------------|
| Invoke Cloud Run Jobs | `roles/run.jobsExecutor` on `clarobill-mrf-scraper` and `clarobill-mrf-parser` | Cloud Scheduler makes an authenticated HTTP POST to the Cloud Run Jobs API. Without this binding on each specific job, the request is rejected with 403. |
| Generate OAuth tokens | Automatic — Scheduler uses the SA to sign HTTP requests | No explicit grant needed; Scheduler handles this internally when the SA is configured on the Scheduler job. |

**Does NOT have:** BigQuery access, GCS access, Cloud Vision access, or any
project-level IAM role. Scope is strictly limited to triggering the two jobs.

---

### Cloud Build Service Account

**Email:** `1034973715010@cloudbuild.gserviceaccount.com`  
**Used by:** Cloud Build trigger (`engine-deploy-on-push`)

| Permission | Role | Why required |
|------------|------|-------------|
| Deploy to Cloud Run | `roles/run.developer` on project | Required to call `gcloud run services update` in the build steps. Without this the deploy step returns 403. |
| Act as engine runtime SA | `roles/iam.serviceAccountUser` on `clarobill-vision-sa` | Cloud Run requires the deployer to have impersonation rights over the service's runtime SA. Without this the deploy step fails with a permission error even if `run.developer` is granted. |

**Does NOT have:** BigQuery access, GCS access, Supabase credentials, or Scheduler permissions.

---

### `clarobill-vision-sa`

**Email:** `clarobill-vision-sa@clarobill-prd.iam.gserviceaccount.com`  
**Used by:** FastAPI engine (Cloud Run service `clarobill-engine`)

| Permission | Role | Why required |
|------------|------|-------------|
| Call Cloud Vision API | `roles/cloudvision.serviceAgent` or `roles/ml.serviceAgent` on project | Required to call `vision.googleapis.com/annotate`. The Vision API uses Application Default Credentials; without this role the API returns 403. |
| Query BigQuery (hospital charges) | `roles/bigquery.dataViewer` on `hospital_prices` dataset | Engine queries `hospital_charges` for gross charge and negotiated rate lookups during bill analysis. |
| Run BigQuery jobs | `roles/bigquery.jobUser` on project | Required to execute the SELECT queries against hospital_charges. |

**Does NOT have:** GCS write access, BigQuery data write access, Cloud Run
invoker, or Scheduler permissions. It reads BigQuery data and calls Vision API
only.

**Credential management:** The engine runs on Cloud Run with this SA as the runtime
service account. Application Default Credentials are provided automatically by Cloud
Run — no JSON key file needed. The SA is never stored in the repo or in environment
variables.

---

## IAM Summary Table

| Service Account | BigQuery read | BigQuery write | BigQuery jobs | GCS read | GCS write | GCS delete | Cloud Vision | Run Jobs invoker | Places API key (Secret Manager) |
|-----------------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `clarobill-pipeline-sa` | ✓ | ✓ | ✓ | ✓ | ✓ | mrf-staging only | — | — | ✓ |
| `clarobill-scheduler-sa` | — | — | — | — | — | — | — | ✓ | — |
| `clarobill-vision-sa` | ✓ | — | ✓ | — | — | — | ✓ | — | — |

**Notes on the GCS-delete column:** `clarobill-pipeline-sa` can delete from `mrf-staging` (working files; parser cleans up after load) but **NOT** from `mrf-archive-clarobill-prd` (immutable evidence vault). The absence of delete capability on the archive bucket is the structural immutability guarantee — a bug, a compromised key, or an accidental rm cannot destroy archived MRFs. To delete from the archive, a human with `bucketAdmin` has to do it explicitly.

**Notes on Places API key:** The pipeline SA reads the API key from Secret Manager via `roles/secretmanager.secretAccessor` scoped to the single secret `google-places-api-key`. The key authorises Places API calls (billed against `clarobill-prd`). Calls are made with `X-Goog-Api-Key` header; the SA itself has no Places-specific IAM role.

---

## Pipeline Data Flow (End to End)

```
1. Cloud Scheduler fires Tuesday 02:00 UTC
   └── clarobill-scheduler-sa POSTs to Cloud Run Jobs API
       └── clarobill-mrf-scraper starts (1–6 tasks)

2. Scraper (clarobill-pipeline-sa)
   ├── Reads hospital_directory from BigQuery (mrf_url, last_modified per hospital)
   ├── Shards hospital list by CLOUD_RUN_TASK_INDEX if --tasks > 1
   ├── For each hospital:
   │   ├── HEAD request to mrf_url → check Last-Modified header
   │   ├── Skip if Last-Modified unchanged (delta-only downloads)
   │   └── Download → write to gs://mrf-staging/raw/{slug}/{timestamp}.json[.gz]
   │       with metadata: hospital_name, mrf_url, state
   └── MERGE updates to hospital_directory.last_modified (task-specific staging table)

3. Cloud Scheduler fires Tuesday 06:00 UTC
   └── clarobill-scheduler-sa POSTs to Cloud Run Jobs API
       └── clarobill-mrf-parser starts (1–6 tasks)

4. Parser (clarobill-pipeline-sa)
   ├── Lists all blobs under gs://mrf-staging/raw/
   ├── Shards blob list by CLOUD_RUN_TASK_INDEX if --tasks > 1
   ├── For each blob:
   │   ├── Reads hospital context from blob metadata
   │   ├── Extracts NPI from MRF JSON root
   │   ├── Stream-parses CMS MRF v2.0.0 (gross charges + per-payer negotiated rates)
   │   ├── Writes NDJSON to gs://mrf-staging/parsed/{npi}/{npi}_{ts}.ndjson
   │   ├── DELETE FROM hospital_charges WHERE hospital_npi = ?
   │   ├── BigQuery load job: NDJSON staging → hospital_charges
   │   ├── UPDATE hospital_directory.last_scraped, hospital_npi
   │   └── DELETE raw MRF blob
   └── hospital_charges now current for all processed hospitals

5. Engine queries hospital_charges during bill analysis
   ├── clarobill-vision-sa (ADC) authenticates BigQuery requests
   ├── _load_hospital_charges(): MAX(gross_charge) per CPT code per NPI
   └── _load_negotiated_charges(): MAX(negotiated_charge) per CPT code
                                   per NPI × payer_name LIKE × plan_name LIKE
```

---

## Scaling Path

| Hospital count | Tasks | Wall-clock estimate | Notes |
|---------------|-------|---------------------|-------|
| ~1,200 (current) | 1 | ~1 hour | Single task, no sharding needed |
| ~3,600 | 3 | ~1 hour | `--tasks 3` |
| ~7,200 (target) | 6 | ~1 hour | `--tasks 6` — each task handles ~1,200 |
| ~18,000 (full US) | 6–15 | 1–2 hours | May need task timeout review at 15+ tasks |

The 4h task timeout comfortably covers the ~1h wall-clock at 6 tasks. At higher
task counts the per-task work shrinks, so the timeout is more than adequate.

**Deploy command (with rebuild):**
```bash
# After any code change to pipeline/ files:
gcloud builds submit \
  --tag us-central1-docker.pkg.dev/clarobill-prd/clarobill-pipeline/mrf-pipeline:latest \
  --project clarobill-prd \
  pipeline/

gcloud run jobs update clarobill-mrf-scraper \
  --image us-central1-docker.pkg.dev/clarobill-prd/clarobill-pipeline/mrf-pipeline:latest \
  --region us-central1

gcloud run jobs update clarobill-mrf-parser \
  --image us-central1-docker.pkg.dev/clarobill-prd/clarobill-pipeline/mrf-pipeline:latest \
  --region us-central1
```

**⚠️ Always rebuild the image before updating the jobs after any Python code change.**
Updating the job without rebuilding means the old image runs regardless of `--tasks`.

---

## Environment Variables (Cloud Run Jobs)

Both jobs receive these env vars via `--set-env-vars` in deploy.sh:

| Variable | Value | Used by |
|----------|-------|---------|
| `GCP_PROJECT_ID` | `clarobill-prd` | BigQuery client initialisation |
| `BIGQUERY_DATASET` | `hospital_prices` | Table references |
| `GCS_MRF_STAGING_BUCKET` | `mrf-staging` | GCS working bucket name |
| `GCS_MRF_ARCHIVE_BUCKET` | `mrf-archive-clarobill-prd` | GCS immutable archive (Phase 4 onward) |
| `CLOUD_RUN_TASK_INDEX` | 0..N-1 (auto-injected by Cloud Run) | Task sharding |
| `CLOUD_RUN_TASK_COUNT` | N (auto-injected by Cloud Run) | Task sharding |

`CLOUD_RUN_TASK_INDEX` and `CLOUD_RUN_TASK_COUNT` are injected automatically
by Cloud Run when `--tasks > 1`. Both default to 0 and 1 respectively in
single-task runs, so the sharding code is a no-op by default.

**Secret references (not env vars):** The Google Places API key is read from
Secret Manager at runtime via the SA's `secretmanager.secretAccessor` role on
`google-places-api-key`. **Never set as an env var** — env vars leak via
process listings, Cloud Run revision history, error stack traces. Code reads
the secret on startup and holds it in memory only.

---

## One-Time Setup Checklist

If recreating the GCP project from scratch:

```bash
# 1. Create service accounts
gcloud iam service-accounts create clarobill-pipeline-sa --project clarobill-prd
gcloud iam service-accounts create clarobill-scheduler-sa --project clarobill-prd
gcloud iam service-accounts create clarobill-vision-sa --project clarobill-prd

# 2. Grant pipeline-sa BigQuery permissions
gcloud projects add-iam-policy-binding clarobill-prd \
  --member serviceAccount:clarobill-pipeline-sa@clarobill-prd.iam.gserviceaccount.com \
  --role roles/bigquery.jobUser

gcloud bigquery datasets add-iam-policy-binding hospital_prices \
  --project clarobill-prd \
  --member serviceAccount:clarobill-pipeline-sa@clarobill-prd.iam.gserviceaccount.com \
  --role roles/bigquery.dataEditor

# 3. Grant pipeline-sa GCS permissions on mrf-staging bucket
gsutil iam ch serviceAccount:clarobill-pipeline-sa@clarobill-prd.iam.gserviceaccount.com:objectAdmin \
  gs://mrf-staging

# 4. Grant vision-sa BigQuery read + Vision API
gcloud projects add-iam-policy-binding clarobill-prd \
  --member serviceAccount:clarobill-vision-sa@clarobill-prd.iam.gserviceaccount.com \
  --role roles/bigquery.jobUser

gcloud bigquery datasets add-iam-policy-binding hospital_prices \
  --project clarobill-prd \
  --member serviceAccount:clarobill-vision-sa@clarobill-prd.iam.gserviceaccount.com \
  --role roles/bigquery.dataViewer

gcloud projects add-iam-policy-binding clarobill-prd \
  --member serviceAccount:clarobill-vision-sa@clarobill-prd.iam.gserviceaccount.com \
  --role roles/cloudvision.serviceAgent

# 5. Create Artifact Registry repo
gcloud artifacts repositories create clarobill-pipeline \
  --repository-format=docker --location=us-central1 --project clarobill-prd

# 6. Create GCS buckets
gsutil mb -l us-central1 gs://mrf-staging
# Immutable archive (Coldline, no-delete IAM) — provisioned via dedicated script
bash scripts/mrf_discovery/setup_archive_bucket.sh

# 7. Enable Places API and provision the API key in Secret Manager.
#    (Required only when running Stage 3 Tier 3 of the discovery pipeline.)
gcloud services enable places.googleapis.com --project clarobill-prd

KEY=$(gcloud alpha services api-keys create \
  --display-name="ClaroBill Places API key" \
  --api-target="service=places.googleapis.com" \
  --project clarobill-prd \
  --format="value(response.keyString)")

echo -n "$KEY" | gcloud secrets create google-places-api-key \
  --replication-policy="automatic" \
  --data-file=- \
  --project clarobill-prd

gcloud secrets add-iam-policy-binding google-places-api-key \
  --member="serviceAccount:clarobill-pipeline-sa@clarobill-prd.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor" \
  --project clarobill-prd

# 8. Deploy pipeline (builds image, creates jobs, grants scheduler, creates schedules)
bash pipeline/deploy.sh
```

---

## Enabled GCP APIs

The project has these APIs enabled. Disabling any of them breaks the corresponding
pipeline path; enabling new APIs should be a documented decision (with cost implications).

| API | Used by | Rationale |
|---|---|---|
| `bigquery.googleapis.com` | All BigQuery operations | Core data layer |
| `storage.googleapis.com` | All GCS operations | Working files + immutable archive |
| `run.googleapis.com` | Cloud Run Jobs (pipeline) and Cloud Run Service (engine) | Pipeline + serverless engine |
| `cloudbuild.googleapis.com` | engine-deploy-on-push trigger | Continuous deploy of engine |
| `cloudscheduler.googleapis.com` | Weekly MRF pipeline schedule | Triggers Cloud Run Jobs |
| `vision.googleapis.com` | Engine OCR | Bill image text extraction |
| `secretmanager.googleapis.com` | Places API key storage | Secrets for paid APIs |
| `places.googleapis.com` | Stage 3 Tier 3 of discovery pipeline | **Paid** — hard $450 ceiling per annual run; see `docs/decisions/2026-04-28-google-places-cost-design.md` |
| `iam.googleapis.com` | All SA management | Standard |
| `iamcredentials.googleapis.com` | OAuth token signing for Scheduler | Standard |
| `serviceusage.googleapis.com` | API enablement / disablement | Standard |
| `artifactregistry.googleapis.com` | Container image storage | Pipeline + engine images |

  # First — preview without making any call                        
  python3 scripts/mrf_discovery/stage3_tier3_places.py \                                                              
    --run-id $RUN_ID --cost-preview --project clarobill-prd                        
                                                                                                                      
  # Review the projected $X. If reasonable:                                                                           
  python3 scripts/mrf_discovery/stage3_tier3_places.py \                                                              
    --run-id $RUN_ID --max-places-cost 450 --project clarobill-prd     