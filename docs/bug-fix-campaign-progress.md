# Bug-fix campaign progress (2026-05-04 → ongoing)

Plan: `~/.claude/plans/vectorized-mapping-waffle.md` (Sandra-local, not in repo).

Multi-agent audit on 2026-05-04 surfaced **29 confirmed findings**: 5 stop-the-line, 11 high-severity, 13 medium. Plus 3 regression-gate breakages that were repaired in Phase 0.

---

## Status snapshot

| Phase | Scope | Status | Commits |
|---|---|---|---|
| **0** | Regression gate green | ✅ done 2026-05-04 | `5b232b6` `29583da` `e294ee7` |
| **1** | Boundary contract (S1) | ✅ done 2026-05-04 | `1c883af` `a0fd6b3` `1264f6b` `ba94306` `009ea70` |
| **CI** | GitHub Actions + Supabase migration-check | ✅ done 2026-05-04 | `8f1d3c8` `f236283` `0624ad9` `694de6a` `5b1ea62` (PR #8 merged) |
| **2** | S2 NCCI modifier-59 per-line | ✅ done 2026-05-04 | `41412c1` |
| **3** | High-severity engine (H1, H2, H3, H8, H9, H10) | ✅ done 2026-05-04 | `be0c76a` `0010f73` `98f51c5` `d5ffd8b` `d3147ac` `45682cc` |
| **4** | MRF pipeline (S3, S4, S5, H4, H5, H6, H7) | ✅ done 2026-05-04 | `062d8dd` `9bf138c` `073f1a1` `d7ba465` `a446c62` `5dbe5a0` `fffda05` |
| **5** | Medium-severity (M3, M4, M5, M6) | ✅ done 2026-05-04 | `587ef04` `ac49324` `8f80207` |
| **6** | Type-truth migration (M7-M13) | ✅ done 2026-05-04 | `107b4b4` `79211f9` `0244166` `c60ea3b` `026e7e1` |
| **6** | Type-truth migration (M7-M13) | pending | — |
| **7** | Universal coverage audit (Rule 8) | pending | — |

---

## Findings closed

### Stop-the-line

| Tag | Description | Commits |
|---|---|---|
| **S1** | BillingError snake/camel mismatch — patient report would crash on first real finding | Zod schemas (`1c883af`), engine alias_generator (`a0fd6b3`), web `.parse()` boundary (`1264f6b`), SQL backfill (`ba94306`), boundary contract test (`009ea70`) |
| **S2** | NCCI modifier-59 override applied per CPT instead of per line — masked unbundled siblings | `41412c1` |

### High-severity

| Tag | Description | Commit |
|---|---|---|
| **H1** | Comma-less ZIP captured as CPT (`Cleveland OH 44195`) | `98f51c5` |
| **H2** | Mileage `unit_charge` rounding lost cents — `qty × unit ≠ total` | `d5ffd8b` |
| **H3** | NCCI `affected_line_item_ids` covered both col1 + col2 — leaked into savings dedup keys | `45682cc` |
| **H4** | Tier 3 Places API booked cost meter BEFORE the request — phantom charges on connection errors | `fffda05` |
| **H5** | Stage 4 staging table prefix `_stage4_*` was hidden from default BQ listings | `d7ba465` |
| **H6** | Stage 1 CMS pagination had no hard cap — runaway loop on bad `count` response | `a446c62` |
| **H7** | Tier 1 invalid-URL rows stuck forever (Tiers 2/3 never re-processed) | `5dbe5a0` |
| **H8** | `AnalysisResult.total_charges` Decimal → JSON string instead of float | `be0c76a` |
| **H9** | NPI fallback regex accepted account/MRN/claim labels (Luhn alone = 10% false positive rate) | `d3147ac` |
| **H10** | `AnalyzeRequest` accepted any string for `state`/`zip_code`/`plan_type` | `0010f73` |
| **H11** | Stale `.venv` shebang from MedScan rename → mypy/ruff/pytest broken locally | Phase 0 (env fix) + `e294ee7` (typed Supabase row helpers, 210 mypy errors fixed) |

### Stop-the-line (continued)

| Tag | Description | Commit |
|---|---|---|
| **S3** | Stage 4 `_persist_results` flush failure silently retained buffer + reported success | `073f1a1` |
| **S4** | Stage 4 `_crawl_hospital` branded transient errors as permanent (no traceback, no retry) | `9bf138c` |
| **S5** | Stage 4 `resp.text` unbounded — single 500MB response could OOM the worker | `062d8dd` |

### Medium

| Tag | Description | Commit |
|---|---|---|
| **M1** | Web vitest configured but no `jsdom` and zero test files | `29583da` |
| **M2** | Ruff N806 on two function-scope constants | `5b232b6` |
| **M3** | Anesthesia time pattern over-matched "5 min" in unrelated text | `587ef04` |
| **M4** | Severity sort key used `.lower()` against what should be a typed enum | `587ef04` |
| **M5** | Charge regex picked up date fragments like `03.05` | `ac49324` |
| **M6** | Prompt injection vector via OCR'd description fields in AI dispute letter | `8f80207` |
| **M7** | Bill mapper duplicated character-for-character across 2 files | `107b4b4` |
| **M8** | Shape clusters duplicated across Pydantic + shared TS + inline TS | closed via Zod schemas (Phase 1) + Pydantic↔Zod parity test (`c60ea3b`) |
| **M9** | LineItem Pydantic field names were snake_case while TS expects camelCase | `c60ea3b` (caught by parity test) |
| **M10** | ProfileMember + InsurancePlan snake_case redeclarations consolidated to shared camelCase | `026e7e1` |
| **M11** | Bill/LineItem mappers extracted to single source | `107b4b4` |
| **M12** | 11 unsafe `as` casts replaced with Zod `parseJsonResponse` | `79211f9` |
| **M13** | BQ DML row-count verification helper + applied at 3 MERGE sites | `0244166` |

---

## Findings open

### Universal coverage (Phase 7)

| Tag | Description |
|---|---|
| **Rule 8** | Every untested service function gets tests; engine 80% coverage threshold; web first-test scaffolding done in M1 |
| **End-to-end smoke** | `apps/engine/tests/integration/test_full_pipeline.py` covering OCR → parser → rules → AI → report |

---

## Test counts (running total)

| Date | Engine pytest | Web vitest |
|---|---|---|
| Pre-campaign baseline (audit found stale) | "421" (collection broken) | 0 (no test files) |
| End of Phase 0 | 469 passed, 10 skipped | 1 passing (sanity) |
| End of Phase 1 | 480 passed, 10 skipped | 24 passing |
| End of Phase 2 | 482 | 24 |
| End of Phase 3 | 502 passed, 10 skipped | 24 |
| End of CI setup (PR #8) | 502 | 24 |
| End of Phase 4 | 510 (engine) + 94 (mrf_discovery scripts) | 24 |
| End of Phase 5 | 529 (engine) + 94 (mrf_discovery scripts) | 24 |
| End of Phase 6 | 538 (engine) + 100 (mrf_discovery scripts) | 41 |

---

## CI gate state

All four checks required for merge-readiness; branch protection adds them as required after first run:

- **Engine (Python)** — ruff, mypy `--strict`, pytest
- **Web (Next.js)** — typecheck, lint, vitest, build
- **Engine to web boundary contract** — Pydantic fixture export ↔ Zod parse ↔ git-diff drift check
- **Apply, verify, reverse migrations** (only on PRs touching `supabase/migrations/**`) — fresh local Postgres, every migration applied + reversed for every changed up-migration

---

## Cost-related decisions (Rule 16)

| Decision | Verified | Source |
|---|---|---|
| Supabase Pro database compute included; backfill migration cost ~$0 | 2026-05-04 | Sandra's plan baseline |
| Supabase preview branches — no fixed fee, $0.01344/hr Micro Compute, ~$0.60/month at beta volume | 2026-05-04 | <https://supabase.com/pricing> |
| GitHub Actions — public repo free; private repo 2,000-3,000 min/month included; CI cost ~750 min/month at 5 PR/day × 3 reruns | 2026-05-04 | <https://github.com/pricing> |
| BQ table rename (H5) — free metadata operation | 2026-05-04 | <https://cloud.google.com/bigquery/docs/managing-tables#renametable> |
| Places API billing — only requests reaching Google's LB are charged; ConnectionError refundable, Timeout defensive-book | 2026-05-04 | <https://developers.google.com/maps/documentation/places/web-service/usage-and-billing>, <https://developers.google.com/maps/billing-and-pricing/manage-costs> |
