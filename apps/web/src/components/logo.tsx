/**
 * ClaroBill logo components.
 *
 * LogoMark  — the rounded-square "C" chip alone (use in favicons, emails, tight spaces)
 * Logo      — wordmark text only (legacy, kept for backwards compat)
 * LogoWithMark — chip + wordmark side by side (use in nav headers)
 */

interface LogoProps {
  size?: 'sm' | 'md' | 'lg';
  variant?: 'light' | 'dark';
}

const markSizes = { sm: 28, md: 34, lg: 38 };
const markRadius = { sm: 8, md: 9, lg: 10 };
const markFontSizes = { sm: '1rem', md: '1.1rem', lg: '1.25rem' };
const wordmarkFontSizes = { sm: '1.1rem', md: '1.25rem', lg: '1.5rem' };
const fontSizes = { sm: '1.2rem', md: '1.35rem', lg: '1.65rem' };

// ─── LogoMark — the sage square chip with italic "C" ─────────────────────────
export function LogoMark({ size = 'md' }: Pick<LogoProps, 'size'>): JSX.Element {
  const px = markSizes[size ?? 'md'];
  const r = markRadius[size ?? 'md'];
  const fs = markFontSizes[size ?? 'md'];

  return (
    <span
      aria-hidden="true"
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: px,
        height: px,
        borderRadius: r,
        background: 'var(--sage, #2D4A2A)',
        fontFamily: 'var(--fd, Georgia, serif)',
        fontStyle: 'italic',
        fontSize: fs,
        fontWeight: 700,
        color: 'var(--accent, #C8F060)',
        flexShrink: 0,
        lineHeight: 1,
      }}
    >
      C
    </span>
  );
}

// ─── LogoWithMark — chip + wordmark, for nav headers ─────────────────────────
export function LogoWithMark({ size = 'md', variant = 'light' }: LogoProps): JSX.Element {
  const color = variant === 'dark' ? '#fff' : 'var(--txt, #1a2e18)';
  const fs = wordmarkFontSizes[size ?? 'md'];

  return (
    <>
      <LogoMark size={size} />
      <span
        style={{
          fontFamily: 'var(--fd, Georgia, serif)',
          fontSize: fs,
          fontWeight: 700,
          letterSpacing: '-.02em',
          color,
        }}
      >
        Claro<em style={{ fontStyle: 'italic', fontWeight: 700 }}>Bill</em>
      </span>
    </>
  );
}

// ─── Logo — wordmark only (legacy) ───────────────────────────────────────────
export function Logo({ size = 'md', variant = 'light' }: LogoProps): JSX.Element {
  const color = variant === 'dark' ? '#fff' : 'var(--txt, #1a2e18)';

  return (
    <span
      style={{
        fontFamily: 'var(--fd, Georgia, serif)',
        fontSize: fontSizes[size],
        fontWeight: 700,
        letterSpacing: '-.02em',
        color,
        textDecoration: 'none',
      }}
    >
      Claro<em style={{ fontStyle: 'italic', fontWeight: 700 }}>Bill</em>.
    </span>
  );
}
