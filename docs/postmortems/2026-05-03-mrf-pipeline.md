# MRF pipeline postmortem — what made the 2026-05-01/02/03 runs slow and what to change

**Date:** 2026-05-03
**Status:** prescriptive — outcomes captured, prod fixes shipped, follow-up
work itemised below

The 2026-05-01 fleet scrape + parse was meant to grow `hospital_charges`
from 55 hospitals to several hundred. After ~48 hours of compute it was
still at 55 hospitals and 1,137 parsed blobs — a $25–$30 chunk of that
day's $121 GCP bill spent moving the count from 1,137 to 1,137. This
doc captures what went wrong, what we shipped to fix it, and what is
still open work for the next run.

---

## What was actually wrong (root causes)

### 1. The scraper saved garbage as JSON

The scraper followed Stage 4-discovered URLs and **wrote whatever the
HTTP response body was** into `mrf-staging/raw/{slug}.json.gz`,
regardless of Content-Type or first-byte. That meant ~16,000 blobs of:

- HTML 404 pages
- Hospital marketing landing pages
- Excel `.xlsx` files
- PDF brochures
- One Facebook redirect (the URL chain ended at fb.com)

These all sat in staging and archive looking like JSON until the
parser tried to read them.

### 2. The parser tried to JSON-stream every garbage blob

Each non-JSON file consumed 5–10 seconds of parser time:

1. Full download from GCS (~MB scale)
2. ijson stream open
3. ijson hits an HTML `<` byte, raises `IncompleteJSONError`
4. Parser tries `seek(0)` to retry alternate root key
5. Gzip stream isn't seekable, raises `UnsupportedOperation`
6. Parser logs warning, marks blob `failed`, moves on

A 30K-blob run at 5–10 s/blob × ~50% garbage ratio is ~25 hours of
wasted runtime per scrape cycle. Not catastrophic, but unbounded —
when the staging bucket grows, the cycle grows with it.

### 3. The parser walked `mrf-staging` directly, not `mrf_archive_index`

`mrf_archive_index` is the BigQuery table where every scraped blob
gets a `parse_status` (pending/parsed/failed/skipped). The parser
should have been pulling work from that table. Instead it walked
`gs://mrf-staging/raw/` from scratch every run and downloaded every
blob — including the ~24K already classified as terminal by previous
runs.

This is why the in-session classifier I wrote (which updated
`mrf_archive_index.parse_status` for ~26K pending blobs) had **zero
effect** on parser throughput: the parser never read that column.

### 4. `hospital_directory` had duplicate rows for the same facility

Saint Michael's Medical Center NJ had two rows: NPI `1568825545`
(active, 1.28M `hospital_charges` rows) and NPI `1164611885` (stale,
zero rows). The resolver picked the stale one due to apostrophe
mismatch (`Saint Michael's` vs `Saint Michaels`) and the engine
silently fell back to generic commercial benchmarks instead of using
real MRF data.

### 5. Discovery cron jobs could re-fire Places API ($349/run) without a budget gate

`clarobill-mrf-discovery-quarterly` was scheduled for May 15 with no
hard cap on Tier 3 spend. Paused manually for now.

### 6. Pipeline `deploy.sh` was broken since `336ef59`

The Dockerfile was updated to COPY from repo root (`pipeline/*` and
`scripts/mrf_discovery/*`), but `deploy.sh` still passed `pipeline/`
as the build context. The script silently failed every time and the
last successful build was carrying stale code.

### 7. Cloud Build trigger had no path filter

Web-only commits triggered engine rebuilds. ~5 today; only 3 touched
engine code.

---

## What shipped during the postmortem (prod fixes)

| Commit | Fix |
|---|---|
| `2af533a` | Gemini truncation guard — non-STOP finish_reason raises so Claude fallback activates instead of shipping partial dispute letters |
| `070cab3` + `e4d79d3` | NPI resolver validates every candidate against `hospital_charges`; apostrophe-tolerant name match; falls through ambiguous matches |
| `5acc1ef` | per-line MAX overcharge calc (no more triple-counting of overlapping rules); line_items dedupe on re-analyze; PDF severity-DESC; analysis page severity-ASC |
| `7880902` | reports list UI bug fix (no more "no errors found + $1,653 savings"); auto-refresh while pending; parallel storage uploads |
| `98a777e` | parser content-sniff guard — fast-fail non-JSON in <1s instead of 5–10s ijson cycle |
| `cc87309` | privacy policy IP redaction — every named vendor → category language |
| `a5c3e7a` | pipeline `deploy.sh` build-context fix — now uses repo-root context via `pipeline/cloudbuild.yaml` |
| `577e6d8` | parser in-memory skip-set — pre-fetches terminal-state URLs at startup so already-classified blobs are skipped before download |

After all of the above, an end-to-end re-analyze of the Saint Michaels
demo bill produced **9 real findings** including 4
`HOSPITAL_CHARGE_OUTLIER` and 4 `NEGOTIATED_CEILING_EXCEEDED`, all
backed by published Saint Michaels rates — vs the 2 generic
commercial-benchmark `PRICE_OUTLIER` findings the prior pipeline produced.

---

## What is still open work

### ~~Scrape-time validation (the root fix)~~ — SHIPPED 2026-05-04 (commit `e2745d4`)

`sniff_mrf_format()` in `pipeline/hospital_mrf_utils.py` plus the
`_PrependedStream` helper in `pipeline/scrape_hospital_mrfs.py` now read
the first 4 KB of every response, classify it (json/csv/zip/xlsx/xml/
pdf/html/empty/unknown), and reject anything outside the
`ACCEPTED_MRF_FORMATS = {json, csv, zip, xlsx, xml}` set before any
write to staging or archive. The 4 KB sniff buffer is spliced back
onto the upload stream so original bytes are preserved.

Coverage in tests: 17 sniffer cases (gzip-of-html, BOM-prefixed JSON,
CSV via URL extension, etc.) plus 6 download-path cases (HTML reject,
PDF reject, JSON accept, CSV accept, gzipped JSON accept, full-body
preservation).

### ~~Parser reads from `mrf_archive_index`, not the bucket~~ — SHIPPED 2026-05-04 (commits `5a1de5d`, `3684894`, `6bc53c5`)

`PARSER_DRIVER=archive_index` env var selects a new mode that reads
`SELECT ... FROM mrf_archive_index WHERE parse_status='pending' GROUP
BY gcs_uri ORDER BY gcs_uri`, opens the blob via its `gcs_uri`
(immutable archive bucket), and processes through the same
`process_blob_with_meta()` core. Source blob is **never** deleted on
success — the immutable-archive invariant is asserted by the
`test_archive_blob_never_deleted_on_success` regression test.

Two follow-up commits hardened this:
  - `3684894` adds `GROUP BY gcs_uri` + an in-memory dedupe set after a
    runaway loop appended 643,839 duplicate rows for Saint Michaels
    Medical Center (the same URL had multiple archive_index entries;
    `update_archive_index_status` flipped them all but the loop kept
    iterating). 643,839 dupe rows were cleaned up via SQL DELETE.
  - `6bc53c5` adds task sharding (`rows[task_index::task_count]`) so
    `--tasks 6 --parallelism 6` cuts wall-clock from ~37h to ~6h.

`PARSER_RETRY_PATTERN` env var, when paired with the archive_index
driver, flips matching `failed` rows back to `pending` for retry.
Used 2026-05-04 to recover the 2,111 NULL-NPI cohort.

### ~~Storage cleanup~~ — DECLINED 2026-05-04

Sampling the "11,984 garbage" cohort showed it's **mixed**: 1,981
blobs (81.76 GB) are real chargemaster data in unsupported formats
(1,216 ZIP, 765 CSV) — these are exactly the cohort that the CSV
parser rollout (Phase 4) is meant to unlock. Bulk delete would erase
recoverable data.

What did happen: the 1,981 non-JSON-extension blobs were reclassified
from `failed`/`classified-as: failed` to
`skipped`/`format not yet supported by parser: <ext>` so they're
properly categorised when CSV/ZIP support lands. No GCS deletes.

Coldline cost for the entire archive (~100 GB) is ~$0.40/month — not
worth the deletion risk.

### ~~GCS lifecycle on `mrf-staging`~~ — DECLINED 2026-05-04

Sandra's decision: keep all blobs. The new content-validation guard
prevents new garbage from accumulating, so unbounded growth is no
longer a concern.

### CSV-format MRF support — IN PROGRESS

Scope re-measured 2026-05-04: **13,206 blobs / 1,973 GB** (much larger
than the original ~11K estimate). Full design doc at
`docs/decisions/2026-05-04-mrf-coverage-plan.md`. Phased rollout:

- **4a** (this session): framework + Sutter parser
- **4b**: Kaiser, HCA, Mercy, Tenet
- **4c**: ZIP-unwrap + recursive dispatch
- **4d**: long-tail vendors + auto-discovery cron

### ~~Cloud Build path filter~~ — out of scope of this postmortem; tracked separately.

### ~~`hospital_directory` deduplication~~ — partially handled by the NPPES resolver (commit `750f83b`); a dedicated dedupe pass remains tracked separately.

### Places API budget alert — still open (separate concern).

### Cloud Build path filter

Add `included_files: ["apps/engine/**", "pipeline/**", "supabase/**"]`
to the engine build trigger so web-only commits skip engine rebuilds.

### `hospital_directory` deduplication

The Saint Michaels case (active NPI vs stale NPI) is unlikely to be
the only one. Run a one-shot dedupe pass that for every (name, state)
group with multiple NPIs, keep only the row(s) whose NPI has rows in
`hospital_charges`. Anything else can be dropped or marked inactive.

### Places API budget alert

GCP doesn't expose a hard "stop billing at $X" knob, but a budget
alert at $5/day on the Places API line would surface another Tier 3
re-fire within hours instead of at the end-of-month bill.

---

## Cost impact

- Yesterday's bill: $121, of which ~$25–30 was wasted parser/scraper
  runtime on garbage.
- Today's bill (so far): roughly $3–5 in re-runs to validate fixes.
- After all fixes ship, expected per-cycle cost (annual + mid-year
  scrape + parse): ~$8–12 for a clean run, vs ~$40–60 with the old
  pipeline burning compute on garbage.

---

## Operating discipline takeaways

1. **The scraper is the integrity layer.** Filter garbage at upload
   time. The parser should be able to assume every blob it sees is
   real MRF JSON.
2. **One source of truth for work queues.** `mrf_archive_index` is it
   — every batch processor reads from it, every status update flows
   to it.
3. **Operational scripts live in `/tmp/` until they earn a `/scripts`
   slot.** Today's debugging scripts (regen, reanalyze, classifier)
   were committed and then ripped out — they should never have been
   committed in the first place.
4. **Every cron that can spend money needs a budget alert** before it
   gets enabled.
5. **Test deploy.sh after every Dockerfile change.** It silently
   failed for ~3 days and we only caught it when the parser was
   running stale code.
