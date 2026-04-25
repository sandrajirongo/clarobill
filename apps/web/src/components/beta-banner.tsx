'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { isBetaMode, BETA_COPY } from '@/lib/beta';
import s from './beta-banner.module.css';

const DISMISS_KEY = 'cb_beta_banner_dismissed';

interface BetaBannerProps {
  // When true, shows the "Help us test" CTA pointing at /pricing.
  // Hide on /pricing itself (the page already has its own beta callout).
  showCta?: boolean;
}

export function BetaBanner({ showCta = true }: BetaBannerProps): JSX.Element | null {
  // SSR-safe: render hidden first, then reveal post-mount based on localStorage.
  // Rendering visible-first would flash the banner for a frame on every nav
  // for users who already dismissed it.
  const [hydrated, setHydrated] = useState(false);
  const [dismissed, setDismissed] = useState(true);

  useEffect(() => {
    setDismissed(localStorage.getItem(DISMISS_KEY) === '1');
    setHydrated(true);
  }, []);

  if (!isBetaMode() || !hydrated || dismissed) return null;

  function handleDismiss(): void {
    localStorage.setItem(DISMISS_KEY, '1');
    setDismissed(true);
  }

  return (
    <div className={s.bar} role="region" aria-label="Beta announcement">
      <div className={s.inner}>
        <span className={s.label}>Beta</span>
        <span className={s.text}>{BETA_COPY.banner.headline}</span>
        {showCta && (
          <Link href="/pricing" className={s.cta}>
            {BETA_COPY.banner.cta}
          </Link>
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
