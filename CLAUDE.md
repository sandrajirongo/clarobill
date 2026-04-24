# CLAUDE.md — ClaroBill: AI Medical Bill Error Finder

---

## PROJECT IDENTITY

**Product:** ClaroBill — an AI-powered web app that analyzes medical bills for errors, overcharges, and coding mistakes, then generates plain-English reports and dispute letters.

**Tech Stack:**
- Frontend: Next.js 14+ (TypeScript, Tailwind CSS)
- Backend: Python FastAPI microservice
- Database: PostgreSQL via Supabase
- OCR: Google Cloud Vision API
- AI: Google Gemini 2.0 Flash via Vertex AI (primary) · Anthropic Claude Sonnet (fallback)
- Payments: Stripe
- File Storage: Supabase Storage (encrypted)
- Hosting: Vercel (frontend) + Google Cloud Run (Python service, deployed via Cloud Build)

**Monorepo Structure:**
```
clarobill/
├── apps/
│   ├── web/                 # Next.js frontend
│   │   ├── src/
│   │   │   ├── app/         # App router pages
│   │   │   ├── components/  # UI components
│   │   │   ├── lib/         # Utilities, API clients, hooks
│   │   │   ├── types/       # TypeScript type definitions
│   │   │   └── styles/      # Global styles
│   │   └── public/
│   └── engine/              # Python FastAPI billing analysis service
│       ├── app/
│       │   ├── api/         # FastAPI route handlers
│       │   ├── core/        # Config, security, dependencies
│       │   ├── models/      # Pydantic models / DB models
│       │   ├── services/    # Business logic (OCR, rules engine, AI analysis)
│       │   │   ├── ocr.py
│       │   │   ├── parser.py
│       │   │   ├── rules_engine.py
│       │   │   ├── ai_analysis.py
│       │   │   └── report_generator.py
│       │   ├── data/        # CMS data loaders and reference tables
│       │   └── utils/
│       └── tests/
├── packages/
│   └── shared/              # Shared types, constants, validation schemas
├── supabase/
│   └── migrations/          # SQL migration files
├── scripts/                 # Data loading, deployment, maintenance scripts
├── docs/                    # Architecture decisions, API docs
└── CLAUDE.md                # This file
```

---

## ENGINEERING PHILOSOPHY

These rules are non-negotiable. They exist because AI-generated code has a tendency toward surface-level fixes, accumulated tech debt, and silent regressions. Every rule here fights a specific failure mode. Follow them without exception.

---

## RULE 1: UNDERSTAND BEFORE YOU TOUCH

**Before writing or modifying any code, you MUST:**

1. Read every file that is related to the change you are about to make. Do not guess what a function does. Do not assume an interface shape. Open the file, read it, confirm.
2. Trace the full execution path of the feature you are modifying. If you are changing how a bill is parsed, trace from upload → OCR → parser → rules engine → report. Understand every step.
3. Identify all callers and consumers. Before changing a function signature, type, or return value, find every file that imports or calls it. List them explicitly in your reasoning.
4. If you are unsure how something works, say so and investigate. Never paper over confusion with a "should work" implementation.

**Why:** The #1 source of bugs in AI-generated code is modifying something without understanding its full context. A 2-minute read prevents a 2-hour debug session.

---

## RULE 2: ROOT CAUSE ONLY — NO SYMPTOM PATCHES

**When you encounter a bug or test failure:**

1. **STOP.** Do not write a fix yet.
2. **Ask "why" five times.** Trace the error back to its origin. The stack trace shows you where it manifested — that is NOT where the bug lives. The bug lives upstream.
3. **Find the root cause.** The root cause is the earliest point in the execution path where the system's actual behavior diverges from its intended behavior. That is what you fix.
4. **Never apply these band-aids:**
   - Adding a `try/catch` to swallow an error that shouldn't happen
   - Adding a null check to guard against data that should never be null
   - Adding a type assertion (`as any`, `as SomeType`) to silence TypeScript
   - Adding a `// @ts-ignore` or `# type: ignore`
   - Wrapping a broken function call in a conditional that skips it
   - Duplicating logic to "work around" a function that isn't behaving correctly
   - Adding a `setTimeout` or retry loop to mask a race condition
5. **If the root cause is in a dependency or external system you can't control,** document it explicitly with a `// WORKAROUND:` comment that explains what the upstream issue is, why this workaround is necessary, and what a proper fix would look like.

**Why:** Symptom patches compound. Each one makes the next bug harder to find. A codebase with 50 symptom patches is unmaintainable. A codebase with 50 root-cause fixes is robust.

---

## RULE 3: EVERY CHANGE MUST BE VERIFIED

**After every meaningful code change, you MUST verify it works before moving on:**

1. **Unit-level verification:** If you wrote or modified a function, write or run a test that exercises it. If a test file exists for that module, run it. If none exists, create one.
2. **Integration verification:** If your change touches the boundary between two systems (frontend ↔ API, API ↔ database, API ↔ external service), verify the integration works. Make a real request. Check the real response.
3. **Regression verification:** Run the full relevant test suite after your change. If you changed the rules engine, run ALL rules engine tests, not just the test for the rule you modified. If you changed a shared type, run tests for every module that imports it.
4. **Build verification:** After any change to types, imports, or configuration, run `tsc --noEmit` (TypeScript) or the equivalent type checker to confirm the build is clean. A file that "looks right" but doesn't compile is worthless.

**Verification commands (always available):**
```bash
# Frontend
cd apps/web && npm run typecheck     # TypeScript compilation check
cd apps/web && npm run lint          # ESLint
cd apps/web && npm run test          # Vitest unit tests
cd apps/web && npm run build         # Full production build

# Engine
cd apps/engine && python -m pytest tests/ -v          # All tests
cd apps/engine && python -m pytest tests/ -x          # Stop on first failure
cd apps/engine && python -m mypy app/ --strict        # Type checking
cd apps/engine && python -m ruff check app/           # Linting

# Full suite
npm run test:all                     # Runs both frontend and engine tests
```

**The rule is simple: green tests before you move to the next task. No exceptions.**

---

## RULE 4: ONE CHANGE AT A TIME

**Every unit of work should be atomic and focused:**

1. **One feature, one branch, one PR.** Do not combine "add upload endpoint" with "refactor database schema" in the same change. If you discover something that needs refactoring while building a feature, finish the feature first, verify it works, then refactor separately.
2. **Make the smallest change that accomplishes the goal.** If you need to add a new field to the bill analysis, add the field, update the type, update the database migration, update the API response, update the frontend display. That's it. Do not also "clean up" three other files you noticed while looking around.
3. **Commit after each verified change.** Write a clear commit message that describes WHAT changed and WHY. Format: `feat(engine): add NCCI unbundling detection to rules engine` or `fix(web): correct Stripe webhook signature validation`.
4. **If a change touches more than 5 files, pause and ask:** "Am I doing one thing, or have I accidentally started doing two things?" Split if necessary.

**Why:** Atomic changes are reviewable, revertable, and debuggable. A 20-file commit that breaks something is a nightmare. A 3-file commit that breaks something takes 5 minutes to diagnose.

---

## RULE 5: TYPES ARE THE SOURCE OF TRUTH

**TypeScript and Pydantic types are not optional annotations — they are the contract between every part of the system.**

1. **Define types FIRST, implement SECOND.** Before building a new feature, define the types/interfaces/models that describe its data shapes. These types drive the implementation, not the other way around.
2. **Shared types live in `packages/shared/`.** If both the frontend and the engine need to agree on a data shape (e.g., `BillAnalysisResponse`), the type is defined once in the shared package and imported by both.
3. **Never use `any`.** Ever. If you're reaching for `any`, you don't understand the type, and that means you don't understand the data. Stop and figure it out.
4. **Pydantic models are strict.** All Python API models use `model_config = ConfigDict(strict=True)`. No silent type coercion.
5. **Database types match application types.** The Supabase schema, the Pydantic models, and the TypeScript interfaces must describe the same shapes. When you change one, update all three. Use the migration system — never modify the database by hand.

```typescript
// WRONG — you've lost all type safety
const data: any = await response.json();

// WRONG — you're lying to the compiler
const data = await response.json() as BillAnalysis;

// RIGHT — validate at the boundary
const raw = await response.json();
const data = BillAnalysisSchema.parse(raw);  // Zod validates at runtime
```

**Why:** Type mismatches between the frontend and backend are the most common source of "it works in dev but breaks in production." Strict types caught at compile time save you from runtime surprises.

---

## RULE 6: ERRORS ARE DATA, NOT EXCEPTIONS

**Design the error handling system intentionally, not reactively:**

1. **Define error types explicitly.** ClaroBill has specific, known failure modes. Each one gets a typed error:
   ```typescript
   type ClaroBillError =
     | { code: 'OCR_FAILED'; detail: string; billId: string }
     | { code: 'INVALID_CPT_CODE'; detail: string; code: string }
     | { code: 'PAYMENT_FAILED'; detail: string; stripeError: string }
     | { code: 'RATE_LIMIT'; detail: string; retryAfter: number }
     | { code: 'ANALYSIS_FAILED'; detail: string; step: string }
   ```
2. **Handle errors at the appropriate layer.** OCR errors are handled in the OCR service. Payment errors are handled in the payment service. The API layer translates service errors into HTTP responses. The frontend translates HTTP errors into user-facing messages. No layer handles errors that belong to another layer.
3. **Never swallow errors silently.** Every `catch` block must either (a) handle the error meaningfully, (b) transform it and re-throw, or (c) log it with full context. An empty `catch {}` is a bug.
4. **User-facing error messages are helpful and specific.** Not "Something went wrong." Instead: "We couldn't read your bill clearly. Try uploading a higher-resolution photo or a PDF version."

---

## RULE 7: THE DATABASE IS SACRED

**Data integrity is non-negotiable:**

1. **All schema changes go through migrations.** Use `supabase migration new <name>` to create migration files. Never use the Supabase dashboard to modify the schema directly.
2. **Migrations are additive and reversible.** Every migration file includes both `up` and `down` logic. If a migration can't be reversed cleanly, document why.
3. **Never delete data columns in production.** Deprecate them first (stop writing to them), then remove reads, then drop in a later migration.
4. **All queries use parameterized inputs.** No string interpolation in SQL. No exceptions.
5. **Foreign keys and constraints are enforced at the database level,** not just in application code. If a line_item must belong to a bill, that's a foreign key constraint, not just a validation rule.

---

## RULE 8: TESTS ARE FIRST-CLASS CITIZENS

**Tests are not an afterthought. They are written alongside the code they test:**

1. **Every service function has a corresponding test.** If you add `detect_duplicates()` to the rules engine, you add `test_detect_duplicates()` in the same session.
2. **Tests test behavior, not implementation.** Test what a function does (given this input, expect this output), not how it does it (it calls this internal method 3 times). This means tests survive refactors.
3. **Test the sad paths.** For every happy-path test, write at least one test for: invalid input, missing data, external service failure, and edge cases (empty bill, bill with one line item, bill with 500 line items).
4. **Use real-ish data.** Test fixtures should resemble actual medical bills, with real CPT codes, realistic charge amounts, and plausible combinations. Don't test with `code: "12345", charge: 100`. Test with `code: "99214", charge: 350.00`.
5. **Test file organization mirrors source organization:**
   ```
   apps/engine/app/services/rules_engine.py
   apps/engine/tests/services/test_rules_engine.py
   ```

---

## RULE 9: SECURITY IS NOT A PHASE — IT'S EVERY LINE

**Medical bills contain PHI. Treat every piece of data as sensitive:**

1. **Never log PHI.** No patient names, dates of birth, diagnosis codes, or bill contents in log output. Log bill IDs, anonymized metadata, and processing status only.
2. **All file uploads are validated.** Check file type (magic bytes, not just extension), file size (max 20MB), and scan for malformed content before processing.
3. **All API endpoints require authentication** except the landing page and public marketing pages.
4. **Stripe webhooks are verified** using the webhook signing secret. Never trust a webhook payload without signature verification.
5. **Environment variables are never committed.** Use `.env.local` for development, environment variables in the deployment platform for production. The `.gitignore` includes `.env*` from day one.
6. **CORS is restrictive.** Only allow requests from the production domain and localhost in development. Never use `*`.
7. **Rate limiting on all endpoints.** Especially the analysis endpoint (expensive AI calls). Use both per-user and global rate limits.

---

## RULE 10: CODE STYLE IS NOT AESTHETIC — IT'S COMMUNICATION

**Consistent, readable code is debuggable code:**

### TypeScript/Next.js
- Functional components only. No class components.
- Named exports. No default exports (except for Next.js pages/layouts where required).
- `const` by default. `let` only when mutation is necessary. Never `var`.
- Explicit return types on all exported functions.
- Descriptive variable names. `billLineItems` not `items`. `medicareBenchmarkRate` not `rate`.
- No abbreviations in variable names except universally understood ones (`id`, `url`, `api`).
- One component per file. File name matches component name.
- Hooks in `lib/hooks/`. Utilities in `lib/utils/`. API clients in `lib/api/`.

### Python/FastAPI
- Type hints on all function parameters and return values.
- Pydantic models for all request/response schemas.
- Docstrings on all public functions. Format: one-line summary, blank line, parameter descriptions.
- Snake_case for everything. No exceptions.
- No mutable default arguments.
- Use `pathlib.Path` not string paths.
- Async by default for I/O operations.
- `ruff` for formatting and linting. Configuration in `pyproject.toml`.

### Both
- No commented-out code. If it's not needed, delete it. Git has history.
- No TODO comments without a linked issue. `# TODO(#42): Add retry logic for OCR timeout` is fine. `# TODO: fix this later` is not.
- Functions do one thing. If a function name has "and" in it, split it.
- Max function length: 40 lines. If it's longer, extract sub-functions.
- Max file length: 300 lines. If it's longer, split into modules.

---

## RULE 11: THE ITERATION PROTOCOL

**When building any feature, follow this exact sequence:**

```
1. DEFINE    → Write the types/interfaces/models for the feature
2. TEST      → Write a failing test that describes the desired behavior
3. IMPLEMENT → Write the minimum code to make the test pass
4. VERIFY    → Run the full test suite to confirm no regressions
5. REFACTOR  → Clean up the implementation (if needed) while tests stay green
6. VERIFY    → Run the full test suite again after refactoring
7. INTEGRATE → Wire the feature into the broader system
8. VERIFY    → Run integration tests and/or manual verification
9. COMMIT    → Atomic commit with descriptive message
```

**At any point, if step 4, 6, or 8 fails:**
- STOP
- Do NOT proceed to the next step
- Diagnose the root cause (Rule 2)
- Fix the root cause
- Re-run verification from the beginning

**Never skip a verification step because "it's a small change." Small changes cause the nastiest bugs because nobody suspects them.**

---

## RULE 12: DEPENDENCY DISCIPLINE

1. **Every dependency must justify its existence.** Before adding a package, ask: "Can I do this in 20 lines without the dependency?" If yes, write the 20 lines.
2. **Pin exact versions.** Use `--save-exact` for npm. Use `==` not `>=` in Python requirements.
3. **Audit before installing.** Check the package's last publish date, download count, open issues, and maintenance status. Do not install packages that haven't been updated in 12+ months unless they are genuinely stable and complete.
4. **No duplicate functionality.** If we use Zod for validation, we don't also use Yup. If we use Tailwind, we don't also install styled-components.

---

## RULE 13: THE REGRESSION GATE

**Before marking ANY task as complete, run this full checklist:**

```bash
# 1. Type safety
cd apps/web && npm run typecheck
cd apps/engine && python -m mypy app/ --strict

# 2. Linting
cd apps/web && npm run lint
cd apps/engine && python -m ruff check app/

# 3. Unit tests
cd apps/web && npm run test
cd apps/engine && python -m pytest tests/ -v

# 4. Build
cd apps/web && npm run build

# 5. If touching API contracts, verify frontend ↔ engine compatibility
# Start both services and make a real request through the full stack
```

**All 5 must pass. If any fails, the task is not complete.**

---

## RULE 14: DOCUMENT THE WHY, NOT THE WHAT

- Code shows WHAT is happening. Comments explain WHY.
- Every non-obvious business rule gets a comment: `# Medicare allows modifier 59 to override NCCI edits when procedures are performed on distinct anatomical sites`
- Architecture decisions go in `docs/decisions/`. Format: `YYYY-MM-DD-title.md` with sections: Context, Decision, Consequences.
- API endpoints are documented with OpenAPI/Swagger (FastAPI generates this automatically — keep the Pydantic models descriptive).

---

## RULE 15: PROGRESSIVE COMPLEXITY

**Build features in this order. Each phase must be fully working and tested before starting the next:**

### Phase 1: Foundation (Week 1)
- [ ] Project scaffolding (Next.js + FastAPI + Supabase)
- [ ] Authentication (Supabase Auth)
- [ ] File upload to Supabase Storage
- [ ] Basic landing page

### Phase 2: Core Engine (Week 2)
- [ ] OCR pipeline (Google Cloud Vision → structured line items)
- [ ] Line item parser (extract CPT codes, charges, dates)
- [ ] Load Medicare fee schedule into PostgreSQL
- [ ] Load NCCI edit pairs into PostgreSQL
- [ ] Rules engine: duplicate detection
- [ ] Rules engine: price outlier detection
- [ ] Rules engine: NCCI unbundling detection

### Phase 3: Analysis & Output (Week 3)
- [ ] Claude API integration for nuanced analysis
- [ ] Report generation (HTML → PDF)
- [ ] Dispute letter generation
- [ ] Results page with teaser/paywall
- [ ] Stripe payment integration
- [ ] Email delivery of reports

### Phase 4: Polish & Launch (Week 4)
- [ ] SEO-optimized landing page
- [ ] 3 pillar blog articles
- [ ] Legal pages (ToS, Privacy Policy, Disclaimers)
- [ ] Analytics (PostHog)
- [ ] Error monitoring (Sentry)
- [ ] Rate limiting
- [ ] Beta testing with real bills
- [ ] Production deployment

**Do NOT start Phase 2 until Phase 1 is fully tested and working. Do NOT start Phase 3 until Phase 2 is fully tested and working. No exceptions.**

---

## EMERGENCY PROCEDURES

### If the build is broken and you can't figure out why:
1. `git stash` your current changes
2. Verify the last known good commit builds and passes tests
3. `git stash pop` and diff your changes against the working state
4. The bug is in the diff. Find it.

### If you're stuck in a loop fixing the same test:
1. Stop fixing the code. Read the test.
2. Is the test correct? Does it test what it claims to test?
3. If the test is wrong, fix the test and document why.
4. If the test is right, the bug is deeper than you think. Trace from the input to the expected output, logging every intermediate value.

### If a third-party service is down or unreliable:
1. Build a mock/stub for development.
2. All external service calls go through a service wrapper (never call Google Vision or Claude API directly from a route handler).
3. The wrapper has a test mode that returns fixture data.

---

## FINAL COMMANDMENT

**Slow is smooth. Smooth is fast.**

It is always faster to write correct code once than to write broken code quickly and then spend 3x the time debugging it. Take the time to understand, test, and verify. The codebase will thank you, and so will future-you when you're not drowning in mystery bugs at 2am before launch.
