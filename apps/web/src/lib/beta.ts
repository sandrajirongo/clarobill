// Beta-mode flag — single source of truth for "is the product currently free?"
//
// Reads NEXT_PUBLIC_BETA_MODE so both server (API routes, RSC) and client
// (paywall CTA, marketing nav) agree. Defaults to TRUE during the public beta
// so a missing env var doesn't accidentally start charging users — flip to
// 'false' in Vercel and remove this default at launch.
//
// Anywhere we want to gate a UX or pricing change on beta status, import
// isBetaMode() — never read the env var directly. That keeps the launch flip
// to a single line in this file.

export function isBetaMode(): boolean {
  return process.env.NEXT_PUBLIC_BETA_MODE !== 'false';
}

export const BETA_COPY = {
  banner: {
    headline: 'ClaroBill is in public beta — every report is free until launch',
    cta: 'Help us test',
  },
  pricingCallout: {
    eyebrow: 'Beta access',
    title: 'Every tier is currently unlocked at no cost',
    body:
      'We are in public beta and collecting feedback before launch. ' +
      'Pricing below shows what each tier will cost when we exit beta — for now, every report and dispute letter is free.',
  },
  paywall: {
    badge: 'Free during beta',
    note: 'Public beta — every report is currently unlocked at no cost.',
    button: 'Get my full report',
  },
  signInBenefit: 'Currently free during public beta — no credit card required',
} as const;
