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
    </div>
  );
}
