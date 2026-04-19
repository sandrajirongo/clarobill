import { withSentryConfig } from '@sentry/nextjs';
import createNextIntlPlugin from 'next-intl/plugin';

const withNextIntl = createNextIntlPlugin('./i18n/request.ts');

/** @type {import('next').NextConfig} */
const nextConfig = {};

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
