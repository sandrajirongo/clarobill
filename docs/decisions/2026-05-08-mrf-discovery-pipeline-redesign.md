# MRF Discovery Pipeline Redesign

**Date:** 2026-05-08  
**Status:** Proposed  
**Author:** Sandra

---

## Problem

The discovery pipeline conflates two logically distinct outputs in `hospital_directory`:

- **Stages 1-3** identify hospital identity: who is this hospital, what is its website URL.
- **Stage 4** crawls that website to find the actual MRF file URL.

Both outputs currently write to `hospital_directory`, which means a single row mixes hospital identity fields (`hospital_name`, `state`, `ccn`, `hospital_npi`) with MRF discovery results (`mrf_url`, `price_transparency_page_url`, `mrf_discovery_method`). This breaks separation of concerns and makes it impossible to partition or expire MRF discovery results independently of hospital identity.

Stage 4 also has three coverage gaps:
1. Only follows links whose **anchor text** contains price-transparency keywords. Links like `<a href="/patients/billing/standard-charges">Learn More</a>` are skipped because "Learn More" has no keywords, even though the href path clearly points to the right page.
2. Only finds files linked in `<a href>` tags. Files referenced in JavaScript variables, `data-` attributes, or inline `<script>` blocks are invisible.
3. Stops at depth 2. Some hospital system hierarchies are 3 levels deep: `homepage → "For Patients" → "Billing & Financial" → MRF files`.

---

## Decision

### 1. Split `hospital_directory` into two tables

**`hospital_directory`** becomes a pure hospital identity table. Stages 1-3 write here. Stage 4 does not.

New columns added to `hospital_directory`:
- `ein STRING` — IRS EIN, nullable until IRS Form 990 loader is built
- `website_discovery_method STRING` — how the website URL was found (`tier1_direct`, `tier2_pattern`, `tier3_google_places`)
- `last_website_validated_at TIMESTAMP` — drives the DATE partition

Deprecated columns (stop writing, do not drop yet, data moves to `hospital_price_transparency`):
- `mrf_url`, `price_transparency_page_url`, `mrf_pricing_effective_year`, `mrf_file_format`, `mrf_file_size_bytes`, `mrf_discovery_method`

BQ cannot add a partition to an existing table. The migration uses CTAS to preserve the 53,662 existing rows:

```sql
CREATE TABLE `clarobill-prd.hospital_prices.hospital_directory_new`
PARTITION BY DATE(last_website_validated_at)
CLUSTER BY ccn, hospital_npi
AS SELECT *, CAST(NULL AS STRING) AS ein,
              CAST(NULL AS STRING) AS website_discovery_method,
              CAST(NULL AS TIMESTAMP) AS last_website_validated_at
FROM `clarobill-prd.hospital_prices.hospital_directory`;

DROP TABLE `clarobill-prd.hospital_prices.hospital_directory`;
ALTER TABLE `clarobill-prd.hospital_prices.hospital_directory_new` RENAME TO hospital_directory;
```

Existing rows land in the `__NULL__` partition. Future Stage 3 runs populate `last_website_validated_at`.

---

**`hospital_price_transparency`** is a new table: Stage 4 output. One row per discovered MRF file URL per hospital.

```sql
CREATE TABLE IF NOT EXISTS `clarobill-prd.hospital_prices.hospital_price_transparency` (
  ccn                         STRING NOT NULL    OPTIONS(description="CMS Certification Number. Primary join key to hospital_directory."),
  hospital_npi                STRING             OPTIONS(description="NULL at Stage 4 insert; backfilled by scraper from file content."),
  mrf_url                     STRING NOT NULL    OPTIONS(description="Public URL of the MRF file as discovered by Stage 4."),
  file_format                 STRING             OPTIONS(description="True inner content format: json, csv, xlsx, tsv, or zip. NULL at Stage 4 insert; set by scraper."),
  price_transparency_page_url STRING             OPTIONS(description="Intermediate webpage URL where the MRF URL was found."),
  mrf_discovery_method        STRING             OPTIONS(description="pass1_cms_filename | pass2_keyword_anchor | pass3_data_ext | pass4_html_scan | path_heuristic"),
  first_discovered_at         TIMESTAMP NOT NULL OPTIONS(description="When Stage 4 first found this URL."),
  last_validated_at           TIMESTAMP          OPTIONS(description="Last HEAD request confirming URL is still reachable."),
  last_scraped_at             TIMESTAMP          OPTIONS(description="Last successful scraper download. Drives the DATE partition."),
  last_modified_header        STRING             OPTIONS(description="HTTP Last-Modified value from most recent HEAD or GET."),
  is_active                   BOOL DEFAULT TRUE  OPTIONS(description="False if most recent HEAD returned 404 or URL is otherwise unreachable.")
)
PARTITION BY DATE(last_scraped_at)
CLUSTER BY ccn, hospital_npi;
```

**Why CCN as primary key:** CCN coverage is 95.6% (53,662 / 56,116 hospitals) vs NPI at 67.3%. CCN is the right join key to `hospital_directory`.

**`(ccn, mrf_url)` is the de-facto unique key.** BQ doesn't enforce uniqueness. The Stage 4 MERGE on `(ccn, mrf_url)` is the only enforcer. Never INSERT directly — always go through the MERGE.

**Rows start in the `__NULL__` partition.** Stage 4 discovers URLs but the scraper hasn't run yet, so `last_scraped_at` is NULL. Once the scraper downloads the file it sets `last_scraped_at`, moving the row into a dated partition.

**`pricing_effective_date` does NOT live here.** Timestamps in this table track operational events (discovery, validation, scrape). The date a price list is effective belongs in `hospital_charges` only.

**Multi-hospital listing pages (known limitation):** When Stage 4 finds 80 CSV files on a Kaiser listing page, it attributes all of them to the parent system CCN. Resolution happens in two passes:
- Option 1 (CCN from CMS-compliant filename): extract the 6-digit prefix from filenames like `123456_kaiser-oakland_standardcharges.csv` and look it up in `hospital_directory.ccn`.
- Option 2 (NPI from file content): the scraper resolves NPI at download time and backfills `hospital_price_transparency.hospital_npi`.

---

### 2. Stage 4 crawler improvements

#### Pass 3: `<a href>` by file extension (new)

Pass 1 requires a `\d{6,12}` CCN/EIN prefix in the filename. Pass 2 requires a price-transparency keyword in the anchor text. Pass 3 catches everything else with a data file extension:

```python
_DATA_FILE_EXTS = (".csv", ".json", ".xml", ".xlsx",
                   ".csv.gz", ".json.gz", ".zip", ".xml.gz", ".gzip")
for anchor_match in re.finditer(r'<a\s+[^>]*?href=["\']([^"\']+)["\']', html, re.IGNORECASE):
    href = anchor_match.group(1)
    if href.lower().split("?", 1)[0].endswith(_DATA_FILE_EXTS):
        found.add(_resolve_url(base_url, href))
```

Example now caught: `<a href="/files/kaiser-oakland-2024-charges.csv">Kaiser Oakland Medical Center</a>`

#### Pass 4: full HTML body scan (new)

Pass 3 only catches `<a href>` tags. Pass 4 scans the entire raw HTML for any URL-shaped string ending in a data file extension — catches JS variables, `data-` attributes, and inline `<script>` blocks:

```python
for url_match in re.finditer(
    r'["\'\ (=]([/][^"\'\>\s)]+(?:' + '|'.join(re.escape(e) for e in _DATA_FILE_EXTS) + r'))',
    html, re.IGNORECASE,
):
    found.add(_resolve_url(base_url, url_match.group(1)))
```

Trade-off: may produce false positives (download links unrelated to price transparency). HEAD validation at the validation stage is the guard.

#### PATH_HEURISTICS as anchor follow signal

The current `_follow_keyword_anchors` only follows a link if the anchor text or href contains a keyword from `_KEYWORD_RE`. Links like `<a href="/patients/billing/standard-charges">Learn More</a>` are skipped because "Learn More" has no keywords.

New: build `_PATH_HEURISTIC_RE` from `PATH_HEURISTICS` and add it as a third follow condition:

```python
if (not _KEYWORD_RE.search(clean_text)
        and not _KEYWORD_RE.search(href)
        and not _PATH_HEURISTIC_RE.search(href)):
    continue
```

#### Depth and breadth limits

| Parameter | Before | After | Reason |
|---|---|---|---|
| `MAX_FOLLOW_DEPTH` | 2 | 3 | Some systems are 3 levels deep |
| `MAX_FOLLOWUPS_PER_PAGE` | 5 | 15 | Large system homepages have 10+ keyword nav sections |

Worst-case fan-out: `15^3 = 3,375` page fetches per hospital. Bounded by `PER_HOST_MAX_CONCURRENT = 2` — no hammering.

#### Listing-page detection logging

Log when a single page yields 5+ file links — surfaces Kaiser, Sutter, HCA, CommonSpirit for manual review:

```python
before = len(found_urls)
for link in _extract_links_from_html(html, base_url):
    found_urls.setdefault(link, discovery_method)
if len(found_urls) - before >= 5:
    logger.info("[listing_page] %s yielded %d file links", base_url, len(found_urls) - before)
```

---

### 3. Scraper reads from `hospital_price_transparency`

The scraper currently reads `mrf_url` from `hospital_directory`. After this change it joins both tables:

```sql
SELECT pt.ccn, pt.hospital_npi, pt.mrf_url, hd.hospital_name, hd.state
FROM `clarobill-prd.hospital_prices.hospital_price_transparency` pt
JOIN `clarobill-prd.hospital_prices.hospital_directory` hd ON pt.ccn = hd.ccn
WHERE pt.is_active = TRUE AND pt.mrf_url IS NOT NULL
```

After a successful download, the scraper backfills `hospital_price_transparency`:

```sql
UPDATE `clarobill-prd.hospital_prices.hospital_price_transparency`
SET file_format = @fmt,
    last_scraped_at = CURRENT_TIMESTAMP(),
    hospital_npi = COALESCE(hospital_npi, @resolved_npi)
WHERE ccn = @ccn AND mrf_url = @url
```

---

## Bucket rename (prerequisite)

Before any pipeline code changes, rename the archive bucket from `clarobill-mrf-archive-uscentral` to `mrf-archive` (short-name convention). This requires an account with `storage.buckets.delete` and `storage.buckets.create` — the pipeline SA cannot do this.

Files to update: `pipeline/scrape_hospital_mrfs.py`, `pipeline/deploy.sh`, `docs/operations/pipeline-runbook.md`, `CLAUDE.md`.

---

## Files changed

| File | Change |
|---|---|
| `scripts/mrf_discovery/migrate_bq_schema.py` | CTAS `hospital_directory` with new columns + partition; CREATE `hospital_price_transparency` |
| `scripts/mrf_discovery/stage4_extract_mrf_urls.py` | Pass 3 + Pass 4; expanded `_KEYWORD_RE`; `_PATH_HEURISTIC_RE` follow signal; `MAX_FOLLOWUPS_PER_PAGE` 5→15; `MAX_FOLLOW_DEPTH` 2→3; listing-page logging; MERGE to `hospital_price_transparency`; CCN extraction from CMS filenames |
| `pipeline/scrape_hospital_mrfs.py` | Read from `hospital_price_transparency`; write `file_format` to `mrf_archive_index`; backfill `hospital_price_transparency` post-scrape |
| `scripts/mrf_discovery/tests/test_stage4_crawler.py` | Pass 3 + Pass 4 tests; depth-3 test; listing-page log test; keyword expansion tests; path heuristic follow test |
| `docs/operations/pipeline-runbook.md` | Add `hospital_price_transparency` section; update Stage 4 coverage notes |

---

## Verification

1. Schema dry-run: `python scripts/mrf_discovery/migrate_bq_schema.py --dry-run`
2. Stage 4 tests: `python -m pytest scripts/mrf_discovery/tests/test_stage4_crawler.py -v`
3. Scraper smoke: run scraper locally with `--limit 5`, confirm reads from `hospital_price_transparency` and backfills `file_format`, `last_scraped_at`, `hospital_npi`
4. Coverage check after Stage 4 re-run:

```sql
SELECT mrf_discovery_method, COUNT(*) AS n
FROM `clarobill-prd.hospital_prices.hospital_price_transparency`
GROUP BY 1 ORDER BY 2 DESC;
```

5. Listing page check: grep Stage 4 logs for `[listing_page]` entries — confirm Kaiser, Sutter, HCA, CommonSpirit appear.

---

## Known issues / future work

- **Multi-hospital listing page attribution:** Files on a system listing page are initially attributed to the parent system CCN. Option 1 (CCN from filename) and Option 2 (NPI from content) correct attribution post-scrape, but the window between Stage 4 run and scrape run has incorrect CCN mapping.
- **EIN loader:** `hospital_directory.ein` is nullable until a separate IRS Form 990 loader is built.
- **Pass 4 false positives:** Scanning entire HTML body for file-extension URLs will produce some false positives. HEAD validation is the guard but increases request volume.
- **`MAX_FOLLOWUPS_PER_PAGE = 15` with `MAX_FOLLOW_DEPTH = 3`:** Monitor Stage 4 wall-clock time after first production run.
