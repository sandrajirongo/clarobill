# MRF coverage remediation plan — 2026-05-04

**Context:** Investigation of the 5/3-5/4 parser run found 60% of `hospital_charges`
rows had NULL `hospital_npi`. URL-regex + directory-join backfills (commit
`cb9b420` + 2026-05-04 BQ ops) recovered 44.7M rows / +23 hospitals.
**605.7M rows / 158 ambiguous EIN-only URLs / 11K skipped CSV blobs remain.**

This doc tracks the remaining coverage work in priority order.

## Checklist (in execution order)

- [ ] **1. NPPES-based EIN/slug → NPI resolver**
  - Source: `bigquery-public-data.nppes.npi_raw` (1.89M organizational NPIs, last updated 2026-02-09)
  - For each ambiguous EIN-only URL: extract filename slug, fuzzy-match against
    `provider_organization_name_legal_business_name` filtered to hospital
    taxonomy codes (`28*` series).
  - Backfill `hospital_charges.hospital_npi` for matches above confidence threshold.
  - Backfill `mrf_archive_index.hospital_npi` for the same URL set.
  - Estimated unlock: up to 158 URLs × ~3M rows/URL = ~440M rows.
  - Risk: bad matches assign wrong NPI to charges → false-flag dispute letters.
    Mitigation: high score threshold + manual review of low-confidence matches.

- [ ] **2. Postmortem #1 — scrape-time content validation (root fix)**
  - Modify `pipeline/scrape_hospital_mrfs.py` to reject responses by Content-Type
    + first-byte sniff *before* writing to staging/archive.
  - Reject: HTML, PDF, redirect chains ending at non-hospital domains.
  - Accept: JSON (`{` / `[` / BOM-prefixed), CSV, ZIP, XLSX.
  - Without this, the next scheduled scrape (Aug 1) re-pollutes the archive
    with garbage, undoing the BQ-side `skipped` reclassifications.
  - Estimated work: ~80 LOC + tests.

- [ ] **3. Postmortem #2 — parser pulls work from `mrf_archive_index`, not bucket walk**
  - Modify `pipeline/parse_hospital_mrfs.py` `main()` to query
    `SELECT gcs_uri FROM mrf_archive_index WHERE parse_status = 'pending'`
    and process those blobs directly.
  - When staging blob is missing, fall back to reading from
    `mrf-archive-clarobill-prd` (immutable copy still has the bytes).
  - Without this, the 2,583 rows reset-to-pending (NULL-NPI parsed cohort)
    can't actually retry — staging blobs are deleted post-parse.
  - Estimated work: ~120 LOC + tests + idempotency check.

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
