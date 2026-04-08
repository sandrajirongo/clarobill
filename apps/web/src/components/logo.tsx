interface LogoProps {
  size?: 'sm' | 'md' | 'lg';
  variant?: 'light' | 'dark';
}

const sizes = {
  sm: { boxPx: 28, radius: 8,  fontSize: 15, wordmark: 'text-xl'  },
  md: { boxPx: 36, radius: 10, fontSize: 19, wordmark: 'text-2xl' },
  lg: { boxPx: 48, radius: 13, fontSize: 25, wordmark: 'text-3xl' },
};

export function Logo({ size = 'md', variant = 'light' }: LogoProps): JSX.Element {
  const s = sizes[size];
  const wordmarkColor = variant === 'dark' ? '#fff' : 'var(--txt, #1a2e18)';

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
      <div
        style={{
          width: s.boxPx,
          height: s.boxPx,
          borderRadius: s.radius,
          background: '#2D4A2A',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}
      >
        <span
          style={{
            color: '#C8F060',
            fontSize: s.fontSize,
            fontWeight: 700,
            fontStyle: 'italic',
            fontFamily: 'Georgia, serif',
            lineHeight: 1,
          }}
        >
          C
        </span>
      </div>
      <span
        className={`font-bold ${s.wordmark}`}
        style={{ color: wordmarkColor, letterSpacing: '-.02em' }}
      >
        Claro<em style={{ fontStyle: 'italic' }}>Bill</em>
      </span>
    </div>
  );
}
