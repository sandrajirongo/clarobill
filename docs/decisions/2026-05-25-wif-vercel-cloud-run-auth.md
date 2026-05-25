# Decision: Workload Identity Federation for Vercel → Cloud Run Auth

**Date:** 2026-05-25  
**Status:** Shipped  
**Owners:** Engineering

---

## Context

The Next.js frontend on Vercel needs to call the Python engine on Cloud Run. Cloud Run requires an OIDC `id_token` in the `Authorization: Bearer` header — the caller must prove it is authorized.

Two options were considered:

1. **Static API key only** — engine validates a shared secret (`ENGINE_API_KEY`) on every request.
2. **Workload Identity Federation (WIF) + static key** — Vercel presents an OIDC token that GCP exchanges for a real service account identity. Static key is a secondary layer.

---

## Decision

**Use WIF as the primary auth mechanism, with a shared static key as a secondary check.**

---

## How It Works

```
Vercel Function
  │ 1. @vercel/oidc::getVercelOidcToken()
  │    → Vercel signs a short-lived OIDC JWT (iss = accounts.google.com, aud = WIF audience)
  │
  │ 2. POST https://sts.googleapis.com/v1/token
  │    → exchange Vercel OIDC token for a GCP federated token
  │
  │ 3. POST https://iamcredentials.googleapis.com/v1/serviceAccounts/{SA}:generateIdToken
  │    → impersonate clarobill-vercel-sa, generate a Cloud Run idToken
  │
  │ 4. GET/POST https://clarobill-engine-xxx-uc.a.run.app/api/v1/...
  │    Authorization: Bearer <idToken>
  │    X-Engine-Api-Key: <ENGINE_API_KEY>
  │
Cloud Run
  │ 5. Cloud Run validates the idToken (GCP-managed, no app code needed)
  │ 6. Engine middleware validates X-Engine-Api-Key (app-level check)
```

Implementation: `apps/web/src/lib/gcp-auth.ts::getCloudRunIdToken(cloudRunUrl)`.

The WIF audience is constructed from three env vars with safe defaults:
```typescript
const pool = process.env.GCP_WORKLOAD_IDENTITY_POOL_ID ?? 'clarobill-vercel-pool';
const provider = process.env.GCP_WORKLOAD_IDENTITY_POOL_PROVIDER_ID ?? 'vercel-provider';
const WIF_AUDIENCE = `//iam.googleapis.com/projects/${projectNumber}/locations/global/workloadIdentityPools/${pool}/providers/${provider}`;
```

---

## Why WIF instead of a static key alone

**Security properties of WIF:**
- No long-lived credentials to rotate, leak, or compromise. The OIDC token is short-lived (minutes) and scoped to the Vercel deployment.
- GCP validates the token issuer and audience — a stolen token is useless outside the expected exchange chain.
- IAM audit logs record every impersonation — `generateIdToken` calls appear in Cloud Audit Logs under the `clarobill-vercel-sa` service account.
- Principle of least privilege: `clarobill-vercel-sa` has only `roles/run.invoker` on the engine service. It cannot access BigQuery, Supabase, or any other resource.

**Why keep the static key as a secondary check:**
- Defense in depth — if WIF config is misconfigured in a non-production environment, the engine still rejects unauthenticated callers.
- Simplifies local dev — without `VERCEL` env var set, `getCloudRunIdToken()` returns null. The engine's API key check is the only gate locally.

---

## Local Development

`getCloudRunIdToken()` checks `process.env.VERCEL` before attempting the WIF exchange. If unset (local dev), it returns `null` immediately — no GCP calls, no auth errors. The engine runs without a Bearer token; only the static key check applies (and it is skipped when `ENGINE_API_KEY` is empty string).

---

## GCP Resources Required

| Resource | Name |
|---|---|
| Workload Identity Pool | `clarobill-vercel-pool` |
| Pool Provider | `vercel-provider` (OIDC, issuer `https://oidc.vercel.com`) |
| Service Account | `clarobill-vercel-sa@clarobill-prd.iam.gserviceaccount.com` |
| SA role on Cloud Run service | `roles/run.invoker` |
| SA allowed to be impersonated by pool | `roles/iam.workloadIdentityUser` binding on SA |

---

## Consequences

- Vercel deployments must have `GCP_PROJECT_NUMBER` set. Without it, `getCloudRunIdToken()` returns `null` and all engine calls proceed without a Bearer token.
- Token generation adds ~150ms latency per cold Vercel function. Warm instances cache the token within the function lifetime.
- `clarobill-vercel-sa` cannot be deleted or its roles removed without breaking all Vercel → Cloud Run calls.
- Rotating the WIF provider or pool requires updating `GCP_WORKLOAD_IDENTITY_POOL_ID` / `GCP_WORKLOAD_IDENTITY_POOL_PROVIDER_ID` env vars on Vercel.
