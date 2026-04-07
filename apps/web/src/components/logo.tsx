interface LogoProps {
  size?: 'sm' | 'md' | 'lg';
  variant?: 'light' | 'dark';
}

const sizes = {
  sm: { box: 'w-7 h-7 rounded-lg', letter: 'text-sm', wordmark: 'text-xl' },
  md: { box: 'w-9 h-9 rounded-xl', letter: 'text-base', wordmark: 'text-2xl' },
  lg: { box: 'w-12 h-12 rounded-2xl', letter: 'text-2xl', wordmark: 'text-3xl' },
};

export function Logo({ size = 'md', variant = 'light' }: LogoProps): JSX.Element {
  const s = sizes[size];
  const wordmarkColor = variant === 'dark' ? 'text-white' : 'text-gray-900';

  return (
    <div className="flex items-center gap-2.5">
      <div className={`${s.box} bg-teal-600 flex items-center justify-center shrink-0`}>
        <span className={`text-white font-bold ${s.letter}`}>C</span>
      </div>
      <span className={`font-bold ${s.wordmark} ${wordmarkColor}`}>Clarobill</span>
    </div>
  );
}
