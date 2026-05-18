import posthog from 'posthog-js';

// Safari Private Browsing and some in-app WebViews throw a ReferenceError on
// localStorage access before you can even check typeof. A write probe inside
// try/catch is the only reliable way to detect this.
function localStorageAvailable(): boolean {
  try {
    localStorage.setItem('__ph_probe__', '1');
    localStorage.removeItem('__ph_probe__');
    return true;
  } catch {
    return false;
  }
}

export function initPostHog(): void {
  if (typeof window === 'undefined') return;
  if (!process.env.NEXT_PUBLIC_POSTHOG_PROJECT_TOKEN) return;
  // Some WebView environments (Electron, Capacitor, in-app browsers) don't
  // support the Blob constructor. PostHog uses Blob internally — skip init
  // rather than crash the app in those environments.
  if (typeof Blob === 'undefined' || typeof Blob !== 'function') return;

  posthog.init(process.env.NEXT_PUBLIC_POSTHOG_PROJECT_TOKEN, {
    api_host: process.env.NEXT_PUBLIC_POSTHOG_HOST ?? 'https://us.i.posthog.com',
    // Don't capture events during development unless explicitly enabled
    loaded(ph) {
      if (process.env.NODE_ENV === 'development' && !process.env.NEXT_PUBLIC_POSTHOG_DEBUG) ph.opt_out_capturing();
    },
    // Respect user privacy — don't capture personal data automatically
    autocapture: false,
    capture_pageview: false,  // We'll capture page views manually via the provider
    // Fall back to in-memory persistence in Safari Private Browsing and
    // restricted WebViews where localStorage throws a ReferenceError.
    persistence: localStorageAvailable() ? 'localStorage' : 'memory',
  });
}

export { posthog };
