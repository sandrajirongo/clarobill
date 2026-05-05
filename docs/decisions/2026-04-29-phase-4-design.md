# Phase 4: Effective-Dated Archiver + Parser — Shipped Record

**Date opened:** 2026-04-29
**Date shipped:** 2026-04-30 (original Q1-Q5 scope) → 2026-04-30 evening (Stage 4 + new cadence + live verification)
**Status:** SHIPPED — every approved decision is on `main`. Stage 4 backfill to populate `validated_mrf_urls` for the existing fleet runs as `clarobill-mrf-discovery-9gvjw`.
**Phase:** 4 of 6 (post Phase 3 = MRF discovery; pre Phase 5 = rules engine cutover)

> **For engineers reading this cold:** this is the canonical record of what
> Phase 4 did and why. The original design proposal was the first half of
> this document; live testing revealed three issues that needed inline
> fixes, and the schedule design changed once we measured how often hospital
> MRFs actually republish. The "Shipped Record" sections at the bottom
> reconcile what's on disk with the original plan. Read top-to-bottom for
> the narrative, or jump to **"How it actually works in production"** if
> you just need the runbook.

## Sandra's decisions (2026-04-29) — all shipped

| Question | Decision | Where it lives |
|---|---|---|
| Q1 — archive key NPI vs CCN | Mixed keys, AND actively backfill NPI when the parser extracts it from MRF JSON root. | `pipeline/scrape_hospital_mrfs.py:_archive_key()`, `pipeline/parse_hospital_mrfs.py:update_hospital_npi()` |
| Q2 — legacy table fate | Keep `hospital_charges_legacy_stale` and **tag every row with `pricing_effective_year = 2025`**. | `scripts/mrf_discovery/backfill_legacy_effective_year.py` (run on prod 2026-04-30) |
| Q3 — re-publish handling | Append-only + query MAX(scraped_at). | `pipeline/parse_hospital_mrfs.py` (DELETE removed). **The schedule changed:** Feb 1 + Aug 1 → Feb 15 + Aug 15 + quarterly May/Aug/Nov 15. See `docs/decisions/2026-04-30-pipeline-cadence.md`. |
| Q4 — concurrency | **Bump from 20 → 60.** | `pipeline/scrape_hospital_mrfs.py:MAX_WORKERS`, also Stage 4 |
| Q5a — stuck-pending bug | Set `website_found_at = NOW()` for Tier 3 `no_result` and `ambiguous_no_verify`. | `scripts/mrf_discovery/stage3_tier3_places.py:apply_results()` |
| Q5b — parse robustness | Multi-strategy fallback + per-row error tolerance. | `pipeline/hospital_mrf_utils.py:stream_charges_v2()` (per-row try/except), CSV explicitly deferred to `docs/future-improvements/csv-mrf-parser.md` |

---

## Why this phase exists

After Phase 3, `hospital_directory` had ~13,833 hospitals with ~83% website
coverage. The directory tells us **which hospital has which MRF URL**.
Phase 4 turns those URLs into actual queryable price data:

1. **Download the MRF file** from each hospital's published URL.
2. **Archive it immutably** to `gs://mrf-archive-clarobill-prd/pricing-year={year}/{npi}/{sha256}.{ext}` so it's reproducible years later.
3. **Parse the file** into per-line-item rows (CPT, gross charge, negotiated rate per payer, etc.).
4. **Insert those rows into `hospital_charges`** with `pricing_effective_year` populated from the file's metadata or the run's calendar year.

Phase 4 is also where the rules engine's "billed > MRF gross charge" rule
becomes real for the post-2025 era. The rule logic was already at
`rules_engine.py:804-849` reading from `hospital_charges_legacy_stale` (the
renamed pre-effective-dating table). Phase 5 (deferred) flips it to read
from the new effective-dated `hospital_charges`.

---

## How it actually works in production

### The end-to-end data flow (current, post-Phase-4)

```
                   ┌─────────────────────────────┐
                   │  CMS publishes hospital     │
                   │  list + Provider of         │
                   │  Services file              │
                   └────────────┬────────────────┘
                                │
                                ▼
        ┌───────────────────────────────────────────────────┐
        │ Discovery pipeline (Cloud Run Job)                │
        │   Annual:    Feb 15 02:00 UTC                     │
        │   Quarterly: May 15 / Aug 15 / Nov 15 02:00 UTC   │
        │   --gap-fill-only on quarterly runs               │
        │                                                   │
        │   Stage 1 → CMS PI list seeder                    │
        │   Stage 2 → NPI Registry + POS + Wikidata + Pass2 │
        │   Stage 3 → website discovery (3 tiers, $450 cap) │
        │   Stage 4 → crawl websites for MRF URLs           │
        │             writes mrf_discovery_checkpoint       │
        │             AND MERGEs into hospital_directory    │
        └────────────┬──────────────────────────────────────┘
                     │
                     ▼
   ┌─────────────────────────────────────┐
   │  hospital_directory                 │
   │  (one row per (hospital, mrf_url))  │
   │  ~13k+ hospitals after Stage 4 lands│
   └────────────┬────────────────────────┘
                │
                ▼
        ┌────────────────────────────────────────────────────┐
        │ Scraper (Cloud Run Job)                            │
        │   Annual:    Feb 15 02:00 UTC                      │
        │   Mid-year:  Aug 15 02:00 UTC                      │
        │                                                    │
        │   For each hospital:                               │
        │     1. HEAD with If-Modified-Since                 │
        │     2. If changed: GET, stream-download            │
        │     3. DUAL-WRITE:                                 │
        │        a) gs://mrf-staging/raw/  (legacy parser)   │
        │        b) gs://mrf-archive-clarobill-prd/          │
        │           pricing-year={Y}/{npi-or-ccn}/           │
        │           {sha256_first16}.{ext}                   │
        │           + sibling .meta.json                     │
        │     4. Insert mrf_archive_index row                │
        │        parse_status='pending' (LOAD JOB,           │
        │        not streaming — see "Surprise #2" below)    │
        └────────────┬───────────────────────────────────────┘
                     │ 4 hours later
                     ▼
        ┌────────────────────────────────────────────────────┐
        │ Parser (Cloud Run Job)                             │
        │   Annual:    Feb 15 06:00 UTC                      │
        │   Mid-year:  Aug 15 06:00 UTC                      │
        │                                                    │
        │   For each staging blob:                           │
        │     1. Strip UTF-8 BOM if present                  │
        │        (Surprise #1 — see below)                   │
        │     2. Resolve pricing_effective_year via          │
        │        effective_year.resolve_year():              │
        │          a) MRF JSON last_updated_on (best)        │
        │          b) HTTP Last-Modified header              │
        │          c) calendar year (fallback)               │
        │     3. Stream-parse v2.0.0 schema                  │
        │        (per-row try/except — bad rows logged       │
        │         and skipped, never abort the file)         │
        │     4. APPEND-ONLY load to hospital_charges        │
        │        (no DELETE — preserves history)             │
        │     5. UPDATE mrf_archive_index.parse_status       │
        │        → 'parsed' / 'failed' / 'skipped'           │
        │     6. If hospital_directory.hospital_npi was      │
        │        NULL, backfill it from the MRF JSON root    │
        └────────────────────────────────────────────────────┘
```

### Why "annual + mid-year" instead of weekly

CMS rule 42 CFR 180 requires hospitals to publish/refresh MRFs **at most
once per year**. Most do it after the Jan 1 deadline; ~10% republish in
summer. Weekly polling produced no new data 51 weeks/year and burned
~96% of compute on no-op `If-Modified-Since` checks.

The Feb 15 anchor gives hospitals a 6-week buffer past Jan 1 to fix
first-pass errors. Aug 15 catches the summer-republish cohort. Quarterly
gap-fills (May/Aug/Nov 15) only re-process hospitals where
`validated_mrf_urls IS NULL` plus any new CMS-listed hospitals.

Full rationale: `docs/decisions/2026-04-30-pipeline-cadence.md`.

### Why append-only instead of DELETE+LOAD

When a hospital re-publishes their MRF mid-year (rare but happens), the
old behavior was to DELETE all existing rows for that NPI then INSERT new
ones. Two problems:
- **Destroys history.** A 2024 bill audited in 2030 must produce the
  same finding it would have produced in 2024. DELETE breaks that.
- **Race window.** Between the DELETE and the LOAD, the table is empty
  for that hospital — concurrent rules-engine queries return zero rows.

New behavior: every scrape APPENDs. The rules engine deduplicates at
query time via `MAX(scraped_at) OVER (PARTITION BY hospital_npi, code,
payer_name, plan_name)`. Old rows remain queryable for forensic audits
("what did we believe was the chargemaster on date X?").

The `pricing_effective_year` partition key + `scraped_at` clustering give
us both year-correct joins (a 2024 bill matches the 2024 chargemaster)
and freshness-correct deduping within a year.

### Why immutable archive + parse on staging

The scraper dual-writes intentionally:
- `mrf-staging/raw/` is mutable — parser deletes blobs after success to
  prevent double-processing. Standard work-queue pattern.
- `mrf-archive-clarobill-prd/` is **Coldline + IAM-enforced no-delete**.
  Every MRF byte we ever downloaded is preserved forever, partitioned by
  the year it applied to, content-addressed by SHA256. This is the
  **chain-of-custody vault** — if a patient's dispute ever cites a
  ClaroBill audit, we can produce the exact bytes that were in force on
  the bill's service date.

Coldline at $0.004/GB-mo + ~20 GB total = ~$0.08/mo storage cost; the
audit-defensibility ROI dwarfs that.

### Why mixed NPI + CCN keys instead of NPI-only

Phase 3 left ~48% of hospitals NPI-keyed and the rest CCN-only (NPPES
Registry returned no NPI). Two paths considered:
- **Defer non-NPI hospitals** until parser backfills NPI: loses 2026
  chargemaster archives for 6,000+ hospitals.
- **Mixed keys**: archive under whatever key we have, backfill NPI to
  `hospital_directory` after first parse.

We chose mixed. `archive_layout.parse_object_uri()` returns the key as a
generic string — callers don't care whether it's CCN or NPI. The cost of
"deferring" is meaningful data loss; the cost of mixed keys is none.

### Why three sources for `pricing_effective_year`

CMS doesn't mandate that hospitals stamp their MRF with the applicable
pricing year. We see three real-world states:
1. **MRF JSON has `last_updated_on`** (CMS v2.0.0): authoritative — use
   the year from this field. ~80% of hospitals.
2. **JSON missing or malformed, but HTTP `Last-Modified` header is
   set**: fallback — use the year from the HTTP header. ~15% of hospitals.
3. **Both missing**: log a warning, fall back to current calendar year.
   ~5% of hospitals (mostly hospitals that serve their MRF without
   correct cache headers).

`pipeline/effective_year.resolve_year()` returns `(year, source)` where
source is one of `"json_last_updated_on" | "http_last_modified" |
"fallback_calendar_year"`. The source string is logged so operators can
investigate the fallback cohort.

### Why per-row tolerance instead of strict parsing

Sandra's directive: *"make parsing as functional as possible — we don't
want to end up with almost no data because of parsing issues."*

The cost asymmetry is decisive:
- Strict parsing: one bad row in a 4 GB file aborts the whole hospital
  → lose 100% of that hospital's data for the year.
- Per-row tolerance: bad row logged + skipped → keep 99.999% of data.

The implementation in `stream_charges_v2()` wraps each `_expand_charge_item`
call in a try/except. Five malformed items log warnings; further malformed
items are silently skipped (counted in the summary). Only a structural
parse failure (root key missing entirely) aborts the file.

CSV-format MRFs are recognized and **skipped cleanly** with
`parse_status='skipped'`. Full CSV support is deferred per
`docs/future-improvements/csv-mrf-parser.md` — adding it requires a
per-vendor column-mapping pass we'd rather build deliberately than rush.

---

## Files Phase 4 changed

### Rewritten

| File | What it did before | What it does now |
|---|---|---|
| `pipeline/scrape_hospital_mrfs.py` | Read `hospital_directory`, write to `mrf-staging`, update `last_modified` | DUAL-write to `mrf-staging` + `mrf-archive-clarobill-prd`; insert `mrf_archive_index` row via LOAD JOB; concurrency 20→60 |
| `pipeline/parse_hospital_mrfs.py` | List `mrf-staging` blobs, parse, DELETE+INSERT into `hospital_charges` | Process staging blobs, strip UTF-8 BOM, resolve `pricing_effective_year`, APPEND-ONLY INSERT, flip `parse_status` |
| `pipeline/hospital_mrf_utils.py` | Existing v2.0.0 streaming parser | `_strip_bom()` added; `ChargeRow` carries `pricing_effective_year` + `source_mrf_url` + `source_gcs_uri`; per-row try/except |
| `pipeline/deploy.sh` | Tue 02:00/06:00 UTC weekly | Feb 15 + Aug 15 02:00/06:00 UTC; deletes legacy weekly schedules |

### New

| File | Purpose |
|---|---|
| `pipeline/effective_year.py` | Three-source year resolver with explicit fallback chain |
| `pipeline/archive_writer.py` | GCS streaming write with inline SHA256 + sibling meta.json + idempotent skip-if-exists |
| `pipeline/tests/test_hospital_mrf_utils.py` | 6 tests covering BOM strip + per-row tolerance |
| `scripts/mrf_discovery/backfill_legacy_effective_year.py` | One-time tag of `hospital_charges_legacy_stale` with `pricing_effective_year=2025` |
| `scripts/mrf_discovery/stage4_extract_mrf_urls.py` | The missing piece: crawl each hospital website for its MRF URL |
| `scripts/mrf_discovery/tests/test_stage4_extract_mrf_urls.py` | 35 tests covering CMS regex, link extraction, TOC walker, file-format inference |
| `scripts/smoke_test_dual_write.py` | Reusable 10-hospital live tester for the dual-write path |
| `docs/decisions/2026-04-30-pipeline-cadence.md` | Full ADR for the new schedule |
| `docs/decisions/2026-04-29-redundant-clinical-pairs-rule.md` | New rule (REDUNDANT_CLINICAL_PAIR) added during Phase 4 |
| `docs/future-improvements/csv-mrf-parser.md` | Why CSV is deferred, build sketch when re-opened |

### Schema changes

`hospital_charges` already had `pricing_effective_year INT64 NOT NULL` from the Phase 1 migration. **One drift discovered during the live test:** the deployed table also has `source_mrf_url` and `source_gcs_uri` (provenance columns) and **does not** have `effective_date`. The parser was conformed to match the deployed schema rather than altering the table — every row now carries the original MRF URL and (when known) the gs:// URI of the immutable archive blob it was parsed from.

`mrf_archive_index` already had `parse_status STRING NOT NULL` from Phase 1. No schema change needed.

---

## Surprises caught only by live data (and how we fixed them)

These are the three "real-data only" bugs the synthetic test suite missed.
The smoke harness `scripts/smoke_test_dual_write.py` was specifically
built to catch this class — using one real hospital's bytes in a
controlled 10-hospital sample exposed all three within an hour.

### Surprise #1 — UTF-8 BOM at file start (commit `92f31bf`)

Saint Michaels Medical Center (NPI 1568825545) exported their MRF from a
Windows tool that prepended `\xef\xbb\xbf` (UTF-8 byte-order mark). ijson
silently emits zero items when it sees a BOM at the start of the
stream — losing the entire 214,613-row hospital's pricing data.

Fix: `pipeline/hospital_mrf_utils.py:_strip_bom()` sniffs the first 3
bytes; if they match the BOM, those bytes are dropped before ijson sees
them. If no BOM, the bytes are restored via a `_PrefixedStream` shim so
parsing starts cleanly from byte 0.

5 unit tests cover the BOM, no-BOM, short-stream, and partial-read cases.

### Surprise #2 — `mrf_archive_index` UPDATE blocked by streaming buffer (commit `92f31bf`)

`insert_archive_index_rows()` originally used `bq.insert_rows_json()`
(streaming insert). Streamed rows sit in BigQuery's streaming buffer for
~30 minutes before they become UPDATE-eligible. The parser runs
immediately after the scraper and needs to flip `parse_status` from
`'pending'` → `'parsed'`, which fails against streamed-but-not-merged
rows: *"UPDATE or DELETE statement over table ... would affect rows in
the streaming buffer, which is not supported."*

Fix: switched to a load job (`LoadJobConfig` + `load_table_from_file`
with `WRITE_APPEND`). Load jobs land directly in storage, no streaming
buffer, DML-eligible immediately. Same pattern Phase 4 already used in
`update_last_modified()`.

### Surprise #3 — schema drift between parser and deployed table (commit `92f31bf`)

Phase 1 migration created `hospital_charges` with `source_mrf_url` and
`source_gcs_uri` (provenance) and **dropped** `effective_date` — but the
parser was still sending `effective_date` and missing the source columns.
LOAD failed with *"Cannot add fields (field: effective_date)."*

Fix: conformed parser's `HOSPITAL_CHARGES_SCHEMA`, `ChargeRow`, and
`stream_charges_v2()` signature to match the deployed table exactly.
Provenance now flows from `process_blob` → `stream_charges_v2` →
`ChargeRow` → BigQuery on every row.

---

## What shipped beyond the original scope

The 2026-04-29 doc anticipated stages 4a-4e (~7 days). The actual
delivery rolled in three additional pieces of work because the live
testing revealed gaps the doc didn't anticipate:

### Stage 4 of discovery — the missing crawler

The original plan assumed `hospital_directory` already had MRF URLs from
Phase 3. **It didn't.** Phase 3 found websites for 11,860 hospitals but
the stage that crawls each website to extract the actual MRF download URL
was never built.

We discovered this by querying `mrf_discovery_checkpoint`:

| Column | Populated | Total |
|---|---|---|
| `hospital_website` | 12,695 | 13,989 |
| `validated_mrf_urls` | **0** | 13,989 |

Stage 4 (`scripts/mrf_discovery/stage4_extract_mrf_urls.py`) closes the
gap: 17 path-heuristic probes (`/price-transparency`, `/standard-charges`,
etc.), HTML link extraction with the CMS filename regex
`\d{6,12}_..._standardcharges.{csv,json,xml,xlsx}`, hospital-system TOC
fan-out, HEAD validation, and MERGE into `hospital_directory` so the
scraper picks them up unchanged. Free, ~15-25 min wall-clock at 60
workers. 35 unit tests.

### REDUNDANT_CLINICAL_PAIR rule

Sandra reported a real bill containing `76817+76801` (OB ultrasound) and
`86900+86901` (ABO+Rh blood typing) was not flagged. Investigation
against the raw 2026 v3.21 CMS NCCI MCR PTP files confirmed neither pair
exists in NCCI in either direction — the engine was correct. But most
commercial payer medical-policy documents deny one of these codes when
both are billed for the same encounter.

Built `apps/engine/app/data/redundant_clinical_pairs.py` (curated
allowlist, 7 starter pairs across 3 categories — OB ultrasound, lab
panels, E&M with procedure) and rule #13 in `rules_engine.py` with
warning severity, hedged copy, and dedup against NCCI when a curated
pair also appears there. 10 unit tests. Documented in
`docs/decisions/2026-04-29-redundant-clinical-pairs-rule.md` and the
rules-engine reference docs.

### New cadence (replaces weekly)

After running Phase 4 once, we measured: `Last-Modified` headers from
December 2024 on a freshly-pulled 2026 MRF. Hospitals republish at most
once per year, with ~10% summer republishes — weekly polling was 96%
waste. Sandra's call: annual full sweep + mid-year safety + quarterly
gap-fills for hospitals still missing URLs.

The new schedule (`docs/decisions/2026-04-30-pipeline-cadence.md`):

| Job | Cron | Scope |
|---|---|---|
| `clarobill-mrf-discovery-annual` | `0 2 15 2 *` (Feb 15) | Full Stages 1-4 + Tier 3 paid sweep |
| `clarobill-mrf-discovery-quarterly` | `0 2 15 5,8,11 *` (May/Aug/Nov 15) | `--gap-fill-only`; skips Tier 3 paid |
| `clarobill-mrf-scraper-annual` | `0 2 15 2 *` (Feb 15) | All hospitals with `mrf_url` |
| `clarobill-mrf-scraper-midyear` | `0 2 15 8 *` (Aug 15) | Same — catches summer republishers |
| `clarobill-mrf-parser-annual` | `0 6 15 2 *` (Feb 15) | 4h after annual scraper |
| `clarobill-mrf-parser-midyear` | `0 6 15 8 *` (Aug 15) | 4h after mid-year scraper |

Legacy weekly + bi-annual schedules deleted by next deploy.

### Cloud Run command/args split (commit `02c2e3a`)

The Dockerfile bakes the script path into `CMD args`. When a user
passes `--args` at execute time, Cloud Run **replaces the args portion
entirely**, including the script path — so
`gcloud run jobs execute --args=--start-stage=...` ended up running
`python --start-stage=...` with no script. Container died in <5s with no
Python output (execution `clarobill-mrf-discovery-g66ns`).

Fix: deploy the Cloud Run Job with the script path in `--command` (which
is preserved across overrides) and only `--project` in `--args` (which
gets replaced; orchestrator's argparse handles the `--project` default
itself). Documented in `pipeline/deploy.discovery.sh` so re-deploys don't
regress this.

---

## Live verification

Smoke test on Saint Michaels Medical Center (NPI 1568825545,
2026-04-29 → 04-30, smoke runs 1-3):

| Metric | Before fixes | After fixes |
|---|---|---|
| Hospital downloaded | 1/1 | 1/1 |
| Archive write succeeded | 0/1 (no NPI/CCN on 1st sample) | 1/1 |
| Parser charge rows | 0 (BOM caused silent failure) | **214,613** |
| `pricing_effective_year` resolved | n/a | **2024 from `json_last_updated_on`** |
| `parse_status` flipped | n/a | parsed (after streaming buffer fix) |
| `hospital_directory.hospital_npi` backfilled | n/a | yes |
| Archive bytes | n/a | 1.67 MB compressed → `gs://mrf-archive-clarobill-prd/pricing-year=2024/1568825545/ffedada42ab0b5b3.json.gz` |

Synthetic regression suite:
- 6 pipeline tests (BOM strip + per-row tolerance) — all pass
- 35 Stage 4 tests (regex + link extraction + TOC walker + format inference) — all pass
- 97 rules engine tests (including 10 new REDUNDANT_CLINICAL_PAIR cases) — all pass
- Total: **138 new + existing tests, zero regressions**

---

## What's not done

| Item | Why deferred | Trigger to revisit |
|---|---|---|
| **Phase 5 — rules engine cutover** | Still reads from `hospital_charges_legacy_stale`. Switching is a single SQL change — pending enough new-table data to compare audit results against. | After 2027-02-15 annual run produces ~140M rows of fresh 2026 chargemaster. |
| **CSV-format MRFs** | Each hospital uses different column names. Per-vendor mapping is a project of its own. | When `parse_status='skipped'` count is meaningful. Build sketch in `docs/future-improvements/csv-mrf-parser.md`. |
| **4f historical PRA backfill** | PRA blocked by Cloudflare; no historical bulk source available today. | If/when CMS or a third party publishes bulk historical chargemaster data. |
| **Pre-Feb-15-2027 Stage 4 backfill** | Currently running as `clarobill-mrf-discovery-9gvjw`. Once it lands, the new ~10k-hospital fleet is scrapable on-demand without waiting for the next scheduled run. | Monitoring the execution; report stats when it completes. |

---

## Migration risks the doc flagged — outcomes

| Risk | Outcome |
|---|---|
| New parser produces different audit results than legacy | Not yet validated against 5 known-flagged bills. **Phase 5 cutover gate.** |
| Archive bucket storage cost balloons | Live test: ~1.6 MB compressed per hospital. ~13k × 1.6 MB = ~20 GB. Coldline at $0.004/GB-mo = $0.08/mo. Way under budget. |
| Parse failures snowball | UTF-8 BOM was 1/1 in our test; per-row tolerance + load-job archive_index status give clean SQL visibility. Run-summary surfaces failure count. |
| Cutover breaks the rules engine | Pre-Phase-5: rules engine still on legacy table. New table fills in parallel. |
| Schedule conflict with discovery | New cadence has zero overlap (Feb 15 + Aug 15 anchors for both discovery + scrape; quarterly only on no-overlap dates). |

---

## What this enables for Phase 5 (rules engine cutover)

After enough Phase 4 runs (target: post-2027-02-15), `hospital_charges`
will have:
- Fresh 2026 + 2027 chargemaster rows for ~13k hospitals
- Year-tagged with `pricing_effective_year`
- Source-tagged with `source_mrf_url` + `source_gcs_uri` for audit
- Cross-referenced via `hospital_npi` to `hospital_directory`

Phase 5 changes one query in `rules_engine.py`:
```sql
-- OLD:
SELECT * FROM hospital_charges_legacy_stale WHERE hospital_npi = @npi
-- NEW:
SELECT * FROM hospital_charges
WHERE hospital_npi = @npi
  AND pricing_effective_year = YEAR(@bill_service_date)
ORDER BY scraped_at DESC
```

Plus a fallback: if no row matches the exact year, pick the nearest
prior year (never future). This is the actual *"audit a 2024 bill
against the 2024 chargemaster"* capability.

---

## Operational reference (for the on-call engineer)

### Manual triggers

```bash
# Full annual discovery (paid) — Stages 1-4 + Tier 3 sweep
gcloud run jobs execute clarobill-mrf-discovery --region us-central1

# Gap-fill only (free) — only hospitals where validated_mrf_urls IS NULL
gcloud run jobs execute clarobill-mrf-discovery --region us-central1 \
  --args=--gap-fill-only

# Re-run only Stage 4 (URL crawler) on an existing run
gcloud run jobs execute clarobill-mrf-discovery --region us-central1 \
  --args=--start-stage=stage4_mrf_urls,--run-id=<run-id>

# Re-run only Tier 3 with a fresh budget
gcloud run jobs execute clarobill-mrf-discovery --region us-central1 \
  --args=--start-stage=stage3_tier3,--run-id=<run-id>

# Manual scrape + parse (e.g. customer reports stale prices)
gcloud run jobs execute clarobill-mrf-scraper --tasks 6 --region us-central1
gcloud run jobs execute clarobill-mrf-parser  --tasks 6 --region us-central1
```

### Health-check queries

```sql
-- Did the latest annual run produce data?
SELECT COUNT(*) AS rows_loaded, MAX(scraped_at) AS latest
FROM `clarobill-prd.hospital_prices.hospital_charges`
WHERE scraped_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR);

-- What's the parse_status distribution?
SELECT parse_status, COUNT(*)
FROM `clarobill-prd.hospital_prices.mrf_archive_index`
WHERE scraped_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
GROUP BY parse_status;

-- Which hospitals failed to parse and why?
SELECT hospital_npi, ccn, parse_error, gcs_uri
FROM `clarobill-prd.hospital_prices.mrf_archive_index`
WHERE parse_status = 'failed'
  AND scraped_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
ORDER BY scraped_at DESC LIMIT 50;

-- Year-resolution coverage (post-parser run)
SELECT pricing_effective_year, COUNT(DISTINCT hospital_npi) AS hospitals
FROM `clarobill-prd.hospital_prices.hospital_charges`
GROUP BY pricing_effective_year
ORDER BY pricing_effective_year DESC;
```

### Runbook entries

- **A scheduled run didn't fire:** check `gcloud scheduler jobs describe <name> --location us-central1` for `state: PAUSED` or auth issues. Re-enable with `gcloud scheduler jobs resume`.
- **Container exits in <5s with no Python output:** the Cloud Run Job's `--command` and `--args` are likely misconfigured. Check `gcloud run jobs describe ... --format=yaml | grep -B1 -A3 -E "command|args:"` — `command` should be `["python", "/app/scripts/discover_mrf_pipeline.py"]` and `args` should be `["--project", "clarobill-prd"]`. Re-run `bash pipeline/deploy.discovery.sh` to fix.
- **`UPDATE or DELETE ... streaming buffer` errors:** archive_index inserts must use load jobs (`bigquery.LoadJobConfig`), not `insert_rows_json`. Already fixed; if it regresses, see commit `92f31bf`.
- **Parser logs `No standard_charge_information found`:** check the file for a UTF-8 BOM (`gsutil cat <gs-uri> | head -c 5 | xxd`). If `efbbbf` is at byte 0, `_strip_bom()` should handle it; verify the parser image was rebuilt after commit `92f31bf`.

### Cost reference

| Cadence | Cost per run | Annual |
|---|---|---|
| Annual discovery (Feb 15) | ~$355-460 first year (Tier 3 capped at $450; Year 1 actual $349.92), ~$15-25/yr after | 1× |
| Quarterly gap-fill (May/Aug/Nov 15) | ~$1 each (no Tier 3) | 3× |
| Annual scrape + parse | bandwidth + ~$3 Cloud Run | 1× |
| Mid-year scrape + parse | bandwidth + ~$3 Cloud Run | 1× |
| **Total** | — | **~$365-470 first year, ~$25-35/yr after** |

vs. the previous weekly cadence: ~52× scrape + ~52× parse weekly = ~$300/yr in compute alone, with no fresher data. ~96% compute reduction.

---

*Document created: 2026-04-29*
*Last updated: 2026-04-30 with the shipped record + live verification + new cadence + Stage 4 + REDUNDANT_CLINICAL_PAIR + Cloud Run command/args fix*
*Owner: ClaroBill Engineering*
