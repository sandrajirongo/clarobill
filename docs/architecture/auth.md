# Authentication

How users sign into ClaroBill across the web app, the mobile app, and the engine.
Single source of truth for accounts: the Supabase Auth project at
`kqecgxxxvvkffjwxxuwp.supabase.co`.

## At a glance

| Surface | Auth methods |
|---|---|
| Web (`apps/web`) | Email + password, magic link, OTP, password reset |
| Mobile (`apps/mobile`) | Email + password, 8-digit OTP code, password reset |
| Engine (`apps/engine`) | None — service-to-service via service-role key |

All three share **one Supabase project**. A user signed up on the web can sign
in on mobile with the same credentials, and vice versa.

## Supabase project configuration

These settings live in the Supabase Dashboard and must be in place for any
of the auth flows to work. They are not in the repo; this doc is the
operational record.

### Authentication → Sign in / Providers → Email

| Setting | Value | Why |
|---|---|---|
| Enable email provider | ✅ on | Required for email/password and OTP |
| Confirm email | ✅ on | Forces users to verify ownership before sign-in |
| Secure email change | ✅ on | Sends confirmation to both old and new addresses |
| OTP Length | **8** | The mobile app's `OTP_LENGTH` constant is hard-coded to match. Changing this requires updating `apps/mobile/src/app/(auth)/magic-link.tsx`. |
| OTP Expiration | 3600 (1 hour) | Mentioned in the email template body copy |

### Authentication → URL Configuration

| Setting | Value |
|---|---|
| Site URL | `https://www.clarobill.com` |
| Redirect URLs | `https://www.clarobill.com/**`, `clarobill://**`, `http://localhost:3000/**` (dev) |

The `clarobill://**` entry is required for the mobile password-reset flow.
When a user taps the reset link in the email, iOS / Android opens the app
via the `clarobill://reset-password` scheme.

### Authentication → SMTP Settings

Recommended: **custom SMTP via SendGrid**. Use the `SENDGRID_API_KEY` already
provisioned in `apps/engine/.env` (same key powers the referral-credit
emails in the Stripe webhook). Supabase's free-tier built-in SMTP rate-limits
to 4 emails/hour and frequently gets spam-filtered.

### Authentication → Email Templates

Three brand-styled templates are managed in the Supabase Dashboard:

| Template | Sends when | Variables used |
|---|---|---|
| Confirm signup | New user signs up | `{{ .ConfirmationURL }}` |
| Magic Link | `signInWithOtp()` is called | `{{ .Token }}` (8-digit code), `{{ .ConfirmationURL }}` (web sign-in link) |
| Reset Password | `resetPasswordForEmail()` is called | `{{ .ConfirmationURL }}` (deep link to `clarobill://reset-password` for mobile, web URL for desktop) |

**Magic Link template special case:** the same template serves both mobile and
web from a single email. The 8-digit code is rendered prominently for mobile
users; an outlined "Sign in on the web" button below the code uses the link
URL for web users. One Supabase project = one Magic Link template, so this
dual-purpose design is intentional.

Reference HTML for the Magic Link template is on the Desktop, not in the
repo (per `feedback_email_files_not_committed`). Filename:
`clarobill-supabase-magic-link-template.md`.

---

## Mobile auth architecture

### Storage

`@supabase/supabase-js` configured with a **LargeSecureStore** adapter on top of
`expo-secure-store`. Located at `apps/mobile/src/lib/supabase.ts`.

Why custom adapter: iOS `SecureStore` has a 2048-byte per-key limit. Supabase
session tokens regularly exceed this. `LargeSecureStore` splits the value
across N chunks keyed by index (e.g. `key__0`, `key__1`, ...) with a header
key (`__chunked__:N`) that records the chunk count.

### Provider + hook

`AuthProvider` at `apps/mobile/src/lib/auth/context.tsx` exposes a `useAuth()`
hook with this shape:

```ts
{
  session: Session | null,
  user: User | null,
  isLoading: boolean,                                       // true during cold-start restore
  signInWithPassword(email, password),
  signUpWithPassword(email, password),
  sendEmailOtp(email),                                      // sends 8-digit code email
  verifyEmailOtp(email, token),
  resetPasswordForEmail(email),                             // sends reset link to clarobill://reset-password
  signOut(),
}
```

Each method returns `{ error: string | null }` for symmetric ergonomics.
The provider subscribes to `supabase.auth.onAuthStateChange` so any sign-in,
sign-out, or token refresh updates the React state immediately.

### Route guard

The root layout `apps/mobile/src/app/_layout.tsx` wraps everything in
`AuthProvider` and runs a `useSegments`-based route guard:

| Auth state | Current group | Action |
|---|---|---|
| Loading initial session | any | Show splash spinner |
| No user, in `(auth)` group | `(auth)/login` etc. | Stay |
| No user, in `(tabs)` group | `(tabs)/index` | Redirect to `/login` |
| Has user, in `(auth)` group | `(auth)/login` etc. | Redirect to `/` |
| Has user, in `(tabs)` group | `(tabs)/index` | Stay |

### Screens

| File | Route | Purpose |
|---|---|---|
| `(auth)/login.tsx` | `/login` | Email + password. Links to forgot-password, magic-link, signup. |
| `(auth)/signup.tsx` | `/signup` | Email + password account creation. Triggers Supabase confirmation email. |
| `(auth)/forgot-password.tsx` | `/forgot-password` | Sends a reset link via `resetPasswordForEmail`. |
| `(auth)/magic-link.tsx` | `/magic-link` | Two-step flow: enter email → send code → enter 8-digit code → verify. Includes a 30-second resend cooldown. |
| `(tabs)/index.tsx` | `/` | Placeholder home; shows signed-in email + sign-out. |

### OTP / magic-link flow

Mobile uses the **same** `signInWithOtp` Supabase call as web, but interprets
the email as an 8-digit code rather than a clickable link. Code flows:

1. User enters email on `/magic-link` → tap **Send code**
2. App calls `supabase.auth.signInWithOtp({ email, shouldCreateUser: false })`
3. Supabase emails the Magic Link template; user reads the 8-digit code
4. User types code into the verify screen → tap **Verify code**
5. App calls `supabase.auth.verifyOtp({ email, token: code, type: 'email' })`
6. Success → `onAuthStateChange` fires → route guard redirects to `/`

**Rate-limit guard:** the resend button is disabled for 30 seconds after each
send. `RESEND_COOLDOWN_SECONDS` constant in `magic-link.tsx`. Matches
Supabase's per-email rate limit so a tap never produces a "rate limit
exceeded" error.

### Password reset flow

1. User enters email on `/forgot-password` → tap **Send reset link**
2. App calls `supabase.auth.resetPasswordForEmail(email, { redirectTo: 'clarobill://reset-password' })`
3. User receives email; tapping the button opens the app via deep link
4. **TODO:** mobile reset-password landing screen at `/reset-password` is not
   yet implemented. Consumes the recovery token and lets the user set a new
   password. See `apps/mobile/src/app/(auth)/` for where it goes when added.

### Sign out

`useAuth().signOut()` → `supabase.auth.signOut()` → `onAuthStateChange` → user
becomes `null` → route guard redirects to `/login`. The SecureStore session
is wiped at the same time.

---

## Web auth architecture

Lives at `apps/web/src/lib/supabase/` and `apps/web/src/app/auth/`.

Uses `@supabase/ssr` for server-side rendering, with two distinct clients:
`createSupabaseBrowserClient` (client components) and `createSupabaseServerClient`
(server components, route handlers). The service-role client
(`createSupabaseServiceClient`) is reserved for code paths that must bypass RLS
(e.g. referral lookups in `/api/stripe/checkout`).

Auth screens are file-based routes under `apps/web/src/app/auth/`:

| Path | Purpose |
|---|---|
| `auth/sign-in/page.tsx` | Email + password, OR magic link via `signInWithOtp` |
| `auth/sign-up/page.tsx` | Account creation |
| `auth/update-password/page.tsx` | Set new password after clicking the reset link |
| `auth/callback/route.ts` | OAuth / magic-link callback handler |

The callback route exchanges the `?code=` URL parameter for a session via
`supabase.auth.exchangeCodeForSession`. This is what makes the "Sign in on
the web" button in the Magic Link email work end-to-end.

---

## Service-role usage in the engine

The Python engine never authenticates as a user. It uses the
`SUPABASE_SERVICE_ROLE_KEY` from `apps/engine/.env` to write to database
tables that bypass RLS — e.g. inserting `analysis_results` rows for any
user's bill after the engine completes its pipeline.

This is why **the mobile app must never receive the service-role key.**
The mobile app uses the public anon key. RLS policies on every table enforce
`auth.uid() = user_id` so a signed-in user can only read and write their own
rows.

---

## Adding a new auth flow

Standard recipe for adding e.g. "Sign in with Apple":

1. **Supabase Dashboard:** Authentication → Sign in / Providers → enable
   the provider and configure its OAuth credentials. Add the appropriate
   redirect URLs (mobile: `clarobill://oauth/callback`; web: the production
   site URL).
2. **Update auth context:** add the new method to `AuthContextValue`
   in `apps/mobile/src/lib/auth/context.tsx`. Wrap the Supabase call and
   return `{ error: string | null }` for consistency with existing methods.
3. **Add the UI:** new Pressable on `/login` (or a new screen if the flow
   needs intermediate steps). Use the same accessibility props pattern
   (`accessibilityRole`, `accessibilityLabel`, `accessibilityState`).
4. **Handle the deep link:** if the provider redirects back via
   `clarobill://oauth/callback`, register a top-level Expo Linking handler
   that consumes the URL and calls `supabase.auth.exchangeCodeForSession`.
5. **Mirror on web:** add the corresponding button to
   `apps/web/src/app/auth/sign-in/page.tsx`. Web uses
   `supabase.auth.signInWithOAuth({ provider, options: { redirectTo } })`.
6. **Document here:** add to the "At a glance" table above.

---

## Common operational issues

| Symptom | Cause | Fix |
|---|---|---|
| Signup email never arrives | Supabase free-tier SMTP rate limit or spam filter | Configure custom SMTP (SendGrid) in Supabase Dashboard |
| OTP says "invalid token" | OTP length mismatch | Verify Dashboard "OTP Length" matches `OTP_LENGTH` constant in `magic-link.tsx` |
| Reset link opens browser not app on mobile | Missing redirect URL | Add `clarobill://**` to Authentication → URL Configuration → Redirect URLs |
| Web magic link goes to localhost | `Site URL` set to localhost | Set to production URL in URL Configuration |
| Mobile session lost on app restart | LargeSecureStore corruption | Sign out + sign in again; the LargeSecureStore reset on next setItem wipes orphaned chunks |
| Web sees user, mobile doesn't (or vice versa) | Different Supabase projects | Verify both `EXPO_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_URL` point at the same project |

---

## Files

| Path | Role |
|---|---|
| `apps/mobile/src/lib/supabase.ts` | Mobile Supabase client + LargeSecureStore adapter |
| `apps/mobile/src/lib/auth/context.tsx` | AuthProvider + useAuth hook |
| `apps/mobile/src/app/_layout.tsx` | Root layout + route guard |
| `apps/mobile/src/app/(auth)/` | Auth route group (login, signup, forgot-password, magic-link) |
| `apps/web/src/lib/supabase/client.ts` | Browser-side Supabase client |
| `apps/web/src/lib/supabase/server.ts` | Server-side + service-role clients |
| `apps/web/src/app/auth/` | Web auth route group |
| `~/Desktop/clarobill-supabase-magic-link-template.md` | Brand-styled Magic Link email template (not in repo per `feedback_email_files_not_committed`) |
