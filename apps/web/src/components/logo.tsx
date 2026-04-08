interface LogoProps {
  size?: 'sm' | 'md' | 'lg';
  variant?: 'light' | 'dark';
}

const fontSizes = {
  sm: '1.2rem',
  md: '1.35rem',
  lg: '1.65rem',
};

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
