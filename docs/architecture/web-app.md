# Web Application Architecture

**Stack:** Next.js 14+ (App Router), TypeScript, Tailwind CSS  
**Hosting:** Vercel (Fluid Compute)  
**Auth:** Supabase Auth

---

## Directory Layout

```
apps/web/src/
├── app/                    # App Router pages and API routes
│   ├── (marketing)/        # Public marketing pages (landing, /learn, /compare, /state/*)
│   ├── (auth)/             # Sign-in, sign-up, password reset
│   ├── dashboard/          # Authenticated app shell
│   │   ├── bills/          # Bill list + per-bill analysis view
│   │   ├── profile/        # Account settings
│   │   └── referral/       # Referral code and credit display
│   ├── api/                # API route handlers
│   │   ├── bills/          # Upload, trigger analysis, fetch results
│   │   ├── insurance-card/ # Proxy to engine /insurance-card/extract
│   │   ├── stripe/
│   │   │   ├── checkout/   # POST: create Checkout Session
│   │   │   └── webhook/    # POST: receive Stripe events
│   │   ├── lead-magnet/    # POST: marketing email capture
│   │   ├── profile/        # PATCH: update user name
│   │   └── user/           # GET: user profile + plan data
│   └── learn/              # Blog/content pages (static)
├── components/             # UI components (one component per file)
├── lib/
│   ├── supabase/           # client.ts (browser), server.ts (server/route)
│   ├── gcp-auth.ts         # WIF: Vercel OIDC → Cloud Run idToken
│   ├── stripe.ts           # Stripe SDK instance + tier re-exports
│   ├── pricing.ts          # PRICING_TIERS + getPriceTier() — client-safe
│   ├── loops.ts            # Loops email helpers (server only)
│   ├── analytics.ts        # PostHog browser client
│   ├── analytics-server.ts # PostHog server-side event capture
│   ├── beta.ts             # isBetaMode() — reads NEXT_PUBLIC_BETA_MODE
│   ├── api/                # Typed fetch wrappers for the engine API
│   └── hooks/              # React hooks (useBill, useProfile, etc.)
└── types/                  # TypeScript interfaces for UI state
```

---

## Authentication

Supabase Auth handles all authentication. The web app uses two Supabase clients:

| Client | File | Use |
|---|---|---|
| Browser client | `lib/supabase/client.ts` | React components — reads auth session from localStorage |
| Server client | `lib/supabase/server.ts::createSupabaseServerClient()` | Server Components + API routes — reads session from cookies |
| Service client | `lib/supabase/server.ts::createSupabaseServiceClient()` | Bypasses RLS — used only in API routes where no user session exists (Stripe webhook, referral settlement) |

`getAuthenticatedUser()` (in `server.ts`) is the standard guard for API routes — returns the `User` object or null. All protected API routes call this first and return 401 if null.

### RLS enforcement

The anon key (browser client + server client) honors Supabase RLS. Users can only read/write their own rows. The service-role key (service client) bypasses RLS and is used only in server-side contexts where no user session is available.

---

## Engine communication

All calls to the Python FastAPI engine go through `lib/api/` wrappers. Authentication is dual-layer:

1. **WIF idToken** (production) — `lib/gcp-auth.ts::getCloudRunIdToken()` exchanges a Vercel OIDC token for a GCP service account idToken via STS. This token is sent as `Authorization: Bearer <token>`.
2. **Shared secret** (secondary) — `X-Engine-Api-Key: <ENGINE_API_KEY>` is sent alongside the idToken. The engine validates this header when set.

In local development, `getCloudRunIdToken()` returns null (no VERCEL env var) and the engine runs without auth (engine_api_key is empty string by default).

See `docs/decisions/2026-05-25-wif-vercel-cloud-run-auth.md` for the WIF design.

---

## API Routes

| Route | Method | Auth | Purpose |
|---|---|---|---|
| `/api/bills` | POST | Required | Create bill record + upload URL |
| `/api/bills/[id]` | GET | Required | Fetch bill + analysis status |
| `/api/bills/[id]/analyze` | POST | Required | Trigger engine analysis |
| `/api/bills/[id]/report` | GET | Required | Download report PDF |
| `/api/insurance-card/extract` | POST | Required | Proxy to engine insurance card extraction |
| `/api/stripe/checkout` | POST | Required | Create Stripe Checkout Session |
| `/api/stripe/webhook` | POST | Stripe sig | Receive `checkout.session.completed` |
| `/api/lead-magnet` | POST | None | Marketing email capture (Loops) |
| `/api/profile` | PATCH | Required | Update first/last name |
| `/api/user` | GET | Required | Return user profile + referral code |

---

## Pricing and Paywall

The paywall shows after analysis completes if savings exceed $20. Pricing is always calculated server-side from `analysis_results.total_potential_savings` — the client never sends or influences the price.

Tier lookup: `lib/pricing.ts::getPriceTier(savingsDollars)` returns the matching `PricingTier`. The checkout route calls this to set `unit_amount` on the Stripe line item.

See `docs/architecture/payments.md` for the full Stripe flow.

---

## Beta Mode

`lib/beta.ts::isBetaMode()` returns `true` when `NEXT_PUBLIC_BETA_MODE` is absent or not `"false"`. When true, the paywall is bypassed and all reports are free. Set `NEXT_PUBLIC_BETA_MODE=false` in Vercel production env vars to enable GA pricing.

---

## SEO / Marketing Pages

- `/learn/*` — Blog articles (static MDX or TSX, App Router)
- `/compare/*` — Side-by-side comparison pages
- `/state/*` — 50 state patient billing rights pages
- `/pricing` — Pricing tiers
- `robots.ts` — Dynamic robots.txt
- `sitemap.ts` — Dynamic sitemap

Public routes are declared in `middleware.ts::PUBLIC_EXACT` to bypass auth middleware.

---

*Last reviewed: 2026-05-25*
