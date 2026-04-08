import { ImageResponse } from 'next/og';

export const size = { width: 180, height: 180 };
export const contentType = 'image/png';

export default function AppleIcon(): ImageResponse {
  return new ImageResponse(
    (
      <div
        style={{
          width: 180,
          height: 180,
          borderRadius: 40,
          background: '#2D4A2A',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <span
          style={{
            color: '#C8F060',
            fontSize: 110,
            fontWeight: 700,
            fontStyle: 'italic',
            lineHeight: 1,
            fontFamily: 'serif',
          }}
        >
          C
        </span>
      </div>
    ),
    { ...size }
  );
}
