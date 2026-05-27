import { ImageResponse } from 'next/og';

// 1200x630 is the canonical OG image size — supported across iMessage, WhatsApp,
// Slack, Twitter, Facebook, LinkedIn. Routes co-located with a layout get
// auto-wired into the page metadata (see app/layout.tsx for metadataBase + alt).
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';
// Edge runtime is required for next/og's font loading via fetch().
export const runtime = 'edge';

// Brand tokens — duplicated here because next/og can't import CSS variables.
// Keep these in sync with apps/web/src/app/globals.css.
const SAGE = '#2D4A2A';
const SAGE_DARK = '#1E3019';
const LIME = '#C8F060';
const WHITE = '#FFFFFF';

// Fetch a single weight/style from Google Fonts. We pull the @font-face CSS
// (Mozilla UA forces woff2 over ttf — woff2 is ~3x smaller and supported by
// Satori, the renderer next/og uses), parse out the binary URL, and fetch it.
// Throws if the URL can't be parsed so a font fetch failure surfaces in build
// logs rather than silently falling back to a system font.
async function loadGoogleFont(
  family: string,
  weight: number,
  style: 'normal' | 'italic' = 'normal',
): Promise<ArrayBuffer> {
  const familySlug = family.replace(/ /g, '+');
  const ital = style === 'italic' ? '1,' : '0,';
  const cssUrl =
    `https://fonts.googleapis.com/css2?family=${familySlug}:ital,wght@${ital}${weight}&display=swap`;
  const css = await fetch(cssUrl, {
    headers: { 'User-Agent': 'Mozilla/5.0' },
  }).then((r) => r.text());

  const fontUrlMatch = css.match(/src:\s*url\((https:\/\/[^)]+)\)/);
  if (!fontUrlMatch || !fontUrlMatch[1]) {
    throw new Error(`Failed to parse Google Font URL for ${family} ${weight} ${style}`);
  }
  return fetch(fontUrlMatch[1]).then((r) => r.arrayBuffer());
}

export default async function OgImage(): Promise<ImageResponse> {
  // Load all four faces in parallel — total fetch is ~250KB and happens once
  // at build time, then the rendered PNG is cached at the edge for a year.
  const [frauncesRegular, frauncesItalic, syneMedium, syneBold] = await Promise.all([
    loadGoogleFont('Fraunces', 700, 'normal'),
    loadGoogleFont('Fraunces', 700, 'italic'),
    loadGoogleFont('Syne', 500, 'normal'),
    loadGoogleFont('Syne', 700, 'normal'),
  ]);

  return new ImageResponse(
    (
      <div
        style={{
          width: 1200,
          height: 630,
          background: SAGE,
          position: 'relative',
          display: 'flex',
          flexDirection: 'column',
          padding: '80px',
          fontFamily: 'Syne',
        }}
      >
        {/* Subtle lime radial highlight in upper-right — matches the landing
            page's hero treatment without replicating the full gradient. */}
        <div
          style={{
            position: 'absolute',
            inset: 0,
            background: 'radial-gradient(ellipse 70% 55% at 80% 20%, rgba(200,240,96,0.12), transparent 65%)',
          }}
        />

        {/* Logo row: LogoMark chip + wordmark — same construction as
            apps/web/src/components/logo.tsx (LogoMark + Claro/Bill). */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 18,
            marginBottom: 'auto',
          }}
        >
          {/* Sage rounded square chip with italic "C" in lime — matches LogoMark */}
          <div
            style={{
              width: 64,
              height: 64,
              borderRadius: 16,
              background: SAGE_DARK,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              border: `1.5px solid rgba(200,240,96,0.25)`,
            }}
          >
            <span
              style={{
                fontFamily: 'Fraunces',
                fontStyle: 'italic',
                fontWeight: 700,
                fontSize: 38,
                color: LIME,
                lineHeight: 1,
              }}
            >
              C
            </span>
          </div>
          {/* Wordmark: Claro (roman) + Bill (italic) + lime period */}
          <div
            style={{
              fontFamily: 'Fraunces',
              fontWeight: 700,
              fontSize: 46,
              color: WHITE,
              letterSpacing: '-1px',
              display: 'flex',
              alignItems: 'baseline',
            }}
          >
            Claro
            <span style={{ fontStyle: 'italic' }}>Bill</span>
            <span style={{ color: LIME }}>.</span>
          </div>
        </div>

        {/* Headline — Fraunces 700, sentence case to match the landing voice */}
        <div
          style={{
            fontFamily: 'Fraunces',
            fontWeight: 700,
            fontSize: 86,
            lineHeight: 1.05,
            letterSpacing: '-2px',
            color: WHITE,
            maxWidth: 900,
            marginBottom: 28,
          }}
        >
          Find errors in your medical bill
        </div>

        {/* Subline — Syne 500, soft white. The opacity of 0.72 matches the
            secondary-text contrast we use on dark sage backgrounds. */}
        <div
          style={{
            fontFamily: 'Syne',
            fontWeight: 500,
            fontSize: 26,
            lineHeight: 1.5,
            color: 'rgba(255,255,255,0.72)',
            maxWidth: 760,
            marginBottom: 36,
          }}
        >
          A line-by-line audit identifies overcharges, duplicate charges, and coding mistakes in minutes.
        </div>

        {/* CTA pill — lime background, sage-dark text, Syne 700. Wrapper row
            keeps the pill at content width; Satori stretches direct flex
            children by default. Matches the landing page's primary lime CTA
            but at OG scale. */}
        <div style={{ display: 'flex' }}>
          <div
            style={{
              background: LIME,
              color: SAGE_DARK,
              fontFamily: 'Syne',
              fontWeight: 700,
              fontSize: 22,
              letterSpacing: '0.01em',
              padding: '14px 32px',
              borderRadius: 999,
              display: 'flex',
              alignItems: 'center',
            }}
          >
            clarobill.com
          </div>
        </div>
      </div>
    ),
    {
      ...size,
      fonts: [
        { name: 'Fraunces', data: frauncesRegular, weight: 700, style: 'normal' },
        { name: 'Fraunces', data: frauncesItalic, weight: 700, style: 'italic' },
        { name: 'Syne', data: syneMedium, weight: 500, style: 'normal' },
        { name: 'Syne', data: syneBold, weight: 700, style: 'normal' },
      ],
    },
  );
}
