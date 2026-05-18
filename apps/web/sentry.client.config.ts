import * as Sentry from '@sentry/nextjs';

Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  environment: process.env.NODE_ENV,
  // Capture 100% of transactions in dev, 10% in production
  tracesSampleRate: process.env.NODE_ENV === 'production' ? 0.1 : 1.0,
  // Never send PHI — bill contents, patient names, or file contents must not appear in errors
  beforeSend(event) {
    // Strip request bodies from error events — may contain file data
    if (event.request?.data) {
      event.request.data = '[redacted]';
    }

    // WORKAROUND: @supabase/supabase-js uses the Web Locks API to synchronize
    // session state across browser tabs. When a second tab steals the lock, the
    // displaced tab's pending lock request throws this AbortError as an unhandled
    // rejection. Supabase handles the contention correctly internally — the session
    // remains valid — but the error escapes into window.onunhandledrejection.
    // We cannot fix this inside the library; dropping it here is the correct response.
    // Upstream issue: https://github.com/supabase/gotrue-js/issues/1004
    const isSupabaseLockSteal = event.exception?.values?.some(
      (e) => e.type === 'AbortError' && e.value?.includes('steal'),
    );
    if (isSupabaseLockSteal) return null;

    return event;
  },
});
