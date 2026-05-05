# PRA-Sourced MRF Discovery Architecture

**Date:** 2026-04-27
**Status:** SUPERSEDED-BY [2026-04-28-cms-direct-mrf-discovery.md](2026-04-28-cms-direct-mrf-discovery.md). Plan B's Cloudflare CDN block defeated the scrape; the team pivoted to CMS-direct discovery the next day.

---

## Context

ClaroBill's strongest violation flag is "hospital billed more than its own published rate." That rule depends on having a complete, fresh, correctly-dated database of hospital chargemaster data — the Machine-Readable Files (MRFs) that CMS Hospital Price Transparency rules require all Medicare-certified hospitals to publish annually.

Before this decision, ClaroBill sourced ~3,119 hospital MRF URLs from Payerset (a third-party GitBook directory) and loaded their parsed contents into a single flat `hospital_charges` BigQuery table. That setup had four serious defects:

1. **Coverage gap.** Payerset covers ~45% of the ~7,000 CMS-registered hospitals. For 55% of hospitals our highest-value rule could never fire.
2. **Staleness.** Payerset URLs go weeks to months stale. When a hospital moves its MRF to a new URL, our scraper 404s indefinitely.
3. **Third-party dependency.** Payerset can disappear, paywall, or throttle without notice. The product's biggest moat sat on an external commercial vendor's free tier.
4. **No effective dating.** The existing `hospital_charges` rows had no `pricing_effective_year` column, so a 2026 bill could be compared to a chargemaster of unknown vintage. Hospitals re-negotiate rates every January per CMS requirement; comparing across years produces false-positive overcharge claims. **This is a correctness defect, not just a freshness issue** — and it is the worst class of defect for a tool that writes dispute letters on a patient's behalf.

A first-party CMS-direct discovery pipeline (Plan B, documented at `docs/future_improvements/mrf-discovery-pipeline.md`) was scoped to fix coverage and dependency. It was estimated at ~7 engineering weeks and required NPPES bulk downloads, Wikidata SPARQL, Google Places API ($150-200/yr), an asyncio Playwright crawler, robots.txt management, and TOC-expansion logic for hospital systems.

During that scoping, Sandra discovered hospitalpricingfiles.org, run by Patient Rights Advocate (PRA), a non-profit advocacy organization. Their sitemap.xml lists exactly 7,096 hospital detail pages — essentially the full CMS census — refreshed monthly (`changefreq: monthly`, all entries `lastmod: 2026-04-15` at investigation time).

---

## Decision

ClaroBill builds a **PRA-sourced MRF discovery pipeline** as the primary data path, with the original CMS-direct plan retained as a documented fallback if PRA disappears or rejects partnership.

### Five core architectural choices

#### 1. PRA is a directory service, never a redistributed data source

We render each `/details/{uuid}` page in headless Playwright once per month, scrape the rendered DOM for the hospital's CCN, address, phone, website, and MRF file URL, and **download the actual MRF file directly from the hospital or its vendor (machine-readable-files.com, Turquoise, Ascension, etc.)**. The MRF URL on a PRA detail page points to the hospital's own infrastructure, not PRA's. We never cache PRA's data; we use them as a federated index of public CMS-mandated URLs.

This is significant because:
- It avoids any redistribution concern (we never re-host their dataset).
- Their bandwidth cost from us is one HTML page render per hospital per month — ~7,096 page views, well within normal traffic.
- If PRA shuts down, we already have the actual MRF files archived; we only lose the *discovery* path for new hospitals.

#### 2. Effective-dating is a NOT NULL column, not a metadata afterthought

The new `hospital_charges` table has `pricing_effective_year INT64 NOT NULL`. New rows cannot be inserted without a vintage. The table is `RANGE_BUCKET` partitioned by `pricing_effective_year` (2024-2034) and clustered by `(hospital_npi, code)`.

The rules engine joins bills to charges by `pricing_effective_year = YEAR(bill.service_date)` with fallback to the nearest prior year (never future-dated). If no MRF exists for a hospital at a given date, the rule is **skipped**, not assumed. Skipping is better than guessing — the cost of a false-flag overcharge in a dispute letter is much higher than the cost of a missed flag.

#### 3. The legacy table is renamed, not migrated

`hospital_charges` is renamed to `hospital_charges_legacy_stale` rather than backfilled with synthetic effective years. The legacy rows have unknown vintage; assigning them a year would be lying to the rules engine. The rename takes them out of the rules-engine read path immediately while preserving them for forensics. They are dropped via a follow-up migration ~6 months after Phase 6 cutover.

We do not start the historical record before 2026. Sandra plans to ask PRA for historical data (2024, 2025) via outreach; if granted we backfill, otherwise we accept that pre-2026 bills audit against current-year rates with a confidence note.

#### 4. GCS archive bucket is an immutable evidence vault, not working storage

A new bucket `gs://mrf-archive-clarobill-prd` (Coldline storage class, US multi-region) holds every MRF file we have ever downloaded, partitioned by pricing year:

```
gs://mrf-archive-clarobill-prd/
  pricing-year={year}/
    {hospital_npi-or-pra_uuid}/
      {sha256_first16}.{ext}              # raw MRF, immutable
      {sha256_first16}.meta.json          # provenance: source_url, scraped_at, etag, last-modified
```

Three guarantees enforced by configuration, not convention:

- **Immutability via IAM, not policy text.** `clarobill-pipeline-sa` gets `roles/storage.objectCreator` and `roles/storage.objectViewer` — but **not** `objectAdmin`. The absence of `storage.objects.delete` means a bug, a compromised key, or an accidental rm cannot destroy archived evidence. To delete anything, a human with bucketAdmin has to do it explicitly.
- **Deduplication via filename, not metadata.** sha256 is part of the object name, so two writes of identical content produce the same path and the second is a no-op. No HEAD-then-decide round trips.
- **Audit trail via versioning.** Object versioning is enabled as belt-and-suspenders. Lifecycle rule deletes noncurrent versions only after 90 days and only when ≥5 newer versions exist; current versions never expire.

This shape exists because if a patient ever sues a hospital using a ClaroBill audit and we get subpoenaed for the MRF that was in force on a given date, "give me everything under `pricing-year=2026/{npi}/`" is a one-line answer. Time-partitioned + immutable + content-hashed = chain of custody.

#### 5. The PRA scraper extracts in two layers: render and parse

The Playwright stage (`stage2_pra_detail_extract.py`) is responsible only for getting rendered HTML out of the JavaScript SPA. The DOM-extraction logic — the CSS selectors that pull `name`, `address`, `ccn`, `mrf_url`, etc. out of that HTML — lives in a separate pure-Python module `pra_dom_extractor.py` that takes raw HTML in and returns a typed dict out.

Reasoning recorded in a separate decision: see `2026-04-27-pra-dom-extractor-separation.md`.

### Pipeline shape (six stages)

```
Monthly Cloud Run Job (1st of each month, ~6 hr wall clock)
  ├─ Stage 1: stage1_pra_sitemap.py
  │            Fetch hospitalpricingfiles.org/sitemap.xml -> 7,096 UUIDs
  │            Seed pra_facility_index_inflight (one row per UUID, run-id-keyed)
  │
  ├─ Stage 2: stage2_pra_detail_extract.py
  │            For each pending UUID, render /details/{uuid} in Playwright.
  │            Pass rendered HTML to pra_dom_extractor.extract().
  │            Write hospital fields back to inflight via mark_complete().
  │            Rate limit: 0.5 req/s (PRA limit is 100/180s; we leave headroom).
  │            User-Agent: ClaroBill-MRFDiscovery/1.0 (...; contact@clarobill.com)
  │
  ├─ Stage 3: stage3_pos_join.py
  │            Left-join CCN -> NPI from CMS Provider of Services file (free).
  │            ~98% NPI coverage expected.
  │
  ├─ Stage 4: stage4_directory_merge.py
  │            MERGE inflight rows into hospital_directory on CCN.
  │            APPEND a snapshot to pra_facility_index (audit trail, immutable).
  │            Write summary row to pra_discovery_runs.
  │
  ├─ Phase 4 archiver: existing pipeline/scrape_hospital_mrfs.py rewritten
  │            For each hospital with mrf_url, HEAD to detect change,
  │            stream-download to gs://mrf-archive-clarobill-prd/pricing-year=Y/...
  │            Insert mrf_archive_index row with parse_status='pending'.
  │
  └─ Phase 4 parser: existing pipeline/parse_hospital_mrfs.py rewritten
               Read mrf_archive_index WHERE parse_status='pending'.
               Parse with hospital_mrf_utils.iter_charges().
               Bulk-load to hospital_charges with pricing_effective_year populated.
               Update parse_status -> 'parsed'.
```

### What we are explicitly *not* doing

- **Not bypassing PRA's Cloudflare Turnstile.** Their JSON API is anti-bot-protected. Rendering the public detail page in Playwright respects their gate by solving it the same way a real user would.
- **Not scraping at API rates.** Their rate-limit header (`100;w=180`) is a posted policy. We target half that.
- **Not redistributing PRA data.** Even though MRF URLs are technically public, their curated index has compilation value to them as an organization. We use their index, never copy it.
- **Not effective-dating retroactively.** Pre-2026 bills audit against the earliest MRF we have; we never invent a vintage for legacy data.

---

## Consequences

### Positive

- **Engineering compression: 7 weeks → ~1 week.** PRA already solved the discovery problem we were going to spend Stages 2-4 of the original plan rebuilding (NPPES bulk + Wikidata + Google Places + crawler + TOC expansion).
- **Coverage compression: 70% Year 1 target → ~95%+ from day one.** PRA already lists ~7,096 hospitals.
- **Cost compression: $165-215 first-run + $22-30/yr → $3 first-run + $3-5/yr.** No paid APIs.
- **Correctness gain: false-positive overcharge claims become structurally impossible.** Effective dating is enforced at the table level.
- **Evidence chain: every audit citation is reproducible.** Year-partitioned, content-hashed, immutable archive means we can produce the exact MRF that was in force when a given bill was generated, years later.

### Negative

- **Single-vendor risk.** If PRA shuts down or rate-limits us out of existence, new-hospital discovery stops. Mitigation: the original CMS-direct plan stays documented as Plan B; existing archived MRFs continue to work.
- **Monthly latency for new hospitals.** A hospital that opens in February won't appear until March's PRA refresh. For a tool auditing already-issued bills, this is acceptable.
- **Browser-based scraping is heavier than API scraping.** Playwright + Chromium adds ~500MB to the discovery image. We isolate that cost with `Dockerfile.discovery` separate from the weekly scraper image.
- **Schema cutover risk.** Renaming `hospital_charges` and rewriting both the scraper and parser is a multi-step migration. We retain the renamed legacy table for ~6 months as rollback; the rules engine flip is a single config change.

### Open commitments

- Send the PRA outreach email (`docs/future_improvements/pra-outreach-email.md`) to ask for bulk historical data and a partnership relationship.
- Build Plan B (CMS-direct pipeline) only if PRA rejects partnership or disappears.
- Document the rules-engine effective-date semantics in `docs/rules-engine.md` at Phase 5.

---

## References

- `docs/future_improvements/pra-pipeline-build.md` — phase-by-phase build log
- `docs/future_improvements/mrf-discovery-pipeline.md` — Plan B (CMS-direct fallback)
- `docs/future_improvements/pra-outreach-email.md` — partnership outreach draft
- `docs/decisions/2026-04-27-pra-dom-extractor-separation.md` — extractor module split rationale
- Schema: `scripts/mrf_discovery/migrate_bq_schema.py`
- Bucket: `scripts/mrf_discovery/setup_archive_bucket.sh`
- Layout helpers: `scripts/mrf_discovery/archive_layout.py`
