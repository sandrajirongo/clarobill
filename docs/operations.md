# ClaroBill Pipeline Operations Runbook

**Audience:** Engineers operating ClaroBill in production.
**Purpose:** Single source of truth for what pipelines exist, what cadence they run on, what they depend on, and what to check when something fails.

If you are onboarding, read this end-to-end before touching any pipeline.

---

## Operating principles

1. **Manual runs are the exception, not the default.** Every recurring pipeline must be Cloud-Run-scheduled by Phase 3g of the MRF discovery rollout. The default operational state is "an engineer is paged when something breaks; otherwise the pipelines run themselves."

2. **Every download is archived to Coldline GCS.** Bills uploaded today must be auditable years from now against the chargemaster that was in force on their service date. Cold storage at $0.004/GB-mo is cheap insurance.

3. **Backward compatibility forever.** A 2024 bill audited in 2030 must produce the same finding it would have produced in 2024. This is enforced by `pricing_effective_year` in `hospital_charges` and immutable archive at `gs://mrf-archive-clarobill-prd/pricing-year={year}/`. **Do not delete historical data.**

4. **Idempotency.** Every pipeline is safe to re-run from any point. Crashes don't require manual cleanup; pipelines pick up where they left off via run-id-keyed checkpoints (BigQuery) or content-hash-keyed objects (GCS).

---

## Pipeline inventory

### 1. Weekly MRF scrape + parse

Keeps `hospital_charges` fresh by re-downloading any MRF whose `Last-Modified` header has changed.

| Property | Value |
|---|---|
| **Cadence** | Weekly, Tuesdays |
| **Scraper job** | `clarobill-mrf-scraper` (Cloud Run Job) |
| **Parser job** | `clarobill-mrf-parser` (Cloud Run Job) |
| **Scraper schedule** | Tue 02:00 UTC (`clarobill-mrf-scraper-weekly`) |
| **Parser schedule** | Tue 06:00 UTC (`clarobill-mrf-parser-weekly`) |
| **Image** | `us-central1-docker.pkg.dev/clarobill-prd/clarobill-pipeline/mrf-pipeline:latest` |
| **Service account** | `clarobill-pipeline-sa@clarobill-prd.iam.gserviceaccount.com` |
| **Reads from** | `hospital_directory` (mrf_url + last_modified) |
| **Writes to** | `gs://mrf-staging/raw/` (scraper), `mrf_archive_index` (Phase 4+), `hospital_charges` (parser) |
| **Why Tuesday** | Hospitals typically update MRF files Mon/Tue after CMS quarterly deadlines. |

**Health check (run weekly):**
- Were both jobs invoked Tuesday? `gcloud run jobs executions list --job clarobill-mrf-scraper --region us-central1`
- Did the parser write rows? `SELECT COUNT(*) FROM hospital_charges WHERE scraped_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 8 DAY)` should be > 0
- Did the scraper detect any change? Some weeks no MRFs change; that's normal. Concerning if zero changes for 4+ consecutive weeks — likely an upstream issue.

**Common failures:**
| Symptom | Cause | Fix |
|---|---|---|
| Scraper logs `404 Not Found` for many hospitals | A hospital system redirected its MRFs | Hosp will re-discover next annual run; flag in `mrf_discovery_checkpoint.error_message` |
| Parser logs `JSONDecodeError` | Hospital published malformed JSON | Skip, alert via Sentry; CMS rule 42 CFR 180 only requires "machine readable", not "valid JSON" |
| Both jobs time out | A slow hospital server is blocking workers | Increase `--task-timeout` or shard via `--tasks N` (already supported) |

---

### 2. Annual MRF discovery

Refreshes `hospital_directory` with newly-certified hospitals, retired hospitals, and changed MRF URLs.

| Property | Value |
|---|---|
| **Cadence** | Annually, mid-January |
| **Why January** | CMS rule 42 CFR 180 requires hospitals to re-publish chargemasters by January 1 each year. Running January 15-20 catches the new versions. |
| **Status** | Stages 1-2 done + applied; Stages 3-6 pending; Cloud Run Job scheduling planned in Phase 3g |
| **Current trigger** | Manual (run `scripts/mrf_discovery/stage*.py` in sequence) |
| **Future trigger** | Cloud Run Job `clarobill-mrf-discovery-annual` on Cloud Scheduler `0 2 15 1 *` (15 January 02:00 UTC) |
| **Reads from** | CMS PI API, CMS POS API, NPPES Registry API, Wikidata SPARQL, hospital websites |
| **Writes to** | `mrf_discovery_checkpoint` (working state), `hospital_directory` (final), `mrf_discovery_runs` (summary) |

**Run order (manual, until Phase 3g):**

```bash
# Generate a fresh run_id once and capture it
RUN_ID=$(python3 scripts/mrf_discovery/stage1_cms_hospital_list.py --project clarobill-prd | tail -1)

# Stages 2A + 2B + 2C run in sequence; each can be re-run if it fails
python3 scripts/mrf_discovery/stage2_pos_file.py --run-id $RUN_ID --project clarobill-prd
python3 scripts/mrf_discovery/stage2_npi_registry.py --run-id $RUN_ID --project clarobill-prd
python3 scripts/mrf_discovery/stage2_wikidata.py --run-id $RUN_ID --project clarobill-prd

# Stages 3-6 (not yet built):
# stage3_website_discovery.py
# stage4_website_crawler.py
# stage5_mrf_validator.py
# stage6_directory_merge.py
```

**Cost estimate (per annual run):**
- Stages 1-2: free (CMS public APIs + NPPES Registry API)
- Stage 3 Tier 3 (Google Places): hard ceiling $450, expected ~$180-220 Year 1, ~$10-20 Year 2+ (cache-driven). See `docs/decisions/2026-04-28-google-places-cost-design.md`.
- Cloud Run Job runtime (~6 hr at 4Gi/2CPU): ~$3
- BigQuery storage: ~$1/yr
- **Total: ~$185-225 first year, ~$15-25/yr after**

**Annual immutable snapshots:** every external-API cache (NPPES at `gs://mrf-staging/nppes-api-cache.json`, Google Places at `gs://mrf-staging/places-api-cache.json`) is snapshotted at end-of-run to `gs://mrf-archive-clarobill-prd/{nppes-api,places-api}-cache-snapshots/{year}.json` for forensic reproducibility. Working caches mutate; snapshots are immutable.

**Why Google Places and not Mapbox / OpenStreetMap:** evaluated 2026-04-28; full reasoning at `docs/decisions/2026-04-28-google-places-cost-design.md` under "Why Google Places, not Mapbox or OpenStreetMap." Short version: cheaper services exist but they don't return the `website` field reliably (Mapbox ~10% coverage vs Google ~80-90%). Mapbox and OSM are kept as future cost-optimisation paths for verification (cheap second-source confirmation) but not for primary discovery.

**Health check (run annually post-execution):**
- `SELECT * FROM mrf_discovery_runs ORDER BY run_started_at DESC LIMIT 1` — final coverage_rate should be ≥ 70% (Year 1 target), trending up year-over-year
- Spot-check 10 random `validated_mrf_urls` — fetch each and confirm it returns valid MRF content

---

### 3. Annual CMS reference data refresh

Keeps the Supabase reference tables (`cms_pfs_indicators`, `ncci_edit_pairs`, `cms_opps_cap`, etc.) fresh against the latest CMS releases.

| Property | Value |
|---|---|
| **Cadence** | Annually (PFS) + Quarterly (NCCI) — varies per source |
| **Trigger** | Manual: `scripts/refresh_cms_data.py` orchestrates the per-source loaders |
| **Future trigger** | Should be moved to a scheduled job (Phase: TBD, likely after MRF discovery automation lands) |
| **Reads from** | Public CMS releases (URLs in each loader script) |
| **Writes to** | Supabase tables under the `public` schema |

Current loaders, by typical refresh cadence:

| Loader | Cadence | Notes |
|---|---|---|
| `scripts/load_cms_pfs.py` | Annual (Jan) | Medicare Physician Fee Schedule |
| `scripts/load_ncci_edits.py` | Quarterly | NCCI Procedure-to-Procedure edit pairs |
| `scripts/load_mue_limits.py` | Quarterly | NCCI Medically Unlikely Edits |
| `scripts/load_opps_cap.py` | Annual (Jan) | OPPS Addendum B (outpatient hospital cap) |
| `scripts/load_ambulance_rates.py` | Annual (Jan) | CMS Ambulance Fee Schedule |
| `scripts/load_ambulance_zip_locality.py` | Annual | Ambulance ZIP-to-locality |
| `scripts/load_anesthesia_cf.py` | Annual | Anesthesia conversion factors |
| `scripts/load_anesthesia_base_units.py` | Annual | Anesthesia base unit table |
| `scripts/load_county_locality.py` | Annual | PFS county-to-locality |
| `scripts/load_hcpcs_codes.py` | Annual | HCPCS Level II quarterly release |
| `scripts/seed_payer_normalizations.py` | Ad-hoc | Payer-name aliases (manual curation) |

**Health check:**
- After each release, `SELECT MAX(effective_year) FROM <table>` should match the year of the latest CMS release.
- A bill with a service date of 2026-Q3 should match a row with `effective_year = 2026`.

---

### 4. Engine deploy (continuous)

| Property | Value |
|---|---|
| **Cadence** | Triggered on every push to `main` that touches `apps/engine/**` |
| **Trigger** | Cloud Build trigger `engine-deploy-on-push` |
| **Image** | `us-central1-docker.pkg.dev/clarobill-prd/cloud-run-source-deploy/clarobill-engine` |
| **Cloud Run service** | `clarobill-engine` |
| **Health check** | `gcloud run services describe clarobill-engine --region us-central1` should show recent deployment after a push. |

---

## Backup and historical-record policy

ClaroBill audits bills against the chargemaster that was in force on the bill's service date. A 2024 bill audited in 2030 must produce the same finding it would have produced in 2024. This requires:

### Immutable evidence vault

- **Bucket:** `gs://mrf-archive-clarobill-prd` (Coldline, US multi-region)
- **Layout:** `pricing-year={year}/{hospital_npi}/{sha256_first16}.{ext}`
- **Retention:** Forever. Lifecycle deletes only noncurrent versions older than 90 days.
- **IAM:** `clarobill-pipeline-sa` has `objectCreator + objectViewer`. **No service account has `objects.delete`** — the absence of delete capability is the immutability guarantee. To clean up anything, a human with `bucketAdmin` has to do it explicitly.

### Versioning of `hospital_charges` rows

- `pricing_effective_year` is `INT64 NOT NULL`. New rows cannot be inserted without a vintage.
- Partitioned by year (`RANGE_BUCKET(pricing_effective_year, GENERATE_ARRAY(2024, 2034, 1))`).
- The rules engine joins by `pricing_effective_year = YEAR(bill.service_date)` with fallback to the nearest prior year, never future-dated.

### Stale data is renamed, not migrated

When a data source is found to be wrong or untrusted (e.g. the legacy Payerset-sourced `hospital_charges` had no vintage and was therefore unreliable for cross-year audits), the table is **renamed** to `*_legacy_stale` rather than fixed in place or deleted. This preserves rows for forensics while taking them out of the rules-engine read path. The rename is a metadata-only operation (instant, free, preserves rows).

---

## Automation roadmap

The current state is "Sandra runs manual `python3 scripts/...` commands." Production-grade is "the pipeline runs itself on Cloud Run + Cloud Scheduler and pages an engineer only on failure." Roadmap:

| Phase | What | Status |
|---|---|---|
| 3g | Cloud Run Job `clarobill-mrf-discovery-annual` + Cloud Scheduler trigger `0 2 15 1 *` | Not started — see `docs/future_improvements/pra-pipeline-build.md` |
| 4 | Effective-dated archiver (rewrite `pipeline/scrape_hospital_mrfs.py` to write to `gs://mrf-archive-clarobill-prd` with year-partitioning) | Not started |
| 5 | Rules engine cutover (read from new effective-dated `hospital_charges`) | Not started |
| Future | Schedule the CMS reference-data loaders as Cloud Run Jobs on cron triggers (today they're manual) | Not started; create a unified `clarobill-cms-refresh` job that orchestrates all loaders |
| Future | Sentry alerting on Cloud Run Job failures (today: only logs in Cloud Logging) | Not started |
| Future | Datadog/Cloud Monitoring dashboards: per-pipeline run-time, success rate, coverage delta vs prior year | Not started |

---

## Pipeline dependency graph

```
              ┌────────────────────────────────────────────┐
              │ ANNUAL MRF DISCOVERY (15 January each year)│
              │ Stages 1-6: refreshes hospital_directory    │
              └─────────────────────┬──────────────────────┘
                                    │
                                    ▼
              ┌────────────────────────────────────────────┐
              │ WEEKLY MRF SCRAPE + PARSE (every Tuesday)   │
              │ Reads hospital_directory.mrf_url            │
              │ Writes mrf_archive_index, hospital_charges  │
              └─────────────────────┬──────────────────────┘
                                    │
                                    ▼
              ┌────────────────────────────────────────────┐
              │ ENGINE (continuous, on every bill upload)   │
              │ Reads hospital_charges by hospital_npi +    │
              │ pricing_effective_year                       │
              └─────────────────────────────────────────────┘
```

**Out-of-band:**

```
              ┌────────────────────────────────────────────┐
              │ ANNUAL CMS REFERENCE DATA REFRESH (Jan/Apr/Jul/Oct)│
              │ Updates Supabase reference tables           │
              │ Independent of MRF pipelines                │
              └─────────────────────────────────────────────┘
```

---

## On-call playbook

### "An audit produced a wrong finding"

1. Pull the bill ID and the rule that fired (`apps/engine/app/services/rules_engine.py`).
2. Find the rule's data source (see "Tables consulted" in `docs/rules-engine.md`).
3. If the source is `hospital_charges`: confirm `pricing_effective_year` matches the bill's service year. If it's a year off, that's the bug — likely a parser issue.
4. If the source is a CMS reference table (`cms_pfs_indicators`, `ncci_edit_pairs`, etc.): confirm the table's `effective_year` matches the bill's service year. If not, the annual loader is overdue.
5. Check whether the source MRF is in `gs://mrf-archive-clarobill-prd/pricing-year=<bill_year>/<npi>/`. If yes, you can reproduce the audit deterministically. If no, the file was never archived for that year — record a known limitation.

### "The weekly scraper logged 0 successful downloads"

1. Look at the most recent run logs: `gcloud run jobs executions list --job clarobill-mrf-scraper --region us-central1`
2. Common causes (in order of likelihood):
   a. CMS or Cloud Build outage during the run window — wait, retry next Tuesday
   b. Massive outage in `hospital_directory.mrf_url` (e.g. a major vendor went down) — confirm by sampling 10 URLs manually with `curl -I`
   c. Service account lost permissions — check `clarobill-pipeline-sa` IAM bindings on the dataset and bucket
3. Manual retrigger: `gcloud run jobs execute clarobill-mrf-scraper --region us-central1`

### "The annual discovery pipeline crashed at stage N"

1. Look up the run_id in `mrf_discovery_checkpoint`.
2. The pipeline is resumable — re-run only the failed stage, e.g. `python3 scripts/mrf_discovery/stage2_npi_registry.py --run-id <run_id> --project clarobill-prd`.
3. The stage will pick up only the rows where its corresponding `*_at` timestamp is NULL.

### "Someone deleted production data"

By design, no service account can delete from `gs://mrf-archive-clarobill-prd`. If data is missing:
1. Check object versioning — `gcloud storage ls --versions gs://mrf-archive-clarobill-prd/...`
2. Restore via `gcloud storage objects restore`
3. If versioning didn't catch it (older than 90-day noncurrent retention), the data is gone — but this scenario should be impossible without a human explicitly using `bucketAdmin`.

---

## References

- `docs/decisions/2026-04-28-cms-direct-mrf-discovery.md` — final architecture decision for the discovery pipeline
- `docs/decisions/2026-04-28-mrf-discovery-build-insights.md` — running insights log (concrete numbers, dead-ends ruled out)
- `docs/future_improvements/pra-pipeline-build.md` — phase-by-phase build status
- `docs/future_improvements/non-medicare-pricing-integrations.md` — coverage roadmap for TRICARE / VA / Medicaid bills
- `docs/gcp-architecture.md` — full GCP architecture, IAM, service accounts
- `docs/rules-engine.md` — rules and the data they read
- `pipeline/deploy.sh` — Cloud Run Job + Cloud Scheduler provisioning script

---

*Last updated: 2026-04-28*
