# MRF coverage remediation — 2026-05-04 session ledger + Phase 4 design

**Audience:** Future ClaroBill engineers (and future-Sandra) reading this six
months from now. Single source of truth for what shipped on 2026-05-04 and
what's planned for the CSV-format MRF parser rollout.

**Trigger:** Investigation of the 5/3-5/4 8-hour parser run found that
**60% of the 1.07B `hospital_charges` rows had NULL `hospital_npi`** — those
charges existed but couldn't be joined to a hospital, so the rules engine
silently fell back to generic Medicare benchmarks for any bill that should
have matched them. Today's work fixes the root causes upstream and rebuilds
coverage from there.

---

## Part 1 — What shipped on 2026-05-04 (in order)

| # | Item | Commit | What it does |
|---|---|---|---|
| 1 | URL-NPI fallback + strict mode | `cb9b420` | Parser pulls NPI from URL filename when MRF JSON internals lack one. Rejects unresolvable blobs as `failed` instead of silently writing NULL-NPI rows. |
| 2 | NPPES-based EIN/slug → NPI resolver | `750f83b` | One-shot script that fuzzy-matches URL slugs against `bigquery-public-data.nppes.npi_raw` for the 158 ambiguous EIN-only URLs whose `hospital_directory` candidates were corrupted. |
| 3 | Scrape-time content validation | `e2745d4` | Scraper sniffs the first 4 KB of every HTTP response and rejects HTML / PDF / unknown formats before writing to staging or archive. Stops new garbage from accumulating. |
| 4 | Parser-from-`mrf_archive_index` driver | `5a1de5d` | New `PARSER_DRIVER=archive_index` mode reads pending work from BQ instead of walking the staging bucket. Reads bytes from `mrf-archive-clarobill-prd` (immutable) so pre-2026-05-04 cohorts whose staging copies were deleted are now reachable. |
| 5 | PostHog 7.x constructor fix (engine) | `93b22d8` | Hot-fix for unrelated PostHog deploy that had been failing health-check since `f9b1b96`. PostHog 7.14 renamed `api_key=` → positional `project_api_key`. |
| 6 | Dedupe `gcs_uri` in archive_index driver | `3684894` | Regression fix after a runaway loop appended 643,839 duplicate rows for Saint Michaels Medical Center. Cause: archive_index has multiple rows per URL (re-scrapes); without `GROUP BY gcs_uri` the loop re-processed the same blob N times. |
| 7 | Task sharding for archive_index driver | `6bc53c5` | `--tasks 6 --parallelism 6` on Cloud Run Jobs. Each task takes a `rows[task_index::task_count]` stripe of the deterministic-ordered pending list. Wall-clock projection drops from ~37 hours single-task to ~6 hours. |

### BigQuery data backfills run during the session

These were data ops only — no code, no commit. Documented here for forensic reproducibility.

| Operation | Rows updated |
|---|---:|
| `hospital_charges.hospital_npi` from URL regex (10-digit prefix) | 25,460,099 |
| `hospital_charges.hospital_npi` from unambiguous `hospital_directory.mrf_url` join | 19,267,106 |
| `hospital_charges.hospital_npi` from NPPES resolver (75 of 210 URLs accepted) | tens of millions across +62 hospitals |
| `mrf_archive_index.hospital_npi` from URL regex | 602 |
| `mrf_archive_index.hospital_npi` from directory join | 2,192 |
| `mrf_archive_index` non-JSON failed → `skipped` reclassify | 1,981 |
| `mrf_archive_index` cohort A `failed` → `pending` reset for retry | 2,111 |
| Cleanup of 643,839 duplicate Saint Michaels rows from runaway loop | 643,839 (deleted) |

### Coverage delta

|  | Session start | After backfills | After NPPES resolver | After parser retry (in flight) |
|---|---:|---:|---:|---:|
| Distinct hospital NPIs in `hospital_charges` | 169 | 192 | **254** | **261+** |
| 2026-priority-year hospitals | 144 | 162 | ~210 | growing |
| NULL-NPI rows | 650.4M | 605.7M | 390.7M | 390.7M (held; strict mode prevents new NULLs) |

### Test count delta

`pipeline/tests/` went from 22 tests → **65 tests** across:
- `test_hospital_mrf_utils.py` — URL-NPI extraction + format sniffer (32 tests)
- `test_scrape_validation.py` — `_PrependedStream` + scraper rejection path (11 tests)
- `test_archive_index_driver.py` — URI parsing, retry-reset, sharding, dedupe (15 tests)
- pre-existing BOM, per-row tolerance, non-seekable stream tests (7 tests)

---

## Part 2 — Phase 4 (CSV-format MRF parser) design

### Scope correction

The original `docs/future-improvements/csv-mrf-parser.md` (2026-04-29) assumed
~11K skipped CSV blobs. **Actual scope as of 2026-05-04 is much larger:**

| Format (`mrf_archive_index.parse_status='skipped'`) | Blobs | Total GB |
|---|---:|---:|
| `.csv` | 9,644 | **1,861** |
| `.csv.gz` | 1,934 | 28 |
| `.zip` (likely contains CSV or JSON) | 1,628 | 84 |
| **Total** | **13,206** | **~1,973 GB** |

This is a **~2 TB** unparsed pricing-data tail. The biggest single coverage
opportunity remaining after items 1-3 above. Most of the volume is from
~5-10 health systems that standardized on CSV: Sutter Health, Kaiser
Permanente, HCA Healthcare, Mercy Health, Ascension, Tenet, CommonSpirit,
Providence-CSV-cohort, Trinity, Bon Secours.

### Design principles

1. **Vendor-detection by header signature, not URL.** A health system can
   change CDN providers without changing CSV layout, and one CDN can host
   files for multiple systems. The CSV header line is the most stable
   fingerprint — hash it, look it up in a registry, dispatch to the
   appropriate column-mapper.

2. **Column maps are data, not code.** Each vendor's mapping lives in a
   YAML/Python-dict registry, not a special-case `if vendor == "sutter"`
   branch. Adding a new vendor is a one-file diff with a fixture.

3. **Stream, never load.** The 1.86 TB raw-CSV figure includes individual
   files in the 100s of MB. Use `csv.DictReader` over a streaming GCS
   read; emit `ChargeRow` objects through the same NDJSON-staging path
   as the JSON parser uses. No `pandas.read_csv` of full files.

4. **Reject silently-wrong matches.** If a CSV's header signature doesn't
   match a known vendor AND lenient-substring detection produces low
   confidence, mark the blob `failed` with `parse_error="csv vendor not
   identified"`. We don't write to `hospital_charges` with guessed
   columns — wrong charges in dispute letters are worse than missing data.

5. **Effective-year resolution must work without `last_updated_on`.** CSV
   files have no canonical "schema version" or "last updated" field.
   Fall back to: scraper-stamped HTTP `Last-Modified` header → calendar
   year. The existing `effective_year.resolve_year()` already supports this.

6. **NPI resolution from URL (item 1) applies to CSV files too.** The
   strict-mode check stays on. CSVs without an NPI source get `failed`,
   not silently NULL'd.

7. **Re-use, don't rewrite.** The infrastructure built in items 1-7 above
   already supports CSV: `sniff_mrf_format()` already returns `'csv'`,
   `_PrependedStream` works for any byte stream, and the
   archive_index driver opens any `gcs_uri` regardless of format. The
   only new code is the column-mapping layer.

### Architecture

```
                    ┌─────────────────────────────────┐
                    │ archive_index_driver / bucket   │
                    │ walk supplies (blob, meta)      │
                    └────────────────┬────────────────┘
                                     │
                                     ▼
                    ┌─────────────────────────────────┐
                    │ sniff_mrf_format(prefix, url)   │
                    │ → 'json' | 'csv' | 'zip' | ...  │
                    └─────────┬──────────────┬────────┘
                              │              │
                       json   │       csv    │  zip
                              ▼              ▼     │
                    ┌─────────────┐  ┌──────────┐  │
                    │stream_      │  │stream_   │  │
                    │charges_v2() │  │charges_  │  │
                    │ (existing)  │  │csv()     │  │
                    │             │  │ (NEW)    │  │
                    └──────┬──────┘  └────┬─────┘  │
                           │              │        │
                           │              │        ▼
                           │              │  ┌──────────────┐
                           │              │  │unzip + recur │
                           │              │  │(Phase 4c)    │
                           │              │  └──────┬───────┘
                           │              │         │
                           ▼              ▼         ▼
                    ┌─────────────────────────────────┐
                    │ ChargeRow stream → NDJSON stage │
                    │ → BigQuery load (existing)      │
                    └─────────────────────────────────┘
```

### `stream_charges_csv()` contract

```python
def stream_charges_csv(
    file_obj: BinaryIO,
    hospital_npi: str,
    pricing_effective_year: int,
    scraped_at: str,
    *,
    source_mrf_url: str,
    source_gcs_uri: str | None,
) -> Iterator[ChargeRow]:
    """Stream-parse a CSV MRF, emit one ChargeRow per (code × payer × setting).

    Detects vendor via header signature, applies the matching column map,
    then yields rows. Same return type as stream_charges_v2 so the parser
    core treats both formats interchangeably.

    Raises CsvVendorNotIdentified if the header signature doesn't match any
    registered vendor and lenient-substring detection scores below threshold.
    The caller catches this and marks the blob 'failed' with a clear reason.
    """
```

### Vendor registry

```python
# pipeline/csv_vendors.py
@dataclass(frozen=True)
class CsvVendor:
    name: str                          # "sutter", "kaiser", "hca", ...
    header_signature: frozenset[str]   # set of normalised column names
    column_map: dict[str, str]         # canonical → vendor-specific
    long_format: bool                  # True if one-row-per-payer; False if wide

VENDORS: list[CsvVendor] = [
    CsvVendor(
        name="sutter",
        header_signature=frozenset({
            "code", "code_type", "description", "rev_code",
            "gross_charge", "discounted_cash_price",
            "min_negotiated_charge", "max_negotiated_charge",
            "payer_name", "plan_name", "negotiated_charge",
        }),
        column_map={
            "code": "code",
            "code_type": "code_type",
            "description": "description",
            "gross_charge": "gross_charge",
            "discounted_cash_price": "discounted_cash_price",
            "min_negotiated": "min_negotiated_charge",
            "max_negotiated": "max_negotiated_charge",
            "payer_name": "payer_name",
            "plan_name": "plan_name",
            "negotiated_charge": "negotiated_charge",
            "negotiated_type": "rate_methodology",
            "setting": "setting",
        },
        long_format=True,
    ),
    # … one entry per vendor we ship in 4a-4d …
]
```

Vendor detection:
1. Read header line, normalize columns (lowercase, strip whitespace, collapse
   internal punctuation).
2. Hash to `frozenset[str]`.
3. Exact match against any `VENDORS[*].header_signature` → use that map.
4. If no exact match, score each vendor by Jaccard similarity of normalized
   columns. Accept the top vendor only if score ≥ 0.75 AND margin ≥ 0.1
   over runner-up — same conservative thresholds as the NPPES resolver.
5. If no match passes, raise `CsvVendorNotIdentified`.

---

## Part 3 — Phase rollout

### Phase 4a (this session)

**Deliverable:** Framework + Sutter parser + tests.

- [ ] `pipeline/csv_vendors.py` — `CsvVendor` dataclass, `VENDORS` registry, `detect_vendor(header_columns)` → `CsvVendor | None`.
- [ ] `pipeline/hospital_mrf_utils.py` — `stream_charges_csv()` generator that takes a `BinaryIO`, runs `csv.DictReader`, dispatches to `_expand_csv_row()` per row.
- [ ] `pipeline/parse_hospital_mrfs.py` — extend `process_blob_with_meta` so when `sniff_mrf_format` returns `'csv'`, it routes to `stream_charges_csv` instead of `stream_charges_v2`. JSON path is unchanged.
- [ ] First vendor: **Sutter Health** — single CSV format used by ~30 NorCal acute-care hospitals. Most uniform schema in the cohort.
- [ ] `pipeline/tests/test_csv_parser.py` — fixture-based tests:
  - exact-header detection
  - lenient-Jaccard detection
  - `CsvVendorNotIdentified` for unknown headers
  - `stream_charges_csv` end-to-end on a 5-row Sutter fixture
  - long-format expansion (one input row → multiple ChargeRow rows when payers are columns)
- [ ] Run dry on a single Sutter blob from `mrf_archive_index.parse_status='skipped'`, confirm row count matches manual line count of the source CSV.
- [ ] Reset Sutter URL `parse_status='skipped'` → `'pending'` for retry via the archive_index driver.

**Expected unlock:** ~30 hospitals (Sutter NorCal cluster).

### Phase 4b (next session)

**Deliverable:** Vendors 2-5.

Priority order (by row-count contribution, estimated):

1. **Kaiser Permanente** — ~40 hospitals across CA, OR, WA, CO, GA, HI. Different format than Sutter; one CSV per facility-year.
2. **HCA Healthcare** — ~180 hospitals nationwide. Largest hospital chain in the US by facility count. CSV is in their proprietary `mrfs.hyvehealthcare.com` template (we already see this URL pattern in the corpus).
3. **Mercy Health** — ~50 hospitals across MO, OK, AR, KS. Same `christushealth`-style format as Christus.
4. **Tenet Healthcare** — ~60 hospitals nationwide. Hosted on `mrfs.hyvehealthcare.com` so likely shares the HCA format — opportunity to reuse the column map.

**Expected unlock:** ~330 hospitals. Combined with 4a, this is the bulk of the
CSV-only chain coverage.

**Risk to watch:** Kaiser publishes "long-format with payer rows" while HCA
publishes "wide-format with payer columns." The column-map struct must
support both via `long_format: bool` + a per-vendor `expand_row()` callback.

### Phase 4c

**Deliverable:** ZIP-unwrap + recursive dispatch.

- [ ] `pipeline/zip_unwrap.py` — streams `zipfile.ZipFile` over a GCS-backed
      file, yields `(inner_name, BinaryIO)` per entry.
- [ ] `process_blob_with_meta` recurses: if `sniff_mrf_format(...)` returns
      `'zip'`, iterate entries; for each entry re-sniff format and dispatch.
      Each emitted entry produces its own NDJSON staging blob and BQ load.
- [ ] `mrf_archive_index` is **not** updated per inner entry — the outer
      gcs_uri stays the canonical row, with `parse_error` recording how
      many entries succeeded vs failed.

**Expected unlock:** ~1,628 ZIP blobs (84 GB). Mostly Mass General Brigham,
Sentara, and similar systems that bundle per-facility files into one ZIP.

**Risk to watch:** ZIP-of-ZIP nesting (Sentara has been observed doing this).
Cap recursion depth at 2 to avoid pathological inputs.

### Phase 4d

**Deliverable:** Long-tail vendors + automation.

- [ ] Author column maps for Ascension, CommonSpirit, Providence-CSV cohort,
      Bon Secours, Trinity Health, and any remaining vendors with > 10 blobs
      in the corpus.
- [ ] Add a daily Cloud Run Job — `clarobill-csv-vendor-discovery` — that
      samples 50 currently-failing CSV blobs per day, clusters their headers
      by Jaccard similarity, and posts a summary so an engineer can author
      a new map per cluster.
- [ ] Promote `stream_charges_csv` to the main scraper-pre-validation path:
      CSV files no longer need to be `parse_status='skipped'` once a vendor
      map exists.

**Expected unlock:** the long-tail ~10% of CSV blobs that the top 8 vendors
don't cover.

---

## Part 4 — Test strategy

Every CSV vendor map must include:

1. **Header-detection test** — exact-match + lenient-substring path, both
   passing the conservative threshold.
2. **End-to-end fixture** — a 10-50 row CSV in `pipeline/tests/fixtures/csv/`
   that produces a known number of `ChargeRow` outputs. Numbers must come
   from the real published file, sliced to a representative sample.
3. **Negative tests** — malformed rows are skipped (per-row tolerance,
   matching `stream_charges_v2`'s behaviour from postmortem #5b).
4. **Effective-year fallback** — fixture with no inline year hint relies
   on the `last_modified` HTTP header from blob metadata.

The full pipeline regression gate (Rule 13 of `CLAUDE.md`) must remain
green at every commit boundary.

---

## Part 5 — Risk register

| Risk | Mitigation |
|---|---|
| **A vendor's column map is subtly wrong → `hospital_charges` rows are wrong → false-flag dispute letters.** | Conservative detection thresholds (0.75 score, 0.1 margin); mandatory fixture round-trip before shipping a map; parse_error="csv vendor map mismatch" if row counts deviate >5% from raw line count. |
| **CSV file is real data but its vendor isn't yet registered.** | Mark `failed`, not `skipped` — the daily discovery cron in 4d catches new vendors. |
| **CSV blobs land in `hospital_charges` with the wrong `pricing_effective_year` because there's no JSON `last_updated_on` field.** | Use HTTP Last-Modified header from blob metadata; fall back to current calendar year. Document this drift bound in operations.md. |
| **`pandas.read_csv` is tempting for vendor maps with messy quoting.** | Use stdlib `csv` only — it's stream-friendly and avoids the 100MB+ memory cost. |
| **A vendor has multiple historical CSV layouts (schema drift).** | `CsvVendor.header_signature` is a `frozenset` — one vendor can have multiple `CsvVendor` entries with different signatures. Detection picks the matching one. |
| **An XLSX or PDF blob is misclassified as CSV by the sniffer.** | The `sniff_mrf_format()` magic-byte check catches XLSX and PDF before CSV; CSV is only reached when the bytes don't match any binary magic. |

---

## Part 6 — Status of the four checklist items (top-level)

- [x] **1. NPPES-based EIN/slug → NPI resolver** — DONE 2026-05-04 (commit `750f83b`)
  - Result: 75 of 210 ambiguous URLs resolved (35.7%). hospital_charges +62 hospitals.

- [x] **2. Postmortem #1 — scrape-time content validation** — DONE 2026-05-04 (commit `e2745d4`)
  - `sniff_mrf_format()` + `_PrependedStream` + scraper rejection of HTML/PDF/unknown.
  - 23 new tests across `test_hospital_mrf_utils.py` (sniffer) and `test_scrape_validation.py`.

- [x] **3. Postmortem #2 — parser pulls work from `mrf_archive_index`** — DONE 2026-05-04 (commits `5a1de5d`, `3684894`, `6bc53c5`)
  - `PARSER_DRIVER=archive_index` mode + `--tasks 6` sharding.
  - 15 new tests in `test_archive_index_driver.py`.
  - Retry execution `clarobill-mrf-parser-8pxsj` running ~6h projected for full drain.

- [ ] **4. CSV-format MRF support** — IN PROGRESS via this design doc.
  - 4a (Sutter + framework) in scope for this session.
  - 4b-4d planned for follow-up sessions.

---

## Part 7 — Out of scope for the entire 4a-4d rollout

- **PDF MRF parsing.** Every observed PDF in the archive was a landing page,
  good-faith-estimate notice, or marketing brochure — not a chargemaster.
  Stay rejected.
- **XLSX MRF parsing.** ~1,981 blobs already reclassified `skipped` with
  reason `format not yet supported by parser: xlsx`. If a vendor lands here
  with real data, build an `xlsx_vendors.py` registry mirroring the CSV one.
  No work planned.
- **Storage cleanup of garbage in `mrf-archive-clarobill-prd`.** Sandra's
  decision 2026-05-04: Coldline cost is ~$0.40/month for the entire archive,
  not worth deletion risk given the cohort is mixed with real data.
- **30-day lifecycle on `gs://mrf-staging`.** Sandra's decision 2026-05-04:
  keep all blobs.
- **56 EIN-only URLs not in `hospital_directory` at all** — discovery gap,
  not a parsing gap. Belongs in a Stage 4 follow-up.

---

## References

- Postmortem that triggered items 1-3: `docs/postmortems/2026-05-03-mrf-pipeline-postmortem.md`
- Operations runbook: `docs/operations/pipeline-runbook.md`
- Phase 4 (effective-dated archive) original design: `docs/decisions/2026-04-29-phase-4-design.md`
- Original CSV-parser sketch (now superseded by this doc): `docs/future-improvements/csv-mrf-parser.md`
- NPPES resolver implementation: `scripts/mrf_discovery/resolve_ambiguous_npis.py`
- Parser source: `pipeline/parse_hospital_mrfs.py`
- Scraper source: `pipeline/scrape_hospital_mrfs.py`
- Shared format utilities: `pipeline/hospital_mrf_utils.py`
- Test suites: `pipeline/tests/test_*.py`
