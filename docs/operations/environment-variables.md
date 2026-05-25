# Environment Variables Reference

This document lists every environment variable used by the ClaroBill monorepo.
It is the authoritative reference for configuring new environments.

**Never commit `.env` files.** Use `.env.local` for local dev (gitignored).
For production, set variables in Vercel (web app) and as Cloud Run env vars (engine).

---

## Web App (`apps/web`)

### Required in production

| Variable | Description |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL (`https://<ref>.supabase.co`). Public. |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon/public key. Public. Honors RLS. |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service-role key. **Secret.** Bypasses RLS. |
| `STRIPE_SECRET_KEY` | Stripe secret key (`sk_live_...`). **Secret.** |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret (`whsec_...`). **Secret.** |
| `LOOPS_API_KEY` | Loops API key. **Secret.** All Loops calls no-op if absent. |
| `ENGINE_URL` | Cloud Run service URL (`https://clarobill-engine-xxx-uc.a.run.app`). |
| `ENGINE_API_KEY` | Shared secret sent as `X-Engine-Api-Key`. **Secret.** |
| `GCP_PROJECT_NUMBER` | Numeric GCP project number (e.g. `1034973715010`). Used for WIF. |

### Optional / feature-gated

| Variable | Default | Description |
|---|---|---|
| `NEXT_PUBLIC_BETA_MODE` | `true` | Set to `"false"` to enable GA pricing. When absent or not `"false"`, all reports are free. |
| `NEXT_PUBLIC_POSTHOG_PROJECT_TOKEN` | — | PostHog project API key. Analytics silently skipped if absent. |
| `NEXT_PUBLIC_POSTHOG_HOST` | `https://us.i.posthog.com` | PostHog ingestion endpoint. |
| `NEXT_PUBLIC_POSTHOG_DEBUG` | — | Set to `"true"` to enable PostHog debug logging. |
| `NEXT_PUBLIC_SENTRY_DSN` | — | Sentry DSN for frontend error monitoring. |
| `NEXT_PUBLIC_SITE_URL` | — | Canonical site URL for SEO / OG tags. |
| `NEXT_PUBLIC_GA` | — | Google Analytics measurement ID. |
| `GOOGLE_SITE_VERIFICATION` | — | Google Search Console meta tag content. |
| `BING_SITE_VERIFICATION` | — | Bing Webmaster Tools meta tag content. |
| `LOOPS_PAYMENT_EMAIL_ID` | — | Loops transactional template ID for payment receipts. Email skipped if absent. |
| `LOOPS_BILLING_TRAPS_EMAIL_ID` | — | Loops template ID for billing traps educational email. |
| `SENDGRID_API_KEY` | — | SendGrid key for referral credit emails. Email skipped if absent. |
| `SENDGRID_FROM_EMAIL` | `noreply@clarobill.com` | From address for SendGrid emails. |
| `GCP_SERVICE_ACCOUNT_EMAIL` | `clarobill-vercel-sa@clarobill-prd.iam.gserviceaccount.com` | SA email for WIF token impersonation. |
| `GCP_WORKLOAD_IDENTITY_POOL_ID` | `clarobill-vercel-pool` | WIF pool ID. |
| `GCP_WORKLOAD_IDENTITY_POOL_PROVIDER_ID` | `vercel-provider` | WIF provider ID. |

### Runtime / system (not manually set)

| Variable | Set by | Description |
|---|---|---|
| `VERCEL` | Vercel platform | Non-empty string when running on Vercel. Used by `gcp-auth.ts` to gate WIF — local dev gets `null` idToken. |
| `NEXT_RUNTIME` | Next.js | `"edge"` or `"nodejs"`. |
| `NODE_ENV` | Next.js | `"production"` / `"development"` / `"test"`. |

---

## Engine (`apps/engine`)

Loaded by Pydantic `Settings` (BaseSettings) from environment or `.env` file.

### Required in production

| Variable | Description |
|---|---|
| `SUPABASE_URL` | Supabase project URL. |
| `SUPABASE_SERVICE_ROLE_KEY` | Service-role key. Bypasses RLS for all DB reads/writes. |
| `ANTHROPIC_API_KEY` | Anthropic API key. Used as AI fallback (Claude Sonnet 4.6). |
| `SENDGRID_API_KEY` | SendGrid key for report delivery emails. |
| `SENDGRID_FROM_EMAIL` | From address (e.g. `reports@clarobill.com`). |

### Optional / feature-gated

| Variable | Default | Description |
|---|---|---|
| `GCP_PROJECT_ID` | `""` | GCP project ID. When empty, BigQuery client is `None` and all BQ-backed rules no-op silently. Set to `"clarobill-prd"` in production. |
| `BIGQUERY_DATASET` | `"hospital_prices"` | BigQuery dataset name for MRF tables. |
| `VERTEX_AI_LOCATION` | `"us-central1"` | Vertex AI region for Gemini calls. |
| `GOOGLE_CREDENTIALS_JSON` | `""` | Full JSON content of a service account key. Preferred for containerized deployments. |
| `GOOGLE_APPLICATION_CREDENTIALS` | `""` | File path to a service account key JSON. Local dev fallback when `GOOGLE_CREDENTIALS_JSON` is unset. |
| `BQ_READER_CREDENTIALS_JSON` | `""` | JSON content of `clarobill-bq-reader-sa` key. Leave empty to fall back to `GOOGLE_APPLICATION_CREDENTIALS`. |
| `GCS_MRF_STAGING_BUCKET` | `"mrf-staging"` | GCS bucket name for staging MRF blobs before parsing. |
| `ENGINE_API_KEY` | `""` | Shared secret validated on every incoming request via `X-Engine-Api-Key` header. Key check skipped when empty (local dev). |
| `SENTRY_DSN` | `""` | Sentry DSN for engine error monitoring. Silent if absent. |
| `POSTHOG_API_KEY` | `""` | PostHog key for engine-side event capture. Silent if absent. |
| `POSTHOG_HOST` | `"https://us.i.posthog.com"` | PostHog ingestion endpoint. |
| `ENVIRONMENT` | `"development"` | Set to `"production"` to tighten security checks. |
| `LOG_LEVEL` | `"INFO"` | Python logging level. |
| `ALLOWED_ORIGINS` | `"http://localhost:3000"` | Comma-separated CORS origins. Set to `"https://clarobill.com"` in production. |

---

## Local development setup

Minimum `.env.local` for the web app:

```bash
NEXT_PUBLIC_SUPABASE_URL=https://<ref>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon-key>
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
ENGINE_URL=http://localhost:8000
ENGINE_API_KEY=dev-secret
```

Minimum `.env` for the engine:

```bash
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
ANTHROPIC_API_KEY=sk-ant-...
SENDGRID_API_KEY=SG....
SENDGRID_FROM_EMAIL=dev@clarobill.com
ENGINE_API_KEY=dev-secret
```

BigQuery-backed rules (HOSPITAL_CHARGE_OUTLIER, NEGOTIATED_RATE_EXCEEDED, NEGOTIATED_CEILING_EXCEEDED) will silently no-op without `GCP_PROJECT_ID`. All other rules run against Supabase data and work without GCP credentials.

---

## Production environment (Vercel)

Set via Vercel dashboard or `vercel env add`. Key vars confirmed set as of 2026-05-25:

- `NEXT_PUBLIC_SUPABASE_URL` ✓
- `NEXT_PUBLIC_SUPABASE_ANON_KEY` ✓
- `SUPABASE_SERVICE_ROLE_KEY` ✓
- `ENGINE_URL` ✓ (`https://clarobill-engine-jal2wnylfq-uc.a.run.app`)
- `ENGINE_API_KEY` ✓
- `GCP_PROJECT_NUMBER` ✓ (`1034973715010`)
- `NEXT_PUBLIC_BETA_MODE` ✓ (`false` — GA pricing active)

---

*Last reviewed: 2026-05-25*
