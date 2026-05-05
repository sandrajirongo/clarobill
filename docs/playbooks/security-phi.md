# Security and PHI handling playbook

ClaroBill ingests medical bills. Bills contain PHI: patient names, dates of
birth, diagnosis codes (ICD), procedure codes (CPT), service dates, and
charge amounts tied to identifiable individuals. CLAUDE.md Rule 9 is the
non-negotiable; this playbook is the consolidated reference for HOW.

## Data classification

| Class | Examples | Where it can live |
|---|---|---|
| **Public** | Hospital names, NPIs, public payer names, CPT code descriptions | Anywhere — repo, logs, telemetry |
| **PII** | User email, account ID, IP address | Supabase (encrypted at rest); never in logs except as bill_id linkage |
| **PHI** | Patient name, DOB, diagnosis pointers, CPT codes ON A SPECIFIC BILL, charges, dispute letter contents, OCR text | Supabase Storage (encrypted), Postgres (encrypted), Cloud Vision API requests, never in logs/telemetry/Sentry |
| **Secrets** | API keys, Stripe webhook secret, service-role key, GCP service account JSONs | Vercel env vars, Cloud Run secrets, GCP Secret Manager — never in repo, never in logs |

## Logging policy

CLAUDE.md Rule 9: "Never log PHI. No patient names, dates of birth, diagnosis
codes, or bill contents in log output. Log bill IDs, anonymized metadata,
and processing status only."

### What to log

- `bill_id`, `user_id`, `analysis_id` — UUIDs, not PHI
- Counts: `len(parsed_items)`, `len(errors)`, `len(rows)`
- Status transitions: `bill -> COMPLETE`, `OCR_PROCESSING`
- Latency, retries, error types (the type, not the message contents)
- External-service identifiers: Stripe session ID, NPI, hospital name
  (not patient context)

### What NOT to log

- Patient name, DOB, address, phone
- Specific CPT codes paired with dollar amounts on a specific bill
- AI prompt contents (they include sanitized but still-identifiable bill data)
- AI response contents (these are the dispute-letter text — full PHI)
- Raw OCR text
- Stripe payment-intent metadata if it carries patient context

The engine's existing logs at INFO/WARN level mostly comply — Phase 8 has
M14 to surface a few outliers (`hospital_name + payer_name + plan_name`
shouldn't be logged at INFO).

## Sentry

Configured in `apps/engine/app/main.py`:

```python
sentry_sdk.init(
    dsn=settings.sentry_dsn,
    environment=settings.environment,
    integrations=[StarletteIntegration(), FastApiIntegration()],
    traces_sample_rate=0.1 if settings.is_production else 1.0,
    before_send=lambda event, hint: {
        **event,
        "request": {**event.get("request", {}), "data": "[redacted]"},
    } if event.get("request") else event,
)
```

The `before_send` redaction only catches `event.request.data`. Phase 8 M18
proposes extending it to also scrub `event.extra`, `event.breadcrumbs`,
and structured `event.contexts.runtime`. Until then, **every Sentry-side
exception report is a potential PHI exfil vector** — ask before adding
new logger.exception calls in PHI-handling paths.

The right Sentry config is `send_default_pii=False` plus an explicit
denylist for `hospital_name`, `payer_name`, `plan_name`, `patient_name`,
`patient_dob`, `member_id`. That's a Phase 8 follow-up.

## PostHog

Configured at `apps/engine/app/core/posthog_client.py` and
`apps/web/src/components/posthog-provider.tsx`.

### Engine policy

Every `posthog_client.capture(...)` call must carry
`properties={"$process_person_profile": False, ...}`. This disables
PostHog's auto-person-profile creation that would otherwise tie events
to a recoverable person identity.

Properties allowed in events:
- `bill_id`, `user_id` (user_id is a UUID — not directly PHI but treat
  as PII; sufficient for product analytics)
- Counts (`errors_found`, `line_item_count`)
- Booleans (`has_savings`, `has_payer_info`, `confident`)
- Stable enums (`plan_type`, `provider`)

Properties NOT allowed:
- Patient name, DOB
- Specific CPT codes (which procedures the patient had)
- Specific charges (dollar amounts tied to a bill)
- `failure_reason` if the reason carries content (the current
  `failure_reason: "ocr_failed" | "pipeline_error"` is fine — it's an
  enum)

### Web policy

The web client uses `posthog-js` with `capture_pageview: false` (we
control this manually) and the same `$process_person_profile` discipline.

## Authentication and authorization

### Supabase Auth (frontend)

- Users authenticate via Supabase Auth (email + password, magic link, or
  OAuth depending on what's enabled).
- The browser uses the **anon key** — RLS policies enforce that
  `auth.uid()` matches `user_id` on every query.
- The session token is a JWT signed by Supabase; lives in HttpOnly cookies
  set by the `@supabase/ssr` integration.
- Server-side (Next.js API routes), we use `createServerClient(...)` which
  reads the cookie and uses the user's session to query Supabase. Same
  RLS enforcement applies.

### Engine API key

- The engine's routers are protected by `verify_engine_api_key` — every
  request must carry `Authorization: Bearer <ENGINE_API_KEY>`.
- The web layer holds the engine API key in `ENGINE_API_KEY` (server-only
  env var); calls the engine server-to-server.
- The browser **never** holds the engine API key. UI calls
  `/api/...` routes on the same Next.js host, which forward server-side.

#### Rotation procedure

1. Generate a new key: `openssl rand -base64 64`.
2. Set `ENGINE_API_KEY` on the **engine** Cloud Run service via:
   `gcloud run services update clarobill-engine --update-env-vars ENGINE_API_KEY=...`
   The engine accepts BOTH the old and new key during a transition window
   if `ENGINE_API_KEY_PREVIOUS` is also set (Phase-8 backlog: not yet
   implemented; for now, deploys are atomic and there's a brief 401 window).
3. Set `ENGINE_API_KEY` on the **web** Vercel project. Vercel preview
   deploys pick up the new value immediately; production needs a redeploy
   to flip.
4. After 60 seconds (long enough for both deploys), unset
   `ENGINE_API_KEY_PREVIOUS` on the engine.

In practice, brief 401s are tolerable; the engine returns a clear 401 and
the web layer surfaces a "Try again" toast. Don't rotate during peak.

### Service role key (engine ↔ Supabase)

- The engine uses `SUPABASE_SERVICE_ROLE_KEY` to bypass RLS — required
  because the engine acts on behalf of an authenticated user it received
  via the Next.js layer.
- This key MUST stay server-only. It's set on Cloud Run; never on Vercel
  (the web layer has its own narrower service role usage in
  `apps/web/src/lib/supabase/server.ts`).
- Rotation: regenerate at Supabase Studio → API → Service role; update
  Cloud Run; redeploy web. Only Sandra rotates this.

## Stripe webhook signature verification

`apps/web/src/app/api/stripe/webhook/route.ts` validates the
`Stripe-Signature` header on every webhook payload. Without this, an
attacker who guesses the URL can mark any bill as paid.

```typescript
const event = stripe.webhooks.constructEvent(rawBody, sig, webhookSecret);
```

If `constructEvent` throws, return 400 — never trust the payload otherwise.

## File upload validation

`apps/web/src/lib/utils/file-validation.ts` validates uploads on the
client side BEFORE upload via:

1. **Magic bytes** — first 4-8 bytes must match PDF (`%PDF`), JPEG
   (`FF D8 FF`), or PNG (`89 50 4E 47`). Never trust the Content-Type
   header alone.
2. **Size cap** — 20 MB. Postgres also has a CHECK constraint at this
   limit; the client check is a usability layer, not security.
3. **MIME type** — closed set: `application/pdf`, `image/jpeg`,
   `image/png`. Database CHECK constraint enforces this server-side too.

## CORS

Engine: configured via `apps/engine/app/main.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,  # comma-separated
    allow_credentials=True,
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type", "Authorization", "X-PostHog-..."],
)
```

`cors_origins` defaults to `https://clarobill.com,https://www.clarobill.com`
in prod and `http://localhost:3000` in dev. Never `*`.

## Rate limiting

Engine uses `slowapi` with `key_func=get_remote_address`. Real cap is
global (per-Cloud-Run-LB-IP) — see Phase 8 M15 for the docstring fix.
Limits:
- `/analyze`: 10/hour
- `/report`: 5/hour
- Everything else: 120/minute (default)

The engine is server-to-server-only; the web layer adds per-user
rate-limiting at the API-route layer (Phase 8 backlog: not yet implemented).

## Incident response — PHI was logged accidentally

1. **Stop the bleed.** If a deploy introduced PHI logging, roll back
   immediately ([../operations/deployment-runbook.md](../operations/deployment-runbook.md)).
2. **Quarantine the logs.** GCP Cloud Logging entries are retained per
   the project's retention policy. To purge:
   ```bash
   gcloud logging logs delete clarobill-engine
   ```
   Note: this nukes ALL engine logs, not just the PHI-bearing ones.
   Targeted deletion isn't possible in standard Cloud Logging — that's
   why preventing the leak matters more than recovering.
3. **Sentry.** Issues containing PHI: delete the issue from the Sentry
   dashboard. Sentry has retention policies that auto-purge after 90
   days, but explicit deletion is faster.
4. **PostHog.** Use the Person Profile delete API:
   `POST /api/projects/{id}/persons/delete_persons` with the affected
   distinct_ids.
5. **Document.** Add a postmortem at `docs/postmortems/YYYY-MM-DD-phi-leak.md`
   with the root cause + fix + prevention.
6. **Notify Sandra.** Even if the surface area was small. Compliance
   posture matters more than scale here.

## Cross-references

- CLAUDE.md Rule 9 — the engineering rule
- [database-schema.md](../architecture/database-schema.md) — RLS layer of defense
- [../operations/deployment-runbook.md](../operations/deployment-runbook.md) — rollback procedure
- [bug-fix-campaign.md](bug-fix-campaign.md) — M6 (prompt injection), M14 (PHI in logs), M18 (Sentry scrubbing) follow-ups

## Outstanding gaps (Phase 8 backlog)

- M14 — engine INFO logs include hospital_name + payer_name + plan_name
- M18 — Sentry `before_send` doesn't scrub `extra`, `breadcrumbs`, `contexts`
- H12 — `generate_bill_summary` doesn't share `_sanitise_for_prompt` discipline
- (Phase-8) — engine API key rotation has a brief 401 window (no `_PREVIOUS` slot)
