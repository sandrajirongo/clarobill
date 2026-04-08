import type { Metadata } from 'next';
import Link from 'next/link';
import { Logo } from '@/components/logo';

export const metadata: Metadata = {
  robots: { index: true, follow: true },
};

export default function LegalLayout({
  children,
}: {
  children: React.ReactNode;
}): JSX.Element {
  return (
    <div style={{ minHeight: '100vh', background: 'var(--cream)', display: 'flex', flexDirection: 'column', fontFamily: 'var(--fb)' }}>
      <header style={{
        position: 'sticky', top: 0, zIndex: 100, height: 60,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 clamp(1rem, 5vw, 2.75rem)',
        background: 'rgba(244, 242, 236, .95)', backdropFilter: 'blur(14px)',
        borderBottom: '1px solid var(--border)',
      }}>
        <Link href="/" style={{ textDecoration: 'none' }}>
          <Logo size="sm" />
        </Link>
        <nav style={{ display: 'flex', gap: '1.5rem' }}>
          {(['terms', 'privacy', 'disclaimer'] as const).map((page) => (
            <Link key={page} href={`/legal/${page}`} style={{
              fontSize: '.8rem', color: 'var(--txt2)', textDecoration: 'none',
              textTransform: 'capitalize', transition: 'color .15s',
            }}>
              {page.charAt(0).toUpperCase() + page.slice(1)}
            </Link>
          ))}
        </nav>
      </header>

      <main style={{ maxWidth: 720, margin: '0 auto', padding: 'clamp(2rem,5vw,3.5rem) clamp(1rem,5vw,2rem)', flex: 1 }}>
        {children}
      </main>

      <footer style={{ borderTop: '1px solid var(--border)', padding: '1.25rem clamp(1rem,5vw,2.75rem)' }}>
        <div style={{ maxWidth: 720, margin: '0 auto', display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '.5rem' }}>
          <span style={{ fontSize: '.72rem', color: 'var(--txt3)' }}>© {new Date().getFullYear()} Clarobill. All rights reserved.</span>
          <nav style={{ display: 'flex', gap: '1.5rem' }}>
            {(['terms', 'privacy', 'disclaimer'] as const).map((page) => (
              <Link key={page} href={`/legal/${page}`} style={{ fontSize: '.72rem', color: 'var(--txt3)', textDecoration: 'none' }}>
                {page.charAt(0).toUpperCase() + page.slice(1)}
              </Link>
            ))}
          </nav>
        </div>
      </footer>
    </div>
  );
}
