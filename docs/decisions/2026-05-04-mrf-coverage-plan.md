# MRF coverage remediation plan — 2026-05-04

**Context:** Investigation of the 5/3-5/4 parser run found 60% of `hospital_charges`
rows had NULL `hospital_npi`. URL-regex + directory-join backfills (commit
`cb9b420` + 2026-05-04 BQ ops) recovered 44.7M rows / +23 hospitals.
**605.7M rows / 158 ambiguous EIN-only URLs / 11K skipped CSV blobs remain.**

This doc tracks the remaining coverage work in priority order.

## Checklist (in execution order)

- [x] **1. NPPES-based EIN/slug → NPI resolver** — DONE 2026-05-04 (commit `750f83b`)
  - Implemented at `scripts/mrf_discovery/resolve_ambiguous_npis.py`.
  - Acceptance gates: score ≥ 0.75 + margin ≥ 0.25 OR score=1.0; ≥ 2 shared
    tokens OR rare token (NPPES freq ≤ 5); pharmacy/clinic/group tiebreak.
  - Result: 75 of 210 URLs resolved (35.7%).
  - hospital_charges: 192 → **254 distinct hospitals** (+62).
  - NULL-NPI rows: 605.7M → **390.7M** (recovered 215M rows).

- [x] **2. Postmortem #1 — scrape-time content validation (root fix)** — DONE 2026-05-04
  - `sniff_mrf_format()` added to `pipeline/hospital_mrf_utils.py` — magic-byte
    + URL/Content-Type detection across json/csv/zip/xlsx/xml/pdf/html/empty.
  - `_PrependedStream` in `pipeline/scrape_hospital_mrfs.py` splices the 4 KB
    sniff buffer back onto the upload stream so original bytes are preserved.
  - Scraper rejects HTML/PDF/unknown responses before any GCS write.
  - 23 new tests across `test_hospital_mrf_utils.py` (sniffer) and
    `test_scrape_validation.py` (PrependedStream + reject path).

- [x] **3. Postmortem #2 — parser pulls work from `mrf_archive_index`** — DONE 2026-05-04
  - `process_archive_index_pending()` added to `pipeline/parse_hospital_mrfs.py`.
  - Selected via env var `PARSER_DRIVER=archive_index`. Bucket-walk remains default.
  - `process_blob` refactored into `process_blob_with_meta(... delete_source_on_success)`
    so archive-bucket blobs are NEVER deleted (immutable forensic invariant).
  - `reset_failed_to_pending(pattern)` flips historical 'failed' rows back
    to 'pending' for retry. Triggered via env var `PARSER_RETRY_PATTERN`.
  - `_blob_from_gcs_uri()` resolves arbitrary `gs://bucket/path` URIs.
  - 11 new tests in `tests/test_archive_index_driver.py` covering URI parsing,
    SQL parameterization, and the immutable-archive invariant.

- [ ] **4. CSV-format MRF support**
  - 11,262 historic + 1,981 reclassified `skipped` blobs (Sutter, Kaiser,
    Mercy Health, et al). 16+ GB of real data.
  - Add CSV parser path in `hospital_mrf_utils.py` keyed by sniffed format.
  - Vendor-specific column mapping (CMS doesn't standardize CSV column names).
  - Largest single coverage win after #1; biggest CA market unlock (Sutter, Kaiser).

## Out of scope for this remediation

- ZIP-format support (1,216 blobs / 65 GB). Many ZIP MRFs contain JSON/CSV
  inside; would benefit from #4 first.
- 56 EIN-only URLs not in `hospital_directory` at all (discovery gap, not a
  resolution gap; needs separate Stage 4 pass).
- 30-day lifecycle on `gs://mrf-staging` — explicitly NOT doing per Sandra
  decision 2026-05-04 (keep all blobs).
- Storage cleanup of garbage in `mrf-archive-clarobill-prd` — Coldline
  cost is ~$0.40/month for the entire archive, not worth deletion risk
  given the cohort is mixed with real data in unsupported formats.
