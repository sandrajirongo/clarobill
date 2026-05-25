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
                          │  clarobill-mrf-discovery-annual  │  Feb 15 02:00 UTC
                          │  clarobill-mrf-discovery-qtrly   │  May/Aug/Nov 15 02:00 UTC
                          │  clarobill-mrf-scraper-annual    │  Feb 15 02:00 UTC
                          │  clarobill-mrf-scraper-midyear   │  Aug 15 02:00 UTC
                          │  clarobill-mrf-parser-annual     │  Feb 15 06:00 UTC
                          │  clarobill-mrf-parser-midyear    │  Aug 15 06:00 UTC
                          └──────────────┬──────────────────┘
                                         │ HTTP POST (OAuth)
                                         ▼
                          ┌─────────────────────────────────────────┐
                          │           Cloud Run Jobs                 │
                          │                                         │
                          │  clarobill-mrf-discovery    ──────────► │ CMS census → NPI →
                          │  clarobill-mrf-scraper      ──────────► │ website → MRF URL
                          │  clarobill-mrf-parser       ──────────► │ download → parse
                          └──────────┬──────────────────────────────┘
                                     │
                  ┌──────────────────┼──────────────────┐
                  ▼                  ▼                   ▼
        ┌──────────────┐   ┌──────────────────┐  ┌─────────────────────┐
        │  GCS Buckets │   │    BigQuery       │  │  Artifact Registry  │
        │              │   │ hospital_prices   │  │  pipeline image     │
        │  mrf-staging │   │                   │  │  engine image       │
        │  mrf-archive │   │ hospital_directory│  └─────────────────────┘
        │  -clarobill  │   │ hospital_charges  │
        │  -prd        │   │ mrf_archive_index │
        └──────────────┘   │ mrf_disc_checkpt  │
                           │ mrf_disc_runs     │
                           │ payer_name_aliases│
                           └──────────────────┘

                          ┌────────────────────────────────────┐
                          │       Cloud Run Service             │
                          │   clarobill-engine (FastAPI)        │◄── Vercel (WIF auth)
                          └──────────┬─────────────────────────┘
                                     │ ADC
                          ┌──────────▼────────────┐
                          │   Vertex AI            │  Gemini 2.5 Flash Lite
                          │   (bill analysis +     │  (primary AI model)
                          │    card extraction)    │
                          └───────────────────────┘
                          ┌───────────────────────┐
                          │   Cloud Vision API     │  OCR extraction
                          └───────────────────────┘
                                         ▲
                          ┌──────────────┴──────────────────┐
                          │         Cloud Build              │
                          │  trigger: engine-deploy-on-push  │
                          │  fires on push to main           │
                          │  when apps/engine/** changes     │
                          └──────────────────────────────────┘
```

---

## Services

### 1. Cloud Run Jobs — MRF Pipeline

Three jobs run on a coordinated annual + mid-year + quarterly schedule. Discovery
and pipeline images are stored separately in Artifact Registry.

#### `clarobill-mrf-discovery`

**Purpose:** Build and maintain the `hospital_directory` of ~13,833 US civilian
hospitals — their CCNs, NPIs, websites, and MRF URLs — by walking public CMS data
sources. Runs four times per year: one full annual sweep (paid), three gap-fill
quarterly runs (free).

**Four stages per run:**
1. Seed CCN list from CMS Promoting Interoperability hospital list
2. Resolve NPI + website from NPPES bulk download, POS file, Wikidata
3. Discover websites for remaining hospitals (Tier 1: direct domain; Tier 2: pattern inference; Tier 3: Google Places API — paid, capped at $450/year)
4. Crawl each hospital website for MRF download URL; MERGE into `hospital_directory`

**Modes:**
- `--gap-fill-only`: skips Tier 3 Google Places, only re-processes hospitals where `validated_mrf_urls IS NULL`. Used for quarterly runs.
- `--start-stage=stage4_mrf_urls`: re-runs only Stage 4 on an existing `run_id`.

**Env vars:**
```
GCP_PROJECT_ID=clarobill-prd
BIGQUERY_DATASET=hospital_prices
GCS_MRF_STAGING_BUCKET=mrf-staging
```

**Resources:** 4Gi memory, 2 vCPU, 4h task timeout, max-retries 0  
**Runs:** Annual Feb 15 02:00 UTC (full + Tier 3 paid). Quarterly May/Aug/Nov 15 02:00 UTC (`--gap-fill-only`, free).

---

#### `clarobill-mrf-scraper`

**Purpose:** Download hospital MRF files from hospital websites to GCS, dual-writing
to both a mutable staging bucket and the immutable chain-of-custody archive.

**What it does (per run):**
1. Reads hospitals with `mrf_url` from `hospital_price_transparency` (joined to `hospital_directory`)
2. For each hospital: sends HTTP HEAD with `If-Modified-Since` — skips if unchanged
3. Downloads changed/new files
4. **Dual-writes:**
   - `gs://mrf-staging/raw/{slug}/{timestamp}.json[.gz]` — mutable; parser deletes after loading
   - `gs://mrf-archive-clarobill-prd/pricing-year={year}/{npi-or-ccn}/{sha256_first16}.{ext}` — immutable Coldline archive with sibling `.meta.json`
5. Inserts a `mrf_archive_index` row (`parse_status='pending'`) via BigQuery load job (not streaming insert — required for immediate DML eligibility)
6. Bulk-updates `hospital_directory.last_modified_header` via BigQuery MERGE

**Env vars:**
```
GCP_PROJECT_ID=clarobill-prd
BIGQUERY_DATASET=hospital_prices
GCS_MRF_STAGING_BUCKET=mrf-staging
GCS_MRF_ARCHIVE_BUCKET=mrf-archive-clarobill-prd
```

**Resources:** 4Gi memory, 2 vCPU, 4h task timeout, max-retries 0  
**Scaling:** `--tasks N` distributes hospitals by `MOD(FARM_FINGERPRINT(ccn), N)`  
**Runs:** Annual Feb 15 02:00 UTC. Mid-year Aug 15 02:00 UTC (catches ~10% of hospitals that republish in summer).

---

#### `clarobill-mrf-parser`

**Purpose:** Parse downloaded MRF JSON files and append normalised charge data to
BigQuery `hospital_charges`.

**What it does (per blob in `gs://mrf-staging/raw/`):**
1. Strips UTF-8 BOM if present (`_strip_bom()` — some hospitals export from Windows tools)
2. Resolves `pricing_effective_year` via three-source fallback:
   - MRF JSON `last_updated_on` field (authoritative, ~80% of hospitals)
   - HTTP `Last-Modified` header from scraper metadata (~15%)
   - Current calendar year as fallback (~5%)
3. Stream-parses CMS MRF v2.0.0 schema via `ijson` with per-row try/except (bad rows logged+skipped; never abort the whole file)
4. **Append-only** INSERT to `hospital_charges` — never DELETE existing rows. Old rows are preserved for forensic audits; the rules engine deduplicates at query time using `DENSE_RANK() OVER (ORDER BY pricing_effective_year DESC)`.
5. Flips `mrf_archive_index.parse_status` from `pending` to `parsed` / `failed` / `skipped`
6. Backfills `hospital_directory.hospital_npi` if the scraper left it null (NPI extracted from MRF JSON root — more authoritative than NPPES name-matching)
7. Deletes the raw staging blob to prevent double-processing

**Env vars:** Same as scraper  
**Resources:** 4Gi memory, 2 vCPU, 4h task timeout, max-retries 0  
**Runs:** Annual Feb 15 06:00 UTC (4h after annual scraper). Mid-year Aug 15 06:00 UTC.

---

### 2. Cloud Scheduler

Triggers MRF pipeline jobs on the annual + mid-year + quarterly cadence. Uses HTTP
POST to the Cloud Run Jobs API with OAuth authentication via `clarobill-scheduler-sa`.

| Job name | Schedule | Target |
|---|---|---|
| `clarobill-mrf-discovery-annual` | `0 2 15 2 *` (Feb 15) | clarobill-mrf-discovery (full) |
| `clarobill-mrf-discovery-quarterly` | `0 2 15 5,8,11 *` (May/Aug/Nov 15) | clarobill-mrf-discovery (`--gap-fill-only`) |
| `clarobill-mrf-scraper-annual` | `0 2 15 2 *` (Feb 15) | clarobill-mrf-scraper |
| `clarobill-mrf-scraper-midyear` | `0 2 15 8 *` (Aug 15) | clarobill-mrf-scraper |
| `clarobill-mrf-parser-annual` | `0 6 15 2 *` (Feb 15) | clarobill-mrf-parser |
| `clarobill-mrf-parser-midyear` | `0 6 15 8 *` (Aug 15) | clarobill-mrf-parser |

**Why the 15th:** Hospitals have until Jan 1 to republish MRFs per CMS rule; the Feb 15 anchor gives a 6-week buffer for stragglers. Quarterly dates are 45 days into each quarter. See `docs/decisions/2026-04-30-pipeline-cadence.md`.

**Legacy weekly schedules (`clarobill-mrf-scraper-weekly`, `clarobill-mrf-parser-weekly`) were deleted** when the annual cadence was adopted. They no longer exist.

---

### 3. Cloud Storage

#### `mrf-staging` (Standard, us-central1)

Mutable working bucket. Raw blobs deleted by parser after successful load.

```
mrf-staging/
  raw/
    {hospital-name-slug}/
      {scraped_at_utc_iso}.json[.gz]   ← downloaded MRF (with hospital metadata)
```

**Object metadata on raw blobs:**
- `hospital_name` — human-readable name
- `mrf_url` — source URL
- `state` — hospital state
- `last_modified` — HTTP Last-Modified from scraper (used as pricing year fallback)

**Lifecycle:** Raw blobs deleted by parser after successful load. No lifecycle rule needed.

#### `mrf-archive-clarobill-prd` (Coldline, us-central1)

Immutable chain-of-custody vault. Every MRF byte ever downloaded is preserved here
permanently. IAM enforces no-delete: `clarobill-pipeline-sa` has `objectCreator`
only, not `objectAdmin`. A human with bucket-level admin must act to delete anything.

```
mrf-archive-clarobill-prd/
  pricing-year={year}/
    {hospital_npi_or_ccn}/
      {sha256_first16}.{ext}        ← compressed MRF (content-addressed)
      {sha256_first16}.meta.json    ← sibling metadata (hospital_npi, mrf_url, scraped_at, etc.)
```

**Why Coldline + immutability:** If a patient's dispute ever cites a ClaroBill audit, we can produce the exact pricing bytes that were in force on the bill's service date. Coldline at $0.004/GB-month; ~20 GB total = ~$0.08/month.

---

### 4. BigQuery — `hospital_prices` dataset

**Project:** `clarobill-prd`  
**Dataset:** `hospital_prices`  
**Location:** US (multi-region)

#### Table: `hospital_directory`

~13,833 US civilian hospitals. Populated by the CMS-direct discovery pipeline. Updated
by the scraper (`last_modified_header`) and parser (`hospital_npi`, `last_scraped_at`).

| Column | Type | Description |
|---|---|---|
| `hospital_npi` | STRING | NPI — primary rules-engine join key |
| `ccn` | STRING | CMS Certification Number — primary discovery + scraper key |
| `hospital_name` | STRING | Human-readable name |
| `state` | STRING | Two-letter state abbreviation |
| `address` | STRING | Street address from NPPES |
| `zip_code` | STRING | 5-digit ZIP from NPPES (backfill pending for full coverage) |
| `phone` | STRING | Phone number from NPPES |
| `ein` | STRING | Employer Identification Number |
| `hospital_website` | STRING | Discovered website URL |
| `website_discovery_method` | STRING | `tier1_direct` / `tier2_pattern` / `tier3_google_places` |
| `last_website_validated_at` | TIMESTAMP | Last HTTP check of hospital website (partition key) |
| `validated_mrf_urls` | STRING | JSON array of confirmed MRF download URLs (Stage 4 output) |
| `last_modified_header` | STRING | HTTP Last-Modified from most recent successful scrape |
| `last_scraped_at` | TIMESTAMP | When the parser last processed this hospital |

**Partitioned by** `DATE(last_website_validated_at)`. **Clustered by** `(ccn, hospital_npi)`.

#### Table: `hospital_charges`

The core price transparency table. One row per procedure × payer × plan combination
per hospital per scrape. Loaded append-only by the parser from CMS MRF v2.0.0 files.
The rules engine deduplicates to the most recent vintage at query time.

| Column | Type | Description |
|---|---|---|
| `hospital_npi` | STRING | Joins to hospital_directory |
| `code_type` | STRING | `CPT`, `HCPCS`, `MS-DRG`, `RC`, etc. |
| `code` | STRING | Procedure code |
| `description` | STRING | Procedure description from MRF |
| `gross_charge` | FLOAT64 | Chargemaster (list) price — HOSPITAL_CHARGE_OUTLIER benchmark |
| `discounted_cash_price` | FLOAT64 | Self-pay negotiated rate |
| `min_negotiated` | FLOAT64 | Minimum across all payer contracts |
| `max_negotiated` | FLOAT64 | Maximum across all payer contracts |
| `payer_name` | STRING | Insurer name — used for NEGOTIATED_RATE_EXCEEDED lookup |
| `plan_name` | STRING | Plan name — used for NEGOTIATED_RATE_EXCEEDED lookup |
| `negotiated_charge` | FLOAT64 | Exact contracted rate for this payer/plan |
| `negotiated_type` | STRING | `negotiated` \| `derived` \| `percentage` \| `range` |
| `setting` | STRING | `inpatient` \| `outpatient` \| null |
| `pricing_effective_year` | INT64 NOT NULL | Year this chargemaster was in effect (partition key) |
| `source_mrf_url` | STRING | URL of the MRF file this row was parsed from |
| `source_gcs_uri` | STRING | `gs://` URI of the archived MRF blob (forensic link to archive) |
| `scraped_at` | TIMESTAMP | When this row was loaded |

**Partitioned by** `pricing_effective_year` (RANGE 2024–2034). **Clustered by** `(hospital_npi, code)`.

**Query patterns used by the rules engine** (all via `hospital_charges`, with year-aware deduplication):
1. Gross charge lookup: `DENSE_RANK() OVER (PARTITION BY code ORDER BY pricing_effective_year DESC)` — returns the most recent vintage on or before the bill's service year
2. Negotiated rate lookup: same pattern, filtered by `payer_name` (via alias table or substring) and `plan_name`
3. Negotiated ceiling: `MAX(max_negotiated)` across all payers for the most recent year

#### Table: `hospital_charges_legacy_stale`

The pre-effective-dating snapshot from before Phase 4. Tagged with `pricing_effective_year=2025`. **Never read by the rules engine.** Retained for forensic reference; will be dropped in 2026 H2 once the new `hospital_charges` table has sufficient coverage.

#### Table: `mrf_archive_index`

Canonical index of every MRF blob in the immutable archive. Drives the parser's work queue.

| Column | Type | Description |
|---|---|---|
| `hospital_npi` | STRING | Hospital NPI (may be null for CCN-keyed rows until parser backfill) |
| `ccn` | STRING | CCN — always populated |
| `source_mrf_url` | STRING NOT NULL | Original MRF download URL |
| `gcs_uri` | STRING | Archive GCS path (`gs://mrf-archive-clarobill-prd/...`) |
| `sha256` | STRING | Content hash of the MRF file |
| `mrf_last_modified_header` | STRING | HTTP Last-Modified at download time |
| `parse_status` | STRING NOT NULL | `pending` → `parsed` / `failed` / `skipped` |
| `scraped_at` | TIMESTAMP | When the scraper downloaded the file |

**Clustered by** `(hospital_npi, sha256)`.

#### Table: `mrf_discovery_checkpoint`

Per-hospital, per-stage state for the annual discovery pipeline. One row per `(run_id, ccn)`.  
**Clustered by** `(run_id, ccn)`.

#### Table: `mrf_discovery_runs`

Annual run summary. One row per discovery run with coverage metrics (hospitals with NPI, with website, with validated URL, coverage rate).

#### Table: `payer_name_aliases`

Canonical mapping of insurer names to payer groups. Used by the rules engine's `_resolve_payer_aliases()` to match user-provided payer names (e.g. "Blue Cross") against MRF-published variants (e.g. "Anthem Blue Cross Blue Shield of California").

---

### 5. Artifact Registry

#### `clarobill-pipeline`

**Repository:** `us-central1-docker.pkg.dev/clarobill-prd/clarobill-pipeline`  
**Image:** `mrf-pipeline:latest`

Stores the Docker image used by the three Cloud Run Jobs (discovery, scraper, parser). Built by `gcloud builds submit` and pushed here. All three jobs are updated to the new image digest after each build.

#### `cloud-run-source-deploy`

**Repository:** `us-central1-docker.pkg.dev/clarobill-prd/cloud-run-source-deploy`  
**Image:** `clarobill-engine:$COMMIT_SHA` and `clarobill-engine:latest`

Stores the FastAPI engine image. Built and pushed automatically by the Cloud Build trigger on every push to main that touches `apps/engine/**`. Both a commit-SHA tag (for rollback) and `latest` are pushed on each build.

---

### 6. Cloud Run Service — Engine

**Service name:** `clarobill-engine`  
**Region:** `us-central1`  
**Runtime SA:** `clarobill-vision-sa`  
**Image source:** `cloud-run-source-deploy/clarobill-engine:$COMMIT_SHA` (deployed by Cloud Build)

The user-facing FastAPI service. Handles bill analysis (OCR → parser → rules engine → AI summary → report), insurance card extraction, and report generation. Authenticates incoming requests via the `Authorization: Bearer <Cloud Run identity token>` header, which the web app obtains through Workload Identity Federation (see WIF section below).

**Rollback:**
```bash
gcloud run services update clarobill-engine \
  --image us-central1-docker.pkg.dev/clarobill-prd/cloud-run-source-deploy/clarobill-engine:<COMMIT_SHA> \
  --region us-central1
```

---

### 7. Cloud Build — Engine Auto-Deploy Trigger

**Trigger name:** `rmgpgab-clarobill-engine-us-central1-sandrajirongo-clarobillwrs`  
**Event:** Push to branch `^main$`  
**Included files filter:** `apps/engine/**`  
**Build config:** `apps/engine/cloudbuild.yaml`  
**Repository:** `sandrajirongo/clarobill` (GitHub App connection)

Builds `clarobill-engine:$COMMIT_SHA` and `:latest`, pushes both to Artifact Registry, deploys to the `clarobill-engine` Cloud Run service.

---

### 8. Vertex AI — Bill Analysis and Card Extraction

**Primary AI model:** Gemini 2.5 Flash Lite (`gemini-2.5-flash-lite`) via Vertex AI  
**Fallback model:** Claude Sonnet 4.6 (`claude-sonnet-4-6`) via Anthropic API  
**SDK:** `google-cloud-aiplatform` (initialised via `vertexai.init()` in `ai_analysis.py`)  
**Location:** `us-central1` (default, configurable via `VERTEX_AI_LOCATION` env var)

Used for two features:
- **Bill analysis AI summary** — receives OCR text + structured line items + all detected billing errors; returns a `ai_summary` JSON with patient-readable narrative and dispute recommendations
- **Insurance card extraction** — stateless extraction of payer name, plan name, member ID, plan type from a card photo; Gemini primary, Claude fallback

**Credential path in Cloud Run:** Application Default Credentials via `clarobill-vision-sa` runtime service account. No JSON key file needed.  
**Credential path locally:** `GOOGLE_CREDENTIALS_JSON` (full JSON content, preferred for Docker), or `GOOGLE_APPLICATION_CREDENTIALS` (file path to a service account key).

See `docs/architecture/vertex-ai.md` for the full AI integration reference.

---

### 9. Cloud Vision API

Used by the FastAPI engine for OCR extraction of uploaded medical bills. Each bill upload triggers one or more Vision API annotate requests (one per page for PDFs, one per image). Separate from Vertex AI — Cloud Vision handles document text extraction only.

---

### 10. Workload Identity Federation — Vercel → Cloud Run Auth

WIF is the authentication mechanism by which the Vercel web app calls the Cloud Run engine without storing a long-lived service account key.

**Flow (`apps/web/src/lib/gcp-auth.ts`):**
1. `getVercelOidcToken()` from `@vercel/oidc` — Vercel issues a short-lived OIDC token for this deployment
2. POST to `sts.googleapis.com/v1/token` — exchanges the Vercel OIDC token for a GCP federated access token
3. POST to `iamcredentials.googleapis.com/v1/projects/.../serviceAccounts/.../generateIdToken` — exchanges the federated access token for a Cloud Run identity token bound to `clarobill-vercel-sa`
4. Engine receives `Authorization: Bearer <identity token>` and validates it via Cloud Run's built-in IAM check

**Local dev bypass:** `getCloudRunIdToken()` returns `null` when `!process.env.VERCEL` so the engine can be called without auth during development.

**GCP resources:**
- Service account: `clarobill-vercel-sa@clarobill-prd.iam.gserviceaccount.com`
- WIF pool: `clarobill-vercel-pool` (global)
- WIF provider: `vercel-provider` (OIDC, audience = Vercel deployment URL)

**Required env vars in Vercel (production):**
| Variable | Default in code | Purpose |
|---|---|---|
| `GCP_PROJECT_NUMBER` | none (required) | Constructs WIF audience URL |
| `GCP_WORKLOAD_IDENTITY_POOL_ID` | `clarobill-vercel-pool` | WIF pool ID |
| `GCP_WORKLOAD_IDENTITY_POOL_PROVIDER_ID` | `vercel-provider` | WIF provider ID |
| `GCP_SERVICE_ACCOUNT_EMAIL` | `clarobill-vercel-sa@clarobill-prd.iam.gserviceaccount.com` | SA to impersonate |

See `docs/decisions/2026-05-25-wif-vercel-cloud-run-auth.md` for the full decision record.

---

## Service Accounts

ClaroBill uses four service accounts, each with the minimum permissions required for its function. No service account has project-level Owner or Editor.

---

### `clarobill-pipeline-sa`

**Email:** `clarobill-pipeline-sa@clarobill-prd.iam.gserviceaccount.com`  
**Used by:** Cloud Run Jobs (discovery, scraper, parser)

| Permission | Role | Why required |
|---|---|---|
| Read BigQuery | `roles/bigquery.dataViewer` on `hospital_prices` dataset | Discovery + scraper read `hospital_directory`, `mrf_discovery_checkpoint` |
| Write BigQuery | `roles/bigquery.dataEditor` on `hospital_prices` dataset | Scraper/parser MERGE to `hospital_directory`; parser appends to `hospital_charges`; discovery writes `mrf_discovery_checkpoint`, `mrf_archive_index`, `mrf_discovery_runs` |
| Run BigQuery jobs | `roles/bigquery.jobUser` on project | Required to execute queries and load jobs |
| Read GCS — mrf-staging | `roles/storage.objectViewer` on `mrf-staging` | Parser reads raw MRF blobs |
| Write GCS — mrf-staging | `roles/storage.objectCreator` on `mrf-staging` | Scraper writes downloaded files |
| Delete GCS — mrf-staging | `roles/storage.objectAdmin` on `mrf-staging` | Parser deletes raw blobs after load |
| Write GCS — archive | `roles/storage.objectCreator` on `mrf-archive-clarobill-prd` | Scraper streams to immutable archive. **No delete permission — that is the immutability guarantee.** |
| Read GCS — archive | `roles/storage.objectViewer` on `mrf-archive-clarobill-prd` | Parser reads from archive |
| Read Places API key | `roles/secretmanager.secretAccessor` on secret `google-places-api-key` | Stage 3 Tier 3 reads the key at startup |

**Does NOT have:** Cloud Run invoker, Vision API, Vertex AI, Supabase credentials, archive delete, or any cross-project permissions.

---

### `clarobill-scheduler-sa`

**Email:** `clarobill-scheduler-sa@clarobill-prd.iam.gserviceaccount.com`  
**Used by:** Cloud Scheduler

| Permission | Role | Why required |
|---|---|---|
| Invoke Cloud Run Jobs | `roles/run.jobsExecutor` on `clarobill-mrf-discovery-annual`, `clarobill-mrf-discovery-quarterly`, `clarobill-mrf-scraper`, `clarobill-mrf-parser` | Scheduler makes authenticated HTTP POST to the Cloud Run Jobs API |

**Does NOT have:** BigQuery, GCS, Vision, Vertex AI, or any data access.

---

### `clarobill-vision-sa`

**Email:** `clarobill-vision-sa@clarobill-prd.iam.gserviceaccount.com`  
**Used by:** FastAPI engine (Cloud Run service `clarobill-engine`)

| Permission | Role | Why required |
|---|---|---|
| Call Cloud Vision API | `roles/cloudvision.serviceAgent` on project | OCR extraction via `vision.googleapis.com/annotate` |
| Call Vertex AI | `roles/aiplatform.user` on project | Gemini 2.5 Flash Lite calls via `aiplatform.googleapis.com` |
| Query BigQuery | `roles/bigquery.dataViewer` on `hospital_prices` dataset | Gross charge and negotiated rate lookups during bill analysis |
| Run BigQuery jobs | `roles/bigquery.jobUser` on project | Execute SELECT queries against `hospital_charges` |

**Credential management:** Cloud Run provides ADC automatically via the runtime service account. No JSON key file in the container or environment variables.

---

### `clarobill-vercel-sa`

**Email:** `clarobill-vercel-sa@clarobill-prd.iam.gserviceaccount.com`  
**Used by:** Vercel web app (via Workload Identity Federation)

| Permission | Role | Why required |
|---|---|---|
| Federated identity binding | `roles/iam.workloadIdentityUser` on WIF pool `clarobill-vercel-pool` | Allows the Vercel OIDC token to impersonate this SA via STS |
| Invoke Cloud Run engine | `roles/run.invoker` on `clarobill-engine` service | Required to generate a valid Cloud Run identity token for the engine |

**Does NOT have:** BigQuery, GCS, Vision, Vertex AI, or any data access. Its only function is to be impersonated by Vercel deployments to call the engine.

---

### Cloud Build Service Account

**Email:** `1034973715010@cloudbuild.gserviceaccount.com`  
**Used by:** Cloud Build trigger (`engine-deploy-on-push`)

| Permission | Role | Why required |
|---|---|---|
| Deploy to Cloud Run | `roles/run.developer` on project | Calls `gcloud run services update` in build steps |
| Act as engine runtime SA | `roles/iam.serviceAccountUser` on `clarobill-vision-sa` | Cloud Run requires the deployer to have impersonation rights over the service's runtime SA |

---

## IAM Summary Table

| Service Account | BQ read | BQ write | BQ jobs | GCS read | GCS write | GCS delete | Vision | Vertex AI | Run.invoker | WIF federated | Places key |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `clarobill-pipeline-sa` | ✓ | ✓ | ✓ | ✓ | ✓ | mrf-staging only | — | — | — | — | ✓ |
| `clarobill-scheduler-sa` | — | — | — | — | — | — | — | — | ✓ (jobs) | — | — |
| `clarobill-vision-sa` | ✓ | — | ✓ | — | — | — | ✓ | ✓ | — | — | — |
| `clarobill-vercel-sa` | — | — | — | — | — | — | — | — | ✓ (engine) | ✓ | — |

**Notes:**
- `clarobill-pipeline-sa` can delete from `mrf-staging` but **NOT** from `mrf-archive-clarobill-prd`. The absence of archive-delete is the structural immutability guarantee.
- `clarobill-vercel-sa` has `Run.invoker` on the engine Cloud Run service only, scoped through WIF pool impersonation.
- `clarobill-vision-sa` uses ADC via Cloud Run — no JSON key file anywhere.

---

## Pipeline Data Flow (End to End)

```
1. Cloud Scheduler fires (annual Feb 15 02:00 UTC or quarterly)
   └── clarobill-scheduler-sa POSTs to Cloud Run Jobs API
       └── clarobill-mrf-discovery starts
           ├── Stage 1: seed CCNs from CMS PI list
           ├── Stage 2: resolve NPIs + websites from NPPES / POS / Wikidata
           ├── Stage 3: Google Places for remaining (annual only; $450 cap)
           └── Stage 4: crawl each hospital website for MRF URL
               └── MERGE validated_mrf_urls into hospital_directory

2. Cloud Scheduler fires (annual Feb 15 02:00 UTC + mid-year Aug 15)
   └── clarobill-mrf-scraper starts (1–6 tasks)
       ├── Reads hospital_price_transparency (join hospital_directory) for mrf_url
       ├── HEAD with If-Modified-Since → skip unchanged
       └── For each changed hospital:
           ├── Download MRF
           ├── Write to mrf-staging/raw/{slug}/{ts}.json[.gz]
           ├── Write to mrf-archive/pricing-year={Y}/{npi}/{sha256}.{ext} (immutable)
           ├── Write sibling .meta.json to archive
           └── INSERT mrf_archive_index row (parse_status='pending') via load job

3. Cloud Scheduler fires (annual Feb 15 06:00 UTC + mid-year Aug 15)
   └── clarobill-mrf-parser starts (1–6 tasks)
       ├── Lists staging blobs
       └── For each blob:
           ├── Strip UTF-8 BOM if present
           ├── Resolve pricing_effective_year (json_last_updated_on > Last-Modified > calendar year)
           ├── Stream-parse CMS MRF v2.0.0 (per-row tolerance — bad rows skipped, not abort)
           ├── APPEND rows to hospital_charges (never DELETE)
           ├── Flip mrf_archive_index.parse_status → parsed / failed / skipped
           ├── Backfill hospital_directory.hospital_npi if null
           └── DELETE staging blob

4. User uploads bill → Vercel web app → engine called via WIF auth
   └── clarobill-vision-sa (ADC) authenticates BigQuery requests
       ├── _load_hospital_charges(): DENSE_RANK by pricing_effective_year → MAX(gross_charge)
       ├── _load_negotiated_charges(): alias-matched or substring payer/plan filter
       └── _load_negotiated_ceiling(): MAX(max_negotiated) across all payers
```

---

## Scaling Path

| Hospital count | Tasks | Wall-clock estimate | Notes |
|---|---|---|---|
| ~13,833 (current) | 6 | ~2–3 hours | Each task handles ~2,300 hospitals |
| ~18,000 (full US + new certs) | 6–8 | ~2–3 hours | `--tasks 8` if needed |
| ~25,000 | 10–15 | ~2–3 hours | May need task timeout review |

**Deploy commands:**

```bash
# After any code change to pipeline/ files — rebuild image first:
gcloud builds submit \
  --tag us-central1-docker.pkg.dev/clarobill-prd/clarobill-pipeline/mrf-pipeline:latest \
  --project clarobill-prd \
  pipeline/

# Then deploy all three jobs:
bash pipeline/deploy.sh

# Manual triggers:
gcloud run jobs execute clarobill-mrf-discovery --region us-central1          # full annual
gcloud run jobs execute clarobill-mrf-discovery --region us-central1 \
  --args=--gap-fill-only                                                       # quarterly gap-fill
gcloud run jobs execute clarobill-mrf-scraper --tasks 6 --region us-central1
gcloud run jobs execute clarobill-mrf-parser  --tasks 6 --region us-central1
```

---

## Environment Variables

### Cloud Run Jobs (pipeline)

| Variable | Value | Used by |
|---|---|---|
| `GCP_PROJECT_ID` | `clarobill-prd` | BigQuery client initialisation |
| `BIGQUERY_DATASET` | `hospital_prices` | Table references |
| `GCS_MRF_STAGING_BUCKET` | `mrf-staging` | Staging bucket |
| `GCS_MRF_ARCHIVE_BUCKET` | `mrf-archive-clarobill-prd` | Immutable archive |
| `CLOUD_RUN_TASK_INDEX` | 0..N-1 (auto-injected) | Task sharding |
| `CLOUD_RUN_TASK_COUNT` | N (auto-injected) | Task sharding |

**Secret references (not env vars):** Google Places API key is read from Secret Manager at runtime via `secretmanager.secretAccessor`. Never set as an env var.

### Cloud Run Service (engine)

See `docs/operations/environment-variables.md` for the full engine env var reference.

---

## Enabled GCP APIs

| API | Used by | Rationale |
|---|---|---|
| `bigquery.googleapis.com` | All BigQuery operations | Core data layer |
| `storage.googleapis.com` | All GCS operations | Working files + immutable archive |
| `run.googleapis.com` | Cloud Run Jobs (pipeline) and Cloud Run Service (engine) | Pipeline + engine |
| `cloudbuild.googleapis.com` | engine-deploy-on-push trigger | Continuous deploy |
| `cloudscheduler.googleapis.com` | MRF pipeline schedules | Triggers Cloud Run Jobs |
| `vision.googleapis.com` | Engine OCR | Bill image text extraction |
| `aiplatform.googleapis.com` | Engine AI analysis + card extraction | Vertex AI / Gemini 2.5 Flash Lite |
| `iam.googleapis.com` | All SA management | Standard |
| `iamcredentials.googleapis.com` | WIF SA impersonation (Vercel→Cloud Run) + Scheduler OAuth | Required for `generateIdToken` in WIF flow |
| `sts.googleapis.com` | WIF OIDC token exchange (Vercel→Cloud Run) | Step 1 of WIF flow |
| `secretmanager.googleapis.com` | Places API key storage | Secrets for paid APIs |
| `places.googleapis.com` | Stage 3 Tier 3 of discovery pipeline | **Paid** — hard $450 ceiling per annual run |
| `serviceusage.googleapis.com` | API enablement / disablement | Standard |
| `artifactregistry.googleapis.com` | Container image storage | Pipeline + engine images |

---

## One-Time Setup Checklist

If recreating the GCP project from scratch:

```bash
# 1. Create service accounts
gcloud iam service-accounts create clarobill-pipeline-sa  --project clarobill-prd
gcloud iam service-accounts create clarobill-scheduler-sa --project clarobill-prd
gcloud iam service-accounts create clarobill-vision-sa    --project clarobill-prd
gcloud iam service-accounts create clarobill-vercel-sa    --project clarobill-prd

# 2. Grant pipeline-sa BigQuery permissions
gcloud projects add-iam-policy-binding clarobill-prd \
  --member serviceAccount:clarobill-pipeline-sa@clarobill-prd.iam.gserviceaccount.com \
  --role roles/bigquery.jobUser

# (dataset-level grants via bq command or Cloud Console)

# 3. Grant pipeline-sa GCS permissions
gsutil iam ch serviceAccount:clarobill-pipeline-sa@clarobill-prd.iam.gserviceaccount.com:objectAdmin \
  gs://mrf-staging
gsutil iam ch serviceAccount:clarobill-pipeline-sa@clarobill-prd.iam.gserviceaccount.com:objectCreator \
  gs://mrf-archive-clarobill-prd
gsutil iam ch serviceAccount:clarobill-pipeline-sa@clarobill-prd.iam.gserviceaccount.com:objectViewer \
  gs://mrf-archive-clarobill-prd

# 4. Grant vision-sa Vision + Vertex AI + BigQuery
gcloud projects add-iam-policy-binding clarobill-prd \
  --member serviceAccount:clarobill-vision-sa@clarobill-prd.iam.gserviceaccount.com \
  --role roles/bigquery.jobUser
gcloud projects add-iam-policy-binding clarobill-prd \
  --member serviceAccount:clarobill-vision-sa@clarobill-prd.iam.gserviceaccount.com \
  --role roles/cloudvision.serviceAgent
gcloud projects add-iam-policy-binding clarobill-prd \
  --member serviceAccount:clarobill-vision-sa@clarobill-prd.iam.gserviceaccount.com \
  --role roles/aiplatform.user
# (BQ dataViewer on hospital_prices dataset via bq command)

# 5. Set up Workload Identity Federation
gcloud iam workload-identity-pools create clarobill-vercel-pool \
  --location global --project clarobill-prd
gcloud iam workload-identity-pools providers create-oidc vercel-provider \
  --location global \
  --workload-identity-pool clarobill-vercel-pool \
  --issuer-uri https://oidc.vercel.com \
  --allowed-audiences https://vercel.com \
  --project clarobill-prd
# Bind WIF pool to clarobill-vercel-sa:
gcloud iam service-accounts add-iam-policy-binding \
  clarobill-vercel-sa@clarobill-prd.iam.gserviceaccount.com \
  --member "principalSet://iam.googleapis.com/projects/$(gcloud projects describe clarobill-prd --format='value(projectNumber)')/locations/global/workloadIdentityPools/clarobill-vercel-pool/*" \
  --role roles/iam.workloadIdentityUser \
  --project clarobill-prd
# Grant vercel-sa Cloud Run invoker on engine:
gcloud run services add-iam-policy-binding clarobill-engine \
  --member serviceAccount:clarobill-vercel-sa@clarobill-prd.iam.gserviceaccount.com \
  --role roles/run.invoker \
  --region us-central1 --project clarobill-prd

# 6. Create Artifact Registry repos
gcloud artifacts repositories create clarobill-pipeline \
  --repository-format=docker --location=us-central1 --project clarobill-prd
gcloud artifacts repositories create cloud-run-source-deploy \
  --repository-format=docker --location=us-central1 --project clarobill-prd

# 7. Create GCS buckets
gsutil mb -l us-central1 gs://mrf-staging
bash scripts/mrf_discovery/setup_archive_bucket.sh   # Coldline + no-delete IAM

# 8. Enable Places API and provision key in Secret Manager
gcloud services enable places.googleapis.com --project clarobill-prd
KEY=$(gcloud alpha services api-keys create \
  --display-name="ClaroBill Places API key" \
  --api-target="service=places.googleapis.com" \
  --project clarobill-prd \
  --format="value(response.keyString)")
echo -n "$KEY" | gcloud secrets create google-places-api-key \
  --replication-policy="automatic" --data-file=- --project clarobill-prd
gcloud secrets add-iam-policy-binding google-places-api-key \
  --member="serviceAccount:clarobill-pipeline-sa@clarobill-prd.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor" --project clarobill-prd

# 9. Deploy pipeline (builds image, creates jobs, grants scheduler, creates schedules)
bash pipeline/deploy.sh

# 10. Deploy engine (Cloud Build trigger handles this automatically on push to main)
# For manual first-time deploy:
cd apps/engine && gcloud run deploy clarobill-engine \
  --source . --region us-central1 \
  --service-account clarobill-vision-sa@clarobill-prd.iam.gserviceaccount.com \
  --project clarobill-prd
```

---

_Last reviewed: 2026-05-25_
