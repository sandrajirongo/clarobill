import { defineRouting } from 'next-intl/routing';

export const LOCALES = ['en', 'es', 'zh', 'tl', 'vi'] as const;
export type Locale = (typeof LOCALES)[number];

export const routing = defineRouting({
  locales: LOCALES,
  defaultLocale: 'en',
  // No locale prefix in URLs — locale is stored in the cb_locale cookie.
  // This keeps all existing routes (/dashboard, /onboarding, etc.) unchanged.
  localePrefix: 'never',
  localeDetection: false,
});
