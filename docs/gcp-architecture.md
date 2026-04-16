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
                          │   (Railway/Fly.io in prod)       │    OCR + rules engine
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
   than the Payerset-scraped NPI in hospital_directory)
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
- `hospital_name` — human-readable name from Payerset directory
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

Seed data loaded from Payerset hospital scrape. Updated by the scraper (last_modified)
and parser (hospital_npi, last_scraped) jobs.

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

### 5. Artifact Registry — `clarobill-pipeline`

**Repository:** `us-central1-docker.pkg.dev/clarobill-prd/clarobill-pipeline`  
**Image:** `mrf-pipeline:latest`

Stores the Docker image used by both Cloud Run Jobs. The image is built by
`gcloud builds submit` in Cloud Build and pushed here. Both jobs are updated
to use the new image digest after each build.

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
**Used by:** Cloud Run Jobs (`clarobill-mrf-scraper`, `clarobill-mrf-parser`)

| Permission | Role | Why required |
|------------|------|-------------|
| Read from BigQuery | `roles/bigquery.dataViewer` on `hospital_prices` dataset | Scraper reads `hospital_directory` to get mrf_url list and last_modified values |
| Write/update BigQuery | `roles/bigquery.dataEditor` on `hospital_prices` dataset | Scraper writes MERGE updates to `hospital_directory`; parser DELETEs + loads rows into `hospital_charges` |
| Run BigQuery jobs | `roles/bigquery.jobUser` on project | Required to execute queries and load jobs; without this, BigQuery API calls are rejected even with data permissions |
| Read GCS objects | `roles/storage.objectViewer` on `mrf-staging` bucket | Parser reads raw MRF blobs from `gs://mrf-staging/raw/` |
| Write GCS objects | `roles/storage.objectCreator` on `mrf-staging` bucket | Scraper writes downloaded MRF files; parser writes NDJSON staging blobs |
| Delete GCS objects | `roles/storage.objectAdmin` on `mrf-staging` bucket | Parser deletes raw blobs after successful load to prevent double-processing. objectAdmin is used because objectCreator + objectViewer does not include delete; objectAdmin scoped to this bucket only. |

**Does NOT have:** Cloud Run invoker, Scheduler invoker, Vision API access,
Supabase credentials, or any cross-project permissions.

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

### `clarobill-vision-sa`

**Email:** `clarobill-vision-sa@clarobill-prd.iam.gserviceaccount.com`  
**Used by:** FastAPI engine (running on Railway/Fly.io)

| Permission | Role | Why required |
|------------|------|-------------|
| Call Cloud Vision API | `roles/cloudvision.serviceAgent` or `roles/ml.serviceAgent` on project | Required to call `vision.googleapis.com/annotate`. The Vision API uses Application Default Credentials; without this role the API returns 403. |
| Query BigQuery (hospital charges) | `roles/bigquery.dataViewer` on `hospital_prices` dataset | Engine queries `hospital_charges` for gross charge and negotiated rate lookups during bill analysis. |
| Run BigQuery jobs | `roles/bigquery.jobUser` on project | Required to execute the SELECT queries against hospital_charges. |

**Does NOT have:** GCS write access, BigQuery data write access, Cloud Run
invoker, or Scheduler permissions. It reads BigQuery data and calls Vision API
only.

**Credential management:** A JSON key for this SA is stored as an environment
variable (`GOOGLE_APPLICATION_CREDENTIALS` or `GOOGLE_SERVICE_ACCOUNT_JSON`) in
the Railway/Fly.io deployment environment. It is never committed to the repo.
On Cloud Run the runtime SA provides ADC automatically without a key file.

---

## IAM Summary Table

| Service Account | BigQuery read | BigQuery write | BigQuery jobs | GCS read | GCS write/delete | Cloud Vision | Run Jobs invoker |
|-----------------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `clarobill-pipeline-sa` | ✓ | ✓ | ✓ | ✓ | ✓ | — | — |
| `clarobill-scheduler-sa` | — | — | — | — | — | — | ✓ |
| `clarobill-vision-sa` | ✓ | — | ✓ | — | — | ✓ | — |

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
| `GCS_MRF_STAGING_BUCKET` | `mrf-staging` | GCS bucket name |
| `CLOUD_RUN_TASK_INDEX` | 0..N-1 (auto-injected by Cloud Run) | Task sharding |
| `CLOUD_RUN_TASK_COUNT` | N (auto-injected by Cloud Run) | Task sharding |

`CLOUD_RUN_TASK_INDEX` and `CLOUD_RUN_TASK_COUNT` are injected automatically
by Cloud Run when `--tasks > 1`. Both default to 0 and 1 respectively in
single-task runs, so the sharding code is a no-op by default.

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

# 6. Create GCS bucket
gsutil mb -l us-central1 gs://mrf-staging

# 7. Deploy pipeline (builds image, creates jobs, grants scheduler, creates schedules)
bash pipeline/deploy.sh
```
