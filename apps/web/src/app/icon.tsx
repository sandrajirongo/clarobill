import { ImageResponse } from 'next/og';

export const size = { width: 32, height: 32 };
export const contentType = 'image/png';

export default function Icon(): ImageResponse {
  return new ImageResponse(
    (
      <div
        style={{
          width: 32,
          height: 32,
          borderRadius: 8,
          background: '#2D4A2A',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <span
          style={{
            color: '#C8F060',
            fontSize: 20,
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
