# MRF Discovery Pipeline — Running Insights Log

**Started:** 2026-04-27
**Status:** Living document — appended every working session
**Purpose:** Capture every "why" decision, every dead-end ruled out, every concrete number observed during the build. The architectural decisions live in their own dated docs; this is the engineer's notebook so future-you (or a partner) can reconstruct the reasoning behind every choice without re-doing the reconnaissance.

---

## How to use this file

- **Insights are dated and bucketed by topic.** Newest at the bottom of each section.
- **Numbers are concrete.** "5,426 hospitals" not "~5,000". "7,131 bytes" not "small". If you find yourself writing a hand-wave, look it up.
- **Dead-ends are recorded too.** A negative finding ("PRA scraping doesn't work because X") is as valuable as a positive one — it stops us from re-attempting.
- **Code paths are linked.** When an insight refers to a behavior in code, cite the file and line so a reader can verify.

---

## Architecture insights

### Why effective-dating is correctness, not metadata (2026-04-27)

A bill from 2026-03-15 must be compared to the MRF that was in force on 2026-03-15, not whatever MRF the hospital published most recently. CMS requires hospitals to re-publish chargemasters every January; comparing across years produces false-positive overcharge claims.

**This is the worst class of defect for ClaroBill.** A false "you were overcharged" in a dispute letter that the hospital can rebut destroys patient trust in our tool. Missing a real overcharge is a smaller harm than asserting a fake one.

The new `hospital_charges` table enforces this at the schema level: `pricing_effective_year INT64 NOT NULL`. New rows cannot be inserted without a vintage. The legacy table (renamed `hospital_charges_legacy_stale`) had no such column — every existing row is of unknown vintage and is therefore untrusted, hence the rename out of the rules-engine read path.

The rules engine (Phase 5) joins by `pricing_effective_year = YEAR(bill.service_date)` with fallback to the nearest prior year, **never future-dated**. If no MRF exists for a hospital at a given date, the rule is **skipped, not assumed**. Skipping is better than guessing.

### GCS as cold archive, BigQuery as hot index (2026-04-27)

GCS holds raw MRF files immutably (cheap: $0.004/GB-mo Coldline). BigQuery holds parsed charges keyed by `(hospital_npi, code, pricing_effective_year)` so range-queries by bill date are O(1). We never re-parse old MRFs and never lose them.

Three guarantees enforced by *configuration*, not policy text:

1. **Immutability via IAM.** `clarobill-pipeline-sa` gets `roles/storage.objectCreator` and `roles/storage.objectViewer` — but **not** `objectAdmin`. The absence of `storage.objects.delete` means a bug, a compromised key, or an accidental rm cannot destroy archived evidence. To delete anything, a human with `bucketAdmin` has to do it explicitly. Same posture banks use for transaction logs.
2. **Deduplication via filename.** sha256 is part of the GCS object name (`{sha256_first16}.{ext}`), so two writes of identical content produce the same path and the second is a no-op. No HEAD-then-decide round trips.
3. **Audit trail via versioning.** Bucket-level versioning is enabled as belt-and-suspenders. Lifecycle deletes noncurrent versions only after 90 days and only when ≥5 newer versions exist; current versions never expire.

This shape exists because if a patient ever sues a hospital using a ClaroBill audit and we get subpoenaed for the MRF that was in force on a given date, "give me everything under `pricing-year=2026/{npi}/`" is a one-line answer. **Time-partitioned + immutable + content-hashed = chain of custody.**

### Why the project-ID suffix on `mrf-archive-clarobill-prd` (2026-04-27)

GCS bucket names are globally unique across all of GCP. The unsuffixed `mrf-archive` was already taken by some other GCP user. We use the project-ID *suffix* pattern that GCP itself applies automatically (`clarobill-prd_cloudbuild`, `run-sources-clarobill-prd-us-central1`).

Sandra's general convention is **no `clarobill-` prefix on resources** — the project ID already namespaces everything inside it. GCS buckets are the documented exception because of the global-uniqueness collision. **Suffix, not prefix.** The project ID stays as a tail-disambiguator, not a primary identifier.

### Why `RANGE_BUCKET(pricing_effective_year, GENERATE_ARRAY(2024, 2034, 1))` (2026-04-27)

BigQuery integer-range partitioning is cheaper than DATE partitioning here because we never query by sub-year granularity, and a 10-year fixed bucket bounds the partition count to 10 (BQ caps at 4,000). The bound is generous — we'll re-extend in 2034.

### Why per-run inflight tables instead of one persistent checkpoint (2026-04-27)

The original CMS-direct doc proposed one big checkpoint table, but for monthly runs that's harder to reason about ("which row belongs to which run?"). Keying by `(run_id, ccn)` means each run is fully isolated and we can keep the audit-trail tables strictly append-only.

`mark_complete` writes to the same row instead of inserting a new one — stages 2-4 all enrich the same hospital. If they each appended, joining them would need MAX-by-stage logic. Updating in place keeps stage joins trivial — `WHERE bq_committed_at IS NOT NULL` is the final-state filter.

---

## Failed reconnaissance — Plan B (PRA scraping)

### Reconnaissance summary (2026-04-27 to 2026-04-28)

Patient Rights Advocate publishes a directory at `hospitalpricingfiles.org` listing 7,096 hospital MRF URLs. Their detail pages render the actual public MRF link (which points to the hospital's own server, not PRA), so the original plan was to render each detail page in headless Playwright once a month and use them as a directory service.

**Result: blocked at the Cloudflare CDN level.** Three escalating attempts:

#### Attempt 1: static fetch (2026-04-27)
```
$ curl https://hospitalpricingfiles.org/details/{uuid}
5039 bytes — React shell, empty <div id="root">
```
Confirmed: page is JS-rendered.

#### Attempt 2: vanilla Playwright + handcrafted stealth (2026-04-27)
- Headed and headless modes
- Patched `navigator.webdriver`, `chrome.runtime`, plugins, languages, WebGL vendor
- Browser-realistic UA, viewport, locale, timezone
- Result: **Turnstile widget rendered but never resolved client-side.** Captured HTML stayed at 7,131 bytes — pre-Turnstile shell. React app sat empty.

#### Attempt 3: `patchright` (Cloudflare-aware Playwright fork) + full stealth init (2026-04-28)
Network-instrumented diagnostic at `_diagnose_pra.py` (now deleted) captured every request/response in a 60-second settle window. Findings:

- **Turnstile widget *did* resolve client-side this time.** `cf-turnstile-response` input field populated with token > 10 chars.
- **Captured HTML at three checkpoints:**
  - t0 (after goto): 7,036 bytes
  - t1 (after Turnstile resolve): 7,036 bytes ← no change
  - t2 (after 60s settle): 7,131 bytes ← only 95 bytes added (CF challenge-platform widget metadata)
- **`document.querySelector('#root').innerText.length` = 4 characters** for the entire 60-second window. The page body was effectively empty.
- **Network log showed the React app made ZERO calls to `staging01.visiblecharges.com`** (the data API). Not before Turnstile, not after. The only post-Turnstile network activity was Cloudflare's own challenge-platform pings, including a critical `[401]` from `cdn-cgi/challenge-platform/h/g/pat/`.

#### Diagnosis (the key insight)

That 401 from `cdn-cgi/challenge-platform/h/g/pat/` is **Cloudflare's silent post-attestation token check**. Turnstile resolving client-side is *not* the actual gating signal — it's theater. An upstream CF state machine validates IP reputation, browser session continuity, and other signals invisible to the page. The `cf-turnstile-response` token populates the form field, but CF still rejects the session for actual data fetches.

**This is why it cannot be defeated by stealth alone.** Stealth fixes the *fingerprint* — what JS detection scripts see when they probe the browser. CF's silent block fails the *session* — what the CF edge already concluded about this IP+UA pair before we sent any request.

The actual paths to bypass are residential-IP proxies + heavier stealth-as-a-service like FlareSolverr, or reusing real-Chrome user-data-dirs with CF-trusted cookies. Both are recurring engineering cost in an ongoing arms race.

#### Why we stopped (the honest reasoning)

1. **Cost-of-ownership math.** Plan A (CMS-direct) is a one-time integration with public APIs. Plan B even after a successful bypass is a perpetual maintenance burden because CF detection updates frequently.
2. **Brand/posture.** ClaroBill's pitch is "we help patients catch unfair behavior." Defeating a non-profit's anti-bot system to scrape their curated dataset, even when our intent is mission-aligned, is the wrong posture. PRA wouldn't assume good intent if they discovered scraping in their logs.
3. **The polite path exists.** Plan C (email PRA for partnership) costs an email and might unlock everything. Sandra sent it 2026-04-28; if granted, PRA's data accelerates Plan A; if declined, Plan A ships unchanged.

#### What's preserved from this dead end

- The diagnosis (in this doc and `2026-04-28-cms-direct-mrf-discovery.md`) so we don't re-attempt without explicit reason
- The schema, archive bucket, and checkpoint helpers (all source-agnostic; they were built before Plan B was attempted)
- A memory note `feedback_no_pra_scraping.md` so future Claude sessions don't try this again

---

## CMS POS file insights

### POS file does NOT contain NPIs (2026-04-28)

The original `mrf-discovery-pipeline.md` doc said the POS file would give us CCN→NPI via a column called `NATL_PRVDR_IDFR`. Probing the live Q1 2026 file showed **473 columns, none of which are NPI**. Either CMS removed it at some point, or the original doc was wrong.

The actual canonical CCN→NPI source is the NPPES bulk download (Substep B), via its `Other_Provider_Identifier_*_*` columns where `Other_Provider_Identifier_Type_Code_X = '04'` (Medicare CCN). NPPES has both NPI and CCN on the same row, plus the website URL we want anyway.

**Implication:** Substep A's job is *not* CCN→NPI. Its actual responsibilities:
1. Add the ~1,500 specialty/critical-access hospitals missing from the PI list (Stage 1's source had only star-rated facilities)
2. Enrich existing checkpoint rows with `bed_count`, `medicare_carrier_code`, `hospital_type` corrections from the authoritative POS columns

### Why we use the stable API URL, not the dated CSV link (2026-04-28)

CMS publishes two URLs for the same data:
- Dated: `data.cms.gov/sites/default/files/2026-04/8ff9bcf4-.../Hospital_and_other.DATA.Q1_2026.csv` — changes every quarter
- Stable: `data.cms.gov/data-api/v1/dataset/8ba0f9b4-9493-4aa0-9f82-44ea9468d1b5/data` — always serves the latest

We hardcode the stable API URL. This means quarterly refreshes happen automatically without code changes; the trade-off is we cannot pin to a specific historical quarter without parsing the dataset's full distribution catalogue from `data.json`. We don't need historical pinning — we re-scan annually and write the result with the run timestamp baked into the checkpoint row.

### Provider category filter (PRVDR_CTGRY_CD) (2026-04-28)

The full POS dataset includes nursing homes, hospices, ambulatory surgical centres, ESRD facilities, etc. None of those publish CMS Hospital Price Transparency MRFs (different rule, 42 CFR 482/485 vs 42 CFR 416 etc.). We filter at parse time to:

- `01` Short-Term Acute Care Hospital
- `02` Long-Term Care Hospital
- `04` Religious Non-Medical Health Care Institution
- `06` Psychiatric Hospital
- `07` Rehabilitation Hospital
- `08` Children's Hospital
- `14` Critical Access Hospital
- `21` Distinct Part Psychiatric Unit
- `22` Distinct Part Rehabilitation Unit

Filtering at parse time means our staging table never contains non-hospital rows, so the MERGE statement against the checkpoint can't accidentally insert a nursing home as if it were a hospital.

### POS uses ALL CAPS; we don't overwrite Stage 1 names (2026-04-28)

POS facility names are like "SOUTHEAST HEALTH MEDICAL CENTER". The PI list (Stage 1) uses Title Case: "Southeast Health Medical Center". When MERGE'ing POS into the checkpoint, we don't update `hospital_name` or `address` on existing rows — the PI list's formatting is cleaner. We only fill in those fields for *new* CCNs that weren't in the PI list.

### Final post-cleanup checkpoint count: 13,833 hospitals (2026-04-28)

After three filter rounds against the real BQ data:

1. **Stage 2A POS produced 29,591 distinct CCNs** post-MERGE — far more than the original "~7,000" planning estimate.
2. **Cleanup DELETE removed 15,758 rows** that did not belong: 15,324 distinct-part psychiatric units (CCN code 21, sub-units inside parent hospitals — parent's MRF covers them), 132 VA medical centers (no CMS MRF; covered by VA Community Care fee schedule), 32 DoD military treatment facilities (no CMS MRF; covered by TRICARE TMAC), and 270 non-US rows (CN/MX cross-border facilities).
3. **Result: 13,833 distinct CCNs, all unique, all US, all civilian, all CMS-MRF-publishing categories.**

**Filter logic now hard-coded for future runs:**
- `stage1_cms_hospital_list.normalise_row` rejects hospital_type starting with "Acute Care - " (catches DoD/VA labels from PI list)
- `stage2_pos_file.HOSPITAL_PRVDR_CTGRY_CDS` excludes codes 21, 22 (distinct-part units)
- `stage2_pos_file.US_STATE_CODES` allowlists 50 states + DC + 5 territories + 3 military "states"; everything else (CN, MX, country codes) rejected

**Reconciliation with planning estimate:**
The original "~7,000 hospitals" was the count of *short-term acute care hospitals*. Our 13,833 includes correctly:
- ~5,400 short-term acute care
- ~1,400 critical access hospitals
- ~1,400 psychiatric hospitals (standalone, not distinct-part units)
- ~94 children's hospitals
- ~39 rural emergency hospitals
- ~5,500 other CMS-certified facility types that publish MRFs

The 13,833 figure is what we should plan against from now on for cost estimation (Google Places API spend, Cloud Run runtime, etc.).

### Federal facilities (DoD/VA) and Medicaid are out-of-scope but not invisible

DoD MTFs (32) and VA Medical Centers (132) showed up in the PI list. They are NOT bugs in the source data — those facilities legitimately exist in CMS's directory because some are partially Medicare-certified for specialty services. We exclude them from MRF discovery because they do not publish CMS MRFs (they have their own pricing systems: TRICARE TMAC for DoD, VA Fee Schedule for VA Community Care).

State Medicaid pricing is similarly out-of-scope for this pipeline. Each state has its own fee schedule, ~51 separate sources, no MRF format. Future loaders for these are documented at `docs/future-improvements/non-medicare-pricing-integrations.md`.

### POS returned 29,583 hospital rows, not ~1,500 net new (2026-04-28 real run)

When Sandra ran Stage 2A against the real BQ on 2026-04-28, the POS scan logged `total=44429 hospitals=29583`. That's much higher than the "~1,500 missing specialty hospitals" estimate — turns out the hospital category filter (`PRVDR_CTGRY_CD in 01,02,04,06,07,08,14,21,22`) is broader than what the original doc assumed.

**Real numbers:**
- POS total rows: 44,429
- Pass `is_hospital()`: 29,583
- After MERGE into checkpoint (already had 5,426 from PI list): TBD — most POS rows will MATCH on existing CCN and update bed_count/carrier_code; the genuinely-new hospitals are a smaller subset.

The 29,583 includes psychiatric units (`21`), rehabilitation units (`22`), and other distinct-part facilities that may share a CCN with their parent hospital. We may want to tighten the filter in a future iteration, but for now the MERGE's `WHEN MATCHED` branch handles dedup correctly — duplicates by CCN just update the same row.

### `insert_rows_json` has practical 10MB limits (2026-04-28 incident)

Sandra's first real Stage 2A run crashed with a 600-second SSL timeout pushing all 29,583 rows in one `insert_rows_json` call. BigQuery's streaming insert practically caps around 10 MB per request even though the documented row limit is 50,000.

**Fix:** Batch in chunks of 500 (same pattern Substep B already used for NPPES). With 29,583 rows × ~12 fields, ~60 chunks complete in ~2 minutes total. Logging every 10th chunk gives operational visibility without flooding logs.

**Lesson for future stages:** Anytime we'd do `insert_rows_json(table, big_list)`, batch it. Don't trust the row-count limit; trust the body-size limit (~10 MB).

### Orphaned staging tables from crashed runs (2026-04-28 incident)

The crashed Stage 2A left `_stage2_pos_staging_<run_id>` behind because the cleanup `finally` block lived inside an inner try, and the failure happened in the `insert_rows_json` call before the inner try opened.

**Fix:** Two changes:
1. Wrap the batched insert in its own try/except that drops the staging table on failure
2. Use `CREATE OR REPLACE TABLE` instead of `CREATE TABLE` for staging — re-runs blow away orphans automatically

**Pattern:** Real persistent tables → `CREATE TABLE IF NOT EXISTS`. Per-run staging tables → `CREATE OR REPLACE TABLE`. Don't mix them.

### Why a temporary staging table for the MERGE (2026-04-28)

`apply_to_checkpoint` creates a per-run staging table (`_stage2_pos_staging_{run_id}`), bulk-inserts all POS rows in one shot, MERGEs into the checkpoint, then drops the staging table. Three reasons over row-by-row UPDATEs:

1. **Atomicity.** The MERGE either fully succeeds or fully fails. If we did 7,000 individual UPDATEs and the run crashed midway, the checkpoint would be in a half-applied state.
2. **Performance.** BigQuery MERGE is one DML statement; 7,000 UPDATEs would be 7,000 DML statements with their own per-statement overhead.
3. **Idempotency.** If a re-run sees the staging table already exists from a prior crash, we can `DROP TABLE IF EXISTS` and recreate it cleanly.

The staging table name includes the run_id so concurrent runs don't collide, even though we don't currently support concurrent runs.

---

## NPPES bulk download insights

### File is 1 GB compressed, not 8 GB (2026-04-28)

The original `mrf-discovery-pipeline.md` doc estimated the NPPES bulk download at ~8 GB compressed / ~35 GB uncompressed. Probing the live April 2026 V2 file showed **1.05 GB compressed**. Either CMS slimmed the schema since the doc was written or the original estimate was wrong. Either way, the download is much faster than expected — ~3 minutes on a residential connection vs the 20-30 min the doc warned about.

### Filename convention has a `_V2` suffix (2026-04-28)

CMS publishes the file at `https://download.cms.gov/nppes/NPPES_Data_Dissemination_<Month>_<Year>_V2.zip`. The `_V2` suffix is required — the unsuffixed URL returns 404. The "V2" refers to the data dissemination version, not the year; CMS migrated from V1 → V2 several years ago and no longer publishes the older format.

`latest_nppes_url()` computes the URL from today's date with a fallback rule: if today is before the 13th of the month, use last month's file (CMS publishes around the 13th). This is approximate but works without an extra HEAD request to discover the latest available filename.

### CCN lives in the Other_Provider_Identifier slots, not its own column (2026-04-28)

NPPES has no dedicated CCN column. Each NPI record has up to 50 `Other_Provider_Identifier_*` columns paired with `Other_Provider_Identifier_Type_Code_*`. Type code `04` = Medicare CCN. We walk all 50 slots per row looking for a type-04 entry, and the corresponding identifier value is the CCN.

The 50-slot range is the NPPES schema's hardcoded ceiling. In practice most hospitals use 2-5 slots; the rest are NULL. Walking all 50 anyway is cheap because we short-circuit on the first match.

### GCS caching of the 1 GB zip (2026-04-28)

We cache the NPPES zip in `gs://mrf-staging/nppes-cache/{filename}` so re-runs within a month don't re-download 1 GB. The cache key is the filename (which includes the year/month), so a new month's file naturally bypasses the cache.

The cache lives in `mrf-staging` (working files) rather than `mrf-archive-clarobill-prd` (immutable evidence) because NPPES files are not evidence we need to retain — we only care about the parsed CCN→NPI/website mappings, which land in the checkpoint table.

### `Authorized Official Web URL` does NOT exist in NPPES V2 (2026-04-28 reconnaissance — both planning docs were wrong)

When Sandra ran Stage 2B against the real NPPES April 2026 V2 file, the bulk scanner returned 0 CCN matches and 0 website rows. A diagnostic probe of the first 200,000 rows surfaced two findings that invalidate the entire bulk-scan approach:

**Finding 1: No Web URL column exists at all.**
The NPPES April 2026 V2 CSV has 330 columns. None contain "Web" in their header name. The columns we *do* see for the Authorized Official are: `Authorized Official Last Name`, `Authorized Official First Name`, `Authorized Official Middle Name`, `Authorized Official Title or Position`, `Authorized Official Telephone Number`, `Authorized Official Name Prefix Text`, `Authorized Official Name Suffix Text`, `Authorized Official Credential Text` — and that's it. Either CMS removed the website column from V2 or `mrf-discovery-pipeline.md` was wrong about its existence. The website data we wanted from NPPES does not exist.

**Finding 2: Type code '04' (Medicare CCN) is never set.**
Of 30,051 Entity Type 2 rows in the sample, only type codes `'01'` (Other, 21,871 occurrences) and `'05'` (Medicaid, 26,199) appear in any of the 50 `Other Provider Identifier Type Code_*` slots. Type `'04'` returned 0 hits across the full sample. Hospitals do not register their Medicare CCN as an Other Provider Identifier in NPPES — at least not under type code 04. The CCN→NPI cross-reference path is empty.

**What this means**: NPPES bulk download is dead as a data source for ClaroBill. Both intended uses (CCN→NPI and NPI→website) yield nothing. We do NOT scan the bulk file in production.

**Replacement path:**
- **NPI lookup**: per-hospital query against the NPPES Registry API (`https://npiregistry.cms.hhs.gov/api/`) by name + state. ~5 req/s rate limit, ~24 min for 7,000 hospitals, cached in GCS. The existing `scripts/scrape_payerset_directory.py` already uses this pattern — we lift the client into a shared `nppes_client.py` module and call it from a new `stage2_npi_registry.py`.
- **Website lookup**: NPPES is no longer in this path at all. Stage 2C (Wikidata) covers ~500 systems, and Stage 3 (pattern inference + Google Places API) covers the rest. The Google Places API spend goes up correspondingly because we cannot pre-resolve any hospitals via NPPES.

**Stage 2B is now a no-op.** It exists only to mark all checkpoint rows as `nppes_resolved_at = NOW()` so Stage 2C and downstream stages can advance. The module's docstring carries a loud DEPRECATED warning so future-Claude doesn't re-attempt the bulk scan.

### NPPES API rejects `enumeration_type=NBO` — must use `NPI-2` (2026-04-28 incident)

Sandra's first run of `stage2_npi_registry.py` returned `0/200 matches`. Live diagnostic showed the API responds with:

```
{"description": "Field contains special character(s) or wrong number of characters", "field": "enumeration_type", "number": "05"}
```

when `enumeration_type=NBO` is passed. The legacy `scripts/scrape_payerset_directory.py` uses `NBO` and presumably worked at some point — the API has tightened its parameter validation since.

**Correct value: `NPI-2`** (organisation NPIs; `NPI-1` is individuals). Confirmed live 2026-04-28. Patched in `nppes_client.py` with a comment explaining the rejection so a future "let me clean up this string" change doesn't regress us.

**Recovery:** the failed run wrote 200 cache entries marked no-match. Wipe `gs://mrf-staging/nppes-api-cache.json` before re-running so those poisoned entries don't skip the API:
```
gcloud storage rm gs://mrf-staging/nppes-api-cache.json
```

**Lesson for the orchestrator:** any "all rows fail" pattern (>5% no-match consecutively) should halt the run, not poison the cache. Currently we cache no-match results indistinguishably from genuine no-matches; that's the right behavior under normal conditions but causes a re-run hazard when a misconfiguration produces 100% failures. Future enhancement: cache no-match results with a TTL OR with a `reason` field so the cache loader can ignore "API error" no-matches but trust "genuinely-not-in-NPPES" no-matches.

### Stage 2B real-run results: 47.7% NPI coverage from name-matching alone (2026-04-28)

**Pass 1 (`stage2_npi_registry.py`) — strict name+state+city scoring:**
- Targets: 13,833 hospitals
- Matched: 6,272 (45.3%)
- No-match: 7,561
- Match-outcome distribution:
  - city_and_taxonomy: 4,434 (high confidence — both verified)
  - city_only: 724 (medium — taxonomy didn't match but city did)
  - taxonomy_only: 168 (medium — wrong city or no city in NPPES)
  - first_result: 105 (LOW confidence — neither verified)
  - cache: 1,145 (system-level repeats; e.g. multiple HCA divisions)

The 105 first-result matches (< 1%) are the only low-confidence ones. The 4,434 city-and-taxonomy matches are extremely unlikely to be wrong-NPI assignments.

**Match-rate degradation across the run.** Match rate started at 56.5% in batch 1 and declined to ~40% by batch 4. Likely cause: alphabetical CCN ordering (`ORDER BY ccn`) means early batches are AL/AK/AZ — small states, lots of POS-only critical-access hospitals where the legal name in CMS POS uses an ALL-CAPS legal-entity form ("HOUSTON COUNTY HEALTHCARE AUTHORITY") that doesn't fuzzy-match how NPPES indexes them.

**Pass 2A (`stage2_npi_registry_pass2.py`) — name-cleaning re-resolution:**
- Targets: 7,561 (Pass 1 no-match set)
- Matched: 331 (4.4% recovery)
- Cumulative: 6,603 / 13,833 = 47.7%
- Strategy breakdown:
  - pass2_suffix_drop_*: 186 matches (50% of recovery)
  - pass2_truncated_*: 145 matches
  - pass2_no_match: 7,230 (95.6% of targets remained unmatched)

**Sample Pass 2A successful matches (regression cases for the cleaner):**
- "GREENE COUNTY HOSPITAL" → "GREENE COUNTY" → NPI 1558567917
- "VALLEYWISE HEALTH MEDICAL CENTER" → "VALLEYWISE HEALTH" → NPI 1114346962
- "TUCSON GENERAL HOSPITAL" → "TUCSON" → NPI 1245891811
- "SCOTTSDALE COMMUNITY HOSPITAL" → "SCOTTSDALE" → NPI 1366762296

### Why we accept 47% and move on

The 7,230 still-unmatched hospitals are not name-matching failures — they're structural mismatches between CMS data and NPPES legal-name indexing. Each additional cleaning pass yields diminishing returns (~5% per pass). To reach 80% via name-matching alone would require 6+ more passes.

**Critical realisation:** the Phase 4 parser will solve this problem authoritatively. Every MRF file the parser processes contains the hospital's NPI in the JSON root metadata. The parser writes it back to `hospital_directory.hospital_npi` regardless of whether Stage 2B's name-matching guessed correctly. The Pass 1+2A NPIs are a *bootstrap* to seed Phase 4's archive layout, not the final coverage number.

**Coverage trajectory:**
- After Stage 2B (today): 6,603 / 13,833 NPIs (47.7%) via name-matching
- After Phase 4 parser: likely 11,000+ / 13,833 (~80%) via authoritative MRF JSON metadata extraction
- Permanent NPI gap: ~2,000-3,000 hospitals whose MRF doesn't parse or doesn't contain NPI metadata. Rare in CMS v2.0.0 schema.

**For hospitals without resolved NPI at any stage:** `archive_layout.py` accepts CCN as the GCS object key (`{ccn}/{sha256}.{ext}`), so they progress through the pipeline normally — just keyed by CCN instead of NPI in the archive. The rules engine in Phase 5 has a NULL-check; bills against NPI-less hospitals get the rule skipped (correct behavior — no false flags).

**Pass 2B (address-based lookup) and Pass 2C (broader-pull + client-side fuzzy match) are designed and deferred.** See `docs/future-improvements/npi-coverage-improvement-passes.md`. Re-evaluate trigger: after Phase 4 parser-driven backfill, if `hospital_directory.hospital_npi IS NULL` rate > 30%, implement Pass 2B; if still > 20% after 2B, implement Pass 2C.

### NPPES Registry API replacement shipped (2026-04-28)

The bulk-file dead-end pushed us to per-hospital API lookups. Module: `stage2_npi_registry.py`. Shared client: `nppes_client.py`. Key design choices (each chosen because the legacy lookup in `scrape_payerset_directory.py` had a bug we wanted to avoid):

1. **City verification.** Legacy code took the first NPPES result for a given name+state. Multiple "Memorial Hospital" entries in Texas would all resolve to the wrong NPI. New `_select_best` scores candidates by city match (10 pts) + taxonomy match (5 pts) and picks the highest. Score 0 ("first result") logs a warning so we can audit low-confidence matches.
2. **Hospital taxonomy preference.** NPPES taxonomy codes starting with `282` (acute care), `283` (specialty), `281` (children's), or `273` (units) are hospitals; everything else is medical groups, IPAs, individual providers tagged as orgs, etc. Preferring hospital taxonomies filters out look-alike non-hospital orgs.
3. **Rate limit at 5 req/s.** NPPES has no documented limit but the API is "best effort." 0.2s minimum interval = 5 req/s = ~46 minutes for 13,833 hospitals.
4. **GCS-backed cache at `gs://mrf-staging/nppes-api-cache.json`.** Cache key is `name|state|city` uppercase. Saved every 200 rows + at end. A crashed run resumes from the cache; a re-run completes in seconds. The legacy script used a local JSON path which doesn't survive Cloud Run job container churn.

**Implication for the orchestrator:** Stage 2B (NPPES bulk no-op) and Stage 2B-replacement (NPI Registry API) are separate scripts. The deprecated no-op exists only because some upstream code still calls "Stage 2B"; the API version is the actual NPI source. Future cleanup: delete the no-op once the orchestrator routes to the API directly.

### Why the 1.4M "hospital orgs" count was misleading (2026-04-28)

The bulk-scan log line `1,388,260 hospital orgs` was a label bug, not a data error. Entity Type Code = 2 in NPPES means "any organisation NPI" — pharmacies, equipment suppliers, transportation services, group practices. Hospital is a tiny minority of those. The accurate label would be "organisation NPIs scanned." Filtering to actual hospitals requires either taxonomy code matching (codes starting with `28` for acute care, `26` for residential, `27` for nursing) OR the per-hospital API approach we're moving to.

---

## Wikidata SPARQL insights

### Real-run results: 4,826 candidates, 3,140 matched (2026-04-28)

Wikidata's SPARQL endpoint returned **4,826 unique US hospitals/systems** with a `P856` (official website) — far richer than the ~500 the planning estimate predicted. This means Wikidata has individual-hospital entries, not just system-level entries (HCA Healthcare, Ascension, etc).

After fuzzy-matching at threshold 0.85 against the 13,833 checkpoint rows: **3,140 matches (22.7%)**. This is the dominant free-tier website source.

**Implication for Stage 3 Tier 3 cost projection:** the Tier 3 input population shrinks. Original estimate was 5,500-7,000 hospitals reaching Tier 3 (paid). Revised estimate post-Stage-2C: ~10,700 hospitals still need a website. After Tier 1 (validates the 3,140 from Wikidata) and Tier 2 (pattern inference for 10,700+), the Tier 3 input population could be 8,000-10,000 hospitals — *higher* than the original estimate, because Wikidata coverage is concentrated and Tier 2 only covers 3-5% of the long tail. The $450 ceiling still holds but is closer to fully consumed than the original projection.

### Fuzzy matcher had to be hardened for the real candidate count (2026-04-28 incident)

The original `match_to_checkpoint` was O(N × M) — 13,833 × 4,826 = 67M comparisons, each calling `SequenceMatcher.ratio()`. Sandra's first run hung indefinitely. The fix was three layers of pre-filter:

1. **Exact-match dict** (O(1) lookup) — for pre-cleaned name matches
2. **First-character bucketing** — names starting with different letters can't cross 0.85 threshold
3. **`real_quick_ratio()` → `quick_ratio()` → `ratio()` cascade** — difflib's documented progressive-cost prefilters

After the fix: 67M comparisons → ~5K expensive comparisons. Runtime: hours → ~10 seconds.

**Lesson for future bulk fuzzy matchers:** always assume the candidate set will be 10× larger than the planning estimate. Use difflib's progressive prefilters by default (`real_quick_ratio()` is free; the only cost is one extra method call before `ratio()`).

### One query, free, fast

Wikidata's SPARQL endpoint is fast (sub-5-second response) and free. A single query for `(?h instance-of hospital OR ?h instance-of hospital-network) AND ?h country US AND ?h has-official-website` returns 4,826 entries.

Live-probe result on 2026-04-28: 5 results returned with the test query — note this was a `LIMIT 5` probe. The first result was actually `USNS Comfort` (a Navy hospital ship), confirming Wikidata's hospital ontology is broad and confirming the country=US filter is necessary.

### Why fuzzy threshold is 0.85 (strict) (2026-04-28)

False positives at this layer are very dangerous: matching "Mayo Clinic" against "Mayo Hospital" with low confidence assigns the wrong website to the wrong CCN, which produces wrong overcharge claims down the line. Threshold of 0.85 means typos and minor formatting variations match ("Mayo Clinic" vs "Mayo Clinc") but substring overlap does not ("Mayo Clinic" vs "Mayo Clinic Hospital" is only 0.71 — rejected).

If we ever want substring/system-level matching, that belongs in a *separate* code path that uses a different reasoning model (e.g. "this hospital_name CONTAINS the system name AND the system has CCN range X-Y"), not a relaxed fuzzy threshold.

### Wikidata is the gap-filler, NPPES has precedence (2026-04-28)

Substep B (NPPES) returns hospital-specific URLs (each NPI registration has the *facility's* website). Substep C (Wikidata) returns system-level URLs (one URL for all 180 HCA facilities). When both have a URL for the same CCN, NPPES wins because the facility-specific URL is more likely to lead to the price-transparency page in Stage 4.

The MERGE in `apply_matches` enforces this with `WHEN MATCHED AND T.hospital_website IS NULL THEN UPDATE`. We never overwrite an NPPES URL with a Wikidata URL.

---

## CMS PI dataset insights

### Discovery: 5,426 hospitals, not 7,000 (2026-04-28)

The CMS Promoting Interoperability "Hospital General Information" dataset (`xubh-q36u`) returns **5,426 rows**, not the ~7,000 figure quoted in earlier planning docs. This is the *star-rated hospital subset*, not the full Medicare-certified census.

The remaining ~1,500-1,700 specialty/critical-access/psychiatric hospitals don't carry star ratings and live in the **CMS Provider of Services (POS) file** instead. Stage 2 substep A pulls them in.

This means:
- After Stage 1: 5,426 hospitals seeded in checkpoint
- After Stage 2A (POS file): ~7,000 hospitals total, ~98% with NPIs

**Implication:** If the rules engine at any point queries `hospital_directory` for a critical-access hospital that wasn't in the PI list, we'd get no rate data and (correctly) skip the overcharge rule. The current Phase 1 schema already supports this — Stages 2-6 will populate the checkpoint and merge into the directory.

### Why the API instead of the bulk CSV download (2026-04-28)

The dataset page (`data.cms.gov/provider-data/dataset/xubh-q36u`) offers three access paths: HTML browser, paginated JSON API, direct CSV download. We use the API because:

1. **Deterministic.** `count` field in the first response tells us the total upfront; we paginate until we've fetched that many. No "did the file finish downloading?" ambiguity.
2. **Properly-typed JSON.** No CSV quoting/escaping bugs around hospital names with commas, addresses with quotes.
3. **Canonical source.** CMS sometimes updates the bulk CSV asynchronously; the API is queried directly against their datastore.

11 pages × 500 rows × ~3 seconds each = ~30 seconds total for the full dataset. Will never be the bottleneck.

### Field name oddity: `facility_id` is the CCN (2026-04-28)

Every other field in this CMS dataset is sensibly snake_case but the primary key is named `facility_id`, not `ccn`. This is a CMS convention inconsistency — other datasets use `ccn` or `provider_id` for the same 6-character identifier.

The normaliser at `scripts/mrf_discovery/stage1_cms_hospital_list.py:78` (`normalise_row`) maps `facility_id` → `ccn` explicitly so the rest of the pipeline only ever sees `ccn`. Same approach for `citytown` → `city` and `telephone_number` → `phone`.

### "Not Available" sentinel (2026-04-28)

CMS uses the literal string `"Not Available"` (case-insensitive) as a sentinel for missing data — not NULL, not empty string. The `_clean_str` helper at `stage1_cms_hospital_list.py:111` treats `"Not Available"` as None so we never store it as a literal value in BigQuery.

### 5,426 in, 5,426 out, 0 skipped (2026-04-28 dry run)

Zero rows missing required fields. Zero normalisation failures. CMS data quality on this dataset is high — every record has both a CCN and a facility name. If we ever see skip count > 0 in production, that's a CMS schema change worth investigating, not a normaliser bug.

---

## Schema migration insights

### Why rename, not migrate, the legacy hospital_charges (2026-04-27)

The legacy table has no `pricing_effective_year`. We could backfill with synthetic values (e.g. `WHEN scraped_at < '2026-01-01' THEN 2025 ELSE 2026 END`) but that's lying — the rows actually represent unknown vintage. Better to rename and let the rules engine ignore them.

The legacy table is retained for ~6 months for forensics (debugging "why did rule X behave differently in March than in April?"), then dropped via a follow-up migration in Phase 6.

### Why `pricing_effective_year` is REQUIRED, not nullable (2026-04-27)

If it were nullable, somebody would forget to populate it once, the row would land in the table, and the rules engine would either crash on `NULL = 2026` or (worse) match-anything if we wrote a permissive query. Making it `NOT NULL` means the bug surfaces at insert time, in the parser code, where it can be fixed — not at audit time, in front of a patient.

---

## Operational insights

### Run IDs are timestamp + 8-char UUID (2026-04-28)

`bq_checkpoint.new_run_id()` returns e.g. `20260428T135630Z_e37a012d`. Format is deliberate:
- ISO timestamp prefix sorts naturally in BQ console queries
- 8-char UUID suffix is enough collision resistance for monthly runs
- Z suffix makes it unambiguous UTC

Stages 2-6 take `--run-id` as input. Stage 1 generates one (or accepts one) and prints it to stdout for the orchestrator to capture: `RUN_ID=$(python3 ... stage1...)`.

### Polite-by-default request rates (2026-04-28)

| Source | Request rate | Why |
|---|---|---|
| CMS Datastore API | 0.25s sleep between pages | No documented limit; polite even though page sizes are small |
| NPPES bulk download | One file pull per month | Hosted as static download; bandwidth cost is on CMS |
| Wikidata SPARQL | One query per run | No pagination needed for ~500 systems |
| Google Places API | 10 req/s | Documented limit is 50; we use 20% to leave headroom for parallel users |
| Hospital websites (Stage 4) | 2s/domain, 1 concurrent per domain | Conservative; some hospital servers are slow |

### Why discovery is annual, not weekly (2026-04-28)

MRF *content* changes annually (CMS requires January re-publication). MRF *URLs* sometimes change mid-year (website redesigns, system acquisitions). The weekly scraper's job is to detect URL-content changes via Last-Modified/ETag headers; the annual discovery job's job is to find new hospitals and stale URLs.

Running discovery monthly would burn ~6× more API quota for almost no incremental coverage. Running annually with an opt-in mid-year refresh (`--force-refresh stages 4,5,6`) covers both cases.

---

## Build sequence learnings

### Phase 1-2 are source-agnostic (proven by the Plan B → A pivot)

When we pivoted from PRA-sourced to CMS-direct, the entire schema migration, GCS bucket setup, and checkpoint helper module shipped unchanged. We only swapped Stage 1's data source.

This is by design: the schema describes *what we know about each hospital*, not *where we learned it from*. If PRA later grants partnership (Plan C), we can integrate them as a Stage 2 substep with no schema changes.

### Generalising the checkpoint helpers (2026-04-28)

`bq_checkpoint.py` was originally written with PRA-specific stage names (`sitemap_seeded`, `detail_extracted`). When we pivoted, we renamed them to Plan A names (`cms_loaded`, `nppes_resolved`, `website_found`, `crawl_complete`, `mrf_validated`, `bq_committed`) and renamed the inflight table to `mrf_discovery_checkpoint`.

Lesson for future stages: name things by what they *mean to the rules engine*, not by what *source they came from*. `nppes_resolved_at` is okay because NPPES is the canonical source for NPI; if we ever resolve NPIs from a different source, we'd want to keep the column name and just update the upstream code.

---

## Tech-debt sweep (2026-04-28)

End-of-day cleanup pass. Sandra's directive: "if we need to fix a piece of code, let's do it before moving forward, we don't want to carry any tech debt."

**Files deleted:**
- `scripts/scrape_payerset_directory.py` — Payerset GitBook scraper. Used `enumeration_type=NBO` which the NPPES Registry API now rejects. Source data (Payerset, ~3,119 hospitals) has been replaced by CMS-direct discovery (~13,833 hospitals).
- `scripts/bootstrap_hospital_directory.py` — consumed Payerset CSV outputs into BQ. Replaced by Stage 1+ of the new pipeline.
- `scripts/mrf_discovery/stage2_nppes_bulk.py` — deprecated no-op replaced by `stage2_npi_registry.py` (NPPES Registry API). Module's docstring already explained why the bulk file was unusable; deleting the module itself removes the historical scaffolding.
- `scripts/mrf_discovery/_probe_nppes.py` — one-off diagnostic that produced the bulk-file findings. Findings preserved in this doc.
- `apps/engine/tests/scripts/test_stage2_nppes_bulk.py` — tests for the deleted module.
- `data/cms/hospitals/{hospitals.csv, hospitals_raw.csv, npi_cache.json}` — Payerset-era working files (gitignored, never tracked). Same data now lives in `mrf_discovery_checkpoint`.

**Code cleaned up in surviving modules:**
- `migrate_bq_schema.py`: renamed PRA-themed function names + docstring to CMS-direct. Dropped creation of unused `pra_facility_index` and `pra_discovery_runs` tables. Replaced with `create_mrf_discovery_runs`. Added `--cleanup-pra-legacy` flag that drops the orphan PRA tables and columns from BQ.
- `nppes_client.py`: docstring no longer references deleted modules.
- `stage2_npi_registry.py`: docstring references stage2_pos_file directly (no chained "deprecated bulk replaced by").
- `stage2_pos_file.py`, `stage2_wikidata.py`: docstring references corrected.
- `bq_checkpoint.py`: `website_source` enum comment updated to reflect actual sources.

**Audit-fix code changes:**
- `bq_checkpoint.seed_hospitals` — duplicate-row protection on Stage 1 re-runs (queries existing CCNs first, skips matches).
- `stage2_npi_registry.get_unresolved_hospitals` — docstring/SQL drift fixed; added `state IS NOT NULL AND hospital_name IS NOT NULL` filters so empty rows don't poison the cache.
- `nppes_client.NppesClient.lookup` — narrowed `except Exception` to `except (RequestException, ValueError)` so Ctrl+C doesn't swallow.
- `nppes_client._select_best` — address fallback chain LOCATION → PRIMARY → first → empty (was LOCATION → first only).
- `stage2_wikidata.apply_matches` — batched insert in chunks of 500 (consistency with other Stage 2 modules).
- `archive_layout._OBJECT_RE` — derived from `VALID_EXTENSIONS` (was hand-coded; drift hazard if a new extension was added).

**BQ-side cleanup (Sandra runs):**
- `python3 scripts/mrf_discovery/migrate_bq_schema.py --cleanup-pra-legacy --project clarobill-prd` — drops `pra_facility_index`, `pra_discovery_runs`, `hospital_directory.pra_facility_uuid`, `hospital_directory.last_pra_check`.
- `gcloud storage rm gs://mrf-staging/nppes-api-cache.json --project clarobill-prd` — wipes poisoned cache from the failed Stage 2B run.

**Result:** 124 tests passing. No deprecated code paths. No orphan BQ tables. No stale data files. Single canonical NPI client. Documentation top-to-bottom matches the deployed system.

---

## Stage 3 Tier 1 + Tier 2 results (2026-04-28)

### Tier 1 — Wikidata URL validation
- **Target:** 3,140 URLs (Wikidata fuzzy matches from Stage 2C)
- **Initial run:** 2,190 valid / 950 invalid (69.7% validation)
- **After UA-fallback patch:** browser UA fallback for 403/406/429 recovered ~250 of the 311 WAF-rejected URLs
- **Failure-mode distribution (initial run):** 311 http_403 (WAF), 259 http_404 (dead), 117 connection_error, 118 timeout, 88 ssl_error, 29 http_429 rate-limited

### Tier 2 — Pattern inference
- **Target:** 10,693 hospitals without a URL after Tier 1
- **Result:** 2,469 matched (23.1%)
- **Vs planning estimate (3-5%):** 5-7× better than expected — hospital naming conventions are more pattern-uniform than anticipated
- **Recovery shape:** `{slug}.org` and `{slug}hospital.org` were the dominant patterns

### Lessons
- **Worker-loop exception handling must be `except Exception:` at the outermost layer.** Sandra's first Tier 2 run crashed on a `UnicodeError` (IDNA encoding rejected `https://.org` from a degenerate slug). Tier 2 only caught `requests.RequestException`; the bare `UnicodeError` escaped, the worker died, and `future.result()` re-raised in the main loop. Fix: catch `Exception` in the future-result loop AND filter degenerate slugs at candidate-generation time (`MIN_SLUG_LEN = 3`).
- **Free-tier discovery scales further than planned.** Wikidata returned 4,826 candidates (vs ~500 planned). Pattern inference recovered 23% (vs 3-5% planned). Sized planning estimates 10× upper bound, but reality has been even more generous.
- **WAF rejection of identifiable User-Agents is real.** ~10% of hospital websites reject our descriptive UA at the edge. Two-step UA strategy (descriptive first, browser-realistic fallback only on 403/406/429) recovered most of these without abandoning our "polite by default" posture.

### Cumulative coverage post-Tier-2 (2026-04-28)
- Hospitals with validated website: ~4,909 / 13,833 = **35.5%**
- Hospitals still needing a website (Tier 3 paid input): ~8,924
- Projected Tier 3 cost: ~$330 baseline + $60 ambiguous-result verification = **~$390** (under the $450 ceiling with ~$60 headroom)

---

## Stage 3 Tier 3 final results (2026-04-29)

Production run completed cleanly. Concrete numbers:

### Run summary
| Metric | Value |
|---|---|
| Hospitals processed | 7,794 |
| Matched (got a website) | 6,616 (84.9%) |
| Skipped (pre-call validator) | 4 |
| No-match | 1,174 |
| Errors (worker exceptions) | 0 |
| Total spent | $349.92 |
| Budget ceiling | $450.00 |
| Headroom remaining | $100.08 |

### Outcome distribution

| Outcome | Count | % of total | Cost contribution |
|---|---|---|---|
| `cache` (recovered from prior run/smoke test) | 501 | 6.4% | $0.00 |
| `single_result` | 4,250 | 54.5% | $127.50 |
| `ambiguous_verified` | 2,353 | 30.2% | $164.71 |
| `ambiguous_no_verify` | 629 | 8.1% | $50.32 |
| `no_result` | 57 | 0.7% | $0.29 |

API breakdown: 7,289 text searches + 12,539 place-details calls = 19,828 Google Places calls.

### Cumulative Stage 3 website coverage (post-all-tiers, 2026-04-29)

| Source | Hospitals with website | % of 13,833 |
|---|---|---|
| Tier 1 (Wikidata-validated existing URLs) | ~2,440 | 17.6% |
| Tier 2 (pattern inference) | 2,469 | 17.8% |
| Tier 3 (Google Places, this run) | 6,616 | 47.8% |
| **TOTAL with confirmed website** | **~11,525** | **83.3%** |
| Still without website | ~2,308 | 16.7% |

The 16.7% with no website are the long tail Google doesn't index well — small critical-access hospitals, recently-renamed facilities, hospitals using shared/system-level URLs, etc. Some will recover via Phase 4 parser-driven discovery (when their CCN's MRF is discovered through other means and the parser writes the website back from MRF metadata if present); the rest stay in the manual-curation queue.

### Cost-preview calibration: closed loop on the original 18% projection gap

The original cost preview projected $295.85 for 8,219 hospitals (calibrated against NPPES match-outcome distribution as a proxy). Real run was $349.92 for 7,794 hospitals — an effective per-hospital cost of $0.0449 vs the projected $0.0360, or 25% higher than projected.

Root cause: **Google's hospital index returns 2-3 candidates more often than NPPES** (38.7% of API-called hospitals returned 2+ candidates vs the 13% modeled). Each ambiguous lookup costs up to $0.080 vs $0.030 single-result.

**Recalibrated constants** in `stage3_tier3_places.py` (committed 2026-04-29):
- `EXPECTED_SINGLE_RESULT_RATE = 0.60` (was 0.85)
- `EXPECTED_AMBIGUOUS_RATE = 0.39` (was 0.13)

These values come directly from the smoke-test outcome distribution. Future cost-preview runs project slightly over what the actual run will spend — the safer side per the original design principle.

### Manual-curation queue from this run

The 629 `ambiguous_no_verify` cases are hospitals where Google returned 2-3 candidates, we paid for all 3 details calls (~$0.080 each = ~$50 total), and none of the candidate websites had the hospital name in their first 64KB of HTML. These are valuable for the manual queue documented at `docs/future-improvements/npi-coverage-improvement-passes.md` — the highest-bed-count hospitals from this set should be hand-curated before next year's run.

---

## Status snapshot (2026-04-28 end-of-day)

**Real number to plan against: 13,833 distinct US civilian-MRF-publishing hospitals.**
(Updated from "~7,000" planning estimate; cleanup removed 15,758 rows for distinct-part units, DoD, VA, non-US.)

| Phase | Status | Last verified |
|---|---|---|
| 1. Schema migration | code + applied | 2026-04-28 |
| 2. GCS archive bucket | code + bucket live | 2026-04-27 |
| 3a. Generalize bq_checkpoint | done | 2026-04-28 |
| 3b. Stage 1 (CMS PI list) | done + applied; DoD/VA filter added | 2026-04-28 — 5,426 hospitals seeded |
| 3c. Stage 2A (POS file) | done + applied; distinct-part + non-US filter added | 2026-04-28 — 13,833 final after cleanup |
| 3c. Stage 2B (NPPES bulk) | DEPRECATED no-op; replacement planned | 2026-04-28 — bulk file has neither website nor CCN type-04 |
| 3c. Stage 2B-replacement (NPI Registry API) | code shipped + 14 tests | 2026-04-28 — `nppes_client.py` + `stage2_npi_registry.py`; ~46 min first run for 13,833 hospitals, near-instant on re-run via cache |
| 3c. Stage 2C (Wikidata SPARQL) | code + tested | 2026-04-28 — 15 tests; awaits apply |
| 3d. Stage 3 (Website discovery) | not started | |
| 3e. Stage 4 (Crawler) | not started | |
| 3f. Stage 5 (MRF validator + TOC) | not started | |
| 3g. Stage 6 (BQ MERGE) | not started | |
| 4. Effective-dated archiver | not started | |
| 5. Rules engine effective-date join | not started | |
| 6. Cutover | not started | |

| External dependency | Status |
|---|---|
| PRA outreach email (Plan C) | sent 2026-04-28, awaiting reply |
| Non-Medicare pricing integrations | documented at `docs/future-improvements/non-medicare-pricing-integrations.md` (TRICARE TMAC, VA Community Care, state Medicaid, commercial TIC) |
