import posthog from 'posthog-js';

export function initPostHog(): void {
  if (typeof window === 'undefined') return;
  if (!process.env.NEXT_PUBLIC_POSTHOG_PROJECT_TOKEN) return;

  posthog.init(process.env.NEXT_PUBLIC_POSTHOG_PROJECT_TOKEN, {
    api_host: process.env.NEXT_PUBLIC_POSTHOG_HOST ?? 'https://us.i.posthog.com',
    // Don't capture events during development unless explicitly enabled
    loaded(ph) {
      if (process.env.NODE_ENV === 'development' && !process.env.NEXT_PUBLIC_POSTHOG_DEBUG) ph.opt_out_capturing();
    },
    // Respect user privacy — don't capture personal data automatically
    autocapture: false,
    capture_pageview: false,  // We'll capture page views manually via the provider
    persistence: 'localStorage',
  });
}

export { posthog };
