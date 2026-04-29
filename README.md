# ClaroBill

AI-powered medical bill error detection. Analyzes itemized bills for overcharges,
duplicate charges, coding violations, and charges above the patient's contracted
insurance rate. Generates plain-English reports and ready-to-send dispute letters.

---

## Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14, TypeScript, Tailwind CSS |
| Backend | Python FastAPI |
| Application database | PostgreSQL via Supabase |
| Price transparency database | BigQuery (`clarobill-prd.hospital_prices`) |
| Auth | Supabase Auth |
| OCR | Google Cloud Vision API |
| AI Analysis | Google Gemini 2.0 Flash via Vertex AI (primary) · Anthropic Claude Sonnet (fallback) |
| Payments | Stripe Checkout |
| File Storage | Supabase Storage (encrypted) |
| Email | SendGrid |
| Error Monitoring | Sentry |
| Analytics | PostHog |
| Frontend Hosting | Vercel |
| Backend Hosting | Google Cloud Run |
| MRF Pipeline | Google Cloud Run Jobs + Cloud Scheduler |
| Container Registry | Google Artifact Registry |

---

## Database Architecture

ClaroBill uses **two databases** for different purposes:

### Supabase (PostgreSQL) — application data
Stores everything related to users and bill analysis:
- `bills` — uploaded bills with OCR status, confirmed hospital/insurance fields
- `line_items` — parsed CPT codes and charges per bill
- `analysis_results` — rules engine output, AI summary, report URLs
- `payments` — Stripe payment records
- `profile_members` — insured members per account (holder + dependents)
- `insurance_plans` — insurance plans per member (payer + plan name for rate lookup)
- CMS reference tables: `cms_pfs_indicators`, `cms_localities`, `ncci_edit_pairs`,
  `cms_opps_cap`, `cms_ambulance_rates`, `cms_hcpcs_codes`, `cms_anesthesia_cf`, etc.

Row Level Security is enabled on all user-facing tables. Users can only access
their own data.

### BigQuery (`clarobill-prd.hospital_prices`) — price transparency data
Stores hospital price transparency data from CMS Machine Readable Files (MRF):
- `hospital_directory` — US hospitals with CCN, NPI, name, MRF URL (~13,833 after CMS-direct discovery cleanup; was ~3,100 under the legacy Payerset seed)
- `hospital_charges` — per-hospital, per-CPT-code charges keyed by `pricing_effective_year` (NOT NULL), including:
  - `gross_charge` — hospital's own published list price (chargemaster)
  - `negotiated_charge` — insurer-specific contracted rate per payer/plan combination
  - `discounted_cash_price` — self-pay rate
- `mrf_archive_index` — canonical index of every MRF file archived to GCS, keyed by (hospital_npi, pricing_effective_year, sha256). Drives the parser's work queue.
- `mrf_discovery_checkpoint` — per-run state for the annual hospital-discovery pipeline. One row per (run_id, ccn) with stage-completion timestamps for resumability.
- `mrf_discovery_runs` — annual summary, one row per discovery run.
- `hospital_charges_legacy_stale` — frozen snapshot of pre-effective-dating charges. Do NOT read from this; the rules engine uses `hospital_charges` only.

BigQuery is used for these tables because:
1. **Scale** — a single hospital's MRF can contain millions of rows (every CPT × every payer × every plan). At 13,000+ hospitals the full dataset is in the billions of rows, which is impractical in Postgres.
2. **Write pattern** — MRF data is bulk-replaced weekly (DELETE + load), not incrementally updated. BigQuery load jobs are purpose-built for this.
3. **Effective dating** — `hospital_charges` is partitioned by `pricing_effective_year` so a 2026 bill is always evaluated against the 2026 chargemaster, never a future-dated re-publication. Critical for correctness; see `docs/decisions/2026-04-28-cms-direct-mrf-discovery.md`.

### GCS (`gs://mrf-archive-clarobill-prd`) — immutable historical archive
Coldline bucket holding every MRF file ever downloaded, partitioned by `pricing-year={year}/{hospital_npi}/{sha256_first16}.{ext}`. The pipeline service account has `objectCreator + objectViewer` only (no delete). This is the chain-of-custody vault — if a patient ever cites a ClaroBill audit in a dispute, we can produce the exact MRF that was in force on the bill's service date, years later.
3. **Query pattern** — The engine issues narrow point queries (specific NPI + CPT codes + payer/plan). BigQuery's columnar storage makes these fast even at scale.

The engine queries BigQuery during bill analysis using Application Default
Credentials (`clarobill-vision-sa` service account).

---

## How It Works

### For users
1. Create account — add profile members (self + dependents) and insurance plans
2. Upload a medical bill (PDF or image)
3. Pre-analysis verification — confirm hospital, insurance plan, service dates, patient name
4. Analysis runs — 10 independent rules check for errors (see `docs/rules-engine.md`)
5. Results teaser — see total potential savings before paying
6. Pay → receive full PDF report + dispute letter by email

### Rules engine (11 rules)
| Rule | Benchmark | Severity |
|------|-----------|----------|
| `NEGOTIATED_RATE_EXCEEDED` | Insurer's contracted rate (MRF) | Critical |
| `HOSPITAL_CHARGE_OUTLIER` | Hospital's own gross charge (MRF) | Critical |
| `DUPLICATE_CHARGE` | Same code billed twice | Critical |
| `NCCI_UNBUNDLING` | CMS NCCI edit pairs | Critical |
| `NON_PAYABLE_CODE` | CMS inactive/bundled codes | Critical/Warning |
| `TERMINATED_CODE_BILLED` | CMS HCPCS termination dates | Critical |
| `ANESTHESIA_OUTLIER` | CMS base units + locality CF | Critical |
| `MUE_EXCEEDED` | CMS Medically Unlikely Edit limits | Critical/Warning |
| `FACILITY_CHARGE_OUTLIER` | CMS OPPS cap | Warning |
| `AMBULANCE_CHARGE_OUTLIER` | CMS Ambulance Fee Schedule | Warning |
| `PRICE_OUTLIER` | Medicare fee schedule (plan-type-aware threshold) | Warning |

`PRICE_OUTLIER` thresholds: medicare/medicaid 1.05×, tricare/self_pay 1.20×, commercial/unknown 1.80×.

See `docs/rules-engine.md` for complete rule documentation.

### Pipelines (scheduled)

ClaroBill operates two distinct pipelines on different cadences:

**Weekly MRF scrape/parse** — Cloud Run Jobs that keep `hospital_charges` fresh:
- **Scraper** (Tue 02:00 UTC) — checks HTTP Last-Modified on every hospital_directory MRF URL, downloads changed files to `gs://mrf-staging` and (Phase 4 onward) `gs://mrf-archive-clarobill-prd` partitioned by `pricing_effective_year`
- **Parser** (Tue 06:00 UTC) — reads pending rows from `mrf_archive_index`, parses CMS MRF v2.0.0 JSON, loads normalised charge rows into `hospital_charges` with `pricing_effective_year` populated

**Annual MRF discovery** — Six-stage pipeline that refreshes `hospital_directory`:
- Currently run manually via `scripts/mrf_discovery/stage*.py`
- Will move to a Cloud Run Job + Cloud Scheduler trigger (Phase 3g, planned)
- Target cadence: once per year (early January, after CMS January re-publication deadline)
- Sources: CMS PI list, CMS POS file, NPPES Registry API, Wikidata SPARQL, then per-hospital website crawl

See `docs/operations.md` for the full pipeline runbook (schedules, dependencies, what to check when something fails) and `docs/gcp-architecture.md` for service accounts and IAM.

---

## Project Structure

```
clarobill/
├── apps/
│   ├── web/                     # Next.js frontend (Vercel)
│   └── engine/                  # Python FastAPI analysis engine (Cloud Run)
│       ├── app/
│       │   ├── api/v1/bills.py  # Analysis pipeline, BigQuery + Supabase queries
│       │   ├── services/
│       │   │   ├── rules_engine.py   # 10 billing rules
│       │   │   ├── parser.py         # OCR text → line items
│       │   │   ├── ai_analysis.py    # Claude integration
│       │   │   └── report_generator.py
│       │   ├── models/bill.py   # Pydantic models + error codes
│       │   └── data/            # CMS reference data loaders
│       └── tests/
├── packages/
│   └── shared/                  # Shared TypeScript types (Bill, BillingError, etc.)
├── pipeline/                    # Weekly MRF scraper + parser (Cloud Run Jobs)
│   ├── scrape_hospital_mrfs.py  # Downloads MRF files to GCS
│   ├── parse_hospital_mrfs.py   # Parses MRF JSON → BigQuery
│   ├── hospital_mrf_utils.py    # CMS MRF v2.0.0 stream parser
│   ├── deploy.sh                # Build image, create/update jobs + schedules
│   └── Dockerfile
├── scripts/                     # Data loaders run on cadences from quarterly to one-time
│   ├── load_*.py                # Annual CMS reference-data loaders (PFS, NCCI, OPPS, etc.)
│   ├── refresh_cms_data.py      # Orchestrates the annual CMS loaders
│   ├── seed_payer_normalizations.py
│   └── mrf_discovery/           # Annual hospital MRF discovery pipeline (CMS-direct)
│       ├── migrate_bq_schema.py        # One-time BQ schema migration
│       ├── setup_archive_bucket.sh     # One-time GCS archive bucket provisioning
│       ├── bq_checkpoint.py            # Shared resumable-checkpoint helpers
│       ├── archive_layout.py           # GCS path scheme for MRF archive
│       ├── nppes_client.py             # NPPES Registry API client
│       ├── stage1_cms_hospital_list.py # CMS PI hospital list seeder
│       ├── stage2_pos_file.py          # CMS POS file enricher
│       ├── stage2_npi_registry.py      # NPI lookups via NPPES Registry API
│       └── stage2_wikidata.py          # Wikidata SPARQL website seeder
├── supabase/
│   └── migrations/              # Supabase schema migrations
└── docs/
    ├── rules-engine.md          # All rules documented
    ├── user-workflow.md         # Full user journey + verification flow
    ├── gcp-architecture.md      # GCP services, IAM, pipelines, data flow
    ├── operations.md            # Pipeline runbook — what runs when, what to check on failure
    ├── decisions/               # Architecture decision records
    └── future_improvements/     # Planned enhancements
```

---

## Local Development

### Prerequisites

- Node.js 20+
- Python 3.11+
- A Supabase project (local or hosted)
- API keys: Anthropic, Google Cloud Vision, Stripe, SendGrid
- (Optional) GCP credentials for BigQuery hospital charge lookups

### Frontend

```bash
cd apps/web
cp .env.example .env.local   # fill in your keys
npm install
npm run dev                  # http://localhost:3000
```

### Engine

```bash
cd apps/engine
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env         # fill in your keys
uvicorn app.main:app --reload --port 8000
```

**Without GCP credentials:** The BigQuery lookups (`HOSPITAL_CHARGE_OUTLIER` and
`NEGOTIATED_RATE_EXCEEDED` rules) are silently skipped when `GCP_PROJECT_ID` is
not set. All Supabase-backed rules still run.

### Running tests

```bash
# Engine (111 tests)
cd apps/engine && python -m pytest tests/ -v

# Type checking
cd apps/engine && python -m mypy app/ --strict
cd apps/web && npm run typecheck

# Frontend
cd apps/web && npm run test
```

### Environment Variables

See `apps/web/.env.example` and `apps/engine/.env.example` for the full list.

Key engine variables:
| Variable | Required | Description |
|----------|----------|-------------|
| `SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Yes | Service role key (bypasses RLS) |
| `ANTHROPIC_API_KEY` | Yes | Claude API key (AI fallback — required so fallback is always available) |
| `GOOGLE_APPLICATION_CREDENTIALS` | No | Path to GCP SA key (enables BigQuery rules) |
| `GCP_PROJECT_ID` | No | GCP project (`clarobill-prd`) |
| `BIGQUERY_DATASET` | No | BigQuery dataset (`hospital_prices`) |

---

## Deployment

| Component | Platform | Config |
|-----------|----------|--------|
| Frontend | Vercel | Root directory: `apps/web` |
| Engine | Google Cloud Run | `apps/engine/Dockerfile` |
| MRF Pipeline | Google Cloud Run Jobs | `pipeline/deploy.sh` |

### Deploy the engine to Cloud Run

**Engine deploys automatically.** Any push to `main` that touches `apps/engine/**`
triggers the Cloud Build trigger `engine-deploy-on-push`, which builds the Docker
image, pushes it to Artifact Registry, and deploys to the `clarobill-engine`
Cloud Run service. No manual deploy needed.

**Manual deploy / rollback:**
```bash
# Build and deploy HEAD manually
gcloud builds submit \
  --config apps/engine/cloudbuild.yaml \
  --project clarobill-prd

# Roll back to a specific commit
gcloud run services update clarobill-engine \
  --image us-central1-docker.pkg.dev/clarobill-prd/cloud-run-source-deploy/clarobill-engine:<COMMIT_SHA> \
  --region us-central1
```

### Deploy the MRF pipeline

```bash
bash pipeline/deploy.sh
```

See `docs/gcp-architecture.md` for complete GCP setup instructions.

---

## Beta Status (2026)

ClaroBill is in beta. Pricing tiers are locked in (`apps/web/src/lib/pricing.ts`) but charges are bypassed via `NEXT_PUBLIC_BETA_MODE=true` until General Availability.

| Phase | Window | Audience | State |
|---|---|---|---|
| Closed beta | now → 2026-05-31 | invite-only, ~50–100 users | active |
| Open beta | 2026-06-01 → 2026-06-30 OR 200 bills processed (whichever first) | public, free signup | upcoming |
| GA | 2026-07-02 onward | public, paid | upcoming |

GA flips `NEXT_PUBLIC_BETA_MODE` to `false` in Vercel and activates Stripe. Full timeline + tier values at `docs/pricing.md`.

---

## License

Proprietary. © Flow Financial Group. All rights reserved.
