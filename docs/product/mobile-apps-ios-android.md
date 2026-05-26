# ClaroBill iOS + Android Mobile Apps

## Context

ClaroBill has a full-featured Next.js web app. The goal is native iOS and Android apps that match the web app feature-for-feature. Users who want to photograph a bill with their phone camera and get results in a mobile-native experience. Both apps will be built from a single React Native / Expo codebase inside the existing monorepo, sharing TypeScript types from `packages/shared/` and calling the same API layer the web app already uses.

---

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Framework | React Native + Expo SDK 52+ | Single codebase, shares types with web, OTA updates via EAS Update |
| Repo location | `apps/mobile/` inside this monorepo | Shares `packages/shared/`, same CI |
| Feature scope | Full web parity | All features the web app has |
| Payments | `@stripe/stripe-react-native` | Native payment sheet, no IAP fees (one-time analysis fees are exempt from Apple/Google IAP rules) |

---

## Architecture

### Directory structure

```
apps/mobile/
├── app/                    # Expo Router file-based routing
│   ├── (auth)/             # Unauthenticated screens: login, signup, OTP
│   ├── (tabs)/             # Main tab navigator (Dashboard, Upload, Profile)
│   │   ├── index.tsx       # Dashboard / bill list
│   │   ├── upload.tsx      # Camera + file picker + upload flow
│   │   └── profile.tsx     # Profile, members, insurance, account
│   ├── bill/[id]/          # Bill detail: verify → analysis → results → payment
│   ├── report/[id].tsx     # Report download
│   └── _layout.tsx         # Root layout, StripeProvider, AuthProvider
├── src/
│   ├── api/                # API clients (thin wrappers over fetch to ClaroBill API)
│   ├── auth/               # Supabase Auth session management (SecureStore)
│   ├── components/         # Shared UI components
│   ├── hooks/              # useSession, useBill, useAnalysisStatus, etc.
│   └── lib/                # Stripe setup, notification registration
├── app.json                # Expo config (bundle IDs, permissions, plugins)
├── eas.json                # EAS Build + Submit config
├── tsconfig.json           # Extends root tsconfig
└── package.json
```

### Shared types

`packages/shared/src/types/bill.ts` already contains `BillAnalysisResult`, `BillingError`, `LineItem`, etc. The mobile app imports these directly — no duplication.

### API layer

The mobile app calls the **same endpoints** the web app uses. No new backend work is required for MVP. All API calls go through `src/api/` clients that attach the Supabase JWT from `SecureStore`.

Key endpoints used by mobile:
- `POST /api/bills/upload` — multipart upload
- `GET /api/bills` — bill list
- `GET /api/bills/[id]` — bill detail + analysis status
- `POST /api/bills/[id]/payment` — Stripe PaymentIntent creation
- `PATCH /api/user/profile` — name update
- `GET /api/user/members`, `POST /api/user/members`
- `GET /api/user/insurance-plans`, `POST /api/user/insurance-plans`
- `POST /api/insurance-card/extract` — OCR of insurance card
- `POST /api/referrals/track`

---

## Key implementation details

### Auth — Supabase + Expo SecureStore

```
supabase-js (web) → AsyncStorage
supabase-js (mobile) → Expo SecureStore adapter
```

Use `@supabase/supabase-js` with a custom `SecureStore` adapter (`expo-secure-store`). Session persists across app restarts. No new backend changes.

Supported flows (matching web): email + password, magic link (deep link via Expo Linking), OTP.

### File upload

- `expo-image-picker` — camera capture and photo library
- `expo-document-picker` — PDF file selection
- Same 20MB limit + MIME validation enforced client-side before upload

### Analysis status polling

`useBill(id)` hook polls `GET /api/bills/[id]` every 5 seconds while `status === 'processing'`. When status transitions to `complete` or `error`, stop polling and navigate to results. Also register for push notifications via `expo-notifications` so users can background the app — engine triggers a Supabase edge function that sends a push when analysis completes.

### Payments — Stripe native SDK

```typescript
// app/_layout.tsx
<StripeProvider publishableKey={STRIPE_PUBLISHABLE_KEY}>
```

Flow: results screen → call `/api/bills/[id]/payment` to create PaymentIntent → `initPaymentSheet` + `presentPaymentSheet` → confirm on server. Identical PaymentIntent creation logic to web; only the presentation layer differs.

### Push notifications

1. Register device token on app launch → store in `user_profiles.push_token` (new column, migration required).
2. When engine job completes, engine triggers a `pg_net` HTTP call to Expo Push API.
3. Tapping the notification deep-links to `bill/[id]`.

Migrations required:
- `supabase/migrations/YYYYMMDD_add_push_token_to_profiles.sql` — add `push_token text` to `user_profiles`
- `supabase/migrations_down/YYYYMMDD_add_push_token_to_profiles.down.sql` — down sibling that drops the column

### App Store / Play Store config

```json
// app.json (key fields)
{
  "ios": {
    "bundleIdentifier": "com.clarobill.app",
    "infoPlist": {
      "NSCameraUsageDescription": "Used to photograph your medical bill for analysis.",
      "NSPhotoLibraryUsageDescription": "Used to select a photo of your medical bill."
    }
  },
  "android": {
    "package": "com.clarobill.app",
    "permissions": ["CAMERA", "READ_EXTERNAL_STORAGE"]
  }
}
```

EAS Build profiles: `development` (local), `preview` (internal TestFlight/Play internal track), `production` (App Store / Play Store).

---

## Build and CI

### EAS Build (not GitHub Actions)

Expo's managed build service (`eas build`) handles Xcode + Android SDK. Binary builds (`.ipa` / `.aab`) run on EAS servers via `eas build --platform all`. Submissions to App Store / Play Store via `eas submit`.

Add typecheck/lint/test to `ci.yml` after the existing web + engine jobs:

```yaml
mobile:
  name: Mobile (Expo / React Native)
  runs-on: ubuntu-latest
  defaults:
    run:
      working-directory: apps/mobile
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-node@v4
      with: { node-version: "20", cache: "npm" }
    - run: npm ci
    - run: npm run typecheck
    - run: npm run lint
    - run: npm run test
```

---

## Files to create / modify

| File | Action |
|---|---|
| `apps/mobile/` (whole dir) | Create — Expo project scaffolded with `npx create-expo-app` |
| `apps/mobile/app.json` | Create — bundle IDs, permissions, plugins |
| `apps/mobile/eas.json` | Create — development/preview/production build profiles |
| `apps/mobile/tsconfig.json` | Create — extends root, path aliases for `packages/shared` |
| `apps/mobile/package.json` | Create — dependencies listed below |
| `apps/mobile/app/_layout.tsx` | Create — StripeProvider, AuthProvider, Expo Router root |
| `apps/mobile/app/(auth)/` | Create — login, signup, OTP screens |
| `apps/mobile/app/(tabs)/` | Create — dashboard, upload, profile tabs |
| `apps/mobile/app/bill/[id]/` | Create — verify, analysis, results, payment screens |
| `apps/mobile/src/api/` | Create — typed fetch wrappers for each API endpoint |
| `apps/mobile/src/auth/session.ts` | Create — Supabase client with SecureStore adapter |
| `supabase/migrations/YYYYMMDD_add_push_token_to_profiles.sql` | Create — `push_token text` column |
| `supabase/migrations_down/YYYYMMDD_add_push_token_to_profiles.down.sql` | Create — drop column |
| `.github/workflows/ci.yml` | Modify — add `mobile` typecheck/lint/test job |
| `package.json` (root) | Modify — add `apps/mobile` to workspaces |

### Key dependencies (apps/mobile/package.json)

```
expo ~52.0
expo-router ~4.0
@supabase/supabase-js
expo-secure-store
expo-image-picker
expo-document-picker
expo-notifications
expo-linking
@stripe/stripe-react-native
react-native-safe-area-context
react-native-screens
zod
```

---

## Feature parity checklist

| Feature | Web | Mobile |
|---|---|---|
| Email/password + magic link + OTP auth | Yes | Yes |
| Bill upload (camera + file picker) | Web upload only | Camera + file + PDF |
| OCR confirmation (verify screen) | Yes | Yes |
| Analysis status + polling | Yes | Yes + push notification |
| Results paywall | Yes | Yes |
| Stripe payment | Yes (web SDK) | Yes (native SDK) |
| PDF + DOCX report download | Yes | Yes (share sheet) |
| Dashboard / savings tracker | Yes | Yes |
| Bill history | Yes | Yes |
| Profile (name, email) | Yes | Yes |
| Members management | Yes | Yes |
| Insurance plans | Yes | Yes |
| Insurance card scanner (OCR) | Yes | Yes |
| Referral tracking | Yes | Yes |
| Account deletion | Yes | Yes |

---

## Build order

1. Scaffold Expo project at `apps/mobile/`, wire into monorepo workspaces
2. Auth screens + Supabase SecureStore session
3. Bottom tab navigator (Dashboard stub, Upload stub, Profile stub)
4. Bill upload flow (picker → upload → verify screen)
5. Analysis status screen + polling hook
6. Results screen + Stripe payment sheet
7. Report download (share sheet)
8. Dashboard (bill list, savings summary)
9. Profile screens (name, email, members, insurance, deletion)
10. Insurance card scanner
11. Push notifications (migration + token registration + deep link)
12. EAS Build config + CI job
13. TestFlight (iOS) + Play internal track (Android) for beta

---

## Verification

```bash
# Type safety
cd apps/mobile && npx tsc --noEmit

# Lint
cd apps/mobile && npm run lint

# Tests
cd apps/mobile && npm run test

# Dev build (requires Expo Go or dev client)
cd apps/mobile && npx expo start

# EAS preview build (generates installable binary)
cd apps/mobile && eas build --profile preview --platform all

# Run on iOS simulator
cd apps/mobile && npx expo run:ios

# Run on Android emulator
cd apps/mobile && npx expo run:android
```

End-to-end verification: install preview build on a real device, sign up, photograph a test bill, complete analysis, pay with Stripe test card `4242 4242 4242 4242`, download report.
