# Hospital MRF Discovery Pipeline
## First-Party Price Transparency Data at Scale

**Status:** ARCHIVED 2026-05-05 — original design proposal. Implementation shipped per [decisions/2026-04-28-cms-direct-mrf-discovery.md](../decisions/2026-04-28-cms-direct-mrf-discovery.md) and now operates per [operations/pipeline-runbook.md](../operations/pipeline-runbook.md).

**Status:** Planned — build after Phase 4 product launch  
**Run cadence:** Once per year (January 15)  
**Target coverage:** 98%+ of ~7,000 CMS-registered hospitals  
**Current coverage (Payerset):** ~3,119 hospitals (~45%), URLs go stale within weeks  

---

## Table of Contents

1. [Why Build This](#1-why-build-this)
2. [Data Sources](#2-data-sources)
3. [Architecture Overview](#3-architecture-overview)
4. [BigQuery Schema](#4-bigquery-schema)
5. [Stage-by-Stage Design](#5-stage-by-stage-design)
6. [The Crawler (Stage 4)](#6-the-crawler-stage-4)
7. [Hospital Systems and TOC Files](#7-hospital-systems-and-toc-files)
8. [Resumability and Checkpointing](#8-resumability-and-checkpointing)
9. [Cloud Infrastructure](#9-cloud-infrastructure)
10. [File Structure](#10-file-structure)
11. [Cost Breakdown](#11-cost-breakdown)
12. [Data Quality Validation](#12-data-quality-validation)
13. [Build Sequence](#13-build-sequence)
14. [Open Questions](#14-open-questions)
15. [Edge Cases and Known Challenges](#15-edge-cases-and-known-challenges)
16. [Coverage Improvement Roadmap](#16-coverage-improvement-roadmap)

---

## 1. Why Build This

### The Problem with Payerset

ClaroBill currently sources hospital MRF URLs from Payerset, a third-party directory:

| Metric | Payerset | This Pipeline |
|---|---|---|
| Hospital count | ~3,119 | ~7,000 |
| CMS coverage | ~45% | ~98% |
| URL freshness | Weeks to months stale | Discovered directly from hospital websites |
| NPI coverage at load time | 4 / 3,119 (0.1%) | ~98% via CMS POS file |
| Hospital metadata | Name, system, state | + Type, rating, address, phone, bed count, CCN, Medicare contractor |
| Third-party dependency | Yes — Payerset can disappear, paywall, or throttle | None |
| Annual cost | Free (for now) | ~$165–215 |

### The Business Moat

CMS requires all Medicare-registered hospitals to publish machine-readable price files (MRFs) annually. There are ~7,000 such hospitals. No commercial product has a complete, fresh, self-sourced database of these files. Building this pipeline gives ClaroBill:

- The most comprehensive hospital charge database of any medical bill auditing product
- Independence from third-party data vendors
- A dataset that can be licensed or offered as an API to other healthcare companies
- A foundation for proactive bill auditing (flag errors before a patient even submits a bill)

---

## 2. Data Sources

### 2.1 CMS Promoting Interoperability Hospital List (Primary Seed)

**URL:** https://data.cms.gov/provider-data/dataset/xubh-q36u  
**API:** `https://data.cms.gov/provider-data/api/1/datastore/query/xubh-q36u/0?format=csv`  
**Update cadence:** Quarterly  
**Cost:** Free  
**Records:** ~7,000 hospitals  

**Fields available:**
- `Facility ID` — CCN (CMS Certification Number), the primary CMS key
- `Facility Name` — Legal hospital name
- `Address`, `City`, `State`, `ZIP Code`, `County Name`
- `Phone Number`
- `Hospital Type` — Acute Care, Critical Access, Children's, Psychiatric, etc.
- `Hospital Ownership` — Government, Non-profit, Proprietary
- `Emergency Services` — Yes/No
- `Hospital overall rating` — 1–5 stars
- `Meets criteria for meaningful use of EHRs`

**Why this is the right seed:** CCN is the authoritative CMS identifier. Every Medicare-certified hospital has one. The CMS PI list is updated quarterly and is the closest thing to a complete census of US hospitals.

---

### 2.2 CMS Provider of Services (POS) File (CCN → NPI Mapping)

**URL:** https://data.cms.gov/provider-characteristics/hospitals-and-other-facilities/provider-of-services-file-hospital-non-hospital-facilities  
**Update cadence:** Quarterly  
**Cost:** Free  
**Expected NPI coverage:** ~98% of CMS-registered hospitals  

This is the most important supplementary source. It is a CMS-to-CMS join — the authoritative mapping from CCN to NPI for every Medicare/Medicaid certified facility. No name-matching, no fuzzy logic, no API calls.

**Key fields beyond CCN and NPI:**
- `BED_CNT` — Total beds
- `CRTFD_BED_CNT` — Medicare-certified beds
- `PRVDR_CTGRY_CD` — Provider category (filter to `01` = short-term acute care, `02` = long-term, `06` = psychiatric, `14` = critical access, `15` = children's)
- `PRVDR_CTGRY_SBTYP_CD` — Subtype code
- `INTRMDRY_CARR_CD` — Medicare contractor/carrier code. **Directly maps to AFS ambulance locality** — removes the ZIP→locality inference step entirely for hospital-billed ambulance services
- `CHOW_DT` — Change of ownership date — flags recently-acquired hospitals whose MRF may have moved
- `ACPT_Medicare_ASSGNMT_CD` — Medicare assignment acceptance

**How to use it:**
```python
# Download quarterly POS file
# Filter: PRVDR_CTGRY_CD in ('01', '02', '06', '14', '15')
# Build lookup: {ccn: {npi, bed_count, category, carrier_code}}
# Merge into hospital_directory at Stage 2
```

---

### 2.3 NPPES Bulk Download (NPI → Website URL)

**URL:** https://download.cms.gov/nppes/NPI_Files.html  
**Update cadence:** Monthly full replacement  
**Cost:** Free  
**File size:** ~8GB compressed, ~35GB uncompressed  
**Expected website coverage:** ~50% of hospitals  

The monthly full replacement file contains all 6M+ NPI records. For hospital NPIs (Entity Type Code = `2`), the relevant fields are:

- `Authorized_Official_Web_URL` — Official website URL. Populated for ~50% of hospitals.
- `Provider_Business_Practice_Location_Address_Telephone_Number` — Phone (cross-validation)
- `Healthcare_Provider_Taxonomy_Code_1` through `_15` — Taxonomy codes (filter to `28*` acute care, `26*` residential, `27*` nursing)

**Processing approach:** Since the file is 35GB, do not load into memory. Use `csv.DictReader` with a generator, filtering on `Entity_Type_Code == '2'` and NPI in the set of hospital NPIs from Stage 2. Write matches to a JSON cache file. Expected ~7,000 rows to extract from 6M.

**Secondary use:** The NPPES file contains `Other_Provider_Identifier` columns where `Type_Code = 04` means Medicare CCN. This is a second path for CCN→NPI resolution that catches hospitals the POS file misses.

---

### 2.4 Wikidata SPARQL (Website URLs for Major Systems, Free)

**Endpoint:** `https://query.wikidata.org/sparql`  
**Cost:** Free  
**Expected coverage:** ~500 major hospital systems  

Large hospital systems (HCA, Ascension, Mayo Clinic, Kaiser, CommonSpirit, Tenet, etc.) all have Wikidata entries with `official website (P856)`. A single SPARQL query returns ~500 systems instantly.

```sparql
SELECT ?hospital ?name ?website WHERE {
  ?hospital wdt:P31/wdt:P279* wd:Q16917.
  ?hospital wdt:P856 ?website.
  ?hospital rdfs:label ?name FILTER(LANG(?name) = "en")
  OPTIONAL { ?hospital wdt:P17 wd:Q30 }  # United States only
}
```

Run this before Stage 3. Any hospital name that fuzzy-matches a Wikidata entry (difflib ratio > 0.85) gets its website pre-populated, avoiding a Google Places API call.

---

### 2.5 Google Places API (Website Gap Coverage, Paid)

**API:** Places API (New) — Text Search + Place Details  
**Cost:** ~$150–200 for ~3,500 hospitals (those not covered by NPPES or Wikidata)  
**Expected coverage:** ~45% additional (combined with NPPES/Wikidata reaches ~98%)  
**Accuracy:** Very high — hospitals actively maintain Google Business profiles for patient visibility  

**Query pattern:**
```python
# Text Search
query = f'"{hospital_name}" "{city}" "{state}" hospital'
params = {"textQuery": query, "type": "hospital"}

# Place Details (to get website)
fields = ["name", "websiteUri", "formattedAddress", "nationalPhoneNumber"]
```

**Cost control:** Gate behind `--use-search-api` flag. Only call for hospitals that have no website after NPPES + Wikidata steps. Cache all results in a JSON file (`data/cms/hospitals/places_cache.json`) so re-runs skip already-resolved hospitals.

**Why Google over alternatives:**
- Bing Places: Lower coverage for hospitals
- Yelp Fusion: Good for restaurants, not hospitals
- Apple Maps: No public API for bulk queries
- SerpApi: More expensive, adds a middleman
- DuckDuckGo scraping: Fragile, violates ToS

---

### 2.6 Internet Archive / Wayback Machine (Fallback for 404 URLs)

**URL:** `https://archive.org/wayback/available?url={url}`  
**Cost:** Free  
**Use case:** When a known MRF URL returns 404, check the Wayback Machine for the last known good snapshot, extract the new URL from redirect chains  

This is a fallback for the ~5-10% of hospitals whose MRF URL has moved since last year's discovery run. The Wayback Machine often has the old URL and can provide the redirect chain that leads to the new location.

---

### 2.7 CommonWell / Carequality Provider Directories (Future Enhancement)

These are healthcare interoperability networks with provider directories. Not yet publicly accessible without membership, but worth monitoring as a potential 99%+ coverage source in future years.

---

## 3. Architecture Overview

### Design Principles

1. **Resumability over speed.** A crash at hospital 4,800 resumes from 4,801. The checkpoint table is the source of truth.
2. **Quality over completeness.** A validated URL is worth more than five unvalidated ones. Never write an MRF URL to `hospital_directory` without passing all validation checks.
3. **No aborts on single failures.** One hospital timing out, one 404, one malformed JSON — none of these should kill the pipeline. Log, checkpoint the error, continue.
4. **Paid API calls are the last resort.** Free CMS data and free APIs exhaust first. Google Places only fires for hospitals that are unresolved after all free methods.
5. **All external calls are cached.** NPPES, Places, Wikidata, robots.txt — everything is written to a cache file or BigQuery before re-running.

### Data Flow

```
CMS PI List (7,000 hospitals)
         │
         ▼ Stage 1: cms_hospital_list
         │  Seed mrf_discovery_checkpoint with all CCNs
         │
         ▼ Stage 2: nppes_crossref
         │  A: CMS POS file → CCN→NPI (~98%)
         │  B: NPPES bulk download → NPI→website (~50%)
         │  C: Wikidata SPARQL → system websites (~500 systems)
         │  Result: ~98% have NPI, ~55% have website
         │
         ▼ Stage 3: website_discovery
         │  Tier 1: Validate NPPES/Wikidata URLs (HEAD check)
         │  Tier 2: Domain pattern inference (slug.org, slughospital.org, etc.)
         │  Tier 3: Google Places API (remaining ~45%)
         │  Result: ~98% have a confirmed live website
         │
         ▼ Stage 4: website_crawler
         │  Per hospital:
         │    1. Fetch homepage (httpx, async)
         │    2. JS detection → Playwright fallback if needed
         │    3. Check robots.txt (2s minimum delay per domain)
         │    4. Search footer, nav, sitemap.xml for price transparency links
         │    5. Check /price-transparency (CMS-mandated path)
         │    6. Detect TOC JSON files
         │  Result: candidate_mrf_urls populated for ~85-90% of hospitals
         │
         ▼ Stage 5: mrf_validator
         │  Per candidate URL:
         │    1. Expand TOC JSON → mrf_toc_index
         │    2. File extension check
         │    3. HEAD request (must return 200, Content-Length > 0)
         │    4. Content sampling (first 512B CSV, 2KB JSON)
         │    5. Deduplication across hospital systems
         │  Result: validated_mrf_urls for ~78-85% of hospitals
         │
         ▼ Stage 6: bq_commit
         │  MERGE validated URLs → hospital_directory (join on CCN)
         │  Write mrf_discovery_runs summary row
         │
         ▼ Existing weekly pipeline (unchanged)
            scraper → parser → hospital_charges populated
```

---

## 4. BigQuery Schema

### 4.1 New Columns on `hospital_directory`

```sql
ALTER TABLE `clarobill-prd.hospital_prices.hospital_directory`
  ADD COLUMN IF NOT EXISTS ccn STRING,
  ADD COLUMN IF NOT EXISTS hospital_website STRING,
  ADD COLUMN IF NOT EXISTS hospital_type STRING,
  ADD COLUMN IF NOT EXISTS hospital_ownership STRING,
  ADD COLUMN IF NOT EXISTS overall_rating INT64,
  ADD COLUMN IF NOT EXISTS bed_count INT64,
  ADD COLUMN IF NOT EXISTS medicare_carrier_code STRING,
  ADD COLUMN IF NOT EXISTS phone STRING,
  ADD COLUMN IF NOT EXISTS zip_code STRING,
  ADD COLUMN IF NOT EXISTS mrf_discovery_method STRING,
  -- 'pos_file' | 'nppes_bulk' | 'wikidata' | 'places_api' |
  -- 'crawl_direct' | 'toc_expansion' | 'pattern_inference' | 'manual'
  ADD COLUMN IF NOT EXISTS last_discovery_run DATE;
```

### 4.2 New Table: `mrf_discovery_checkpoint`

One row per CCN. The pipeline's heartbeat. All stages read from and write to this table.

```sql
CREATE TABLE IF NOT EXISTS `clarobill-prd.hospital_prices.mrf_discovery_checkpoint` (
  -- Identity
  ccn                   STRING NOT NULL,
  hospital_name         STRING NOT NULL,
  address               STRING,
  city                  STRING,
  state                 STRING,
  zip_code              STRING,
  phone                 STRING,
  hospital_type         STRING,
  hospital_ownership    STRING,
  overall_rating        INT64,

  -- Stage completion timestamps (NULL = not yet attempted or not yet complete)
  cms_loaded_at         TIMESTAMP,
  nppes_resolved_at     TIMESTAMP,
  website_found_at      TIMESTAMP,
  crawl_complete_at     TIMESTAMP,
  mrf_validated_at      TIMESTAMP,
  bq_committed_at       TIMESTAMP,

  -- Resolution outputs
  hospital_npi          STRING,
  bed_count             INT64,
  medicare_carrier_code STRING,
  hospital_website      STRING,
  website_source        STRING,  -- which tier/source found the website

  -- Crawl outputs
  candidate_mrf_urls    JSON,    -- array of strings, all URLs found pre-validation
  toc_url               STRING,  -- if a TOC JSON was found, its URL
  toc_expanded          BOOL DEFAULT FALSE,

  -- Validation outputs
  validated_mrf_urls    JSON,    -- array of strings, confirmed MRF URLs
  discovery_method      STRING,  -- final method that produced the validated URL

  -- Error tracking
  error_stage           STRING,
  error_message         STRING,
  consecutive_failures  INT64 DEFAULT 0,

  last_updated          TIMESTAMP
)
PARTITION BY DATE(last_updated)
CLUSTER BY state, ccn;
```

### 4.3 New Table: `mrf_toc_index`

Hospital systems publish one Table of Contents (TOC) JSON listing MRF URLs for all their facilities.

```sql
CREATE TABLE IF NOT EXISTS `clarobill-prd.hospital_prices.mrf_toc_index` (
  toc_url               STRING NOT NULL,
  system_ccn            STRING,           -- CCN of the hospital system entry point
  system_name           STRING,
  facility_name         STRING,           -- Name from inside the TOC JSON
  facility_ccn          STRING,           -- Matched CCN if fuzzy match succeeded
  facility_npi          STRING,           -- Matched NPI if available
  facility_mrf_url      STRING NOT NULL,
  plan_name             STRING,
  last_updated_on       STRING,           -- From TOC "last_updated_on" field
  file_size_bytes       INT64,
  discovered_at         TIMESTAMP,
  validated_at          TIMESTAMP
);
```

### 4.4 New Table: `mrf_discovery_runs`

Annual run summary for tracking coverage improvement over time.

```sql
CREATE TABLE IF NOT EXISTS `clarobill-prd.hospital_prices.mrf_discovery_runs` (
  run_date                    DATE NOT NULL,
  total_hospitals_in_cms      INT64,
  hospitals_with_npi          INT64,
  hospitals_with_website      INT64,
  hospitals_crawled           INT64,
  hospitals_with_candidate_url INT64,
  hospitals_with_validated_url INT64,
  coverage_rate               FLOAT64,  -- validated / total
  urls_from_pos_file          INT64,
  urls_from_nppes             INT64,
  urls_from_wikidata          INT64,
  urls_from_places_api        INT64,
  urls_from_crawl_direct      INT64,
  urls_from_toc_expansion     INT64,
  urls_from_pattern_inference INT64,
  toc_files_found             INT64,
  toc_facilities_mapped       INT64,
  places_api_calls_made       INT64,
  places_api_cost_usd         FLOAT64,
  hospitals_with_404_url      INT64,    -- known stale URLs from prior year
  new_hospitals_added         INT64,    -- CCNs not in last year's run
  hospitals_removed_from_cms  INT64,
  run_duration_seconds        INT64,
  notes                       STRING
);
```

---

## 5. Stage-by-Stage Design

### Stage 1 — CMS Hospital List

**Script:** `scripts/mrf_discovery/stage1_cms_hospital_list.py`  
**Input:** CMS PI API  
**Output:** `mrf_discovery_checkpoint` populated, ~7,000 rows  
**Duration:** ~2 minutes  
**Resumable:** Yes — INSERT if not exists, skip rows where `cms_loaded_at IS NOT NULL`  

```python
API_URL = "https://data.cms.gov/provider-data/api/1/datastore/query/xubh-q36u/0"
PARAMS = {"format": "csv", "offset": 0, "limit": 500}
# Paginate with offset until empty result
# Batch INSERT to checkpoint in groups of 500
# CCN is the dedup key — INSERT IGNORE on conflict
```

**Annual re-run behavior:** New hospitals (CMS adds ~200-300/year) get INSERTed. Existing hospitals are skipped. Hospitals that leave Medicare are flagged in `mrf_discovery_runs` but NOT deleted from `hospital_directory` (they may still have historical charge data worth keeping).

---

### Stage 2 — NPI + Metadata Resolution

**Script:** `scripts/mrf_discovery/stage2_nppes_crossref.py`  
**Input:** CMS POS file (download), NPPES bulk file (download), Wikidata SPARQL  
**Output:** `hospital_npi`, `bed_count`, `medicare_carrier_code`, partial `hospital_website` populated in checkpoint  
**Duration:** ~30 minutes (dominated by NPPES 35GB file scan)  
**Resumable:** Yes — skip rows where `nppes_resolved_at IS NOT NULL`  

**Step A — CMS POS file (CCN→NPI, ~98% coverage):**
```
Download: https://data.cms.gov/provider-characteristics/hospitals-and-other-facilities/
          provider-of-services-file-hospital-non-hospital-facilities
Format: CSV, ~500MB
Filter: PRVDR_CTGRY_CD in ('01','02','06','14','15','16','17','22')
Join key: CCN (PRVDR_NUM column in POS file)
Outputs: NPI (NATL_PRVDR_IDFR), BED_CNT, CRTFD_BED_CNT, INTRMDRY_CARR_CD
```

**Step B — NPPES bulk download (NPI→website, ~50% coverage):**
```
Download: https://download.cms.gov/nppes/NPI_Files.html
File: NPPES_Data_Dissemination_{MONTH}_{YEAR}.zip (~8GB compressed)
Scan: csv.DictReader generator, filter Entity_Type_Code == '2'
      + NPI in set of hospital NPIs from Step A
Extract: Authorized_Official_Web_URL
Write: to nppes_website_cache.json (skip re-download on re-run)
```

**Step C — Wikidata SPARQL (~500 major systems):**
```
Endpoint: https://query.wikidata.org/sparql
One HTTP request, returns ~500 US hospitals/systems with websites
Fuzzy match hospital_name against Wikidata name (difflib ratio > 0.85)
Cache result in wikidata_website_cache.json
```

**Batch update:** After all three steps, bulk UPDATE checkpoint via staging table MERGE (existing pattern from `bootstrap_hospital_directory.py`).

---

### Stage 3 — Website Discovery

**Script:** `scripts/mrf_discovery/stage3_website_discovery.py`  
**Input:** Checkpoint rows where `website_found_at IS NULL`  
**Output:** `hospital_website` populated for ~98% of hospitals  
**Duration:** ~3–4 hours (dominated by Google Places API calls)  
**Resumable:** Yes — skip rows where `website_found_at IS NOT NULL`  

**Tier 1 — Validate existing URLs (from Stage 2, ~55% of hospitals):**
- HEAD request to each URL (timeout: 10s)
- Accept: 200, 301, 302 response codes
- Reject: 404, 5xx, connection timeout, non-hospital domain (check domain against hospital name)
- Cache: write validation result to checkpoint immediately

**Tier 2 — Domain pattern inference (~3–5% additional):**
```python
DOMAIN_PATTERNS = [
    "{slug}.org",
    "{slug}.com",
    "{slug}hospital.org",
    "{slug}medical.org",
    "{slug}health.org",
    "{slug}healthcare.org",
    "{city}{slug}.org",
    "www.{slug}.org",
]
# slug = re.sub(r'[^a-z0-9]', '-', name.lower()).strip('-')[:40]
# HEAD request each candidate, 5s timeout
# First 200/301 wins
# Log domain + hospital name for manual review of false positives
```

**Tier 3 — Google Places API (~40–45% additional):**
```python
# Only called if --use-search-api flag passed
# Only for hospitals with no website after Tiers 1+2
search_url = "https://places.googleapis.com/v1/places:searchText"
headers = {"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": "places.id,places.displayName"}
body = {"textQuery": f'"{name}" "{city}" "{state}" hospital', "maxResultCount": 1}
# Then Place Details for websiteUri
detail_url = f"https://places.googleapis.com/v1/places/{place_id}"
headers["X-Goog-FieldMask"] = "websiteUri,formattedAddress,nationalPhoneNumber"
# Rate limit: 10 req/s, cache to places_cache.json immediately
```

**Cross-validation:** After finding a website URL, verify it mentions the hospital name (within the `<title>` tag or first `<h1>`). Rejects review sites (Healthgrades, US News, Yelp, Vitals) and generic system homepages when the search was for a specific facility.

---

### Stage 4 — Website Crawler

**Script:** `scripts/mrf_discovery/stage4_website_crawler.py`  
**Input:** Checkpoint rows where `website_found_at IS NOT NULL` and `crawl_complete_at IS NULL`  
**Output:** `candidate_mrf_urls` populated  
**Duration:** ~8–12 hours (the longest stage)  
**Resumable:** Yes — per-hospital `crawl_complete_at` written as each hospital finishes  

See [Section 6 — The Crawler](#6-the-crawler-stage-4) for full design.

---

### Stage 5 — MRF Validator

**Script:** `scripts/mrf_discovery/stage5_mrf_validator.py`  
**Input:** Checkpoint rows where `crawl_complete_at IS NOT NULL` and `mrf_validated_at IS NULL`  
**Output:** `validated_mrf_urls` populated, `mrf_toc_index` expanded  
**Duration:** ~2–4 hours  
**Resumable:** Yes  

**Per candidate URL validation pipeline:**

```
Step 1 — TOC detection and expansion
  If URL ends in .json and does NOT end in _standardcharges.json:
    Fetch first 2KB
    Check for TOC markers: "standard_charge_links" OR "hospital_location" array
    If TOC: expand all facility URLs → mrf_toc_index
             fuzzy-match facility names to CCNs
             mark toc_expanded = TRUE in checkpoint

Step 2 — Extension check
  Accept: .json, .json.gz, .csv, .csv.gz, .zip, .xlsx
  Reject anything else — HTML, PDF, .docx, etc.

Step 3 — HEAD request
  Must return: 200 OK
  Must have: Content-Length > 1024 (rejects empty or near-empty files)
  Note the Last-Modified and ETag for future change detection

Step 4 — Content sampling
  For .json / .json.gz:
    Fetch first 4KB
    Must contain at least one of:
      "hospital_name", "standard_charge_information",
      "standard_charges", "reporting_entity_name"
    Must NOT be an HTML error page (check for <!DOCTYPE or <html)

  For .csv / .csv.gz:
    Fetch first 512 bytes
    Parse header row
    Must contain at least one of:
      "description", "cpt_code", "hcpcs_code", "ms-drg",
      "rev_code", "payer_name", "standard_charge"

  For .xlsx:
    Download to GCS staging (mrf-staging/validation/{ccn}/)
    Use openpyxl to read first sheet header row
    Apply same column checks as CSV
    Delete staging file after check

  For .zip:
    Download to GCS staging
    List archive contents
    Find first .json or .csv file inside
    Apply above checks to that file
    Delete staging file after check

Step 5 — Deduplication
  Check hospital_directory: does this mrf_url already exist for a different CCN?
  If yes: this is a system-level file — link via TOC, don't duplicate
  Check mrf_toc_index: is this URL already expanded from a system TOC?
  If yes: record the parent TOC URL as the canonical source

Step 6 — Write to checkpoint
  validated_mrf_urls = [url] (or expanded array if TOC)
  mrf_validated_at = NOW()
  discovery_method = determined from source
```

---

### Stage 6 — BigQuery Commit

**Script:** `scripts/mrf_discovery/stage6_bq_commit.py`  
**Input:** Checkpoint rows where `mrf_validated_at IS NOT NULL` and `bq_committed_at IS NULL`  
**Output:** `hospital_directory` updated  
**Duration:** ~10 minutes  

**MERGE logic:**
```sql
MERGE `clarobill-prd.hospital_prices.hospital_directory` T
USING `staging` S
ON T.ccn = S.ccn OR T.mrf_url = S.validated_mrf_url
WHEN NOT MATCHED THEN
  INSERT (hospital_npi, hospital_name, system_name, state, city, zip_code,
          phone, mrf_url, ccn, hospital_website, hospital_type,
          hospital_ownership, overall_rating, bed_count,
          medicare_carrier_code, mrf_discovery_method, last_discovery_run)
  VALUES (...)
WHEN MATCHED THEN
  UPDATE SET
    -- Always refresh from new discovery run
    mrf_url              = COALESCE(S.validated_mrf_url, T.mrf_url),
    hospital_npi         = COALESCE(T.hospital_npi, S.hospital_npi),
    hospital_name        = COALESCE(S.hospital_name, T.hospital_name),
    system_name          = COALESCE(S.system_name, T.system_name),
    hospital_website     = COALESCE(S.hospital_website, T.hospital_website),
    bed_count            = COALESCE(S.bed_count, T.bed_count),
    medicare_carrier_code = COALESCE(S.medicare_carrier_code, T.medicare_carrier_code),
    overall_rating       = COALESCE(S.overall_rating, T.overall_rating),
    mrf_discovery_method = S.discovery_method,
    last_discovery_run   = CURRENT_DATE()
```

After the MERGE, write a row to `mrf_discovery_runs` with the coverage summary.

---

## 6. The Crawler (Stage 4)

The crawler is the most complex component. It handles everything from static HTML to JavaScript single-page applications, respects robots.txt at scale, and handles the wide variety of hospital website architectures.

### 6.1 Fetch Strategy

```
Hospital website URL
        │
        ▼ httpx async fetch (15s timeout)
        │
        ├─ Response body > 1000 chars of real content?
        │   └─ YES → Use httpx response → proceed to link extraction
        │
        └─ NO (JS-rendered shell detected)
            Detection criteria:
              - body length < 500 chars
              - contains "<div id='root'>" or "<div id='app'>" with no children
              - contains "You need to enable JavaScript"
              - contains "window.__INITIAL_STATE__" with empty body
            │
            ▼ Playwright fallback
              headless Chromium, wait_until="networkidle"
              30s timeout
              Shared browser instance (not one per hospital)
              Per-worker browser context (isolated cookies/state)
```

### 6.2 Crawl Sequence Per Hospital

```
1. Fetch homepage
   ├─ Apply JS detection (above)
   └─ Extract all <a href> links

2. Score links by price transparency relevance
   High-score patterns (URL path contains):
     /price-transparency  ← CMS-mandated exact path
     /standard-charges
     /chargemaster
     /cdm
     /pricing
     /price-list
     /financial-assistance
     /billing-information
     /cost-estimates
     /mrf
   
   High-score patterns (link text contains, case-insensitive):
     "price transparency"
     "standard charges"
     "chargemaster"
     "charge master"
     "machine readable"
     "cost estimates"
     "financial assistance"
     "price list"
     "billing information"

3. Fetch top 3 scored links (deduplicated)
   Repeat link extraction on each linked page

4. Fetch /sitemap.xml or /sitemap_index.xml
   Parse all <loc> URLs
   Filter to price-related paths (same patterns)
   Fetch those pages

5. Check /price-transparency directly
   CMS requires all hospitals to have this exact path
   Many hospitals use it even if not linked from homepage

6. Scan page footers specifically
   Look for <footer> element
   Extract all links within footer
   Apply scoring patterns

7. Collect all candidate file links
   (.json, .json.gz, .csv, .csv.gz, .zip, .xlsx)
   Also collect links to pages that contain those files
   Write all candidates to checkpoint
```

### 6.3 robots.txt Compliance

```python
class RobotsCache:
    """Per-domain robots.txt cache with 24-hour TTL."""
    
    def can_fetch(self, url: str) -> bool:
        domain = urlparse(url).netloc
        if domain not in self._cache or self._cache_expired(domain):
            self._fetch_robots(domain)
        return self._cache[domain].can_fetch("ClaroBill-MRFDiscovery/1.0", url)
```

User-Agent string in robots.txt: `ClaroBill-MRFDiscovery/1.0`  
Minimum delay between requests to same domain: 2 seconds  
Minimum delay between requests to same IP: 1 second  
Max concurrent requests to same domain: 1  

**Important:** If `robots.txt` disallows crawling, mark `crawl_complete_at` with a note but do NOT mark as an error. On next year's run, check robots.txt again — many hospitals only temporarily restrict crawlers during site rebuilds.

### 6.4 Concurrency Model

```
ThreadPoolExecutor(max_workers=10)
  │
  ├─ Worker 1: httpx AsyncClient (own event loop)
  │            Playwright browser context (shared browser)
  │            domain_semaphores dict (per-domain rate limiting)
  │
  ├─ Worker 2: same pattern
  │
  ... × 10 workers

Per-domain semaphore: asyncio.Semaphore(1) per domain
                      + asyncio.sleep(2) between requests to same domain
```

10 workers × ~3 HTTP requests per hospital × 2s delay = effective throughput of ~5 hospitals/minute. For 7,000 hospitals: ~23 hours worst case, ~8–12 hours typical (most hospitals have only 1-2 pages to check).

### 6.5 Playwright Configuration

```python
# At container startup — shared across all workers
playwright = await async_playwright().start()
browser = await playwright.chromium.launch(
    headless=True,
    args=[
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-images",      # Don't load images — saves bandwidth
        "--disable-javascript",  # Wait — we NEED JS for JS-rendered sites
        # Actually: only disable images, keep JS enabled
    ]
)

# Per worker — isolated from other workers
context = await browser.new_context(
    user_agent="ClaroBill-MRFDiscovery/1.0 (price transparency research; contact@clarobill.com)",
    java_script_enabled=True,
    accept_downloads=False,
)
```

**Memory note:** One Chromium instance idles at ~200MB. With 10 browser contexts: ~400-600MB total for Playwright. Combined with the 4Gi container allocation, this is comfortable.

---

## 7. Hospital Systems and TOC Files

### 7.1 The Problem

Major hospital systems (HCA: 180 hospitals, Ascension: 140, CommonSpirit: 140, Tenet: 60, etc.) publish a single Table of Contents (TOC) JSON file at their corporate website. This one file lists MRF URLs for all their individual facilities. If the crawler only visits the facility website and doesn't find the TOC at the system level, it misses all those hospitals.

### 7.2 CMS TOC JSON Schema

```json
{
  "hospital_name": "HCA Healthcare",
  "last_updated_on": "2025-01-15",
  "version": "1.1",
  "reporting_entity_name": "HCA Healthcare",
  "reporting_entity_type": "hospital location",
  "affirmation": {
    "affirmation": "To the best of its knowledge...",
    "confirm_affirmation": true
  },
  "standard_charge_links": [
    {
      "hospital_name": "HCA Florida Bayonet Point Hospital",
      "hospital_location": "Port Richey, FL",
      "license_number": "....",
      "ein": "59-1234567",
      "last_updated_on": "2025-01-10",
      "url": "https://hcahealthcare.com/.../340_standardcharges.json.gz",
      "file_size": 45231890,
      "filename": "340_HCA_Florida_Bayonet_Point_standardcharges.json.gz"
    },
    ...
  ]
}
```

### 7.3 TOC Detection in Stage 4

```python
def _is_toc_candidate(url: str, content_type: str) -> bool:
    """Return True if this URL might be a CMS TOC JSON file."""
    path = urlparse(url).path.lower()
    # Must be JSON
    if not (path.endswith('.json') or 'application/json' in content_type):
        return False
    # Must NOT look like an individual MRF file
    if '_standardcharges' in path or 'standard_charges' in path:
        return False
    # Heuristic: TOC files are usually at domain root or /price-transparency/
    return True

def _verify_toc(content: bytes) -> bool:
    """Return True if this JSON looks like a CMS TOC file."""
    try:
        snippet = json.loads(content[:4096].decode('utf-8', errors='replace') + '"}]}')
    except json.JSONDecodeError:
        # Partial JSON — check for marker strings
        pass
    markers = [b'"standard_charge_links"', b'"hospital_location"', b'"affirmation"']
    return any(m in content[:4096] for m in markers)
```

### 7.4 TOC Expansion in Stage 5

```python
def expand_toc(toc_url: str, system_ccn: str, bq_client, bucket) -> list[dict]:
    resp = requests.get(toc_url, timeout=30)
    toc = resp.json()
    
    facilities = toc.get('standard_charge_links') or toc.get('hospital_location') or []
    rows = []
    for facility in facilities:
        name = facility.get('hospital_name') or facility.get('facility_name')
        mrf_url = facility.get('url')
        if not mrf_url:
            continue
        
        # Fuzzy match facility name to a CCN in our checkpoint table
        matched_ccn = _fuzzy_match_ccn(name, facility.get('hospital_location'), checkpoint_df)
        
        rows.append({
            'toc_url': toc_url,
            'system_ccn': system_ccn,
            'facility_name': name,
            'facility_ccn': matched_ccn,
            'facility_mrf_url': mrf_url,
            'last_updated_on': facility.get('last_updated_on'),
            'file_size_bytes': facility.get('file_size'),
            'discovered_at': datetime.utcnow().isoformat(),
        })
    
    # Insert all rows to mrf_toc_index
    # Update checkpoint for all matched CCNs
    return rows
```

### 7.5 System-Level Website Strategy

For hospital systems, the crawler also needs to check the parent system website, not just the individual facility website. Strategy:

1. Group hospitals in checkpoint by `system_name` (populated from CMS PI list where available)
2. For groups of 3+ hospitals with the same system_name, find the system website separately
3. Crawl the system website first — if a TOC is found, all facilities in that system get their MRF URLs from the TOC expansion
4. This means one crawl can resolve 180 hospitals (HCA) instead of visiting 180 individual sites

---

## 8. Resumability and Checkpointing

### 8.1 Checkpoint Table Contract

**Every stage follows this exact pattern:**

```python
def run_stage(bq_client, project, concurrency):
    # 1. Get all pending hospitals for this stage
    pending = get_pending(bq_client, project, stage="crawl_complete")
    logger.info("Stage 4: %d hospitals pending", len(pending))
    
    for hospital in pending:
        try:
            result = process_hospital(hospital)
            mark_complete(bq_client, project, hospital["ccn"], "crawl_complete", result)
        except Exception as exc:
            mark_error(bq_client, project, hospital["ccn"], "crawl_complete", str(exc))
            continue  # NEVER raise — one bad hospital cannot kill the pipeline
    
    logger.info("Stage 4 complete")
```

`mark_complete()` writes the result to the checkpoint and sets `{stage}_at = NOW()`. `mark_error()` writes to `error_stage` and `error_message` but leaves `{stage}_at = NULL` — so the hospital is automatically retried on the next run.

### 8.2 Re-run Behavior

**Normal annual re-run (most common):**
- All 7,000 hospitals from prior year: Stages 1-3 skip (all `_at` fields populated)
- ~200-300 new hospitals: process through all 6 stages
- ~500 hospitals with stale MRF URLs (404 last scrape): Stage 5 re-validates
- Net result: ~15-30 minute run for a normal annual refresh

**Force-refresh (use when Payerset data was the source and you want fresh discovery):**
```bash
python scripts/discover_mrf_pipeline.py \
  --force-refresh stages 4,5,6 \
  --project clarobill-prd
```
Clears `crawl_complete_at`, `mrf_validated_at`, `bq_committed_at` for all rows — forces full re-crawl and re-validation. First-year use case.

**Single state test run:**
```bash
python scripts/discover_mrf_pipeline.py \
  --state TX \
  --project clarobill-prd
```
Texas has ~600 hospitals — ideal for testing all 6 stages end-to-end before a full run.

### 8.3 Cache Files (Local, Complement the BQ Checkpoint)

| Cache file | Contents | When to delete |
|---|---|---|
| `data/cms/hospitals/nppes_website_cache.json` | NPI → website URL from NPPES bulk download | After annual run if NPPES bulk file changes |
| `data/cms/hospitals/places_cache.json` | CCN → Places API result | Never — saves ~$150/year on re-runs |
| `data/cms/hospitals/wikidata_cache.json` | Hospital name → Wikidata website | Never — update via append |
| `data/cms/hospitals/robots_cache.json` | Domain → robots.txt content | Before each annual run |

---

## 9. Cloud Infrastructure

### 9.1 Cloud Run Job: `mrf-discovery-annual`

```yaml
name: mrf-discovery-annual
image: us-central1-docker.pkg.dev/clarobill-prd/clarobill-pipeline/mrf-pipeline:latest
command: ["python", "discover_mrf_pipeline.py", "--resume"]
memory: 4Gi
cpu: 2
task_timeout: 86400  # 24 hours
max_retries: 0       # Pipeline is resumable — auto-retry wastes work
schedule: "0 2 15 1 *"  # 2:00 AM UTC, January 15 every year
service_account: clarobill-pipeline-sa@clarobill-prd.iam.gserviceaccount.com
env:
  GCP_PROJECT_ID: clarobill-prd
  BIGQUERY_DATASET: hospital_prices
  GCS_MRF_STAGING_BUCKET: mrf-staging
  MRF_DISCOVERY_CONCURRENCY: "10"
  MRF_DISCOVERY_USE_SEARCH_API: "true"  # Enable Google Places on annual run
  GOOGLE_PLACES_API_KEY: (from Secret Manager)
```

**Why `max_retries: 0`:** The pipeline is checkpointed per hospital. If the container crashes at hour 20, re-running with `--resume` picks up exactly where it left off. Auto-retrying would duplicate the already-completed work from hours 1-20.

### 9.2 Dockerfile Additions

The existing `pipeline/Dockerfile` needs Playwright + lxml:

```dockerfile
# After pip install requirements.txt
RUN pip install playwright==1.44.0 lxml==5.2.2 openpyxl==3.1.2 httpx==0.27.0 && \
    playwright install chromium --with-deps

# Chromium dependencies add ~500MB to the image
# Total image size estimate: ~1.5GB (vs ~300MB current)
```

**Note:** The existing `scrape_hospital_mrfs.py` and `parse_hospital_mrfs.py` jobs share this image. The Playwright binary adds ~500MB but is only loaded when `discover_mrf_pipeline.py` is the entrypoint. It does not affect the weekly scraper/parser jobs.

**Alternative:** Create a separate Dockerfile at `pipeline/Dockerfile.discovery` for the annual job. Keeps the weekly scraper image lean (~300MB) and the discovery job image fat (~1.5GB). Recommended if Cloud Build time or image pull time becomes an issue.

### 9.3 Secret Manager

Add `GOOGLE_PLACES_API_KEY` to Secret Manager (not an env var — it's a paid API key):

```bash
gcloud secrets create google-places-api-key \
  --replication-policy="automatic" \
  --project=clarobill-prd

gcloud secrets add-iam-policy-binding google-places-api-key \
  --member="serviceAccount:clarobill-pipeline-sa@clarobill-prd.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor" \
  --project=clarobill-prd
```

### 9.4 GCS Bucket Usage

The existing `mrf-staging` bucket is used for two temporary purposes during discovery:

- `mrf-staging/validation/{ccn}/` — temporary storage for ZIP/XLSX files during content sampling (deleted immediately after validation)
- `mrf-staging/discovery-cache/` — optional: backup of the JSON cache files so they survive container restarts

---

## 10. File Structure

```
scripts/
│
├── discover_mrf_pipeline.py          # Orchestrator
│   # Args: --project, --state, --resume, --force-refresh, --stage {1-6},
│   #       --use-search-api, --concurrency, --dry-run
│   # Calls each stage script via subprocess.run()
│   # Prints coverage summary on completion
│
└── mrf_discovery/
    ├── __init__.py
    │
    ├── migrate_bq_schema.py          # One-time BQ schema setup
    │   # Creates checkpoint, toc_index, discovery_runs tables
    │   # Adds new columns to hospital_directory
    │   # Args: --project, --dry-run
    │
    ├── bq_checkpoint.py              # Shared BQ checkpoint helpers
    │   # init_checkpoint(client, project, hospitals)
    │   # get_pending(client, project, stage) -> list[dict]
    │   # mark_complete(client, project, ccn, stage, updates)
    │   # mark_error(client, project, ccn, stage, message)
    │   # get_coverage_summary(client, project) -> dict
    │
    ├── nppes_client.py               # Extracted from scrape_payerset_directory.py
    │   # lookup_npi(name, state, session) -> str | None
    │   # lookup_npi_bulk(npis, nppes_file_path) -> dict[str, str]  (website URLs)
    │   # Rate limiting, JSON cache support
    │
    ├── robots_cache.py               # Per-domain robots.txt cache
    │   # RobotsCache class
    │   # can_fetch(url) -> bool
    │   # TTL-based refresh (24h)
    │
    ├── price_transparency_patterns.py # All constants — no logic
    │   # URL_PATH_PATTERNS: list of regex strings
    │   # LINK_TEXT_PATTERNS: list of regex strings
    │   # TOC_SCHEMA_MARKERS: list of bytes
    │   # VALID_MRF_EXTENSIONS: set of strings
    │   # MRF_CSV_REQUIRED_COLUMNS: set of strings
    │   # MRF_JSON_REQUIRED_KEYS: set of strings
    │   # REVIEW_SITE_DOMAINS: set (healthgrades.com, usnews.com, etc.)
    │
    ├── stage1_cms_hospital_list.py
    ├── stage2_nppes_crossref.py
    ├── stage3_website_discovery.py
    ├── stage4_website_crawler.py
    ├── stage5_mrf_validator.py
    └── stage6_bq_commit.py

apps/engine/tests/scripts/
    ├── test_price_transparency_patterns.py   # Pure unit tests on regex constants
    ├── test_mrf_discovery_crawler.py         # Fixture HTML, mock httpx
    ├── test_mrf_toc_expansion.py             # Fixture TOC JSON
    └── test_mrf_validator.py                 # Fixture MRF content, mock BQ
```

---

## 11. Cost Breakdown

### One-Time Setup Costs

| Item | Cost |
|---|---|
| Google Places API key (no setup fee) | $0 |
| BigQuery schema migration | $0 |
| First full pipeline run (Cloud Run 4Gi × 2CPU × 24hr) | ~$14 |
| Google Places API calls (3,500 hospitals × 2 calls) | ~$150–200 |
| **Total first run** | **~$165–215** |

### Annual Recurring Costs

| Item | Cost/year | Notes |
|---|---|---|
| Cloud Run Job (24hr × 4Gi × 2CPU) | ~$14 | One 24hr run per year |
| Google Places API (new hospitals only, ~300/year) | ~$5–10 | Cached for known hospitals |
| BigQuery storage (checkpoint + toc tables, ~50MB) | ~$1 | Negligible |
| BigQuery queries (all pipeline stages) | ~$2–5 | ~50GB scanned/year |
| GCS staging (validation temp files, deleted immediately) | ~$0 | Ephemeral |
| **Total annual recurring** | **~$22–30** | After first year |

### Cost vs. Value

| Comparison | Value |
|---|---|
| Payerset equivalent (if they charged) | Market rate for healthcare data: $5,000–50,000/year |
| Coverage improvement | 3,119 → ~6,500 hospitals (2× more charge data) |
| Data freshness improvement | Weeks stale → discovered fresh annually |
| Independence value | No third-party risk |
| Potential licensing revenue | Hospital price database as a product: $10,000–100,000+/year ARR |

---

## 12. Data Quality Validation

### 12.1 Coverage Metrics (Primary KPIs)

After each annual run, query `mrf_discovery_runs` for:

| Metric | Year 1 Target | Year 2+ Target |
|---|---|---|
| Hospitals with validated MRF URL | ≥ 70% (4,900) | ≥ 85% (5,950) |
| Hospitals with NPI | ≥ 95% (6,650) | ≥ 98% (6,860) |
| Hospitals with website | ≥ 90% (6,300) | ≥ 98% (6,860) |
| MRF URLs that resolve to live file | ≥ 95% | ≥ 98% |
| TOC files found | ≥ 50 | ≥ 100 |
| Facilities mapped via TOC | ≥ 2,000 | ≥ 3,500 |

### 12.2 URL Staleness Detection

After each annual run, compare new `validated_mrf_urls` against prior year's `mrf_url` in `hospital_directory`:

```sql
SELECT
  h.hospital_name, h.state, h.mrf_url AS old_url,
  c.validated_mrf_urls AS new_url,
  DATE_DIFF(CURRENT_DATE(), h.last_discovery_run, DAY) AS days_since_last_check
FROM `hospital_prices.hospital_directory` h
JOIN `hospital_prices.mrf_discovery_checkpoint` c ON h.ccn = c.ccn
WHERE JSON_VALUE(c.validated_mrf_urls, '$[0]') != h.mrf_url
  AND c.mrf_validated_at IS NOT NULL
ORDER BY h.state, h.hospital_name;
```

Hospitals where the URL changed year-over-year are flagged for manual spot-check. This detects hospitals that moved their MRF to a new URL (common after website redesigns or system acquisitions).

### 12.3 Large-State Audit Query

After the run, hospitals in large states with no MRF found are high-priority for investigation (CMS requires all Medicare hospitals to post MRF files — if we didn't find one, we likely hit a robots.txt block or JS rendering failure):

```sql
SELECT state, COUNT(*) AS hospitals_without_mrf
FROM `hospital_prices.hospital_directory` h
LEFT JOIN `hospital_prices.mrf_discovery_checkpoint` c ON h.ccn = c.ccn
WHERE h.mrf_url IS NULL
  AND c.crawl_complete_at IS NOT NULL
  AND h.state IN ('CA', 'TX', 'NY', 'FL', 'PA', 'OH', 'IL', 'GA', 'NC', 'MI')
GROUP BY state
ORDER BY hospitals_without_mrf DESC;
```

### 12.4 Manual Curation Queue

After the automated pipeline completes, generate a prioritized list of hospitals for manual research:

```sql
SELECT
  c.ccn, c.hospital_name, c.city, c.state, c.hospital_website,
  c.error_stage, c.error_message,
  h.overall_rating,
  h.bed_count
FROM `hospital_prices.mrf_discovery_checkpoint` c
LEFT JOIN `hospital_prices.hospital_directory` h ON h.ccn = c.ccn
WHERE c.mrf_validated_at IS NULL
  AND c.crawl_complete_at IS NOT NULL  -- we tried but found nothing
ORDER BY h.overall_rating DESC, h.bed_count DESC  -- highest-rated/largest first
LIMIT 500;
```

The top 500 hospitals by rating and bed count that the pipeline failed to find MRFs for are worth manual investigation. Large, well-rated hospitals are most valuable to ClaroBill's users and are most likely to have non-standard price transparency implementations.

---

## 13. Build Sequence

### Phase 1 — Foundation (Week 1, no external calls)

- [ ] Create `scripts/mrf_discovery/__init__.py`
- [ ] Create `scripts/mrf_discovery/price_transparency_patterns.py` with all regex constants
- [ ] Write `tests/scripts/test_price_transparency_patterns.py` — verify all patterns against fixtures
- [ ] Create `scripts/mrf_discovery/bq_checkpoint.py` — all three helper functions with unit tests
- [ ] Create `scripts/mrf_discovery/migrate_bq_schema.py` with `--dry-run`
- [ ] Run migration against dev BQ project, verify all 4 tables created
- [ ] Add new columns to `hospital_directory` via migration script

**Acceptance criteria:** All schema objects exist in BigQuery. All regex patterns pass tests.

### Phase 2 — CMS Data Sources (Week 2, free API calls only)

- [ ] Create `scripts/mrf_discovery/nppes_client.py` (extract from `scrape_payerset_directory.py`)
- [ ] Update `scrape_payerset_directory.py` to import from `nppes_client.py`
- [ ] Create `scripts/mrf_discovery/stage1_cms_hospital_list.py`
- [ ] Create `scripts/mrf_discovery/stage2_nppes_crossref.py`
  - [ ] CMS POS file integration (download + parse)
  - [ ] NPPES bulk download scan
  - [ ] Wikidata SPARQL integration
- [ ] Run Stages 1+2 on `--state TX` (600 hospitals)
- [ ] Measure: CCN→NPI coverage, website coverage by source

**Acceptance criteria:** ≥95% of Texas hospitals have NPI. ≥50% have website from free sources.

### Phase 3 — Website Discovery (Week 3)

- [ ] Create `scripts/mrf_discovery/stage3_website_discovery.py`
  - [ ] URL validation (Tier 1)
  - [ ] Domain pattern inference (Tier 2)
  - [ ] Google Places API integration (Tier 3)
- [ ] Obtain Google Places API key, add to Secret Manager
- [ ] Run Stage 3 on `--state TX`
- [ ] Measure tier breakdown: how many resolved at each tier?

**Acceptance criteria:** ≥95% of Texas hospitals have a confirmed live website.

### Phase 4 — Crawler (Weeks 4-5, hardest stage)

- [ ] Add `playwright==1.44.0`, `lxml==5.2.2`, `httpx==0.27.0` to pipeline dependencies
- [ ] Update `pipeline/Dockerfile` or create `pipeline/Dockerfile.discovery`
- [ ] Create `scripts/mrf_discovery/robots_cache.py`
- [ ] Create `scripts/mrf_discovery/stage4_website_crawler.py`
  - [ ] httpx async fetcher
  - [ ] JS detection heuristic
  - [ ] Playwright fallback
  - [ ] Link extraction and scoring
  - [ ] Sitemap.xml parsing
  - [ ] /price-transparency path check
  - [ ] TOC detection (stage 4 side)
  - [ ] robots.txt compliance
  - [ ] Per-domain rate limiting
- [ ] Write `tests/scripts/test_mrf_discovery_crawler.py` with 10+ fixture HTML files:
  - Static HTML with footer link
  - JS-rendered site (empty shell)
  - Site with sitemap.xml
  - Site with robots.txt disallow
  - Site with TOC JSON link
  - 404 homepage
  - Redirect chain
  - Hospital system parent site with TOC
- [ ] Run Stage 4 on `--state TX`, review candidate URLs
- [ ] Tune JS detection threshold if false-positive rate > 5%

**Acceptance criteria:** ≥80% of Texas hospitals with websites have ≥1 candidate MRF URL.

### Phase 5 — Validation and Commit (Week 6)

- [ ] Create `scripts/mrf_discovery/stage5_mrf_validator.py`
  - [ ] TOC expansion + mrf_toc_index population
  - [ ] Extension check
  - [ ] HEAD request validation
  - [ ] Content sampling (.json, .csv, .xlsx, .zip)
  - [ ] Deduplication across hospital systems
- [ ] Write `tests/scripts/test_mrf_validator.py`
- [ ] Create `scripts/mrf_discovery/stage6_bq_commit.py`
- [ ] Run Stages 5+6 on Texas results
- [ ] Verify `hospital_directory` updated correctly for Texas hospitals
- [ ] Spot-check 10 random hospital_directory rows against live URLs

**Acceptance criteria:** All validated_mrf_urls resolve to real MRF files. hospital_directory updated with correct CCN, NPI, website, discovery_method.

### Phase 6 — Orchestrator and Full Run (Week 7)

- [ ] Create `scripts/discover_mrf_pipeline.py`
- [ ] Run full pipeline on `--state TX` end-to-end, verify coverage metrics
- [ ] Update `pipeline/deploy.sh` to add `mrf-discovery-annual` Cloud Run Job
- [ ] Deploy Cloud Run Job
- [ ] Trigger first full 7,000-hospital run
- [ ] Monitor via Cloud Run logs
- [ ] Query `mrf_discovery_runs` for coverage summary
- [ ] Run large-state audit query
- [ ] Generate manual curation queue, review top 100 hospitals

**Acceptance criteria:** ≥70% of all 7,000 CMS hospitals have validated MRF URLs. Coverage report written to `mrf_discovery_runs`.

---

## 14. Open Questions

These questions must be answered before or during Phase 4 build. Some require business decisions, some require technical research.

### 14.1 Legal / Compliance

**Q1: Is crawling hospital websites for price transparency data legally permissible?**  
**Context:** CMS regulations (45 CFR §180.50) require hospitals to make MRF files publicly accessible. Crawling to find those files is consistent with the regulatory intent. However, individual hospital websites may have ToS that prohibit automated access.  
**Recommendation:** Include a descriptive `User-Agent` (`ClaroBill-MRFDiscovery/1.0 price transparency research contact@clarobill.com`), respect `robots.txt`, keep request rates low (2s/domain), and avoid crawling anything beyond price transparency pages.  
**Action needed:** Legal review of CMS §180.50 and general web crawling case law (hiQ Labs v. LinkedIn) to confirm this is low-risk.

**Q2: Can ClaroBill store and redistribute hospital charge data extracted from MRF files?**  
**Context:** MRF data is published under CMS mandate and is technically public. However, some hospitals assert copyright over their charge data.  
**Action needed:** Legal review before building any data licensing or API product on top of this database.

**Q3: Does ClaroBill need to notify hospitals that it is crawling their websites?**  
**Likely answer:** No — this is standard web crawling. The descriptive User-Agent string is sufficient disclosure.

### 14.2 Technical Decisions

**Q4: Separate Dockerfile for discovery job, or extend the existing pipeline image?**  
**Trade-off:** Shared image = simpler deploy process but adds ~500MB Playwright binary to an image used by the weekly scraper (which doesn't need it). Separate image = cleaner but requires updating `deploy.sh` to build and push two images.  
**Recommendation:** Separate `pipeline/Dockerfile.discovery`. The weekly scraper runs 52×/year and a smaller image means faster cold starts.

**Q5: Should Stage 4 use `asyncio` with `httpx` throughout, or stay with synchronous `requests` + `ThreadPoolExecutor`?**  
**Trade-off:** Async is more efficient for I/O-bound work (crawling is almost entirely I/O). But the existing codebase uses `requests` + `ThreadPoolExecutor` everywhere — mixing async would add cognitive overhead.  
**Recommendation:** Use `asyncio` + `httpx` for Stage 4 only (it's the most I/O-intensive). All other stages stay synchronous. Document this clearly in the stage4 module docstring.

**Q6: What is the right JS detection threshold?**  
**Current heuristic:** body length < 500 chars OR presence of `<div id="root">` without children.  
**Risk:** False positives (triggering Playwright for a static site) are expensive (Playwright is ~10× slower than httpx). False negatives (not triggering Playwright for a JS site) mean missing MRF links.  
**Recommendation:** Test against 100 hospital websites manually before setting the threshold. Aim for false positive rate < 10%.

**Q7: How long should the annual Cloud Run Job run before being considered stuck?**  
**Current setting:** 24-hour task timeout.  
**Context:** 7,000 hospitals × ~3 requests × 2s/domain = worst case ~23 hours. 24 hours is a tight window.  
**Recommendation:** Increase to 48 hours to handle slow hospital servers and rate limiting. Cloud Run Jobs support up to 7 days.

**Q8: Should the NPPES bulk download be stored in GCS for re-use, or re-downloaded each year?**  
**Context:** The NPPES full replacement file is ~8GB compressed. Re-downloading each year is slow (20-30 minutes). Storing in GCS costs ~$0.80/year (8GB × $0.10/GB-month × 1 month).  
**Recommendation:** Store in GCS. Upload once, scan from GCS stream each year. Cheaper and faster than re-downloading.

**Q9: How should the pipeline handle a hospital that merges with or is acquired by another system mid-year?**  
**Context:** Hospital M&A is frequent. An acquired hospital may redirect its website to the acquiring system's website, or its MRF may be folded into the system's TOC file.  
**Recommendation:** The `CHOW_DT` (change of ownership date) field from the POS file flags this. For hospitals with a CHOW_DT in the current year, force re-crawl even if the MRF URL is already known.

**Q10: What happens to hospitals that are in `hospital_directory` but no longer in the CMS PI list?**  
**Context:** ~100-200 hospitals close or lose Medicare certification each year.  
**Recommendation:** Do NOT delete them from `hospital_directory` — their historical charge data in `hospital_charges` is still valid for analyzing bills from prior years. Add a `cms_active` boolean column to flag them as inactive.

### 14.3 Coverage Questions

**Q11: What is the expected MRF URL coverage gap that can't be automated?**  
**Estimate:** ~5-15% of hospitals may be permanently uncrawlable due to:
- Aggressive CAPTCHA on price transparency pages
- MRF only accessible behind a patient portal login (non-compliant with CMS rules)
- MRF on a vendor portal that requires hospital-specific credentials
- Hospital website under construction or redirected
- Small critical access hospitals with minimal web presence

**Q12: Should there be a manual data entry UI for hospitals that the crawler can't find?**  
**Context:** For the top 500 hospitals by patient volume, having their MRF is high-value. If the crawler fails, manual entry by a ClaroBill team member is worth the effort.  
**Recommendation:** Yes — build a simple admin interface (or even a Google Sheet) where team members can submit `{ccn, mrf_url}` pairs. These get imported via a small script that writes to `hospital_directory` with `discovery_method = 'manual'`.

**Q13: Is there a CMS or state government data source that directly maps hospital websites to CCNs?**  
**Research needed:** Some state health departments maintain hospital directories with official websites. California (OSHPD), New York (SPARCS), Texas (THCIC), Florida (AHCA) all have hospital data programs.  
**Action needed:** Research each state's data availability. A state-by-state website supplement could add another 5-10% coverage for states with good data programs.

**Q14: Should the pipeline also capture hospital group purchasing organization (GPO) memberships?**  
**Context:** GPO memberships affect negotiated rates. This data is not publicly available but could improve ClaroBill's analysis quality.  
**For now:** Out of scope. Document for future enhancement.

---

## 15. Edge Cases and Known Challenges

### 15.1 Hospital Systems with Multi-Level TOC

Some large systems (Kaiser Permanente, VA Health System) have a regional TOC that links to regional index files, which in turn link to facility-level MRF files. The Stage 5 TOC expander needs to handle at least 2 levels of nesting.

**Implementation:** Make `expand_toc()` recursive with a max depth of 3. Track visited URLs to prevent infinite loops.

### 15.2 MRF Files Served Behind a Query String (Non-Standard)

Some hospital vendors serve MRF files at URLs like:
`https://vendor.com/mrf?hospital_id=12345&type=standard_charges`

The URL has no file extension. Detection strategy: if `Content-Type` is `application/json` or `text/csv` and the response body looks like an MRF, treat it as a direct download even without a file extension. The `_infer_extension()` function in the existing scraper handles this via `Content-Type`.

### 15.3 ZIP Files Containing Multiple MRFs

Some hospital systems ZIP multiple MRF files (one per payer) into a single download. The validator's ZIP handling (Stage 5) must enumerate all files inside the ZIP and validate each one, inserting multiple rows into `mrf_toc_index`.

### 15.4 Excel (XLSX) Files

Some smaller hospitals still publish their charge data as Excel files. These are technically CMS non-compliant (v2.0.0 requires JSON or CSV) but are still valuable. The validator should:
1. Accept `.xlsx` files
2. Use `openpyxl` to read the first sheet
3. Write the data as CSV to GCS staging for the parser to handle
4. Flag with `schema_version = 'xlsx'` in `hospital_directory`

### 15.5 The `/robots.txt` Disallow Problem for Price Transparency

Some hospital websites have a blanket `Disallow: /` in `robots.txt` (usually a misconfiguration). CMS regulations override this — hospitals are legally required to make MRF files publicly accessible. The recommended approach: still respect `robots.txt`, but flag these hospitals in the manual curation queue. A human can then submit the MRF URL directly (bypassing crawling entirely).

### 15.6 Geographic Name Ambiguity in Website Discovery

"Memorial Hospital" is the name of hospitals in dozens of cities. Stage 3's domain pattern inference and Stage 4's cross-validation both need to verify the found website corresponds to the correct hospital by checking city + state in the page content.

### 15.7 Temporary Hospital Website Outages

Some hospital websites are down or redirecting during the annual crawl (scheduled maintenance, migrations). Mitigation: if a hospital's website returns 503/502, mark it with `error_stage = 'crawl_complete'` but set `crawl_complete_at = NULL`. Retry up to 3 times with 1-hour delays before giving up.

### 15.8 MRF Files Hosted on Third-Party Platforms

Many hospitals use third-party vendors (ClearPoint, Turquoise Health, Strata, etc.) to host their MRF files. The vendor URL may look like:
`https://mrf.turquoisehealth.com/hospital-name_standardcharges.json.gz`

The crawler will find these via the hospital's price transparency page link. The validator should recognize known vendor domains and fast-track them through validation (skip content sampling if the domain is in a trusted vendor allowlist).

**Known MRF vendor domains to add to trusted allowlist:**
- `mrf.turquoisehealth.com`
- `transparency.hhs.gov` (CMS direct)
- `healthcare.ascension.org`
- `hcahealthcare.com`
- `apps.para-hcfs.com`
- `edge.sitecorecloud.io` (Sutter Health)
- `s3.amazonaws.com` (common for hospitals hosting on S3)
- `blob.core.windows.net` (Azure Blob)
- `storage.googleapis.com` (GCS)

---

## 16. Coverage Improvement Roadmap

### Year 1 (First Run) — Target: 70% Coverage

Focus: Get the pipeline working end-to-end. Accept some gaps.
- CMS PI list seed + POS file NPI mapping
- NPPES + Wikidata website resolution
- Google Places API for remaining hospitals
- Basic crawler (httpx + Playwright)
- TOC expansion for major systems

**Expected outcome:** ~5,000 hospitals with validated MRF URLs (70%)

### Year 2 — Target: 85% Coverage

Focus: Close the gaps identified in Year 1.
- Manual curation of top 500 unresolved hospitals
- State health department data integration (CA, NY, TX, FL)
- Improve JS detection heuristics with Year 1 false positive data
- Add Wayback Machine fallback for 404 URLs
- Tune fuzzy matching threshold for TOC facility→CCN mapping

**Expected outcome:** ~6,000 hospitals with validated MRF URLs (85%)

### Year 3+ — Target: 95%+ Coverage

Focus: Near-complete coverage.
- Admin UI for manual MRF URL submission
- Hospital system acquisition tracking (CHOW monitoring)
- CommonWell/Carequality provider directory integration (if accessible)
- CMS FHIR endpoint discovery (CMS is moving toward FHIR-based price transparency)
- Automated re-validation of stale URLs using Wayback Machine

**Expected outcome:** ~6,650+ hospitals (95%+)

### Future Enhancement: Real-Time MRF Change Detection

Instead of once-a-year discovery, monitor each hospital's MRF URL for changes using the `Last-Modified` and `ETag` headers (the weekly scraper already does this). Add a webhook or notification system that flags when an MRF has been updated outside the normal weekly scrape cycle — some hospitals update mid-year when CMS issues new rate guidance.

---

*Document created: April 2026*  
*Last updated: April 2026*  
*Owner: ClaroBill Engineering*  
*Related: `pipeline/deploy.sh`, `scripts/bootstrap_hospital_directory.py`, `scripts/scrape_payerset_directory.py`*