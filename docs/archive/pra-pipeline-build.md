# MRF Discovery Pipeline — Build Log

**Status:** ARCHIVED 2026-05-05 — pipeline build complete; current operating contract lives in [operations/pipeline-runbook.md](../operations/pipeline-runbook.md). Kept as a chronological record of the build phases.

> **Note:** This file was originally named for the PRA-sourced plan. As of
> 2026-04-28 we have pivoted to CMS-direct discovery (`docs/decisions/2026-04-28-cms-direct-mrf-discovery.md`).
> The schema and infrastructure work in Phases 1-2 is unchanged; only the
> discovery source has changed.

Living document for the in-progress build. Tracks what's done, what's next,
and the rollback plan if any phase needs to be aborted.

Companion docs:

- `docs/future-improvements/mrf-discovery-pipeline.md` — full CMS-direct pipeline design
- `docs/future-improvements/pra-outreach-email.md` — Plan C partnership outreach to Patient Rights Advocate (sent 2026-04-28, awaiting reply)
- `docs/decisions/2026-04-28-cms-direct-mrf-discovery.md` — final architecture decision
- `docs/decisions/2026-04-28-mrf-discovery-build-insights.md` — **running insights log** (every "why" decision, every dead-end, every concrete number). Updated every working session.

---

## Architecture in one paragraph

CMS requires every Medicare-certified hospital (~7,000 of them) to publish a Machine-Readable File of standard charges. We discover each hospital's MRF URL once a year by combining four free public sources (CMS Promoting Interoperability hospital list, CMS Provider of Services file, NPPES bulk download, Wikidata) and filling the long tail with the Google Places API. Once we have a website per hospital, a crawler (httpx with Playwright fallback for JS-rendered sites) finds the MRF link via the price-transparency page, sitemap, or footer, plus TOC expansion for hospital systems. Every download is archived immutably to GCS partitioned by `pricing_effective_year` and indexed in BigQuery. Bills are joined to charges by `pricing_effective_year = YEAR(bill.service_date)` so a 2026 bill is always evaluated against the 2026 chargemaster.

---

## Phase 1 — Schema (done 2026-04-27)

### What got built

- `scripts/mrf_discovery/__init__.py` — package marker
- `scripts/mrf_discovery/migrate_bq_schema.py` — idempotent migration with `--dry-run` and `--rollback-rename`
- `scripts/mrf_discovery/bq_checkpoint.py` — shared checkpoint helpers (will be generalized for Plan A stage names in Phase 3a)

### What the migration does

1. **Renames `hospital_charges` → `hospital_charges_legacy_stale`.** Legacy rows have no `pricing_effective_year`, so a 2026 bill could be compared to a chargemaster of unknown vintage. Renaming takes them out of the rules-engine read path immediately while preserving rows for forensics.
2. **Creates a fresh `hospital_charges`** with `pricing_effective_year INT64 NOT NULL`, partitioned by year, clustered by `(hospital_npi, code)`. New rows cannot be inserted without a vintage.
3. **Adds 12 new columns to `hospital_directory`:** `ccn`, `address`, `zip_code`, `phone`, `hospital_website`, `price_transparency_page_url`, `pra_facility_uuid`, `last_pra_check`, `mrf_pricing_effective_year`, `mrf_discovery_method`, `mrf_file_format`, `mrf_file_size_bytes`. The two PRA-named columns (`pra_facility_uuid`, `last_pra_check`) are unused under Plan A but harmless; they may be repurposed if Plan C lands and we re-introduce PRA as a seed source.
4. **Creates `mrf_archive_index`** — canonical index of every MRF file archived to GCS, keyed by `(hospital_npi, pricing_effective_year, sha256)`. `parse_status` drives the parser's work queue.
5. **Creates `mrf_discovery_runs`** — one row per discovery run for coverage trending.

### How to apply

```bash
python scripts/mrf_discovery/migrate_bq_schema.py --dry-run --project clarobill-prd
python scripts/mrf_discovery/migrate_bq_schema.py --project clarobill-prd
```

### Rollback

```bash
python scripts/mrf_discovery/migrate_bq_schema.py --rollback-rename --project clarobill-prd
```

---

## Phase 2 — GCS archive bucket (done 2026-04-27, applied)

### What got built

- `scripts/mrf_discovery/setup_archive_bucket.sh` — idempotent provisioning script (`APPLY=1` to execute).
- `scripts/mrf_discovery/archive_layout.py` — pure-function helpers for the GCS path scheme.
- `apps/engine/tests/scripts/test_archive_layout.py` — 27 passing tests.

### Bucket configuration

- **Name:** `gs://mrf-archive-clarobill-prd` (project-ID suffix because GCS bucket names are globally unique)
- **Storage class:** Coldline (5x cheaper than Standard for write-once, read-rarely)
- **Versioning:** enabled
- **IAM:** `clarobill-pipeline-sa` gets `objectCreator + objectViewer` only — no delete capability (immutability guarantee for evidence)

### Layout

```
gs://mrf-archive-clarobill-prd/
  pricing-year={year}/
    {hospital_npi-or-uuid}/
      {sha256_first16}.{ext}              # raw MRF, immutable
      {sha256_first16}.meta.json          # provenance metadata
```

---

## Phase 3 — CMS-direct discovery pipeline (in progress)

Pivoted from PRA-sourced to CMS-direct on 2026-04-28 after Cloudflare silent-block prevented PRA scraping. See `docs/decisions/2026-04-28-cms-direct-mrf-discovery.md` for full reasoning.

Six stages, executed in sequence by a top-level orchestrator. Each stage is resumable independently via the `mrf_discovery_checkpoint` table.

### Stage 1: CMS Promoting Interoperability hospital list (next)

- Source: `data.cms.gov/provider-data/dataset/xubh-q36u` (CMS PI list, ~7,000 hospitals, free, quarterly refresh)
- Output: one row per CCN seeded into `mrf_discovery_checkpoint` with name, address, city, state, zip, phone, hospital type, ownership, overall rating
- Resumable: skip rows where `cms_loaded_at IS NOT NULL`

### Stage 2: NPI + metadata resolution

- **Substep A:** CMS Provider of Services file → CCN→NPI mapping (~98% coverage). Free, quarterly, includes bed counts and Medicare carrier codes.
- **Substep B:** NPPES bulk download (monthly full replacement, ~8GB compressed) → website URLs for ~50% of hospitals.
- **Substep C:** Wikidata SPARQL → ~500 major hospital systems.

### Stage 3: Website discovery

- **Tier 1:** Validate URLs from Stage 2 (HEAD check).
- **Tier 2:** Domain pattern inference for hospitals without a Stage 2 URL.
- **Tier 3:** Google Places API for the long tail (~$150-200 one-time, cached forever).

### Stage 4: Crawler

- httpx async fetch with Playwright fallback for JS-rendered sites
- Score links against CMS-mandated paths (`/price-transparency`), patterns (`/standard-charges`, `/chargemaster`, `/cdm`), sitemap.xml, footer
- TOC detection for hospital systems (HCA, Ascension, etc. — one TOC resolves up to 180 facilities)

### Stage 5: MRF validation

- HEAD check, content sample, extension validation
- TOC expansion → populate `mrf_toc_index`

### Stage 6: BigQuery MERGE

- MERGE into `hospital_directory` on CCN
- Append summary row to `mrf_discovery_runs`

---

## Phase 4 — Effective-dated archiver (DONE 2026-04-29, hardened 2026-05-04)

`pipeline/scrape_hospital_mrfs.py` and `pipeline/parse_hospital_mrfs.py`
were rewritten in commit `8e4a796` to compute `pricing_effective_year`,
stream-download to `gs://mrf-archive-clarobill-prd/pricing-year={year}/...`,
and use `mrf_archive_index` for parse-state tracking.

**5/3 postmortem follow-ups shipped 2026-05-04:**

| # | Item | Commit |
|---|---|---|
| 1 | URL-NPI fallback + strict mode | `cb9b420` |
| 2 | Scrape-time content validation (HTML/PDF reject, format sniff) | `e2745d4` |
| 3 | Parser-from-`mrf_archive_index` driver (`PARSER_DRIVER=archive_index`) | `5a1de5d` |
| 4 | NPPES-based EIN/slug → NPI resolver | `750f83b` |
| 5 | Driver dedupe (`GROUP BY gcs_uri`) — runaway-loop fix | `3684894` |
| 6 | Driver task sharding (`--tasks 6 --parallelism 6`) | `6bc53c5` |

**4a-4d (CSV-format support):** see
[`docs/decisions/2026-05-04-mrf-coverage-plan.md`](../decisions/2026-05-04-mrf-coverage-plan.md)
for the full design and phased rollout.

---

## Phase 5 — Rules engine effective-date join (not yet started)

`apps/engine/app/services/rules_engine.py` lines ~804-849 are updated to query by `pricing_effective_year = YEAR(bill.service_date)` with fallback to the nearest prior year. Test cases: 2026 bill against 2026 MRF fires; 2026 bill against 2027 MRF does not; 2026 bill with only 2025 MRF available fires using 2025; 2026 bill with no MRF skips silently.

---

## Phase 6 — Cutover (not yet started)

Switch rules engine to read new `hospital_charges`. Retain `hospital_charges_legacy_stale` for ~6 months for forensics, then drop.

---

## Status board

| Phase | Status | Notes |
|---|---|---|
| 1. Schema | done + applied | Migration applied to `clarobill-prd` 2026-04-28 |
| 2. GCS archive bucket | done + applied | `gs://mrf-archive-clarobill-prd` live as of 2026-04-27 |
| 3a. Generalize bq_checkpoint for Plan A | done | 2026-04-28 — stage names renamed to `cms_loaded`/`nppes_resolved`/`website_found`/`crawl_complete`/`mrf_validated`/`bq_committed` |
| 3b. Stage 1 (CMS PI list) | done + applied | 2026-04-28 — 5,426 hospitals seeded; DoD/VA filter added after real run; dry-run + real-run executed |
| Real checkpoint state (post-cleanup) | 13,833 distinct US civilian-MRF-publishing hospitals | 2026-04-28 |
| 3c. Stage 2A (POS file) | done + applied | `stage2_pos_file.py`; ran 2026-04-28 with batched insert fix |
| 3c. Stage 2B (NPI Registry API) | done + applied | `stage2_npi_registry.py` + `stage2_npi_registry_pass2.py` (suffix-drop + truncation re-pass) + shared `nppes_client.py`. Real-run results 2026-04-28: 6,603 / 13,833 NPIs (47.7%) via name-matching. Pass 2B (address-based) + Pass 2C (broad-pull fuzzy match) designed and deferred to `docs/future-improvements/npi-coverage-improvement-passes.md`; revisit after Phase 4 parser backfill. |
| 3c. Stage 2C (Wikidata SPARQL) | done (code) | `stage2_wikidata.py` + 15 tests; runs in <5 sec |
| 3d. Stage 3 (Website discovery + Google Places) | not started | |
| 3e. Stage 4 (Crawler) | not started | The hardest stage |
| 3f. Stage 5 (MRF validator + TOC expansion) | not started | |
| 3g. Stage 6 (BQ MERGE) + orchestrator | not started | |
| 3h. Discovery Dockerfile + Cloud Run job | not started | |
| 4. Effective-dated archiver | **done + applied** | Phase 4 base shipped 2026-04-29 (`8e4a796`); 5/3 postmortem follow-ups + hardening shipped 2026-05-04 (`cb9b420`, `e2745d4`, `5a1de5d`, `750f83b`, `3684894`, `6bc53c5`) |
| 4a-4d. CSV-format MRF support | in progress | Design at `docs/decisions/2026-05-04-mrf-coverage-plan.md`; 4a (Sutter + framework) targeted for the 2026-05-04 session |
| 5. Rules engine effective-date join | not started | |
| 6. Cutover | not started | |
