/**
 * Below are the colors that are used in the app. The colors are defined in the light and dark mode.
 * There are many other ways to style your app. For example, [Nativewind](https://www.nativewind.dev/), [Tamagui](https://tamagui.dev/), [unistyles](https://reactnativeunistyles.vercel.app), etc.
 */

import '@/global.css';

import { Platform } from 'react-native';

// ClaroBill brand palette. Sage + cream + ink — see docs/product/brand-guidelines.md.
// Tabs, buttons, and accents all key off these tokens so the app stays consistent
// across light and dark system themes.
export const Colors = {
  light: {
    text: '#1A1A14',           // ink — primary text
    textSecondary: '#5A5A50',  // body
    background: '#F4F2EC',     // cream — page bg
    backgroundElement: '#ffffff', // white — card / input bg
    backgroundSelected: '#2D4A2A', // sage — selected tab / pressed
    accent: '#2D4A2A',         // sage — buttons, links, indicators
    accentOn: '#ffffff',       // text/icon color on sage
    border: '#E2DDD4',
    muted: '#9A9A8E',
  },
  dark: {
    text: '#F4F2EC',
    textSecondary: '#B8B5AC',
    background: '#1A1A14',
    backgroundElement: '#2A2A22',
    backgroundSelected: '#2D4A2A',
    accent: '#C8F060',         // lime accent on dark
    accentOn: '#1A1A14',
    border: '#3A3A30',
    muted: '#7A7A6E',
  },
} as const;

export type ThemeColor = keyof typeof Colors.light & keyof typeof Colors.dark;

export const Fonts = Platform.select({
  ios: {
    /** iOS `UIFontDescriptorSystemDesignDefault` */
    sans: 'system-ui',
    /** iOS `UIFontDescriptorSystemDesignSerif` */
    serif: 'ui-serif',
    /** iOS `UIFontDescriptorSystemDesignRounded` */
    rounded: 'ui-rounded',
    /** iOS `UIFontDescriptorSystemDesignMonospaced` */
    mono: 'ui-monospace',
  },
  default: {
    sans: 'normal',
    serif: 'serif',
    rounded: 'normal',
    mono: 'monospace',
  },
  web: {
    sans: 'var(--font-display)',
    serif: 'var(--font-serif)',
    rounded: 'var(--font-rounded)',
    mono: 'var(--font-mono)',
  },
});

export const Spacing = {
  half: 2,
  one: 4,
  two: 8,
  three: 16,
  four: 24,
  five: 32,
  six: 64,
} as const;

export const BottomTabInset = Platform.select({ ios: 50, android: 80 }) ?? 0;
export const MaxContentWidth = 800;
