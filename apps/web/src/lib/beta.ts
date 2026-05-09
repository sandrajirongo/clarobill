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
    // Short enough that both text and Share button fit a 360px viewport
    // without truncation. Longer "until launch" framing lives on /pricing.
    headline: 'ClaroBill is free during public beta',
    cta: 'Share',
  },
  // Used by the Share button — Web Share API on mobile, clipboard or
  // X/Twitter intent URL on desktop. Tone is informational, trust-forward,
  // not promotional.
  //
  // `tweetText` is the same content with our X handle (@clarobillai) prefixed
  // so when a user shares to X via the OS share sheet OR the desktop fallback
  // intent URL, the post tags us. We keep `text` un-prefixed for non-X
  // surfaces (iMessage, email, etc.) where a leading @ handle reads weirdly.
  share: {
    title: 'ClaroBill: medical bill review',
    text: 'ClaroBill reviews medical bills for errors and overcharges, and generates dispute letters. Currently free during their public beta.',
    tweetText: 'Just used @clarobillai to review my medical bill for errors and overcharges. Free during their public beta.',
  },
  pricingCallout: {
    eyebrow: 'Beta access',
    title: 'Every tier is currently unlocked at no cost',
    body:
      'We are in public beta and collecting feedback before launch. ' +
      'Pricing below shows what each tier will cost when we exit beta. For now, every report and dispute letter is free.',
  },
  paywall: {
    badge: 'Free during beta',
    note: 'Public beta. Every report is currently unlocked at no cost.',
    button: 'Get my full report',
  },
  signInBenefit: 'Currently free during public beta. No credit card required.',
} as const;

// ─── Social media presence ─────────────────────────────────────────────────
// Single source of truth so headers, footers, share dialogs, and email
// templates all link to the right handles. Update in one place.
export const SOCIAL_LINKS = {
  instagram: {
    handle: '@clarobill',
    url: 'https://www.instagram.com/clarobill/',
  },
  x: {
    handle: '@clarobillai',
    url: 'https://x.com/clarobillai',
  },
  linkedin: {
    handle: 'ClaroBill',
    url: 'https://www.linkedin.com/company/clarobill/',
  },
  youtube: {\n    handle: '@clarobillai',\n    url: 'https://www.youtube.com/@clarobillai',\n  },\n  email: {
    handle: 'support@clarobill.com',
    url: 'mailto:support@clarobill.com',
  },
} as const;

// X/Twitter "share intent" URL — opens a pre-populated compose window in
// the browser. Used as the desktop fallback when the OS Web Share API
// isn't available. Includes our @handle so the post is tagged.
export function buildTweetIntentUrl(text: string, url: string): string {
  const params = new URLSearchParams({ text, url });
  return `https://twitter.com/intent/tweet?${params.toString()}`;
}
