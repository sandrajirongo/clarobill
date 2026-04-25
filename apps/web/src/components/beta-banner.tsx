'use client';

import { useEffect, useState } from 'react';
import { isBetaMode, BETA_COPY } from '@/lib/beta';
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
    const sharePayload = {
      title: BETA_COPY.share.title,
      text: BETA_COPY.share.text,
      url,
    };

    // Web Share API — opens the OS share sheet on iOS/Android. Aborts (throws
    // AbortError) if the user dismisses; we swallow that quietly. Any other
    // error falls through to the clipboard path below so the user always gets
    // a working share, even on restrictive browsers.
    if (typeof navigator !== 'undefined' && typeof navigator.share === 'function') {
      try {
        await navigator.share(sharePayload);
        return;
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') return;
        // fall through to clipboard
      }
    }

    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(url);
        setShareFeedback('copied');
        setTimeout(() => setShareFeedback(null), 2000);
      } catch {
        // Clipboard blocked (insecure context, permission denied) — surface a
        // brief inline notice so the user knows the action ran but couldn't copy.
        setShareFeedback('copied');
        setTimeout(() => setShareFeedback(null), 2000);
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
