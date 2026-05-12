import type { Metadata } from 'next';
import Link from 'next/link';
import { LogoWithMark } from '@/components/logo';
import s from './demo.module.css';

// Unlisted route. Reachable only via direct link (pitch decks, investor
// outreach). Not in nav, footer, or sitemap. noindex/nofollow keeps it out
// of search results so it stays a controlled-distribution surface.
export const metadata: Metadata = {
  title: 'ClaroBill: walkthrough',
  description: 'See how ClaroBill audits a real medical bill against published hospital rates.',
  robots: { index: false, follow: false },
};

export default function DemoPage(): JSX.Element {
  return (
    <main className={s.page}>
      <header className={s.header}>
        <LogoWithMark size="lg" />
        <span className={s.tagline}>Product walkthrough</span>
      </header>

      <div
        id="floik-iframe-container-moq3h5jb"
        className={s.videoFrame}
        style={{ aspectRatio: '2.0824295010845986' }}
      >
        <iframe
          id="floik-iframe-moq3h5jb"
          title="ClaroBill product walkthrough"
          src="https://www.floik.com/embed/3b650f72-b8ee-4665-a9eb-31a2d4f9a773/6866a8fd-1542-41cb-b1d8-1a1e0097f746-flo.html"
          allow="clipboard-read; clipboard-write"
          allowFullScreen
          className={s.iframe}
        />
      </div>

      <div className={s.actions}>
        <Link href="/auth/sign-in" className={s.cta}>
          Try it on your own bill
        </Link>
        <a href="https://www.clarobill.com" className={s.secondary}>
          clarobill.com
        </a>
      </div>
    </main>
  );
}
