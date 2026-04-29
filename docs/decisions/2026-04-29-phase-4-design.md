# Phase 4: Effective-Dated Archiver + Parser — Design Proposal

**Date:** 2026-04-29
**Status:** Designed — code not started; awaiting Sandra approval before implementation
**Phase:** 4 of 6 (post Phase 3 = MRF discovery; pre Phase 5 = rules engine cutover)

---

## Why this phase exists

After Phase 3, `hospital_directory` has ~13,833 hospitals with ~83% website coverage. The directory tells us **which hospital has which MRF URL**. Phase 4 turns those URLs into actual queryable price data:

1. **Download the MRF file** from each hospital's published URL
2. **Archive it immutably** to `gs://mrf-archive-clarobill-prd/pricing-year={year}/{npi}/{sha256}.{ext}` so it's reproducible years later
3. **Parse the file** into per-line-item rows (CPT, gross charge, negotiated rate per payer, etc.)
4. **Insert those rows into `hospital_charges`** with `pricing_effective_year` populated from the file's metadata or the run's calendar year

Phase 4 is also where the rules engine's "billed > MRF gross charge" rule becomes real. Right now `rules_engine.py:804-849` has the rule logic but reads from `hospital_charges_legacy_stale` (the renamed pre-effective-dating table). After Phase 4, the rule reads from the new effective-dated `hospital_charges` and fires correctly.

---

## What Phase 4 changes vs. what already exists

The repo already has a working scraper + parser at `pipeline/scrape_hospital_mrfs.py` and `pipeline/parse_hospital_mrfs.py`. They do not currently:

- Write to the immutable archive bucket (only to `mrf-staging`, which is mutable and rotating)
- Tag rows with `pricing_effective_year`
- Read from `mrf_archive_index` as a work queue (instead they list raw GCS blobs)
- Skip files whose SHA256 we've already archived for the current year

Phase 4 is a **rewrite of both**, not new modules. The existing files keep their names; their internals change. The weekly Cloud Run Job schedule (Tue 02:00 / 06:00 UTC) is unchanged.

---

## Architectural shape

### The new flow

```
Tuesday 02:00 UTC: clarobill-mrf-scraper

  For each hospital where hospital_directory.mrf_url IS NOT NULL:
    1. HEAD the URL (5s timeout)
    2. If Last-Modified or ETag matches the most recent mrf_archive_index row
       for this (npi, current_year), SKIP — we already have it.
    3. Otherwise:
       a. GET the file with streaming download
       b. Compute SHA256 inline as bytes flow through
       c. Determine pricing_effective_year (see below for the rule)
       d. Stream the bytes to:
            gs://mrf-archive-clarobill-prd/pricing-year={year}/{npi or ccn}/{sha256_first16}.{ext}
       e. Write a sibling meta.json:
            {sha256_first16}.meta.json containing source_url, scraped_at,
            content_type, file_size_bytes, etag, last_modified
       f. Insert a row into mrf_archive_index with parse_status='pending'

Tuesday 06:00 UTC: clarobill-mrf-parser

  SELECT * FROM mrf_archive_index WHERE parse_status='pending':
    1. Stream-download the GCS object (it's already in gs://mrf-archive-clarobill-prd/)
    2. Parse with hospital_mrf_utils.iter_charges()
    3. For each parsed row, attach pricing_effective_year from the
       mrf_archive_index row
    4. Bulk-insert rows into hospital_charges (NOT REPLACE — append-only;
       see "How re-published MRFs are handled" below)
    5. Update mrf_archive_index.parse_status = 'parsed' (or 'failed' with parse_error)
```

### Pricing-effective-year resolution rule

Three sources, in order of preference:

1. **MRF JSON `last_updated_on` field** — CMS v2.0.0 schema includes this. Parse the date and use its year.
2. **HTTP `Last-Modified` header** — fallback if MRF JSON doesn't have the field or is malformed.
3. **Current calendar year** — fallback if both above are missing. Logged as a warning so operators can investigate.

This logic is encapsulated in a new helper `pipeline/effective_year.py` with unit tests against fixture MRFs. The fallback chain is documented in code so future engineers don't second-guess the priority order.

### Key data integrity rule: hospital_charges is append-only with year+sha as the dedup key

When a hospital re-publishes its MRF mid-year (rare but happens):

- Old behavior: parser would DELETE all existing rows for this NPI then INSERT new ones. This destroys history.
- **New behavior:** insert the new rows tagged with the new sha256 and the same pricing_effective_year. The rules engine queries by `(hospital_npi, pricing_effective_year)` and uses `ORDER BY scraped_at DESC LIMIT N` to pick the freshest version, but old rows remain queryable for forensic audits.

This is the foundation of "audit a 2024 bill in 2030 against the chargemaster that was actually in force." Old data must persist; only the **active query view** changes.

---

## Files changing

### Rewritten (existing names, new internals)

| File | What it does today | What it does after Phase 4 |
|---|---|---|
| `pipeline/scrape_hospital_mrfs.py` | Reads `hospital_directory`, writes to `mrf-staging`, updates `last_modified` | Reads `hospital_directory`, archives to `mrf-archive-clarobill-prd` partitioned by year, writes `mrf_archive_index` row, never deletes |
| `pipeline/parse_hospital_mrfs.py` | Lists `gs://mrf-staging/raw/` blobs, parses, DELETE+INSERT into `hospital_charges` | Reads `mrf_archive_index WHERE parse_status='pending'`, parses, append-only INSERT with `pricing_effective_year` |
| `pipeline/hospital_mrf_utils.py` | Existing v2.0.0 streaming parser | Adds `extract_last_updated_on(stream)` helper for the year resolution |

### New

| File | Purpose |
|---|---|
| `pipeline/effective_year.py` | Resolves `pricing_effective_year` from MRF metadata + HTTP headers + fallback |
| `pipeline/archive_writer.py` | GCS streaming write helper that computes SHA256 inline and writes both data + meta.json sibling. Reuses `scripts/mrf_discovery/archive_layout.py` for path construction. |
| `apps/engine/tests/pipeline/test_effective_year.py` | Unit tests against fixture MRFs |
| `apps/engine/tests/pipeline/test_archive_writer.py` | Unit tests with mock GCS |

### Schema changes (BigQuery — additional migration)

`hospital_charges` already has `pricing_effective_year INT64 NOT NULL` from the Phase 1 migration. No schema change needed.

`mrf_archive_index` already has `parse_status STRING NOT NULL` and the right shape from Phase 1. No schema change needed.

**One small DDL addition:** add an index/clustering hint on `mrf_archive_index` by `parse_status` so the parser's "WHERE parse_status='pending'" query is fast as the index grows. Already in the `CLUSTER BY hospital_npi, parse_status` clause from Phase 1 — verified.

### Files that DO NOT change

- `pipeline/Dockerfile` (the weekly image) — same `CMD`, same dependencies. The new code lives in the same Python files.
- `pipeline/deploy.sh` — same Cloud Run Jobs, same Cloud Scheduler triggers, same Tue 02:00/06:00 UTC schedule.
- `pipeline/requirements.txt` — no new dependencies (everything we need is already pinned: `google-cloud-bigquery`, `google-cloud-storage`, `requests`, `ijson`).

This is an internals rewrite, not an infrastructure change.

---

## Stage-by-stage build plan (proposed)

### 4a — Schema verification and test scaffolding (1 day)

- Confirm `hospital_charges` and `mrf_archive_index` schemas match Phase 4 expectations (they should, but verify against live BQ).
- Add MRF fixture files for testing: 5-10 real anonymized MRF samples covering CSV / JSON / JSON.GZ formats. Land them in `apps/engine/tests/fixtures/mrf/`.
- Write `effective_year.py` + tests (target: 100% branch coverage on the resolution rule).

### 4b — Archive writer module (1 day)

- New `pipeline/archive_writer.py` with:
  - `class ArchiveWriter` — streams bytes to GCS, computes SHA256 inline, writes data + meta.json
  - `def write_archive(npi_or_ccn, year, source_url, headers, byte_stream) -> ArchiveResult`
  - Idempotent: same source URL + sha256 in same year is a no-op (existing object detected, no re-write)
- Tests with `google-cloud-storage` test client: happy path, idempotent skip, partial-stream failure, oversized file rejection.

### 4c — Scraper rewrite (2 days)

- Rewrite `scrape_hospital_mrfs.py` to:
  - Pull from `hospital_directory` (unchanged)
  - HEAD-check via `mrf_archive_index` (NEW query path)
  - Archive via `archive_writer` (NEW)
  - Insert into `mrf_archive_index` (NEW)
  - No longer touch `hospital_directory.last_modified` (it remains a free-form column from older code; tracking moves to `mrf_archive_index`)
- Test against the 5-10 fixture MRFs through a mock HTTP layer.
- Live test on `--limit 10` against 10 known-working hospital URLs to verify the full path actually writes archive + index entries.

### 4d — Parser rewrite (2 days)

- Rewrite `parse_hospital_mrfs.py` to:
  - Read pending work from `mrf_archive_index` (NEW)
  - Stream from the archive bucket directly (NEW — was reading from `mrf-staging`)
  - Use `effective_year.py` to attach the year to each parsed row
  - Append-only INSERT to `hospital_charges` (NEW — was DELETE+INSERT)
  - Update `parse_status` on success or failure
- Test with the same fixtures, verify row counts and year tagging.

### 4e — Cutover plan (1 day)

- Run new scraper against `--limit 100` real hospitals. Verify:
  - Archive bucket has objects at expected paths
  - `mrf_archive_index` has 100 pending rows
- Run new parser against those 100. Verify:
  - `hospital_charges` has rows with `pricing_effective_year` populated
  - `parse_status='parsed'` on the index rows
- Compare audit results: pull 5 bills that previously got "billed > MRF" hits from `hospital_charges_legacy_stale`, run through the new pipeline, confirm same hits (or explain any differences).
- Cutover: deploy new image, schedule kicks in next Tuesday automatically.

### 4f — Backfill historical years if PRA grants (optional, deferred)

If Sandra hears back from PRA with bulk historical data (2024, 2025), Phase 4 has the shape to ingest it: download each historical file, archive at `pricing-year={historical_year}/`, parse with the year tag, INSERT. Same code path; only the year tag differs.

**Total estimated time: 7 days of focused engineering.** Most risk is in 4d (parser rewrite — handles the largest data volumes and has the most edge cases around malformed MRFs).

---

## Open questions for Sandra to answer before code starts

### Q1 — Archive key: `npi` or `ccn` or both?

`archive_layout.build_object_uri()` accepts a `key` parameter that's either NPI (when known) or CCN (when not). Phase 4 currently has ~83% website coverage but only ~48% NPI coverage from Stage 2B. For the 35% of hospitals where we have a website but no NPI yet, Phase 4 will write the archive object under their CCN key — and the parser, after extracting the NPI from the MRF JSON root, will write the row to `hospital_charges` with the discovered NPI.

**Choice:** are we OK with mixed-key archive paths (`{npi}/...` for some, `{ccn}/...` for others), or should Phase 4 ALWAYS use NPI even if it means deferring those hospitals until the parser backfills the NPI?

**Recommendation:** mixed keys. The `archive_layout.parse_object_uri()` function already returns the key as a generic string; callers don't care whether it's a CCN or NPI. The cost of "deferring" a hospital is that we don't have its 2026 chargemaster archived for 2026 — meaningful loss. Mixed keys lose nothing.

### Q2 — What happens to `hospital_charges_legacy_stale` after cutover?

Two options:
1. **Drop it** as soon as the new pipeline is producing rows. Saves storage cost (~$1/year). Loses the audit trail of "what we believed pre-effective-dating."
2. **Keep it forever**, just never read from it. Storage cost is ~$1/year; reading cost is $0 if nothing queries it.

**Recommendation:** keep forever. The cost is negligible and the audit trail is valuable. If anyone ever asks "why did our August 2026 audit say X but our December 2026 audit say Y for the same bill?" the legacy table is the only record of the pre-cutover state.

### Q3 — Append-only vs. soft-delete on re-published MRFs

Suppose a hospital publishes their MRF in February 2026, then re-publishes in August 2026 with corrected rates. Two design choices:

**A) Append-only with "active version" flag** — Parser inserts the August version's rows. The old February rows stay. Rules engine queries with `ORDER BY scraped_at DESC` and picks the latest per (npi, year, code). Adds a tiny bit of query complexity but preserves history.

**B) Append-only without flag** — Same as A but the rules engine just `SELECT MAX(scraped_at)` to pick the version. Simpler engine logic; same data shape.

**C) Soft delete** — Mark old rows `is_superseded=TRUE` when new ones land. Most explicit, most code, easiest to query "what was active when?" by filtering on the flag.

**Recommendation:** B (append-only, query for max scraped_at). Simplest. The forensic question "what was in force on date X?" is answered by adding `WHERE scraped_at <= bill_service_date` to the query — no schema change needed. C is over-engineering until we actually have a use case for "is_superseded" boolean.

### Q4 — Concurrency for the scraper

Today's scraper uses ThreadPoolExecutor with 20 workers. Phase 4's archive write is per-hospital and bounded by GCS throughput, not hospital server. Three options:

1. Keep 20 workers (current).
2. Bump to 40 (faster, but 13,833 hospitals × 5MB avg MRF = 70GB total throughput; want to make sure GCS can absorb).
3. Reduce to 10 (more conservative, longer runtime).

**Recommendation:** keep 20. Existing behavior is known-good; no need to change concurrency in a rewrite that's already changing logic.

### Q5 — Failed-parse handling

Some hospitals publish malformed JSON or non-spec MRFs. The legacy parser would crash on these. Phase 4 needs explicit handling:

- Catch parse failures per-file
- Set `mrf_archive_index.parse_status='failed'` with `parse_error=<reason>`
- Move on to the next file
- Surface failure count in run summary

**Recommendation:** above. No retry logic in-pipeline; fixes for malformed MRFs go through manual triage of the `parse_status='failed'` queue. (Most are vendor format quirks that need code changes to handle.)

---

## Migration risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| New parser produces different audit results than legacy | Medium | High (false-positives in dispute letters) | Phase 4e cutover plan: compare 5 known-flagged bills, verify same outcome, document any differences |
| Archive bucket storage cost balloons | Low | Medium ($) | Coldline storage at $0.004/GB-mo; 13,833 hospitals × 5MB avg = 70GB = $0.28/mo. Negligible. Year 5+ if growth is 100GB/yr would still be < $5/mo. |
| Parse failures snowball | Medium | Low | `parse_status='failed'` filter prevents re-attempting same file; manual triage queue documented |
| Cutover breaks the rules engine | Medium | High (audit accuracy) | Rules engine still reads from `hospital_charges_legacy_stale` until Phase 5; Phase 4 just produces the new table in parallel. Phase 5 is the cutover. |
| Schedule conflict with running discovery job | Low | Low | Discovery runs annually on Jan 15; weekly scraper runs Tue 02:00. They never overlap. |

---

## What this enables for Phase 5 (rules engine cutover)

After Phase 4 has been running for ~4 weeks (one full monthly cycle), `hospital_charges` will have:

- ~3-4 weeks of fresh weekly-scraped data
- ~13,833 hospitals × ~10,000 rows per hospital = ~140M rows (rough order of magnitude)
- Year-tagged with `pricing_effective_year=2026`
- Cross-referenced via `hospital_npi` to `hospital_directory`

Phase 5 changes one query in `rules_engine.py:804-849`:
```python
# OLD:
SELECT * FROM hospital_charges_legacy_stale WHERE hospital_npi = @npi
# NEW:
SELECT * FROM hospital_charges
WHERE hospital_npi = @npi
  AND pricing_effective_year = YEAR(@bill_service_date)
ORDER BY scraped_at DESC
```

Plus a fallback: if no row matches the exact year, pick the nearest prior year (never future). This is the actual "audit a 2024 bill against the 2024 chargemaster" capability.

---

## Decisions needed before implementation starts

Sandra reviews this doc. Specifically:
1. ✅ or 🔧 the recommendations to Q1-Q5
2. Confirm 7-day estimate is reasonable (or push back if the timeline doesn't fit other priorities)
3. Confirm we want to ship Phase 4 before tackling any other deferred work (Pass 2C didn't ship; non-Medicare pricing integrations didn't ship; etc.)

Once those are answered, Phase 4a starts on the next working day.

---

*Document created: 2026-04-29*
*Owner: ClaroBill Engineering*
