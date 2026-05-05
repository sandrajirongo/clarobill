# ClaroBill Frontend — UI Design, Flow, and Implementation

This document covers the user experience philosophy, complete user flows, component architecture, and the reasoning behind key implementation decisions.

---

## Design Principles

**Zero friction over completeness.** Every form field, every screen, every step has a cost in user attention. We only ask for what is necessary to deliver the analysis. When something can be inferred (OCR hospital name, primary member, primary plan), we infer it rather than asking.

**Show value before asking for anything.** The teaser error is shown before payment. The upload wizard asks for confirmation, not re-entry. Every screen should answer "why should I continue?" before asking "what do you need from me?"

**Graceful recovery, not dead ends.** A failed analysis, a stuck bill, a lapsed session — each has a visible recovery path. We never leave users stranded.

**Errors are information, not failures.** When something goes wrong (analysis failed, payment pending, report generating), tell users what is happening and what will happen next. Don't disappear behind a spinner.

---

## User Flows

### New User (first bill)

```
Landing → Sign Up → Dashboard
  ↓
Upload zone (drop file or choose)
  ↓
Staged upload — name input pre-filled with filename stem
  ↓ (Upload & Analyze →)
/dashboard/bills/{id}/verify (expanded wizard)
  Step 1: "Who is this bill for?" — inline member creation
    → Full name, DOB, state, county, ZIP
    → After save: immediately prompted to add insurance plan
  Step 2: "Which insurance plan?" — inline plan creation
    → Insurer name, plan name, plan type
  Step 3: "Run Analysis" CTA
  ↓ (Run Analysis button)
Analyzing screen (animated progress steps, ~30s)
  ↓ (status = complete)
/dashboard/bills/{id} (results page)
  → Summary cards, AI summary, top billing error (teaser)
  → Paywall CTA with price if errors exist
  → (No CTA if zero errors found)
```

### Returning User (subsequent bill)

```
Dashboard → Upload zone
  ↓
Staged upload — name input
  ↓
/dashboard/bills/{id}/verify (compact mode — auto-selected if primary member + plan exist)
  → Summary card: patient name + insurance plan
  → "Change member or insurance →" to expand if needed
  ↓
Analyzing screen
  ↓
/dashboard/bills/{id}
```

### Post-Payment

```
Results page → "Get Full Report" CTA → Stripe Checkout
  ↓ (Stripe redirects back with ?payment=success)
Results page — paymentStatus = 'success'
  → Success banner: "Payment confirmed — your report is being generated"
  → Document card: "Generating your report…" spinner + explanation
  → Page polls every 5s and router.refresh() when reportUrl appears
  → Download buttons appear when report + dispute letter are ready
```

### Failed Bill Recovery

```
Dashboard → bill row shows "Failed" badge + "Retry →" link
  ↓
/dashboard/bills/{id}/verify (wizard — same as new bill, but status was 'failed')
  → User can re-select member/plan and re-submit
  → Verify route allows re-triggering for 'failed' status
  → Analysis runs again
```

---

## Component Architecture

### Upload Flow

**`bill-uploader.tsx`** — Drop zone with staged upload flow.

State machine: `idle → validating → staged → uploading → ready → (navigate to /verify)`

The staged state is the key addition. After file validation passes, we pause and show a name input rather than immediately uploading. This serves two purposes:
1. Users can give bills meaningful names ("January ER Visit") for later identification
2. The brief pause feels intentional — we're checking the file, not just streaming bytes

The name input is pre-filled with the filename stem (extension stripped). The default requires zero effort from users who don't care about naming.

**`use-bill-upload.ts`** — Two-phase upload hook.

- `stage(file)` — validates, sets `staged` state
- `upload(file, displayName)` — sends init request to `/api/bills/upload`, then PUTs to signed URL

The API accepts `displayName` and stores it as `bills.display_name`. Falls back to `file_name` at display time.

### Verification Wizard

**`bill-verification.tsx`** — Pre-analysis confirmation flow.

Two render modes based on profile completeness:

**Compact mode** (returning users, primary member + plan exist):
- Summary card showing patient + insurance
- Single "Run Analysis" CTA
- "Change →" link to expand if incorrect
- No hospital field — reduces cognitive load

**Expanded mode** (new users or when compact is expanded):
- Step 1: Patient selection + inline member creation form
- Step 2: Insurance plan selection + inline plan creation form
- No step 3 (hospital removed — see below)
- Run Analysis CTA (disabled until member + plan both selected)

**Why the hospital field was removed:**
The hospital name was an optional field used for BigQuery price-list lookup. OCR already extracts the hospital name from the bill. Presenting it as a user-editable field:
1. Implies the user needs to know the exact hospital name
2. Adds a step with unclear value ("what does this affect?")
3. Can be filled silently from OCR — better UX

The OCR-extracted name is passed to the engine automatically. Users never see this field.

**Analysis progress steps:**
During the ~30s engine run, instead of a bare spinner, we show 6 labeled steps advancing every 6 seconds. These map to real checks run by the rules engine:
1. Reading your bill (OCR + parse)
2. Extracting charge codes
3. Comparing against Medicare benchmarks (PFS data)
4. Checking your insurer's contracted rates (BigQuery MRF)
5. Scanning for duplicate charges
6. Finalizing your report

Steps advance on a timer regardless of actual engine progress — this is expected and honest. The labels are accurate (these checks do run), the timing is approximate. The visual effect is that users understand what we're doing rather than staring at an unexplained spinner.

### Results Page

**`bill-results-view.tsx`** — Analysis findings + paywall.

Server Component (`page.tsx`) fetches all data and passes it as props. Client component handles polling and interactions.

**Error sorting:** Errors are sorted by `estimatedOvercharge` descending before the paywall slice. The teaser always shows the highest-value finding. A teaser showing a $0 error (e.g. a code flag with no dollar estimate) kills paywall conversion because it makes the product look low-value.

**Paywall visibility:** `showPaywall = !hasPaid && errors.length + hiddenErrorCount > 0`. On a clean bill (zero errors), the paywall CTA is hidden entirely. Offering to sell a "full report" when there's nothing to report is dishonest and destroys trust.

**Post-payment polling:** After payment, report generation is async (the engine generates a PDF + dispute letter, which takes 15–60s). The component polls every 5s and calls `router.refresh()` when reportUrl appears. The success banner copy changes based on whether the report is ready:
- Pending: "Payment confirmed — your report and dispute letter are being generated. This page updates automatically."
- Ready: "Payment confirmed. Your documents are ready below."

This prevents the confusing state where the banner says "prepared below" but nothing is below yet.

### Dashboard

**`dashboard/page.tsx`** — Server Component with bill list.

Bill name display: `display_name ?? file_name`. If a `display_name` exists, the original filename is shown as a small subtitle below it so the file is still identifiable.

Status → action mapping:

| Status | Badge | Action link |
|--------|-------|-------------|
| uploading | Needs review | Analyze → (to /verify) |
| ocr_processing | Reading… | View → (to results) |
| analyzing | Analyzing… | View → (to results, shows loading state) |
| complete | Ready | View → |
| failed | Failed | Retry → (to /verify, allows re-run) |

The onboarding nudge was reframed from "Set up your profile first" to "Upload your first bill to get started." The profile setup happens inline on the verify page — prompting users to set up a profile before they've seen any value from the product is friction without reward.

---

## API Routes

### `POST /api/bills/upload`

Creates the bill record and returns a signed upload URL. Accepts `displayName` for the user-supplied label.

### `POST /api/bills/[billId]/verify`

Saves the confirmed member + insurance to the bill record and triggers the engine. Accepts both `uploading` and `failed` bill statuses so users can retry after a failure.

### `GET /api/profile/members`

Returns all members for the authenticated user with nested `insurance_plans`. Used to populate the verification wizard.

### `POST /api/profile/members`

Creates a new profile member. If `isPrimary: true`, unsets the existing primary first.

### `POST /api/profile/members/[memberId]/plans`

Adds an insurance plan to an existing member.

---

## Session Management

Sessions use Supabase Auth with `@supabase/ssr` for cookie-based SSR support. Key configuration:

**Cookie persistence:** Auth cookies now have a `maxAge` fallback of 7 days. Without this, cookies were session cookies (expired on browser close), causing users to be logged out after switching tabs or restarting the browser.

**Browser client:** `autoRefreshToken: true` and `persistSession: true` are set on the browser client. This ensures active tabs proactively refresh JWTs before expiry so users aren't logged out mid-session.

**Middleware:** The middleware calls `supabase.auth.getUser()` on every request, which triggers token refresh when the access token is near expiry. Combined with the `maxAge` cookie fix, sessions persist correctly across the 30–45 minute idle window.

**Token lifetime:** Supabase project JWT access token lifetime must be ≥ 1 hour (configured in Supabase dashboard → Auth → Settings). The 7-day cookie `maxAge` ensures the refresh token survives browser restarts and can silently re-issue access tokens.

---

## CSS Architecture

All component styles use CSS Modules (`.module.css`) co-located with the component file. No global style pollution.

CSS custom properties (defined in `globals.css`):
- Colors: `--sage`, `--sage-l`, `--sage-dark`, `--accent`, `--cream`, `--cream2`, `--white`, `--border`
- Text: `--txt`, `--txt2`, `--txt3`
- Borders: `--r` (small), `--r-xl` (large), `--r-full` (pill)
- Fonts: `--fd` (display/headings), `--fb` (body/UI)

Animation: `@keyframes spin` and `@keyframes pulse` are defined per-module where needed.

---

## Database Schema (relevant to frontend)

```sql
bills
  id                uuid  primary key
  user_id           uuid  references auth.users
  display_name      text  -- user-supplied label; NULL falls back to file_name
  file_name         text  -- original filename from upload
  file_path         text  -- storage path: {user_id}/{bill_id}/{file_name}
  status            text  -- uploading | ocr_processing | analyzing | complete | failed
  hospital_npi      text  -- OCR-extracted
  hospital_name     text  -- OCR-extracted
  profile_member_id uuid  -- confirmed at verify time
  payer_name        text  -- from selected insurance plan
  plan_name         text  -- from selected insurance plan
  confirmed_at      timestamptz  -- when user completed verification

profile_members
  id            uuid
  user_id       uuid
  full_name     text
  date_of_birth date
  state         text  -- CMS uppercase, e.g. "CALIFORNIA"
  county        text  -- e.g. "LOS ANGELES"
  zip_code      text  -- 5-digit
  is_primary    boolean

insurance_plans
  id                uuid
  profile_member_id uuid
  payer_name        text
  plan_name         text
  plan_type         text  -- commercial | medicare | medicaid | tricare | self_pay
  is_primary_plan   boolean
```

---

## Pending: Migration Deployment

**Migration `20260417000014_bills_display_name.sql`** adds `display_name TEXT` to the `bills` table. This migration has been committed to `supabase/migrations/` but must be applied to the production database manually via the Supabase dashboard:

1. Go to Supabase project → SQL Editor
2. Run:
   ```sql
   ALTER TABLE public.bills ADD COLUMN display_name text;
   COMMENT ON COLUMN public.bills.display_name IS
     'User-supplied label for the bill (e.g. "January ER Visit"). Falls back to file_name when null.';
   ```

Until this runs, the upload flow will work (the API silently ignores `displayName` inserts to a missing column — Supabase will return an error but the bill row is still created), but display names won't be persisted.

---

_Last reviewed: 2026-05-05_
