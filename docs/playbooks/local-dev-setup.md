# Local development setup

What the README's "Local Development" section doesn't tell you. Read both
together.

## First-time setup

```bash
# 1. Clone the repo
git clone git@github.com:sandrajirongo/clarobill.git
cd clarobill

# 2. Engine (Python)
cd apps/engine
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # fill in your keys (see "Env vars" below)
cd ../..

# 3. Web (Next.js)
cd apps/web
cp .env.example .env.local  # fill in your keys
npm install
cd ../..

# 4. Optional: Supabase local stack
supabase start  # boots Postgres + Auth + Storage in Docker
```

You can develop against the hosted Supabase project instead of `supabase
start` — both work. Local stack is faster and lets you destroy state at
will; hosted is closer to prod.

## Engine in isolation (no GCP creds, no Stripe, no Anthropic)

The engine has graceful-skip paths for every external dep so you can run
it locally with placeholder keys:

| Dep | Behavior without real credentials |
|---|---|
| Google Cloud Vision (OCR) | Pass `OcrService(test_mode=True)` — returns the canned fixture from `app/services/ocr.py::_fixture_text` |
| BigQuery (hospital_charges, MRF data) | `_build_bq_client()` returns `None` when `GCP_PROJECT_ID` is unset; all BQ-backed rules silently no-op |
| Vertex AI Gemini (primary AI) | `AiAnalysisService(test_mode=True)` — returns `_fixture_summary()` and `_fixture_dispute_letter()` |
| Anthropic Claude (fallback AI) | Same — covered by `test_mode=True` |
| Stripe | Use `STRIPE_SECRET_KEY=sk_test_...` from your test-mode dashboard. Local webhooks: `stripe listen --forward-to localhost:3000/api/stripe/webhook` |
| SendGrid | Set `SENDGRID_API_KEY=SG.test` and `SENDGRID_FROM_EMAIL=test@clarobill.com`; emails won't actually send but the service constructs cleanly |

So a "minimal local engine" needs: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`,
and any string for `ANTHROPIC_API_KEY`. Everything else can be a placeholder.

## Engine venv troubleshooting

### "python: command not found" or "stale shebang"

The venv was created on a previous folder name (the project was renamed
from MedScan → ClaroBill on 2026-04-XX). Recreate:

```bash
cd apps/engine
rm -rf .venv
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Mypy explodes after `pip install`

Sometimes a fresh install pulls a newer mypy with stricter checks. Pin if
you need to (in `pyproject.toml`), or fix the surfaced types — usually
they're real issues that the prior version missed.

### Tests fail with "google.cloud.bigquery has no attribute Client"

The conftest at `tests/api/conftest.py` and `tests/integration/conftest.py`
stubs google.cloud.* at import time. If you added a new test file outside
those directories that imports from `app/api/v1/bills.py`, you need a
conftest in that file's directory too — copy from `tests/api/conftest.py`.

## Web setup

```bash
cd apps/web
npm install
npm run dev    # http://localhost:3000
```

### Without Supabase

The frontend can boot, but every authenticated route 401s without a
Supabase URL. For UI-only work (designs, components), you can mock Supabase
calls at the route-handler level. Phase 7's `bill-results-view.test.tsx`
shows the pattern.

### Without engine

Most engine calls are made server-side from `apps/web/src/app/api/*`. If
the engine is down locally, those API routes 502. To work on the frontend
without the engine running, you can either:
- Hardcode fixture data in the API route (return `NextResponse.json({...})`
  without forwarding to the engine)
- Use Vitest with mocked `fetch` (see `bill-results-view.test.tsx`)

## Test data

The engine tests use synthetic OCR text built inline (see
`tests/integration/test_full_pipeline.py::_RAW_OCR_TEXT`) — no shared test
DB, no shared fixture file. You can copy that pattern when adding new
integration tests.

For manual end-to-end testing against a real Supabase + engine + Vision
pipeline, you need a real bill PDF/JPEG. Sandra has a small set of
anonymized bills locally; ask her if you need one. Don't commit bills to
the repo — they're PHI.

## Hot reload

- Engine: `uvicorn app.main:app --reload --port 8000` watches the `app/`
  tree and restarts on save. Unrelated changes (e.g. in `tests/`) don't
  trigger a reload.
- Web: `npm run dev` hot-reloads the browser on save.

## Port collisions

| Port | Service |
|---|---|
| 3000 | Next.js dev server |
| 8000 | FastAPI engine |
| 54321 | Supabase Studio (when `supabase start` is running) |
| 54322 | Postgres (Supabase local) |
| 54323 | Inbucket (local email capture) |
| 54324 | Storage |
| 54325 | Auth |

If something else is bound to one of these, kill it: `lsof -i :8000` →
`kill -9 <PID>`.

## Running the regression gate locally

The exact same commands CI runs:

```bash
# Engine (~10s, no network)
cd apps/engine
python -m ruff check app/
python -m mypy app/ --strict
python -m pytest tests/ -v

# Web (~30s, no network)
cd apps/web
npm run typecheck
npm run lint
npm run test
npm run build
```

If all six pass, GitHub Actions will pass too.

See [testing-guide.md](testing-guide.md) for the deeper testing workflow.

## Env vars (engine)

| Variable | Required for | Default | Notes |
|---|---|---|---|
| `SUPABASE_URL` | Everything | none | Project URL or `http://localhost:54321` for local |
| `SUPABASE_SERVICE_ROLE_KEY` | Everything | none | Bypasses RLS — keep server-only |
| `ANTHROPIC_API_KEY` | AI fallback | none | Required even in test mode (the client constructs at module load) |
| `SENDGRID_API_KEY` | Email | none | Use `SG.test` for local |
| `SENDGRID_FROM_EMAIL` | Email | none | `test@clarobill.com` for local |
| `GOOGLE_APPLICATION_CREDENTIALS` | Vision + BigQuery | none | Path to JSON key. Optional — without it, BQ rules skip |
| `GCP_PROJECT_ID` | BigQuery | none | `clarobill-prd` in prod; unset locally → BQ skipped |
| `BIGQUERY_DATASET` | BigQuery | `hospital_prices` | |
| `POSTHOG_API_KEY` | Analytics | none | Optional |
| `SENTRY_DSN` | Error monitoring | none | Optional |
| `LOG_LEVEL` | Logging | `INFO` | Set `DEBUG` for chatty local dev |

## Env vars (web)

| Variable | Required for | Notes |
|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Everything | Same as engine's SUPABASE_URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Everything | Anon key, NOT service role |
| `SUPABASE_SERVICE_ROLE_KEY` | API routes | Server-only — never exposed to the browser |
| `STRIPE_SECRET_KEY` | Checkout | Test-mode key for local |
| `STRIPE_WEBHOOK_SECRET` | Webhook | From `stripe listen` output |
| `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` | Checkout | Test-mode pk_test_... |
| `ENGINE_URL` | API routes | `http://localhost:8000` for local |
| `ENGINE_API_KEY` | API routes | Any string for local — the engine compares against the same env var |
| `NEXT_PUBLIC_BETA_MODE` | Paywall | Default true; set `false` to test paid flow |

The full lists are in `apps/engine/.env.example` and `apps/web/.env.example`.
