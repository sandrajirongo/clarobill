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

### 1. Annual + mid-year MRF scrape + parse

Keeps `hospital_charges` fresh by re-downloading any MRF whose `Last-Modified` header has changed. Runs only twice a year because CMS rule 42 CFR 180 requires hospitals to publish/refresh MRFs at most once per year, with ~10% of hospitals also updating in summer. Weekly polling produced no new data 51 weeks per year — the cadence change shipped 2026-04-30 (commit on `main`).

| Property | Value |
|---|---|
| **Cadence** | Annual (Feb 15) + mid-year (Aug 15) |
| **Scraper job** | `clarobill-mrf-scraper` (Cloud Run Job) |
| **Parser job** | `clarobill-mrf-parser` (Cloud Run Job) |
| **Scraper schedules** | Feb 15 02:00 UTC (`clarobill-mrf-scraper-annual`), Aug 15 02:00 UTC (`clarobill-mrf-scraper-midyear`) |
| **Parser schedules** | Feb 15 06:00 UTC (`clarobill-mrf-parser-annual`), Aug 15 06:00 UTC (`clarobill-mrf-parser-midyear`) |
| **Image** | `us-central1-docker.pkg.dev/clarobill-prd/clarobill-pipeline/mrf-pipeline:latest` |
| **Service account** | `clarobill-pipeline-sa@clarobill-prd.iam.gserviceaccount.com` |
| **Reads from** | `hospital_price_transparency` (mrf_url, last_modified_header) joined to `hospital_directory` (hospital_name, state) |
| **Writes to** | `gs://mrf-staging/raw/` (scraper), `gs://mrf-archive/` (immutable archive), `mrf_archive_index`, `hospital_price_transparency` (backfill: file_format, last_scraped_at, hospital_npi), `hospital_charges` (parser) |
| **Why Feb 15** | 6 weeks past the Jan 1 CMS republish deadline — gives hospitals time to fix first-pass errors. Same date as annual discovery so newly-discovered URLs feed straight into the scrape. |
| **Why Aug 15** | Catches the ~10% of hospitals that republish in summer. |

#### Parser env vars (2026-05-04+)

| Var | Default | Effect |
|---|---|---|
| `PARSER_DRIVER` | `bucket_walk` | `archive_index` mode reads pending work from BigQuery and opens blobs from `mrf-archive-clarobill-prd`. Required for retrying historical cohorts whose staging copies were already deleted post-parse. |
| `PARSER_RETRY_PATTERN` | unset | SQL LIKE pattern. When set, matching `parse_status='failed'` rows are flipped to `'pending'` before the run starts. Only useful with `PARSER_DRIVER=archive_index`. Example: `parsed with NULL NPI%`. |
| `CLOUD_RUN_TASK_INDEX` / `_COUNT` | injected by Cloud Run | Task sharding. Both bucket-walk and archive_index drivers stripe work as `rows[index::count]`. Recommended: `--tasks 6 --parallelism 6`. |

#### Scrape-time content validation (2026-05-04+, commit `e2745d4`)

The scraper sniffs the first 4 KB of every HTTP response via
`sniff_mrf_format()` and rejects responses whose format is not in
`ACCEPTED_MRF_FORMATS = {json, csv, zip, xlsx, xml}`. HTML, PDF, and
unknown formats are dropped with no GCS write and no `mrf_archive_index`
row. The 4 KB sniff buffer is spliced back onto the upload stream via
`_PrependedStream` so the bytes the parser eventually sees are
bit-identical to what the scraper received.

Without this, every scheduled scrape re-pollutes the archive with the
same garbage that the 5/3 postmortem flagged.
| **Why not weekly** | MRFs change at most twice a year per CMS rule. Weekly polling burned ~96% of compute on no-op `If-Modified-Since` checks. See `docs/decisions/2026-04-30-pipeline-cadence.md`. |

**Health check (run after each Feb 15 / Aug 15 firing):**
- Were both jobs invoked? `gcloud run jobs executions list --job clarobill-mrf-scraper --region us-central1`
- Did the parser write rows? `SELECT COUNT(*) FROM hospital_charges WHERE scraped_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)` should be in the millions for an annual run, in the hundreds-of-thousands for mid-year (only the ~10% summer republishers register).
- Did `mrf_archive_index.parse_status` flip from 'pending' to 'parsed' for most rows? Some 'failed' is acceptable; many 'failed' = parser regression.

**Manual trigger (one-off for a customer report):**
```bash
# Forces all hospitals' If-Modified-Since to re-evaluate. The scraper still
# skips unchanged files via Last-Modified — this just runs the comparison.
gcloud run jobs execute clarobill-mrf-scraper --region us-central1 --tasks 6
gcloud run jobs execute clarobill-mrf-parser  --region us-central1 --tasks 6
```

**Common failures:**
| Symptom | Cause | Fix |
|---|---|---|
| Scraper logs `404 Not Found` for many hospitals | A hospital system redirected its MRFs | Hosp will re-discover next annual run; flag in `mrf_discovery_checkpoint.error_message` |
| Parser logs `JSONDecodeError` | Hospital published malformed JSON | Skip, alert via Sentry; CMS rule 42 CFR 180 only requires "machine readable", not "valid JSON" |
| Both jobs time out | A slow hospital server is blocking workers | Increase `--task-timeout` or shard via `--tasks N` (already supported) |

---

### 2. Annual + quarterly MRF discovery

Refreshes `hospital_directory` (identity) and `hospital_price_transparency` (MRF URLs) with newly-certified hospitals and changed MRF file locations. Runs Feb 15 (full) + the 15th of May/Aug/Nov (gap-fill only).

| Property | Value |
|---|---|
| **Cadence** | Annual full run + quarterly gap-fills |
| **Job** | `clarobill-mrf-discovery` (Cloud Run Job) |
| **Annual schedule** | Feb 15 02:00 UTC (`clarobill-mrf-discovery-annual`) — runs every stage including Tier 3 paid sweep |
| **Quarterly schedule** | May 15 / Aug 15 / Nov 15 02:00 UTC (`clarobill-mrf-discovery-quarterly`) — passes `--gap-fill-only`; only crawls hospitals where `validated_mrf_urls IS NULL` plus any new CMS-listed hospitals; **skips Tier 3 paid** unless `--include-tier3` is also passed |
| **Why Feb 15** | 6 weeks past Jan 1 CMS republish deadline — hospitals get time to fix first-pass errors before we crawl. |
| **Why the 15th of May/Aug/Nov** | 45 days into each remaining quarter — picks up newly-certified hospitals + retries the ~20% Stage 4 didn't resolve on the previous pass. |
| **Reads from** | CMS PI API, CMS POS API, NPPES Registry API, Wikidata SPARQL, hospital websites |
| **Writes to** | `mrf_discovery_checkpoint` (working state, all stages), `hospital_price_transparency` (MERGEd by Stage 4 on ccn + mrf_url) |
| **Stages** | 1 (CMS list) → 2A/B/B'/C (NPI + website) → 3.1/3.2/3.3 (website discovery) → 4 (MRF URL extraction) |

**Stage 4 (MRF URL extraction):** for each hospital with `hospital_website` set, probes PATH_HEURISTICS paths (~50+) plus the homepage, follows keyword-matching anchors up to `MAX_FOLLOW_DEPTH=3` levels deep (up to `MAX_FOLLOWUPS_PER_PAGE=15` anchors per page), extracts MRF download links via four-pass HTML scan (CMS filename regex, keyword-anchor, any `<a href>` to a data extension, and full-body URL scan for JS/data-attribute links), expands hospital-system TOC JSONs (`*-toc.json`), HEAD-validates every candidate, MERGEs into `hospital_price_transparency` on `(ccn, mrf_url)`. Free, ~20-35 min wall-clock at 60 concurrent workers for ~12,000 hospitals.

**Stage 4 follow signals:** three conditions cause an anchor link to be fetched: (1) keyword in anchor text, (2) keyword in href, (3) href matches a PATH_HEURISTICS path. Condition 3 (`_PATH_HEURISTIC_RE`) catches generic "Learn More" links that route to a price-transparency page.

**Listing-page detection:** Stage 4 logs `[listing_page] <url> yielded N file links` when a single page yields 5 or more file links. These entries in Cloud Run logs are the signal for Kaiser, HCA, CommonSpirit, and other multi-facility systems. Check for them after each run.

**Manual triggers:**

```bash
# Full annual run (Stages 1-4 + Tier 3 paid)
gcloud run jobs execute clarobill-mrf-discovery --region us-central1

# Gap-fill only (free, skips Tier 3)
gcloud run jobs execute clarobill-mrf-discovery --region us-central1 \
  --args=--gap-fill-only

# Re-run only Stage 4 (URL crawler) on an existing run
gcloud run jobs execute clarobill-mrf-discovery --region us-central1 \
  --args=--start-stage=stage4_mrf_urls,--run-id=<existing-run-id>

# Re-run only Tier 3 with a fresh budget
gcloud run jobs execute clarobill-mrf-discovery --region us-central1 \
  --args=--start-stage=stage3_tier3,--run-id=<existing-run-id>
```

**Cost estimate:**
- **Annual run (Feb 15):** Stages 1-2 free; Stage 3 Tier 3 hard ceiling $450 (Year 1 actual ran $349.92); Stage 4 free; Cloud Run runtime ~$3-5. **~$355-460 first year, ~$15-25/yr after** (cache-driven post-Year-1 Tier 3).
- **Quarterly gap-fills (May/Aug/Nov 15):** all free — `--gap-fill-only` skips Tier 3 by default. Cloud Run runtime ~$1 each. **~$3/yr total.**
- See `docs/decisions/2026-04-28-google-places-cost-design.md` and `docs/decisions/2026-04-30-pipeline-cadence.md`.

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

## Running migrations locally

The Supabase CLI's local Docker stack mirrors the prod schema, so it's the right place to verify a migration before applying it to prod.

```bash
# One-time per machine — boots Postgres + Auth + Storage in Docker.
supabase db start

# Iterate: edit migration files, then re-apply against the local stack.
supabase db reset       # tears down the local DB, re-applies every migration in order

# When you're satisfied, push to prod (the CLI checks schema_migrations and
# only sends migrations not yet recorded as applied).
supabase db push
```

### Migration-check CI

Every PR that touches `supabase/migrations/**` triggers `.github/workflows/migration-check.yml`, which boots a fresh local Postgres on the GitHub runner, applies every migration in lex order, runs the down-migration sibling for every up-migration touched in the PR, then re-applies the up. A red migration-check almost always means one of:

- A new migration assumes a dashboard-enabled extension. Wrap the call in the `do $$ if exists ... end $$` guard from CLAUDE.md Rule 7.
- A new `.down.sql` sibling is missing or doesn't actually reverse the up. The CI logs the failing `psql -f` line.
- The PR added an up migration but didn't add a down sibling. CI emits a `::warning::` rather than failing for this — the workflow allows reversibility-untested migrations through, so don't ignore the warning.

### Down migrations

Down siblings live in `supabase/migrations_down/<version>_<name>.down.sql` (mirror of the up filename). They're never auto-applied — they exist solely for the reversibility test and for the rare case where Sandra needs to manually roll back a migration (in which case: run the down via SQL editor, then `supabase migration repair --status reverted <version>` to update the cloud's tracking table).

### One-time history repair (2026-05-04)

The `schema_migrations` table on the cloud project carried duplicate rows for several pre-CLI migrations because the SQL-editor-applied history was never reconciled. The fix was a one-time `supabase migration repair --status applied <version> ...` covering all 23 versions. After repair, `supabase migration list` returns clean local↔remote pairs with no phantoms. If the cloud DB ever shows phantoms again, the dedup query at `docs/operations/ci-cd.md` collapses them safely (system table, no application data risk).

---

## Automation roadmap

The current state is "Sandra runs manual `python3 scripts/...` commands." Production-grade is "the pipeline runs itself on Cloud Run + Cloud Scheduler and pages an engineer only on failure." Roadmap:

| Phase | What | Status |
|---|---|---|
| 3g | Cloud Run Job `clarobill-mrf-discovery-annual` + Cloud Scheduler trigger `0 2 15 1 *` | Not started — see `docs/future-improvements/pra-pipeline-build.md` |
| 4 | Effective-dated archiver (rewrite `pipeline/scrape_hospital_mrfs.py` to write to `gs://mrf-archive-clarobill-prd` with year-partitioning) | **Done 2026-04-29** (commit `8e4a796`) |
| 4 follow-ups | Postmortem #1 (scrape-time validation) + #2 (parser-from-archive_index) + URL-NPI fallback + NPPES resolver | **Done 2026-05-04** (`cb9b420`, `e2745d4`, `5a1de5d`, `750f83b`, `3684894`, `6bc53c5`) |
| 4a-4d | CSV-format MRF parser rollout | In progress — see `docs/decisions/2026-05-04-mrf-coverage-plan.md` |
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
              │ SCRAPE + PARSE (Feb 15, Aug 15)             │
              │ Reads hospital_price_transparency.mrf_url   │
              │ Writes mrf_archive_index, hospital_charges, │
              │ hospital_price_transparency (backfill)       │
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
2. Find the rule's data source (see "Tables consulted" in `docs/architecture/rules-engine.md`).
3. If the source is `hospital_charges`: confirm `pricing_effective_year` matches the bill's service year. If it's a year off, that's the bug — likely a parser issue.
4. If the source is a CMS reference table (`cms_pfs_indicators`, `ncci_edit_pairs`, etc.): confirm the table's `effective_year` matches the bill's service year. If not, the annual loader is overdue.
5. Check whether the source MRF is in `gs://mrf-archive-clarobill-prd/pricing-year=<bill_year>/<npi>/`. If yes, you can reproduce the audit deterministically. If no, the file was never archived for that year — record a known limitation.

### "The annual/mid-year scraper logged 0 successful downloads"

1. Look at the most recent run logs: `gcloud run jobs executions list --job clarobill-mrf-scraper --region us-central1`
2. Common causes (in order of likelihood):
   a. CMS or Cloud Build outage during the run window — wait, retry on the next scheduled date
   b. Massive outage in `hospital_price_transparency.mrf_url` (e.g. a major vendor went down) — confirm by sampling 10 URLs manually with `curl -I`
   c. Service account lost permissions — check `clarobill-pipeline-sa` IAM bindings on the dataset and bucket
   d. **Scrape-time format guard rejecting everything** — this can happen if `sniff_mrf_format()` is over-strict; check logs for `Rejecting non-MRF response` warnings. Compare reject volume against historic %.
3. Manual retrigger: `gcloud run jobs execute clarobill-mrf-scraper --region us-central1`

### "I shipped a parser fix and want to retry historical 'failed' rows"

1. Identify the cohort by `parse_error` LIKE pattern from `mrf_archive_index`.
2. Trigger a one-off run with both env-var overrides:
   ```bash
   gcloud run jobs execute clarobill-mrf-parser \
     --region=us-central1 --tasks=6 \
     --update-env-vars="PARSER_DRIVER=archive_index,PARSER_RETRY_PATTERN=<your-LIKE-pattern>"
   ```
3. The driver flips matching rows to `pending`, then processes from
   `mrf-archive-clarobill-prd`. Source blobs are NOT deleted (immutable).
4. Watch BQ delta: `parse_status` distribution + `hospital_charges` row + NPI counts.

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

## BigQuery tables (hospital_prices dataset)

| Table | Partition | Written by | Purpose |
|---|---|---|---|
| `hospital_directory` | `DATE(last_website_validated_at)` | Stages 1-3 | Hospital identity: one row per hospital. Contains name, state, CCN, NPI, website URL. Join key for all pipeline tables. |
| `hospital_price_transparency` | `DATE(last_scraped_at)` | Stage 4 (MRF URLs), scraper (backfill) | One row per discovered MRF file URL per hospital. Stage 4 MERGEs on `(ccn, mrf_url)`. Scraper backfills `file_format`, `last_scraped_at`, `hospital_npi`. `is_active=FALSE` when HEAD returns 404. |
| `mrf_archive_index` | `DATE(scraped_at)` | Scraper | Scrape ops log. One row per downloaded file. Tracks `parse_status` (pending/parsed/failed) so the parser can pick up work. |
| `hospital_charges` | `pricing_effective_year` | Parser | Price data at scale. One row per CPT/line-item/payer combination per hospital. The only table with `pricing_effective_year`. |
| `mrf_discovery_checkpoint` | None | All discovery stages | Working state for the annual discovery run. Keyed on `(run_id, ccn)`. Stages write their outputs here; Stage 4 promotes to `hospital_price_transparency`. |

**Join pattern (rules engine):**
```sql
SELECT hc.*
FROM hospital_charges hc
WHERE hc.hospital_npi = @npi
  AND hc.pricing_effective_year = EXTRACT(YEAR FROM @service_date)
```
CCN is stored for traceability but the rules engine joins on NPI only.

**Coverage check after Stage 4 run:**
```sql
SELECT mrf_discovery_method, COUNT(*) AS n
FROM `clarobill-prd.hospital_prices.hospital_price_transparency`
GROUP BY 1 ORDER BY 2 DESC;
```

**Listing-page check after Stage 4 run:**
Grep Cloud Run logs for `[listing_page]` — confirms Kaiser, Sutter, HCA, CommonSpirit system pages were found.

---

## References

- `docs/decisions/2026-04-28-cms-direct-mrf-discovery.md` — final architecture decision for the discovery pipeline
- `docs/decisions/2026-04-28-mrf-discovery-build-insights.md` — running insights log (concrete numbers, dead-ends ruled out)
- `docs/future-improvements/pra-pipeline-build.md` — phase-by-phase build status
- `docs/future-improvements/non-medicare-pricing-integrations.md` — coverage roadmap for TRICARE / VA / Medicaid bills
- `docs/architecture/gcp-resources.md` — full GCP architecture, IAM, service accounts
- `docs/architecture/rules-engine.md` — rules and the data they read
- `pipeline/deploy.sh` — Cloud Run Job + Cloud Scheduler provisioning script

---

*Last updated: 2026-04-28*

---

_Last reviewed: 2026-05-08_
