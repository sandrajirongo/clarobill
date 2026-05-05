# Google Places API — Cost-Minimization Design for Stage 3 Tier 3

**Date:** 2026-04-28
**Status:** Designed (code pending)
**Decision authority:** Sandra Jirongo
**Constraint:** $450 hard budget ceiling per annual run.

---

## Why this doc exists

Stage 3 Tier 3 of the MRF discovery pipeline calls the Google Places API to resolve hospital websites for the long tail of hospitals that Tiers 1 and 2 (existing-URL validation, domain pattern inference) couldn't handle. Places is the **only paid service** in the entire ClaroBill data infrastructure. Mistakes here cost real money.

This document records every cost-control decision, why it was made, and the test gates a code change must pass before it touches a real API. It also defines the **post-Stage-3 checkpoint** that determines whether we proceed to Phase 4 or loop back for more coverage work.

---

## Context

### What Stage 3 Tier 3 does

For each hospital in `mrf_discovery_checkpoint` where:
- `website_found_at IS NULL` (Tier 1 didn't find a working URL)
- `hospital_website IS NULL` (no source has populated one)
- `hospital_name`, `state`, `city` all NOT NULL

call Places API to resolve the hospital's website, then write `hospital_website` and `website_source = 'google_places'` back to the checkpoint.

### Pricing context (Google Places API "New", 2026)

| SKU | Cost / 1,000 calls | When fired |
|---|---|---|
| Free tier monthly cap | $200/mo (covers ~3,100 cheap-search calls) | First N calls/month |
| Text Search (Essentials field mask) | $5 / 1,000 | One per hospital |
| Place Details (Enterprise — includes `websiteUri`) | $25 / 1,000 | One per confirmed match |

**Worst-case projected cost:** 7,000 hospitals × ($0.005 search + $0.025 details) = **$210** if every Search call returns exactly 1 result and every Details succeeds. Doubles to ~$420 if half the searches return 2+ candidates and we verify multiples (per Decision 4 below).

**$450 budget ceiling** has 7% headroom over worst-case; pipeline halts cleanly if exceeded.

---

## The six cost-control layers

### Layer 1 — Free upstream sources exhaust first

By the time a hospital reaches Tier 3, it has already failed:
- Stage 2B Pass 1+2A (NPPES Registry API, free) — resolves NPI but also returns address-validated identity
- Stage 2C (Wikidata SPARQL, free) — ~500 system-level websites
- Stage 3 Tier 1 (HEAD-validate any URL we already have, free)
- Stage 3 Tier 2 (domain pattern inference, free) — recovers ~3-5%

**Estimated input population to Tier 3: 5,500-7,000 hospitals** (out of 13,833).

### Layer 2 — Permanent GCS-backed cache

- **Working cache:** `gs://mrf-staging/places-api-cache.json` — read at start, written incrementally during run
- **Annual immutable snapshot:** `gs://mrf-archive-clarobill-prd/places-api-cache-snapshots/{year}.json` — written at end of run, never deleted
- **Cache key:** `f"{hospital_name}|{state}|{city}".upper()` — same shape as NPPES cache
- **Cache value:** `{"place_id": str | None, "website": str | None, "checked_at": iso8601, "verification_method": str}`

**Year 1 first run:** ~6,000 calls.
**Year 2+:** Only hospitals added by CMS since last year (typically 200-300/year per CMS) need new calls. Cumulative annual cost after Year 1 should be under $20.

### Layer 3 — Hard cost ceiling enforced by code

`--max-places-cost USD` flag, default $450.

Every call increments a running cost counter. Before each call, code checks:
```python
if running_cost + worst_case_next_call_cost > budget:
    halt_run_and_log()
```

Halt is clean: remaining hospitals get `error_stage = 'stage3_tier3_budget_exhausted'`, which a follow-up run can pick up. No partial state corruption.

### Layer 4 — Field masks (the largest cost lever)

Without a field mask, every Places call returns ~50 fields and bills at the highest-tier SKU. With narrow field masks:

- **Text Search:** `places.id,places.displayName.text` → Essentials SKU, $0.005/call (vs $0.032 default)
- **Place Details:** `id,websiteUri,formattedAddress` → Enterprise SKU, $0.025/call (vs $0.040 default)

A 6,000-hospital run with narrow masks costs ~$180. The same run with default masks costs ~$430+.

### Layer 5 — Pre-call validators reject bad inputs

A hospital does NOT generate a Tier 3 call if any of:
- `state IS NULL` (API requires state for narrow geographic search)
- `city IS NULL` (city is the disambiguator for hospital-name searches)
- `LENGTH(hospital_name) < 5` (e.g. "St" or "VA" alone — generates noise, not matches)
- `hospital_name` matches a **system-level name** we already have via Wikidata (e.g. "HCA Healthcare" — Tier 3 lookup would just re-find the system website, not the facility website)

These filters typically eliminate 5-10% of would-be calls.

### Layer 6 — Cost preview before any real call

`--cost-preview` mode runs the full pre-call validation logic against the checkpoint, counts how many hospitals *would* generate a call, multiplies by per-call cost, prints the projected USD, exits without making a single HTTP call.

```
Stage 3 Tier 3 cost preview (run_id=20260428T135512Z_b844d689):
  hospitals to process:        5,847
  pre-call rejections:           312
  expected text-search calls:  5,535
  expected details calls:      ~4,800 (estimated 87% of searches return 1 result)
  expected verification calls: ~735   (estimated 13% return 2+, max 3 per lookup)
  projected USD: $182.45
  budget ceiling: $450.00
  headroom:       $267.55
```

Sandra reviews this number BEFORE the production run. If it looks wrong, we fix the bug — not the wallet.

---

## Decisions Sandra signed off on (2026-04-28)

### Decision 1 — Budget ceiling: **$450**
Hard limit enforced by `--max-places-cost`. Worst-case projection is $420; $30 headroom for off-by-one or unexpected verification cost. The pipeline halts cleanly when crossed; remaining hospitals retry on next annual run.

### Decision 2 — Field mask split into Search (cheap) + Details (expensive)
Text Search field mask is narrow (`places.id,places.displayName.text`, Essentials SKU). Place Details only fires when Search returns exactly 1 candidate AND we still need the website URL. **Search-only calls cost $0.005; full lookups cost $0.030.** A failed search costs 6× less than a successful one — efficient against the long tail.

### Decision 3 — Multi-result verification (vs blanket skip)
**Sandra's preference: never blanket-skip ambiguous results.** When Text Search returns 2 or 3 candidates:
1. Fetch Place Details for **each** candidate (capped at 3 — "Memorial Hospital" returning 14 candidates won't burn 14× the budget; we cap at top 3 by Google's relevance ranking)
2. For each candidate's `websiteUri`, fetch the homepage HTML (HEAD or partial GET, free)
3. Verify the hospital name appears in the page `<title>` or first `<h1>` (case-insensitive substring match)
4. Pick the verified one. If multiple verify, pick the one whose `formattedAddress` city matches our checkpoint city.
5. If zero verify, record `website_source = 'places_ambiguous_no_verify'` — leave website NULL, log for manual review.

**Cost impact:** ambiguous lookups cost up to $0.080 each (1 search + 3 details). Estimated 13% of searches are ambiguous → ~750 hospitals × $0.080 = $60 total bump vs the single-result baseline. Worth it for accuracy.

### Decision 4 — Cache: permanent in working bucket + annual immutable snapshot
- Working cache (mutable): `gs://mrf-staging/places-api-cache.json`
- Year snapshots (immutable): `gs://mrf-archive-clarobill-prd/places-api-cache-snapshots/{year}.json`
- The annual discovery run reads the working cache, processes only hospitals not present in cache, updates the working cache, snapshots to the year-stamped immutable copy at run completion.
- This pattern is documented in `docs/operations/pipeline-runbook.md` under "Automation roadmap" and "Backup and historical-record policy."

### Decision 5 — API key managed via Secret Manager, not env var
- Key created on `clarobill-prd` (steps below)
- Stored in Secret Manager as `google-places-api-key`
- The pipeline service account (`clarobill-pipeline-sa`) gets `roles/secretmanager.secretAccessor` scoped to that secret only
- Code reads the secret at startup; never logs it; never writes it to disk
- Local dev can set `GOOGLE_PLACES_API_KEY` env var as a fallback (only used when not running in GCP)

---

## API key provisioning runbook

Sandra runs this **once**, before the first Stage 3 Tier 3 production run.

```bash
PROJECT="clarobill-prd"

# 1. Enable the Places API on the project
gcloud services enable places.googleapis.com --project "$PROJECT"

# 2. Create an API key with restrictions
KEY=$(gcloud alpha services api-keys create --display-name="ClaroBill Places API key" --api-target="service=places.googleapis.com"  --project "$PROJECT" --format="value(response.keyString)")
echo "Generated key (first 20 chars): ${KEY:0:20}..."

# 3. Store in Secret Manager
echo -n "$KEY" | gcloud secrets create google-places-api-key --replication-policy="automatic" --data-file=- --project "$PROJECT"

# 4. Grant pipeline SA access
gcloud secrets add-iam-policy-binding google-places-api-key --member="serviceAccount:clarobill-pipeline-sa@$PROJECT.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor" --project "$PROJECT"

# 5. Verify
gcloud secrets versions access latest --secret=google-places-api-key --project "$PROJECT" | head -c 20
echo " ... (key starts with the same prefix? if so, done)"
```

Cost of these provisioning steps: $0. Places API is enabled but not called yet.

---

## Test strategy — every code path proven locally before any real call

### Phase 1: Unit tests (no network, no cost) — must be green before merging

| Test | What it proves |
|---|---|
| `test_cost_calculator` | Cost-per-call math is correct; free-tier crossover handled; halts at exactly the right call number for any budget |
| `test_budget_enforcer` | Given budget $X and N simulated calls, halts at the right call. Edge: budget=0 makes 0 calls. Edge: $0.005 budget makes 1 search but blocks Details. |
| `test_cache_key_normalisation` | `"Mayo Clinic"|MN|"Rochester"` and `"mayo clinic"|MN|" rochester "` produce the same key |
| `test_pre_call_validator` | Rejects state=NULL, city=NULL, name<5 chars, system-level names |
| `test_field_mask_constants` | Field mask strings match Google's documented SKU boundaries (regression guard if Google renames the masks) |
| `test_cost_preview` | `cost_preview()` against a 100-row test checkpoint returns the right USD without making any HTTP calls |
| `test_verification_logic` | Multi-result verification: name appears in title or H1 → match; appears nowhere → reject; appears in both candidates → city tie-break |

### Phase 2: Integration tests against mock Places server (no real cost)

Use the `responses` library to mock Places API responses.

| Scenario | What we mock | Expected behavior |
|---|---|---|
| Happy path — single result | Text Search returns 1 place_id; Details returns websiteUri | Cache populated. Cost = $0.030. |
| Search miss | Text Search returns 0 results | No Details call. Cache: `place_id=None`. Cost = $0.005. |
| Details fails | Search OK, Details returns 404 | Cache: `place_id` preserved, website=None. Cost = $0.030. |
| Multi-result, all verify | Search returns 3 places; all 3 homepages have hospital name | First (most relevant) wins; logged. Cost = $0.080. |
| Multi-result, none verify | Search returns 3 places; none of the 3 homepages mention hospital name | website=None, source='places_ambiguous_no_verify'. Cost = $0.080. |
| Rate limit (429) | Mock returns 429 once, then 200 | Backoff and retry once; succeed. Cost = $0.030. |
| Cache hit | Pre-populate cache for "Mayo Clinic"/MN/Rochester | Second lookup returns from cache. 0 HTTP calls. |
| Budget exhausted mid-run | Budget=$0.030, 5 hospitals to look up | Halts after 1 successful lookup. Remaining 4 marked `error_stage = 'stage3_tier3_budget_exhausted'`. |

### Phase 3: ONE real live call (~$0.030)

After all unit + integration tests pass, run with `--limit 1` against a known hospital:
```bash
python3 scripts/mrf_discovery/stage3_website_discovery.py \
  --tier 3 \
  --limit 1 \
  --target-ccn 240008 \
  --project clarobill-prd
```

Expected:
- Single Text Search + Place Details call
- Cost incurred: ~$0.030
- Cache written
- BQ checkpoint updated

If the result matches what cost calculator predicted, we know the loop is sound.

### Phase 4: Production run with cost preview

```bash
# Preview first
python3 scripts/mrf_discovery/stage3_website_discovery.py \
  --tier 3 \
  --cost-preview \
  --project clarobill-prd

# Sandra reviews "$X projected" output. If reasonable, proceed:
python3 scripts/mrf_discovery/stage3_website_discovery.py \
  --tier 3 \
  --max-places-cost 450 \
  --project clarobill-prd
```

---

## Post-Stage-3 + Phase-4 coverage validation checkpoint

This is the explicit **decision gate** Sandra requested for re-evaluating Pass 2B/2C and overall pipeline coverage.

### When to run it
After Stage 3 (all 3 tiers) completes AND Phase 4 (effective-dated archiver + parser) lands and processes its first weekly batch.

### Queries to run

```sql
-- 1. Coverage breakdown by stage
SELECT
  COUNT(*)                                              AS total_in_run,
  COUNTIF(hospital_website IS NOT NULL)                 AS with_website,
  COUNTIF(hospital_npi IS NOT NULL)                     AS with_npi,
  COUNTIF(validated_mrf_urls IS NOT NULL)               AS with_validated_mrf,
  COUNTIF(bq_committed_at IS NOT NULL)                  AS committed_to_directory
FROM `clarobill-prd.hospital_prices.mrf_discovery_checkpoint`
WHERE run_id = '<latest>';

-- 2. NPI coverage post-Phase 4 backfill
SELECT
  COUNTIF(hospital_npi IS NULL) AS without_npi,
  COUNT(*) AS total,
  ROUND(COUNTIF(hospital_npi IS NULL) / COUNT(*) * 100, 1) AS pct_missing
FROM `clarobill-prd.hospital_prices.hospital_directory`;

-- 3. Website source attribution (cost validation)
SELECT website_source, COUNT(*) AS rows
FROM `clarobill-prd.hospital_prices.mrf_discovery_checkpoint`
WHERE run_id = '<latest>' AND hospital_website IS NOT NULL
GROUP BY website_source
ORDER BY rows DESC;

-- 4. Stage 3 Tier 3 cost reconciliation
SELECT notes
FROM `clarobill-prd.hospital_prices.mrf_discovery_runs`
WHERE run_id = '<latest>';
```

### Decision rules

| Coverage signal | Decision |
|---|---|
| `with_validated_mrf >= 70%` of total | Phase 4 launch validated. Proceed to Phase 5 (rules engine cutover). |
| `pct_missing` (NPI) `<= 30%` | Pass 2B/2C deferred indefinitely. Document and close. |
| `pct_missing` (NPI) > 30% but bills against NPI-less hospitals < 5% of monthly volume | Pass 2B/2C deferred. Audit-impact too low to justify cost. |
| `pct_missing` (NPI) > 30% AND audit-impact >= 5% | Implement Pass 2B (address-based). Re-evaluate after. |
| Stage 3 Tier 3 actual cost > $450 budget | Bug in cost-tracking. Halt new runs until root-caused. |
| Website source breakdown shows `places_ambiguous_no_verify` > 10% of all Places matches | Manual curation queue: top 100 ambiguous hospitals by bed count, resolve by hand. |

This decision gate gets walked through with Sandra after Stage 3 + Phase 4. Findings are documented as an addendum to this doc.

---

## Why each decision was made (process record)

### Why budget ceiling, not unlimited
**Risk:** A bug in pre-call filtering or cache loading could cause every hospital to query Places on every run, including the ~6,400 that already had Tier 1 URLs. Without a ceiling, that's a $200+ surprise. With $450 ceiling, worst-case loss is bounded.

### Why field-mask split, not unified call
**Cost arithmetic:** A unified Text Search with `websiteUri` in the field mask costs $0.040/call (Enterprise SKU). A split Search ($0.005) + Details ($0.025) costs $0.030 when both fire, $0.005 when Search misses. Average for our use case: ~25% Search-misses → $0.024/call vs $0.040/call. Saves ~$100 across 6,000 hospitals.

### Why verify multi-result rather than skip
**Sandra's preference, recorded 2026-04-28:** "lets not waste any calls, if the search returns 2 website urls lets check both and make sure we have the accurate information." Translation: ambiguous lookups are valuable signal, not waste. The verification (homepage HEAD + name-in-title check) is free; the extra Details calls are cheap; the accuracy gain is worth more than the marginal cost.

### Why cache forever
**Cost arithmetic:** ~6,000 hospitals don't change websites year-over-year for the most part. CMS adds ~200-300 new hospitals/year. Annual re-validation of all 6,000 would cost ~$180/year forever; cache-then-only-call-new-hospitals costs ~$10-20/year.

### Why immutable annual snapshots
**Operational principle (`feedback_production_grade_default.md`):** Every download we make should be archivable for backward-compatibility audits. Year-stamped snapshots mean "what did we believe in 2026?" is answerable in 2030.

### Why Secret Manager, not env var
**Security:** Env vars leak via process listings, accidental log lines, error stack traces. Secret Manager has audit logs, IAM-scoped access, and rotation support. The code-cost difference is negligible (one extra API call at startup).

### Why narrow vs default field mask
**Cost arithmetic above** + Google explicitly documents the narrow masks as the "Essentials SKU" rate. We're using their advertised cost-saving feature, not exploiting a loophole.

### Why Google Places, not Mapbox or OpenStreetMap (evaluated 2026-04-28)
Sandra raised: "Mapbox has a free tier up to 100,000 calls; would that work instead?"

**Pricing comparison:**

| Service | Free tier | Cost above tier |
|---|---|---|
| Mapbox Geocoding API | 100,000 req/mo | $0.75 / 1,000 |
| Google Places Text Search | $200/mo credit ≈ ~6,250 Essentials calls | $0.005-0.032 / call |
| OSM Nominatim | unlimited (rate-limited 1 req/s) | free, but TOS requires bulk users to self-host |

For our annual workload (~5,500-7,000 calls), Mapbox is genuinely free. But:

**Field coverage is the deal-breaker.** Mapbox Geocoding v5 returns coordinates, formatted address, POI categories — **NOT website URLs**. The newer Mapbox Search API has a `metadata` field that *can* contain a website, but population is roughly ~10% for hospital POIs vs Google's ~80-90%. Mapbox would resolve the hospital's identity but not solve our actual problem (getting the website URL for Stage 4 to crawl).

OpenStreetMap Nominatim has POI tags including `website=*`, but coverage is patchy (especially for smaller hospitals) and bulk usage requires self-hosting per their tile usage policy.

**Decision:** Stick with Google Places. Mapbox/OSM kept as future cost-optimisation paths in two scenarios:
1. **Verification, not discovery.** Use Mapbox/OSM (free) to confirm a Google-resolved hospital's lat/lng matches our address-on-file, instead of paying for a second Google Place Details call.
2. **Last-resort fallback** if Google ever sunsets the free $200/mo credit or raises Essentials SKU pricing materially.

Both are deferred until measured spend justifies the engineering work. Filed at `docs/future-improvements/places-api-cost-optimisation.md` (to be created if we revisit).

---

## What this doc commits us to

When Stage 3 Tier 3 ships, the following must all be true:
- [ ] All Phase 1 unit tests pass
- [ ] All Phase 2 integration tests pass against mock Places server
- [ ] Phase 3 single-call live test produced a $0.030 charge with the expected NPI, website, and cache state
- [ ] `--cost-preview` produced a projection that Sandra reviewed and approved
- [ ] API key is in Secret Manager, not env var, not log lines
- [ ] Pipeline halts cleanly at $450 ceiling — verified by integration test
- [ ] Annual snapshot bucket path is documented in `docs/operations/pipeline-runbook.md`

If any of these isn't green, the pipeline doesn't run against production data.

---

*Document created: 2026-04-28*
*Owner: ClaroBill Engineering*
*Re-evaluation trigger: post-Stage-3 + Phase-4 coverage checkpoint (queries above)*
