# UI refresh direction — single-surface, wordmark-anchored

**Status:** future improvement, no committed timeline
**Reference implementation:** `apps/web/src/app/demo/page.tsx` (live at
`clarobill.com/demo`)
**Decided:** 2026-05-03

The `/demo` page was built as an unlisted pitch-deck surface and ended
up reading cleaner than the rest of the site. Sandra reviewed it, liked
the simplicity, and asked to lock it as the visual direction for the
next UI refresh. This doc captures the principles so future-us can
apply them across landing, dashboard, and any new product surface
without re-deriving them.

---

## Why /demo reads better than the current landing

The rest of the site stitches multiple surface treatments together:
hero gradient → sage carousel strip → cream stats panel → sage CTA
strip → footer. Each is fine alone; layered they feel busy. The /demo
page is one cream surface, centered, with a single focal element and
a clean CTA hierarchy. That single-surface approach is what reads as
"premium."

## Five principles to apply

### 1. One surface treatment per page
Cream OR sage. Not both stitched together. The eye should rest on a
single ground colour and only the focal element breaks it.

### 2. Wordmark as the visual anchor
Italic *Bill* + lime period dot, large, on the page itself. Not buried
in nav or footer. The wordmark is the brand mark; treat it like one.

### 3. One primary CTA + one secondary text link
Maximum two CTAs visible at any one time. Sage pill button (primary) +
underlined text link (secondary). Never three button styles competing
on the same page.

### 4. Centre-align hero content
Centre alignment for the focal block (wordmark + headline + media +
CTA row). Left-align only flowing text body content.

### 5. Drop the partner carousel and testimonial scroller from the hero
Let the value prop breathe before piling on social proof. The current
landing page leads with logos and stats; the refreshed version should
lead with the headline and the product, then layer in proof below.

## What this looks like as a refactor

When the time comes to refactor the existing landing page:

- **Hero:** large centred wordmark, single headline, single sub, single
  primary CTA. No partner carousel above the fold. No "works with"
  pill row.
- **How it works:** keep, but restyle as single-cream-surface (drop the
  sage CTA strip below it). Sage stays only as accent on numbers and
  the CTA pill.
- **What you get:** keep the two cards, drop the third "Results in
  minutes" card — it's redundant with copy elsewhere.
- **Stats + reviews:** strip the testimonial carousel, replace with a
  static three-card layout. Less motion, more confidence.
- **FAQ:** keep as-is, it's already clean.
- **Footer CTA:** retain but match the sage pill + text-link
  hierarchy. Drop the "HIPAA-aligned · Encrypted · No credit card
  required" pill row.

## Dashboard application

The dashboard already uses cream-as-ground. Two refactors there would
align it with the /demo aesthetic:

1. **Make the wordmark visible on the dashboard top bar.** Right now
   only "Dashboard" text is there. Replace with the italic-Bill
   wordmark.
2. **Drop the lime accents on dashboard CTAs.** Lime should be
   reserved for the wordmark dot + accent moments. Dashboard CTAs
   should be sage pill, not lime fill.

## What NOT to do without explicit go-ahead

- Don't refactor the existing landing page proactively. This is a
  forward-looking direction, not a mandate to retrofit immediately.
  Sandra will commission the refresh when ready.
- Don't introduce a third button style anywhere on the site.
- Don't add a partner carousel, testimonial scroller, or trust-pill
  row to any new hero.
- Don't reuse the /demo cream-on-cream styling for surfaces that need
  to be visually loud (e.g. the paid-tier paywall, error states). Loud
  states still use sage-on-cream contrast.

## Reference files

- `apps/web/src/app/demo/page.tsx` — JSX shape
- `apps/web/src/app/demo/demo.module.css` — colour tokens, type scale,
  CTA treatment
- `apps/web/src/app/page.tsx` + `page.module.css` — current landing,
  for diff reference when the refresh ships
