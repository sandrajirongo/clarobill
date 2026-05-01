'use client';

import { useEffect, useState } from 'react';
import { isBetaMode, BETA_COPY, buildTweetIntentUrl } from '@/lib/beta';
import s from './beta-banner.module.css';

const DISMISS_KEY = 'cb_beta_banner_dismissed';

interface BetaBannerProps {
  // Reserved for future surface-specific overrides — currently unused since the
  // Share CTA is universally relevant. Kept in the API so callers don't break.
  showCta?: boolean;
}

export function BetaBanner({ showCta = true }: BetaBannerProps): JSX.Element | null {
  // SSR-safe: render hidden first, then reveal post-mount based on localStorage.
  // Rendering visible-first would flash the banner for a frame on every nav
  // for users who already dismissed it.
  const [hydrated, setHydrated] = useState(false);
  const [dismissed, setDismissed] = useState(true);
  const [shareFeedback, setShareFeedback] = useState<'copied' | null>(null);

  useEffect(() => {
    setDismissed(localStorage.getItem(DISMISS_KEY) === '1');
    setHydrated(true);
  }, []);

  if (!isBetaMode() || !hydrated || dismissed) return null;

  function handleDismiss(): void {
    localStorage.setItem(DISMISS_KEY, '1');
    setDismissed(true);
  }

  async function handleShare(): Promise<void> {
    const url = window.location.origin;

    // Web Share API path — opens the OS share sheet on iOS/Android. We use
    // the @clarobillai-prefixed text so when the user picks X/Twitter from
    // the OS sheet, the post tags us. Other targets (iMessage, email) get
    // the same string; the leading @ handle is harmless context there.
    const sharePayload = {
      title: BETA_COPY.share.title,
      text: BETA_COPY.share.tweetText,
      url,
    };

    if (typeof navigator !== 'undefined' && typeof navigator.share === 'function') {
      try {
        await navigator.share(sharePayload);
        return;
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') return;
        // fall through to desktop fallback below
      }
    }

    // Desktop fallback — open X's tweet-intent compose window in a new tab
    // with the @clarobillai-tagged text and the URL pre-populated. This is
    // the same UX every other consumer product uses (Stripe Atlas, Linear,
    // Vercel) when navigator.share isn't available. The user lands on a
    // pre-filled tweet draft and just hits Post.
    const intentUrl = buildTweetIntentUrl(BETA_COPY.share.tweetText, url);
    if (typeof window !== 'undefined') {
      window.open(intentUrl, '_blank', 'noopener,noreferrer');
      // Also drop the URL onto the clipboard as a belt-and-suspenders so
      // users on browsers that block the popup still have the URL ready.
      if (navigator.clipboard?.writeText) {
        try {
          await navigator.clipboard.writeText(url);
          setShareFeedback('copied');
          setTimeout(() => setShareFeedback(null), 2000);
        } catch {
          /* clipboard blocked — popup is the primary path, this is just backup */
        }
      }
    }
  }

  return (
    <div className={s.bar} role="region" aria-label="Beta announcement">
      <div className={s.inner}>
        <span className={s.label}>Beta</span>
        <span className={s.text}>{BETA_COPY.banner.headline}</span>
        {showCta && (
          <button
            type="button"
            onClick={handleShare}
            className={s.cta}
            aria-label="Share ClaroBill"
          >
            <svg
              className={s.ctaIcon}
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <circle cx="18" cy="5" r="3" />
              <circle cx="6" cy="12" r="3" />
              <circle cx="18" cy="19" r="3" />
              <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
              <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
            </svg>
            <span className={s.ctaText}>
              {shareFeedback === 'copied' ? 'Link copied' : BETA_COPY.banner.cta}
            </span>
          </button>
        )}
        <button
          type="button"
          onClick={handleDismiss}
          className={s.close}
          aria-label="Dismiss beta announcement"
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            <path d="M3 3l8 8M11 3l-8 8" />
          </svg>
        </button>
      </div>
    </div>
  );
}
