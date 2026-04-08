import type { Config } from "tailwindcss";

// Major Third type scale (ratio 1.25) anchored at 16px — SKILL.md
const majorThird: Record<string, [string, { lineHeight: string }]> = {
  '2xs': ['0.64rem',  { lineHeight: '1rem' }],
  xs:    ['0.8rem',   { lineHeight: '1.2rem' }],
  sm:    ['0.889rem', { lineHeight: '1.375rem' }],
  base:  ['1rem',     { lineHeight: '1.5rem' }],
  lg:    ['1.25rem',  { lineHeight: '1.75rem' }],
  xl:    ['1.563rem', { lineHeight: '2rem' }],
  '2xl': ['1.953rem', { lineHeight: '2.375rem' }],
  '3xl': ['2.441rem', { lineHeight: '2.875rem' }],
  '4xl': ['3.052rem', { lineHeight: '3.5rem' }],
};

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    // 8-point grid: use multiples of space-2 (8px), space-4 (16px), space-6 (24px), etc.
    extend: {
      fontSize: majorThird,
      colors: {
        brand: {
          50:  '#f0fdfa',
          100: '#ccfbf1',
          500: '#14b8a6',
          600: '#0d9488',
          700: '#0f766e',
          900: '#134e4a',
        },
      },
    },
  },
  plugins: [],
};

export default config;
