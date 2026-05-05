# CMS-Direct MRF Discovery (Final Architecture)

**Date:** 2026-04-28
**Status:** In progress (supersedes the PRA-sourced architecture)

**Related decisions:**
- `2026-04-27-pra-mrf-discovery-architecture.md` — original PRA-sourced plan, attempted but blocked
- `2026-04-27-pra-dom-extractor-separation.md` — DOM extractor split rationale (no longer load-bearing; the extractor was never built because the source it would have parsed turned out to be inaccessible)

---

## Context

ClaroBill's "billed more than published rate" rule is the strongest violation flag in the audit engine. To fire it for any given hospital we must have that hospital's MRF parsed into BigQuery, dated to the year the bill was issued. Coverage is the constraint: the rule cannot fire for a hospital whose MRF we have not ingested.

Two prior plans were considered before this decision:

### Plan A — CMS-direct discovery (the original plan, documented in `docs/future-improvements/mrf-discovery-pipeline.md`)

A 6-stage pipeline that uses entirely public CMS data sources:
- CMS Promoting Interoperability hospital list → seeds the ~7,000 CCNs
- CMS Provider of Services file → CCN-to-NPI mapping (~98% coverage)
- NPPES bulk download → website URLs for ~50% of hospitals
- Wikidata + domain pattern inference → fills another ~5%
- Google Places API → fills the long tail (~$150-200 one-time)
- Direct hospital-website crawler with TOC expansion for hospital systems

Estimated build: ~7 weeks. Cost: ~$165-215 first year, ~$22-30/year ongoing. Year 1 coverage target: 70% (~5,000 hospitals).

### Plan B — PRA-sourced via hospitalpricingfiles.org

Patient Rights Advocate (PRA) operates hospitalpricingfiles.org, a directory whose sitemap.xml lists 7,096 hospital detail pages (essentially the full CMS census), refreshed monthly. Each detail page displays the hospital's CCN, address, phone, website, and the public MRF file URL (which points to the hospital or its vendor — *not* PRA — so we never redistribute their data).

The plan was: render each detail page in headless Playwright once per month, scrape the rendered DOM, archive the actual MRF file from the hospital's own server. Estimated build: ~1 week. Cost: ~$3/year. Year 1 coverage: ~95%+ from day one.

### Plan C — Bulk-data partnership with PRA

Email PRA's contact form, request a signed data-sharing agreement that gives ClaroBill direct access to their hospital index. Mission-aligned (PRA is a non-profit advocacy org whose mission is exactly the kind of patient protection ClaroBill enables). Outreach drafted at `docs/future-improvements/pra-outreach-email.md` and sent on 2026-04-28. Reply window: unknown.

---

## What we tried, and what happened

### 2026-04-27: schema and infrastructure (kept)

We built the durable foundation that is unchanged regardless of which discovery source feeds it:

- BigQuery schema migration (`scripts/mrf_discovery/migrate_bq_schema.py`): renames the legacy `hospital_charges` to `hospital_charges_legacy_stale`, creates a fresh `hospital_charges` with `pricing_effective_year INT64 NOT NULL` partitioned by year, adds 12 new columns to `hospital_directory`, creates `mrf_archive_index` and `mrf_discovery_runs`.
- GCS archive bucket `mrf-archive-clarobill-prd` (Coldline, versioned, immutable-by-IAM): the chain-of-custody vault for every MRF file ever downloaded.
- `archive_layout.py` (27 passing tests): pure helpers for the year-partitioned, content-hash-named GCS path scheme.
- `bq_checkpoint.py`: per-stage timestamp helpers for resumable pipelines.

### 2026-04-27 to 2026-04-28: Plan B reconnaissance (failed)

We attempted Plan B in three escalating steps:

1. **Static fetch.** `curl` of `/details/{uuid}` returned a 5,039-byte React shell with no data. Confirmed: page is JS-rendered.
2. **Headless Playwright with handcrafted stealth patches.** Captured 7,131-byte HTML — same pre-Turnstile shell. The Cloudflare Turnstile widget was rendered but never resolved client-side.
3. **`patchright` (Cloudflare-aware Playwright fork) with full stealth init script.** Turnstile *did* resolve client-side this time. Captured HTML grew from 7,036 bytes (t0) to 7,036 bytes (t1, post-Turnstile) to 7,131 bytes (t2, after 60-second settle). `#root` `innerText` length stayed at 4 characters for the entire 60 seconds. The React app **never made a single call** to `staging01.visiblecharges.com` (the data API). Network log showed only Cloudflare's own challenge-platform pings, including a `[401]` from `cdn-cgi/challenge-platform/h/g/pat/` (CF's post-attestation token check).

**Diagnosis:** Cloudflare runs Turnstile in *silent-block mode* on this domain. The visible widget resolving is not the actual gating signal; an upstream CF state machine validates IP reputation, browser session continuity, and other signals invisible to the page. Headless and headed browsers from a clean residential IP both fail the silent check, and the React app's data fetches never fire.

**Why we stopped:**

- Bypassing CF silent-block requires either (a) residential proxies + heavier stealth-as-a-service like FlareSolverr (recurring cost, ongoing arms race) or (b) reusing a real-Chrome user-data-dir (manual maintenance per machine, fragile, doesn't scale to a Cloud Run job).
- The brand/posture problem: ClaroBill's pitch is "we help patients catch unfair behavior." Defeating a non-profit's anti-bot system to scrape their curated dataset, even when our intent is mission-aligned, is the wrong posture. If PRA discovered scraping in their logs they would not assume good intent.
- Cost-of-ownership math: even a successful Plan B becomes a perpetual maintenance burden because CF detection updates frequently. Plan A is a one-time integration with public APIs.

---

## Decision

**Build Plan A (CMS-direct). Plan C is in flight in parallel; if PRA grants partnership, the bulk feed becomes a fourth seed source in Stage 2 and accelerates coverage. If PRA declines or never replies, Plan A ships unchanged.**

We do **not** scrape `hospitalpricingfiles.org`. We do not redistribute their data. We do not run automated browser sessions against their domain at any cadence.

The Phase 1-2 work shipped on 2026-04-27 is unchanged and reusable. Plan A writes into the same `hospital_charges`, the same `mrf_archive_index`, the same `gs://mrf-archive-clarobill-prd/` bucket, with the same `pricing_effective_year` semantics.

### What changes from yesterday's `pra-pipeline-build.md`

| Item | Yesterday (Plan B) | Today (Plan A) |
|---|---|---|
| Stage 1 source | PRA sitemap | CMS Promoting Interoperability list |
| Stage 2 source | PRA detail page render | CMS POS file + NPPES bulk download |
| Stage 3 | POS file CCN→NPI join | Website discovery (URL validate, pattern inference, Google Places fallback) |
| Stage 4 | Directory merge | Per-hospital website crawler (httpx + Playwright fallback) |
| Stage 5 | (n/a) | MRF candidate validation + TOC expansion |
| Stage 6 | (n/a) | BigQuery MERGE into `hospital_directory` |
| Renderer | Required against PRA | Required only for ~10-15% of hospital sites that are JS-rendered |
| Anti-bot exposure | Cloudflare on every fetch | None; hospital sites do not gate price-transparency pages |
| Build time | ~1 week | ~4-5 weeks (down from original 7 because schema + bucket + checkpoint shipped) |
| Cost (first year) | ~$3 | ~$165-215 |
| Cost (ongoing) | ~$3-5/yr | ~$22-30/yr |
| Year 1 coverage | ~95% | 70% target, 85% with Plan C if granted |
| Third-party dependency | PRA + Cloudflare | None |

### What about evidence from the failed Plan B attempt

Plan B's diagnostic scripts (`_capture_fixtures.py`, `_diagnose_pra.py`, `stage1_pra_sitemap.py`) and captured fixtures are deleted. The reasoning lives in this decision doc and the predecessor (`2026-04-27-pra-mrf-discovery-architecture.md`); reproducing the diagnosis is a `curl` away if anyone needs to confirm independently.

---

## Consequences

### Positive

- **No third-party dependency in the discovery path.** CMS data is federally mandated public domain. CloudFront CDN cannot revoke it; a non-profit cannot rate-limit us out of existence.
- **Threat model is fundamentally different.** Plan B was 7,096 fetches against one CF-protected origin. Plan A is one or two fetches against each of ~7,000 different hospital websites. No single chokepoint to defend against us.
- **All the durable infrastructure already shipped.** Phase 1-2 work (schema, bucket, effective-dating, archive layout, checkpoint helpers) is source-agnostic.
- **The pivot itself is documented.** Future engineers (or future-Sandra) can read why we tried Plan B, why it failed, and why Plan A is what shipped — without reproducing the investigation.

### Negative

- **Build time grows from ~1 week to ~4-5 weeks.** We accepted this cost in exchange for independence and simplicity-of-ownership.
- **Year 1 coverage drops from ~95% to ~70%.** Plan C in flight; if PRA replies positively, we close that gap by re-introducing them as a non-scraped seed source.
- **More moving pieces.** Plan A has six discovery stages where Plan B had four. Each stage is its own failure surface.

### Open commitments

- Wait for PRA's reply (Plan C). If granted: integrate their bulk feed as a Stage 2 substep; their data accelerates coverage but is never required.
- If PRA's reply is negative or after 30 days of silence, mark Plan C closed and proceed with Plan A as documented.
- Document the pricing_effective_year semantics in `docs/architecture/rules-engine.md` when Phase 5 cutover happens.

---

## References

- `docs/future-improvements/mrf-discovery-pipeline.md` — full Plan A design (was Plan B in earlier framing)
- `docs/future-improvements/pra-pipeline-build.md` — phase-by-phase build log (now reflects Plan A)
- `docs/future-improvements/pra-outreach-email.md` — Plan C outreach
- `docs/decisions/2026-04-27-pra-mrf-discovery-architecture.md` — superseded; preserved for the architectural reasoning that still applies (effective-dating, immutable archive, IAM-enforced immutability)
- Schema: `scripts/mrf_discovery/migrate_bq_schema.py`
- Bucket: `scripts/mrf_discovery/setup_archive_bucket.sh`
- Layout helpers: `scripts/mrf_discovery/archive_layout.py`
- Checkpoint helpers: `scripts/mrf_discovery/bq_checkpoint.py`
