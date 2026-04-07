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
    return event;
  },
});
