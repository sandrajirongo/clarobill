# Supabase Security Model

**Date:** 2026-04-10
**Status:** Implemented

---

## Context

ClaroBill processes medical bills containing Protected Health Information (PHI). The database holds patient bill data, OCR output, AI analysis results, and payment records. We use Supabase (PostgreSQL) as the database with two access paths:

1. **Next.js API routes** — server-side, running in our infrastructure, using either a session-scoped anon client or the service role client
2. **FastAPI engine** — separate backend service, always uses the service role key

The Supabase anon key (`NEXT_PUBLIC_SUPABASE_ANON_KEY`) is embedded in the browser bundle and is therefore publicly visible to anyone who inspects the page source. This is by design in Supabase's architecture — the anon key alone grants no data access; Row Level Security (RLS) policies are the actual enforcement layer.

---

## Decision

### Server-only access model

All database access goes through our own servers. No component allows direct browser-to-database queries. The anon key is used only for Supabase Auth (sign-in, session management) — never for data reads or writes from the browser.

### RLS enabled on every table

RLS is enabled on all tables in the `public` schema. This means:
- A request using the anon key with no valid session gets denied on every table
- A request using the anon key with a valid session is scoped strictly by the table's policy
- A request using the service role key bypasses RLS entirely — full access

### Two client types, used deliberately

**`createSupabaseServerClient()`** — anon key + user session cookie
- Used in Next.js API routes where the authenticated user's identity matters
- `auth.uid()` resolves to the signed-in user, so RLS policies scope reads/writes to their own data
- Never used in webhook handlers or background jobs (no user session exists in those contexts)

**`createSupabaseServiceClient()`** — service role key, bypasses RLS
- Used for admin operations: storage signed URL generation, Stripe webhook payment updates, referral credit increments
- Used in the FastAPI engine for all CMS reference data reads and bill analysis writes
- The service role key is never in a `NEXT_PUBLIC_` environment variable — server-side only

---

## Table-by-table policy breakdown

### User data tables — isolated by `auth.uid()`

These tables contain PHI and user-specific data. Each has a `FOR ALL` RLS policy that prevents any user from accessing another user's rows.

| Table | Policy | Effect |
|---|---|---|
| `bills` | `auth.uid() = user_id` | Users see and modify only their own bills |
| `line_items` | `EXISTS (SELECT 1 FROM bills WHERE bills.id = line_items.bill_id AND bills.user_id = auth.uid())` | Scoped via parent bill ownership |
| `analysis_results` | Same subquery pattern via `bills` | Same |
| `payments` | `auth.uid() = user_id` | Users see only their own payment records |
| `referral_codes` | `user_id = auth.uid()` | Users see only their own referral code and credit balance |
| `referrals` | `referrer_user_id = auth.uid() OR referred_user_id = auth.uid()` (SELECT only) | Participants can view; writes handled exclusively by service role via webhook |

The `FOR ALL` policy covers SELECT, INSERT, UPDATE, and DELETE. For INSERT, PostgreSQL applies the `USING` expression as the `WITH CHECK` constraint — meaning a user cannot insert a row with someone else's `user_id`.

### CMS reference tables — no policy (deny by default)

These tables contain public CMS Medicare data (fee schedules, NCCI edits, OPPS caps, locality mappings). They hold no PHI and no user data. Only the FastAPI engine reads them, via the service role key which bypasses RLS.

| Table | Policies | Reason |
|---|---|---|
| `cms_pfs_indicators` | None | Engine reads via service role; anon access unnecessary |
| `cms_localities` | None | Same |
| `cms_opps_cap` | None | Same |
| `cms_anesthesia_cf` | None | Same |
| `cms_anesthesia_base_units` | None | Same |
| `cms_county_locality` | None | Same |
| `ncci_edit_pairs` | None | Same |

RLS enabled + no policy = deny for all non-service-role requests. This is intentional. Earlier migrations created permissive `FOR SELECT USING (true)` policies on these tables; those were dropped on 2026-04-10.

---

## Component implications

### FastAPI engine (`apps/engine`)
- Uses `SUPABASE_SERVICE_ROLE_KEY` exclusively
- Bypasses RLS on all tables — reads CMS data, writes bill/line_item/analysis_results rows
- No risk from policy changes; service role is always unrestricted

### Next.js API routes (`apps/web/src/app/api`)
- Most routes use `createSupabaseServerClient()` — anon key + user session. These depend on the user isolation policies being in place. If those policies were removed, bill/analysis/payment reads would return empty.
- Stripe webhook (`/api/stripe/webhook`) uses `createSupabaseServiceClient()` for all DB operations — Stripe calls this endpoint directly with no user session, so `auth.uid()` would be null and user isolation policies would block it. Service client is required here.
- Storage operations (signed URL generation, PDF uploads) use `createSupabaseServiceClient()` — storage bucket permissions are separate from table RLS

### Next.js pages and components (`apps/web/src/app`, `apps/web/src/components`)
- No component queries Supabase directly from the browser
- All data fetching goes through Next.js API routes (server-side), which then apply the appropriate client

### Supabase Auth
- Sign-in, sign-out, and session refresh use the anon key via `@supabase/ssr`
- This is the only legitimate use of the anon key and operates on `auth.*` tables, not `public.*`

---

## Consequences

**Positive:**
- A compromised or leaked anon key grants no data access — RLS denies everything without a valid session
- PHI is isolated at the database level, not just the application level
- CMS reference tables cannot be bulk-scraped via the public API
- Each access path (user session vs service role) has the minimum permissions it needs

**Constraints to be aware of:**
- Any new Next.js API route that runs without a user session (webhooks, cron jobs, background tasks) must use `createSupabaseServiceClient()`, not `createSupabaseServerClient()`
- Any new table added to the schema needs an explicit RLS decision before going to production — the default (RLS disabled) is not acceptable for any table holding user data or internal reference data
- New CMS reference tables should follow the same pattern: enable RLS, create no policies, let the engine access via service role
