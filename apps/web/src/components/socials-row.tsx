'use client';

// Marketing-and-dashboard footer row for social presence.
// Single source of truth for handles + URLs lives in @/lib/beta SOCIAL_LINKS,
// so updating a handle (or adding LinkedIn / TikTok) is a one-line change.
//
// Icons inline as SVG — no third-party icon library, no extra network request,
// no licensing exposure on third-party logos. Per brand guideline: no emojis.

import { SOCIAL_LINKS } from '@/lib/beta';
import s from './socials-row.module.css';

interface SocialsRowProps {
  // Optional alignment override. Default centred for marketing footer; the
  // dashboard footer uses left-align to match its existing layout.
  align?: 'center' | 'left';
}

export function SocialsRow({ align = 'center' }: SocialsRowProps): JSX.Element {
  const wrapCls = align === 'left' ? `${s.row} ${s.rowLeft}` : s.row;
  return (
    <div className={wrapCls} aria-label="Follow ClaroBill">
      <a
        href={SOCIAL_LINKS.instagram.url}
        target="_blank"
        rel="noopener noreferrer me"
        className={s.iconLink}
        aria-label={`ClaroBill on Instagram (${SOCIAL_LINKS.instagram.handle})`}
      >
        <svg
          width="20" height="20" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
          aria-hidden="true"
        >
          <rect x="2" y="2" width="20" height="20" rx="5" ry="5" />
          <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z" />
          <line x1="17.5" y1="6.5" x2="17.51" y2="6.5" />
        </svg>
      </a>
      <a
        href={SOCIAL_LINKS.x.url}
        target="_blank"
        rel="noopener noreferrer me"
        className={s.iconLink}
        aria-label={`ClaroBill on X (${SOCIAL_LINKS.x.handle})`}
      >
        {/* X (formerly Twitter) glyph — official mark, redrawn here as
            simple stroke geometry so it renders cleanly at small sizes
            without bringing in an icon library. */}
        <svg
          width="20" height="20" viewBox="0 0 24 24" fill="currentColor"
          aria-hidden="true"
        >
          <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
        </svg>
      </a>
      <a
        href={SOCIAL_LINKS.linkedin.url}
        target="_blank"
        rel="noopener noreferrer me"
        className={s.iconLink}
        aria-label={`ClaroBill on LinkedIn (${SOCIAL_LINKS.linkedin.handle})`}
      >
        <svg
          width="20" height="20" viewBox="0 0 24 24" fill="currentColor"
          aria-hidden="true"
        >
          <path d="M20.45 20.45h-3.55v-5.57c0-1.33-.02-3.04-1.86-3.04-1.86 0-2.14 1.45-2.14 2.95v5.66H9.35V9h3.41v1.56h.05c.47-.9 1.63-1.86 3.36-1.86 3.6 0 4.26 2.37 4.26 5.46v6.29zM5.34 7.43a2.06 2.06 0 1 1 0-4.12 2.06 2.06 0 0 1 0 4.12zM7.12 20.45H3.56V9h3.56v11.45zM22.22 0H1.77C.79 0 0 .77 0 1.72v20.56C0 23.23.79 24 1.77 24h20.45c.98 0 1.78-.77 1.78-1.72V1.72C24 .77 23.2 0 22.22 0z" />
        </svg>
      </a>
      <a
        href={SOCIAL_LINKS.youtube.url}
        target="_blank"
        rel="noopener noreferrer me"
        className={s.iconLink}
        aria-label={`ClaroBill on YouTube (${SOCIAL_LINKS.youtube.handle})`}
      >
        <svg
          width="20" height="20" viewBox="0 0 24 24" fill="currentColor"
          aria-hidden="true"
        >
          <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" />
        </svg>
      </a>
      <a
        href={SOCIAL_LINKS.tiktok.url}
        target="_blank"
        rel="noopener noreferrer me"
        className={s.iconLink}
        aria-label={`ClaroBill on TikTok (${SOCIAL_LINKS.tiktok.handle})`}
      >
        <svg
          width="20" height="20" viewBox="0 0 24 24" fill="currentColor"
          aria-hidden="true"
        >
          <path d="M19.59 6.69a4.83 4.83 0 0 1-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 0 1-2.88 2.5 2.89 2.89 0 0 1-2.89-2.89 2.89 2.89 0 0 1 2.89-2.89c.28 0 .54.04.79.1V9.01a6.33 6.33 0 0 0-.79-.05 6.34 6.34 0 0 0-6.34 6.34 6.34 6.34 0 0 0 6.34 6.34 6.34 6.34 0 0 0 6.33-6.34V8.69a8.18 8.18 0 0 0 4.78 1.52V6.75a4.85 4.85 0 0 1-1.01-.06z" />
        </svg>
      </a>
    </div>
  );
}
