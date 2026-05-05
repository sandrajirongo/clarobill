# Test coverage gap inventory — 2026-05-04

Snapshot taken at end of Phase 6 (commit `d91ac0f`). This is the starting point for Phase 7 of the bug-fix campaign — universal coverage per CLAUDE.md Rule 8.

## Baseline measurement

```bash
# Engine
cd apps/engine && ./.venv/bin/python -m pytest tests/ --cov=app --cov-report=term

# Web
cd apps/web && npm run test -- --coverage
```

## Engine — 55% line coverage (538 tests passing, 10 skipped)

| Module | Lines | Cov | Priority | Notes |
|---|---:|---:|---|---|
| `app/services/rules_engine.py` | 375 | **98%** | ✅ done | Bug-fix targets exercised in 100+ tests |
| `app/services/ai_analysis.py` | 120 | **98%** | ✅ done | M6 + Gemini/Claude fallback covered |
| `app/services/parser.py` | 265 | **82%** | low | H1/H2/H9/M3/M5 + happy paths covered. Remaining gap: column-interleaved fallback corners |
| `app/models/bill.py` | 104 | **100%** | ✅ done | Full schema parity |
| `app/core/config.py` | 29 | **93%** | low | Env config |
| `app/core/posthog_client.py` | 7 | **100%** | ✅ done | |
| `app/core/dependencies.py` | 18 | 78% | low | DI factories |
| `app/services/email_service.py` | 33 | 55% | medium | Send-success path covered; HTML edge cases not |
| `app/api/v1/bills.py` | **604** | **28%** | **high** | Largest module. Core pipeline orchestrator. Most reference-data loaders + report-trigger endpoint untested |
| `app/services/report_generator.py` | 235 | **13%** | **high** | Skipped tests need fpdf2 in test env. Would benefit from a Docker-test path |
| `app/api/insurance_card.py` | 84 | **0%** | **high** | Vision OCR + Claude/Gemini fallback — no tests at all |
| `app/services/ocr.py` | 65 | 29% | medium | Vision API pieces |
| `app/main.py` | 33 | 0% | low | App bootstrap; covered indirectly by every test |
| `app/core/security.py` | 7 | 0% | medium | Token handling — small but security-sensitive |
| `app/core/supabase_helpers.py` | 16 | 62% | low | Newer module; has tests via callers |

**Engine total: 2017 stmts / 903 missed / 55%.**

### Engine priorities for Phase 7

1. `app/api/v1/bills.py` (604 stmts, 28% → target 70%): the request-handler surface for the core pipeline. Highest blast radius; lowest current coverage. Mock Supabase + the AI service via the existing conftest pattern.
2. `app/api/insurance_card.py` (84 stmts, 0% → target 80%): user-facing OCR endpoint. Currently zero tests.
3. `app/services/report_generator.py` (235 stmts, 13% → target 60%): PDF/DOCX generation. Currently the local DejaVu-font absence forces skips. Either: (a) add fonts-dejavu to a Docker test env, or (b) test the layout/sort logic in pure-function isolation and accept that PDF rendering itself is exercised only in CI/Cloud.

## Web — 1.22% line coverage (41 tests passing)

| Area | Lines covered | Priority | Notes |
|---|---|---|---|
| `lib/api/parsers.ts` | 90% | ✅ done | M12 boundary parser |
| `lib/api/mappers.ts` | 62% | low | M11+M10 mappers — extend as new shapes appear |
| `app/dashboard/**` | 0% | medium | Server components — exercise via `@testing-library` page renders |
| `components/bill-results-view.tsx` | 0% | **high** | Paywall logic, error rendering — most expensive to break in production |
| `components/bill-verification.tsx` | 0% | **high** | Pre-analysis form; selection logic |
| `components/members-panel.tsx` | 0% | medium | Profile management |
| `lib/hooks/**` | 0% | medium | useCardScan, useBillUpload |
| `lib/utils/**` | 0% | low | Static data + pure helpers — lowest-hanging fruit |
| `lib/beta.ts`, `lib/pricing.ts` | 0% (branches 100%) | low | Logic-light, but functions are pure — easy unit tests |

### Web priorities for Phase 7

1. `bill-results-view.tsx` paywall + error rendering — render-mock the component with React Testing Library, snapshot the visible-vs-hidden errors logic that S1's whole campaign protected.
2. `bill-verification.tsx` member/plan selection — exercise the `loadMembers`-then-auto-select flow + the form validation paths.
3. `lib/utils/**` (static data, validation, constants) — quickest wins; pure functions, no React.
4. API route handlers under `app/api/**` — currently zero coverage but they're the engine→DB boundary that actually moves bills through the pipeline.

## End-to-end smoke test (planned commit 66 in original plan)

`apps/engine/tests/integration/test_full_pipeline.py` — OCR (mocked Vision) → parser → rules engine → AI (test mode) → report generator → DB write (mocked Supabase). One fixture bill carrying NCCI-bundling, mileage, anesthesia, NPI label and fallback shapes. Compares the final analysis_results JSON against a checked-in expected blob.

This single test would lift `bills.py` coverage substantially because it exercises the orchestrator end-to-end. Best ROI item in Phase 7.

## How to read this file

- ✅ done = covered well, no Phase 7 work needed
- low = nice to have, won't impact reliability much
- medium = scope it into Phase 7 if time permits
- high = real risk surface; do these first

The campaign's S/H/M bug-fix work intentionally added ≥1 test per fix. So the modules touched by the campaign (rules_engine, parser, ai_analysis, models/bill) are well-exercised. The gaps are in modules the campaign DIDN'T touch — most notably `bills.py` and the insurance-card OCR endpoint.
