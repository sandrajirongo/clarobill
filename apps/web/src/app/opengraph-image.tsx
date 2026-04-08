import { ImageResponse } from 'next/og';

export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

export default function OgImage(): ImageResponse {
  return new ImageResponse(
    (
      <div
        style={{
          width: 1200,
          height: 630,
          background: '#2D4A2A',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'flex-start',
          justifyContent: 'flex-end',
          padding: '72px 80px',
          position: 'relative',
        }}
      >
        {/* Subtle radial highlight */}
        <div
          style={{
            position: 'absolute',
            inset: 0,
            background: 'radial-gradient(ellipse 70% 55% at 80% 20%, rgba(200,240,96,0.10), transparent 65%)',
          }}
        />

        {/* Wordmark */}
        <div
          style={{
            fontFamily: 'serif',
            fontSize: 52,
            fontWeight: 700,
            color: '#fff',
            letterSpacing: '-1px',
            marginBottom: 32,
            display: 'flex',
          }}
        >
          Claro
          <span style={{ fontStyle: 'italic' }}>Bill</span>
          <span style={{ color: '#C8F060' }}>.</span>
        </div>

        {/* Headline */}
        <div
          style={{
            fontFamily: 'serif',
            fontSize: 64,
            fontWeight: 700,
            color: '#fff',
            lineHeight: 1.1,
            letterSpacing: '-1.5px',
            maxWidth: 820,
            marginBottom: 28,
          }}
        >
          Find Errors in Your Medical Bill
        </div>

        {/* Sub-line */}
        <div
          style={{
            fontFamily: 'sans-serif',
            fontSize: 26,
            color: 'rgba(255,255,255,0.60)',
            maxWidth: 680,
            lineHeight: 1.5,
          }}
        >
          AI-powered analysis finds overcharges, duplicates, and billing mistakes in minutes.
        </div>

        {/* Accent pill */}
        <div
          style={{
            marginTop: 40,
            background: '#C8F060',
            color: '#1E3019',
            fontFamily: 'sans-serif',
            fontWeight: 700,
            fontSize: 22,
            padding: '12px 28px',
            borderRadius: 9999,
            display: 'flex',
          }}
        >
          clarobill.com
        </div>
      </div>
    ),
    { ...size }
  );
}
