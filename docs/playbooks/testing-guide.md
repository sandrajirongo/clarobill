# Testing guide

Phase 7 of the bug-fix campaign added 100 engine tests and 75 web tests
(commits `9c611c7`, `b657dcd`). This is the playbook for adding tests in
that style.

## Test pyramid

```
                          /\
                         /  \   boundary contract test (1 — Pydantic→Zod parity)
                        /----\
                       /      \  integration tests (1 — full pipeline)
                      /--------\
                     /          \  endpoint + service tests (engine + web)
                    /------------\
                   /              \  unit tests (pure functions)
                  /----------------\
```

Most new tests should be unit tests. Reach for integration tests only when
the bug surface is cross-cutting — the Phase 7 `test_full_pipeline.py` is
the keystone because it caught S1 (camelCase boundary), H2 (mileage
cents), H8 (Decimal serialization), and H9 (NPI label) all in one file.

## Engine tests (pytest)

Location: `apps/engine/tests/`.

### Layout

```
tests/
├── api/                # tests/api/test_*.py — route handlers + reference loaders
│   ├── conftest.py     # stubs google.cloud.* + slowapi import-time issues
│   ├── test_bills_endpoints.py
│   ├── test_bills_pipeline.py
│   ├── test_bq_loaders.py
│   ├── test_insurance_card.py
│   └── test_reference_loaders.py
├── integration/        # tests/integration/test_*.py — end-to-end with all boundaries mocked
│   └── test_full_pipeline.py
├── services/           # tests/services/test_*.py — pure-function service tests
│   ├── test_ai_analysis.py
│   ├── test_parser.py
│   ├── test_report_generator.py
│   ├── test_rules_engine.py
│   └── test_pydantic_zod_parity.py
└── scripts/            # tests/scripts/test_*.py — MRF discovery scripts
```

### Run a test

```bash
cd apps/engine

# Whole suite
python -m pytest tests/ -v

# One file
python -m pytest tests/integration/test_full_pipeline.py -v

# One test
python -m pytest tests/integration/test_full_pipeline.py::TestFullPipeline::test_bill_status_is_complete_at_end -v

# Stop on first failure
python -m pytest tests/ -x

# Show coverage
python -m pytest tests/ --cov=app --cov-report=term
```

### Fixture patterns (lift these directly when writing new tests)

#### Build a Supabase mock

```python
def _mock_supabase_with_data(table_data: dict[str, list[dict]]) -> MagicMock:
    """Each table returns a query whose execute() returns its rows."""
    def _build_query(name):
        response = MagicMock()
        response.data = table_data.get(name, [])
        query = MagicMock()
        for m in ("select", "eq", "in_", "lte", "gte", "is_", "or_",
                  "order", "limit", "single", "neq"):
            getattr(query, m).return_value = query
        query.execute.return_value = response
        return query
    client = MagicMock()
    client.table.side_effect = _build_query
    client.storage.from_.return_value.download.return_value = b"%PDF-1.4 fake"
    return client
```

Source: `tests/integration/test_full_pipeline.py:_mock_supabase_with_data`. Re-use; don't reinvent.

#### Build a BigQuery mock

```python
def _bq_returning(rows_per_call: list[list[dict]]) -> MagicMock:
    """Each call to client.query(...) returns rows from the next batch."""
    client = MagicMock()
    jobs = []
    for batch in rows_per_call:
        job = MagicMock()
        job.result.return_value = iter(batch)
        jobs.append(job)
    client.query.side_effect = jobs
    return client
```

Source: `tests/api/test_bq_loaders.py:_bq_returning`.

#### Build a `ParsedLineItem`

```python
def _make_line_item(cpt: str, charge: float, d: date | None = None) -> ParsedLineItem:
    return ParsedLineItem(
        cpt_code=cpt, description="Test procedure",
        service_date=d or date(2026, 3, 15),
        quantity=1,
        unit_charge=Decimal(str(charge)),
        total_charge=Decimal(str(charge)),
        modifier=None, diagnosis_pointers=[],
    )
```

Source: `tests/api/test_bills_pipeline.py`.

#### Stub Gemini / Claude

```python
async def _gemini_stub(_bytes: bytes, _mime: str) -> str:
    return _gemini_response(payer_name="Anthem")

with patch("app.api.insurance_card._extract_via_gemini", new=_gemini_stub):
    response = client.post("/api/v1/insurance-card/extract", files={...})
```

Source: `tests/api/test_insurance_card.py`.

### conftest.py rules

`tests/api/conftest.py` and `tests/integration/conftest.py` set env vars +
stub `google.cloud.bigquery`, `google.cloud.vision`, `fpdf`, `docx` at
import time. **Do not stub slowapi** — it's installed and its
`@limiter.limit` decorator must keep the wrapped function's signature for
FastAPI introspection. A MagicMock stub here makes every TestClient
request to a rate-limited route return 422.

### Coverage targets

Set on a per-module basis. Phase 7's targets and final results are in
[../playbooks/bug-fix-campaign.md](bug-fix-campaign.md). Future code:

| Surface | Target |
|---|---|
| Anything in `app/services/*.py` (rules engine, parser, AI, report generator) | ≥80% |
| `app/api/v1/bills.py` orchestrators + loaders | ≥70% |
| `app/api/insurance_card.py` route + helpers | ≥80% |
| `app/main.py` (FastAPI bootstrap) | not measured — covered indirectly |
| `app/core/security.py` | ≥80% — small but security-sensitive |
| Anything in `scripts/` | functional smoke test sufficient; no coverage target |

## Web tests (vitest)

Location: `apps/web/src/**/__tests__/*.test.{ts,tsx}`.

### Run a test

```bash
cd apps/web
npm run test                                    # whole suite (run mode)
npm run test:watch                              # watch mode
npx vitest run src/components/__tests__/bill-results-view.test.tsx
```

### Fixture patterns

#### Mock Next.js navigation

```typescript
vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }),
}));

vi.mock('next/link', () => ({
  default: ({ children, href }: any) => <a href={href}>{children}</a>,
}));
```

Source: `apps/web/src/components/__tests__/bill-results-view.test.tsx`.

#### Stub fetch

```typescript
beforeEach(() => {
  global.fetch = vi.fn(async () =>
    new Response(JSON.stringify({ status: 'complete' }), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    })
  ) as typeof fetch;
});
```

#### Build a typed shared-package fixture

```typescript
function makeError(overrides: Partial<BillingError> = {}): BillingError {
  return {
    code: 'NCCI_UNBUNDLING',
    severity: 'critical',
    affectedLineItemIds: ['li-1'],
    description: '...',
    estimatedOvercharge: 500.0,
    medicareBenchmarkRate: 350.0,
    ...overrides,
  };
}
```

This pattern lets every test call `makeError({estimatedOvercharge: 0})`
and override only the field that matters for the assertion.

### Boundary contract test

`tests/services/test_billing_error_fixture_export.py` writes a Pydantic
fixture; `apps/web/src/lib/__tests__/engine-boundary.contract.test.ts`
parses it via Zod. CI runs both halves on every PR — if they drift, one
side fails. **Always extend this when adding a new field to a shared
type.** Source of S1 → never again.

## Writing a regression test for a bug

Use the campaign's S/H/M tagging:

1. Pick an ID — `S` (stop-the-line), `H` (high), `M` (medium), `L` (low).
2. Write the test in the closest existing file. Name it
   `test_<id>_<short_description>` so future grep finds it. Example:
   `test_s1_billing_error_jsonb_uses_camelcase_keys`.
3. Add a comment block citing the bug in the campaign tracker:
   `# S1 regression net: see docs/playbooks/bug-fix-campaign.md`.
4. Make the test fail with the bug present (revert the fix locally, run,
   confirm fail) — then put the fix back and confirm pass.

## Common pitfalls

- **slowapi stub** — see `conftest.py rules` above.
- **fpdf2 + DejaVu fonts** — PDF tests in `test_report_generator.py` skip
  on dev machines without `fonts-dejavu-core` (Linux apt) or `matplotlib`
  (any OS). CI installs `fonts-dejavu-core` so they always run there.
- **conftest module-stub ordering** — stubs run at import time; if you
  `import google.cloud.bigquery` before conftest runs, the real (uninstalled)
  package fails. Don't skip the conftest; don't import google in test files
  before the conftest path.
- **Background-task warnings** — FastAPI's `BackgroundTasks` runs
  coroutines on a different loop; tests for handlers that schedule
  background work should use a true `async def` no-op, not
  `MagicMock(side_effect=async_fn)` — the latter emits "coroutine never
  awaited" warnings.
- **Decimal vs float on the boundary** — Pydantic's `field_serializer`
  converts `Decimal` to `float` at JSON-dump time. Tests that assert on
  `analysis_results` payload values should expect floats, not Decimals.
  See H8.

## Debugging a flaky test

1. Run it 10× with `pytest tests/path/to/test.py::test_name --count=10`
   (requires `pytest-repeat`, not installed by default — easier: a shell loop).
2. If it fails intermittently in CI but never locally, suspect timezone
   (`date.today()`) or random-seed-free dict iteration order.
3. If it fails after a refactor that didn't touch the test, look for
   conftest module-stub leakage — a previous test polluted `sys.modules`.
4. If it's a vitest test that hangs, check for a missing `await` on
   `screen.findByText` (synchronous `getByText` for static content,
   async `findByText` for content that appears after render).
