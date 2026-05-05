/**
 * Beta-mode toggle — single source of truth for whether the product
 * is currently free. The default-true behaviour is intentional: a missing
 * env var must NOT silently start charging users.
 */

import { afterEach, describe, expect, it } from 'vitest';
import { BETA_COPY, SOCIAL_LINKS, buildTweetIntentUrl, isBetaMode } from '@/lib/beta';

describe('isBetaMode', () => {
  const original = process.env.NEXT_PUBLIC_BETA_MODE;

  afterEach(() => {
    if (original === undefined) {
      delete process.env.NEXT_PUBLIC_BETA_MODE;
    } else {
      process.env.NEXT_PUBLIC_BETA_MODE = original;
    }
  });

  it('returns true when env var is unset', () => {
    delete process.env.NEXT_PUBLIC_BETA_MODE;
    expect(isBetaMode()).toBe(true);
  });

  it('returns true when env var is empty string', () => {
    process.env.NEXT_PUBLIC_BETA_MODE = '';
    expect(isBetaMode()).toBe(true);
  });

  it('returns true when env var is "true"', () => {
    process.env.NEXT_PUBLIC_BETA_MODE = 'true';
    expect(isBetaMode()).toBe(true);
  });

  it('returns false ONLY for the exact string "false"', () => {
    process.env.NEXT_PUBLIC_BETA_MODE = 'false';
    expect(isBetaMode()).toBe(false);
  });

  it('case-sensitive: "False" still resolves to beta-on', () => {
    // Important — defaulting to "free" on any non-canonical value protects
    // against accidental capitalization in the Vercel env editor.
    process.env.NEXT_PUBLIC_BETA_MODE = 'False';
    expect(isBetaMode()).toBe(true);
  });

  it('any other value defaults to beta-on', () => {
    process.env.NEXT_PUBLIC_BETA_MODE = '0';
    expect(isBetaMode()).toBe(true);
  });
});

describe('buildTweetIntentUrl', () => {
  it('builds a valid Twitter intent URL with text + url', () => {
    const intent = buildTweetIntentUrl('Hello world', 'https://clarobill.com');
    expect(intent).toMatch(/^https:\/\/twitter\.com\/intent\/tweet\?/);
    expect(intent).toMatch(/text=Hello\+world/);
    expect(intent).toMatch(/url=https%3A%2F%2Fclarobill\.com/);
  });

  it('escapes special characters in text and url', () => {
    const intent = buildTweetIntentUrl('Save $$$ now!', 'https://clarobill.com/r/abc?q=1&z=2');
    // The query parameters should be URL-encoded — & inside the URL must not
    // be interpreted as a parameter separator.
    expect(intent).toContain('Save+%24%24%24+now%21');
    expect(intent).toContain('q%3D1%26z%3D2');
  });
});

describe('SOCIAL_LINKS contract', () => {
  it('exposes Instagram, X, LinkedIn, and email entries with handle + url', () => {
    for (const key of ['instagram', 'x', 'linkedin', 'email'] as const) {
      const link = SOCIAL_LINKS[key];
      expect(link.handle).toBeTruthy();
      expect(link.url).toBeTruthy();
    }
  });

  it('email url is a mailto: link', () => {
    expect(SOCIAL_LINKS.email.url).toMatch(/^mailto:/);
  });

  it('X handle is the AI-tagged @clarobillai', () => {
    // The tweetText copy uses this handle directly; a rename must not
    // silently leave the share text out of sync.
    expect(SOCIAL_LINKS.x.handle).toBe('@clarobillai');
  });
});

describe('BETA_COPY contract', () => {
  it('paywall button copy is a non-empty string', () => {
    expect(BETA_COPY.paywall.button.length).toBeGreaterThan(0);
  });

  it('share tweetText tags @clarobillai (so X posts surface in our mentions)', () => {
    expect(BETA_COPY.share.tweetText).toContain('@clarobillai');
  });
});
