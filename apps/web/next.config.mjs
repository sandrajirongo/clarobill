import { withSentryConfig } from '@sentry/nextjs';
import createNextIntlPlugin from 'next-intl/plugin';

const withNextIntl = createNextIntlPlugin('./i18n/request.ts');

/** @type {import('next').NextConfig} */
const nextConfig = {
  // posthog-js minifies ternary+float as `?.4` (e.g. `isNaN(d)?.4:d`) which
  // some parsers misread as optional chaining. Recompiling through SWC emits
  // the float as `0.4`, making the ternary unambiguous for all parsers.
  transpilePackages: ['posthog-js'],
  async redirects() {
    return [
      {
        source: '/methodology',
        destination: '/about',
        permanent: true,
      },
      {
        source: '/free-medical-bill-check',
        destination: '/upload',
        permanent: true,
      },
    ];
  },
};

export default withSentryConfig(withNextIntl(nextConfig), {
  // Suppresses Sentry CLI output during builds
  silent: true,
  // Upload source maps to Sentry for readable stack traces in production
  // Requires SENTRY_AUTH_TOKEN env var — set in Vercel deployment settings
  widenClientFileUpload: true,
  // Hides source maps from the client bundle
  hideSourceMaps: true,
  // Disable the Sentry telemetry
  telemetry: false,
});
