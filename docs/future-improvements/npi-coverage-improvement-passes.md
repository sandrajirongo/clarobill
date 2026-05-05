# NPI Coverage Improvement — Pass 2B and Pass 2C (Deferred)

**Status:** Deferred. Re-evaluate after Stage 3 (website discovery) lands.
**Trigger to revisit:** If Phase 4 parser-driven NPI backfill leaves > 30% of `hospital_directory` rows with NULL `hospital_npi`.

---

## Current state (2026-04-28)

After Stage 2B Pass 1 (`stage2_npi_registry.py`) + Pass 2A (`stage2_npi_registry_pass2.py`), 6,603 of 13,833 hospitals have a resolved NPI. The remaining 7,230 are unmatched.

The decision was to **accept 47.7% and move on to Stage 3**, because the Phase 4 parser will backfill NPI authoritatively from MRF JSON root metadata for every hospital whose MRF parses successfully. The expected coverage trajectory:

- After Stage 2B today: 6,603 / 13,833 NPIs (47.7%) via name-matching
- After Phase 4 parser: likely 11,000+ / 13,833 (~80%) via authoritative MRF metadata
- Permanent NPI gap: ~2,000-3,000 hospitals whose MRF doesn't parse or doesn't contain NPI metadata

If Phase 4 leaves the gap larger than expected, two follow-up passes can be implemented to close it.

---

## Pass 2B — Address-based lookup

**Premise:** Match by physical address rather than name. NPPES API supports searching by city + state + street address.

**Strategy:**
For each unmatched CCN with a known address (we have it from POS):
1. Query NPPES with `city + state + address_purpose=LOCATION` and the street address as a substring match
2. Filter results to hospital taxonomies (`282*`, `283*`, `281*`, `273*`)
3. Accept matches where the street address has high token overlap with our stored address

**Why it should help:**
Hospitals occasionally rename or rebrand but rarely move buildings. CMS keeps the address consistent across PI list and POS file. NPPES is required to keep the LOCATION address accurate. Address overlap is a higher-confidence signal than name overlap.

**Why we didn't do it in this round:**
The NppesClient currently doesn't expose address-based queries. Adding it requires:
1. Extending `NppesClient.lookup` to accept an `address` parameter (or a separate `lookup_by_address` method)
2. Building an address-tokenization helper (handle "St" vs "Street", PO Box rejection, suite/floor stripping)
3. Adding a new scoring mode in `_select_best` that weights address-token-overlap

**Estimated impact:**
- Engineering: ~30 min for the basic version
- Runtime: ~50 min for 7,230 hospitals at 5 req/s
- Recovery: estimate 1,000-2,000 additional NPIs (15-30% of unmatched)
- Cumulative coverage: 7,600-8,600 / 13,833 (~55-62%)

---

## Pass 2C — Broader pull + client-side fuzzy match

**Premise:** Don't trust NPPES's server-side `organization_name` index. Pull *every* hospital-taxonomy NPI in (city, state) and run client-side fuzzy match using `difflib.SequenceMatcher` against our hospital_name.

**Strategy:**
For each unmatched CCN:
1. Query NPPES by `city + state + taxonomy_description=Hospital` (broad pull)
2. Get up to 200 results in that city
3. Client-side: SequenceMatcher.ratio between each result's organization_name (and each of its `other_names`) and our hospital_name
4. Accept the highest-scoring match if ratio ≥ 0.75 AND city matches AND taxonomy is hospital-class

**Why it should help:**
NPPES's server-side name search is fuzzy but follows internal rules we can't predict. Client-side matching with full visibility into all hospital NPIs in a city catches matches the server-side search filters out due to its own opaque heuristics. We also get to compare against `other_names` (DBAs, trade names) which the basic API call doesn't search.

**Why we didn't do it in this round:**
1. ~3× more API calls than Pass 1+2A combined (one query per (city, state) for every unmatched hospital, with a 200-row pagination limit)
2. Client-side fuzzy matching at this scale takes ~2-3× longer in Python than network I/O
3. Higher false-positive risk because fuzzy thresholds are inherently softer

**Estimated impact:**
- Engineering: ~1 hour
- Runtime: ~2 hours for 7,230 hospitals
- Recovery: estimate 2,000-3,000 additional NPIs (30-40% of unmatched)
- Cumulative coverage: 8,600-9,600 / 13,833 (~62-69%)
- False-positive risk: 1-3% (mitigation: require taxonomy-AND-city scoring before accepting)

---

## RESOLUTION (2026-04-29): Pass 2B and 2C are closed — not needed

Stage 3 landed on 2026-04-29 with **83.3% website coverage** (11,525 / 13,833
hospitals confirmed websites across Tiers 1+2+3). Of the Tier 3 paid sweep,
6,616 hospitals got a website — those will all feed Phase 4's parser, which
backfills NPI authoritatively from each MRF's JSON root.

**Projected post-Phase-4 NPI coverage:**

| Source | NPI count | Notes |
|---|---|---|
| Stage 2B Pass 1 + 2A | 6,603 | name-match against NPPES API |
| Phase 4 parser backfill | ~5,600 | estimated 85% of the 6,616 Stage 3 hospitals will have parseable MRFs with NPI metadata |
| **Combined post-Phase-4** | **~12,200 / 13,833 = ~88%** | |

The gap (~12% / ~1,600 hospitals) is below the 30% threshold that would
trigger Pass 2B implementation. **Pass 2B and 2C are formally closed.**

Reasoning recorded for future revisit:
- The original 47.7% Stage 2B figure looked alarming, but it was the wrong
  baseline. Most of the unmatched hospitals were ones we'd never have built
  audits for anyway (no website → no MRF → no `hospital_charges` row → no
  rule fires regardless of NPI).
- Stage 3's website coverage closely tracks Phase 4's NPI-backfill ceiling.
  Hospitals without a website never become NPI-mappable via parser; they
  also never become rules-engine targets. Two unrelated discovery problems
  collapse into one.
- The 1,600-hospital permanent gap is bound to the long-tail-of-the-long-tail.
  Their absence from `hospital_directory` produces a NULL-NPI skip in the
  rules engine — correct behavior, no false-flag.

If the post-Phase-4 NPI-missing rate ends up higher than projected (>30%),
the original Pass 2B/2C plans below remain on the shelf for re-implementation.
Otherwise: leave them.

---

## Re-evaluation triggers (original — kept for completeness)

This document was created on 2026-04-28 with the assumption that Phase 4 (the
parser) would backfill NPI authoritatively from MRF JSON root metadata, so the
47.7% Stage 2B coverage would naturally rise to ~80%+ once Phase 4 ran.

Sandra has explicitly asked to **re-evaluate Pass 2B and 2C immediately after
Stage 3 (website discovery) lands**, before Phase 4. Stage 3 is the next stage
to ship; re-evaluation timing:

1. After Stage 3 finishes, query `mrf_discovery_checkpoint` to see how the
   7,230 NPI-less hospitals fared on website discovery:
   - If most still have `website_found_at IS NULL`, those hospitals will
     never contribute an MRF for Phase 4 to parse, so the parser cannot
     backfill their NPI either. In that case, Pass 2B/2C is the only path
     to NPI coverage for them.
   - If most got a website, they will likely have an MRF in Phase 4, and
     the parser will backfill their NPI from the JSON root — Pass 2B/2C
     becomes redundant for them.
2. Compute the audit-impact projection: of the 7,230 NPI-less hospitals,
   how many process bills via ClaroBill in a typical month? Bills against
   hospitals without NPI hit the NULL-NPI rule-skip path, which means the
   "billed > MRF gross charge" rule cannot fire for that bill.
3. Decide: if the projected audit-impact gap is significant, implement
   Pass 2B. If marginal, defer.

## Decision rule (long-term)

Even if the post-Stage-3 evaluation defers Pass 2B/2C, run them later if
**Phase 4 parser-driven backfill leaves > 30% of `hospital_directory` rows
with NULL `hospital_npi`**.

Specifically, after Phase 4 lands:

```sql
SELECT
  COUNTIF(hospital_npi IS NULL) AS without_npi,
  COUNT(*) AS total,
  ROUND(COUNTIF(hospital_npi IS NULL) / COUNT(*) * 100, 1) AS pct_missing
FROM `clarobill-prd.hospital_prices.hospital_directory`
```

If `pct_missing > 30`: implement Pass 2B first (lower effort, lower false-positive risk). If still > 20% after 2B: implement 2C.

If `pct_missing <= 30`: accept and move on. The remaining gap is a known limitation; rules engine handles NPI-less rows by skipping NPI-keyed rules (correct behavior — no false flags).

---

## What this implies for the rules engine

`rules_engine.py:804-849` (the "billed > MRF gross charge" rule) reads `hospital_charges` keyed by `hospital_npi`. Hospitals with NULL `hospital_npi` in the directory mean their bills can't trigger that rule.

For an audit on a bill:
1. Engine extracts `hospital_name` from the bill (via OCR + verification)
2. Engine looks up `hospital_directory` by name + state to find `hospital_npi`
3. If `hospital_npi` is NULL or no match: the rule is **skipped silently** — better than guessing
4. The rest of the rules engine runs unchanged

Skipping is correct. False positives in dispute letters are the worst class of defect; missing real overcharges is a smaller harm than asserting a fake one.

---

*Document created: 2026-04-28*
*Owner: ClaroBill Engineering*
