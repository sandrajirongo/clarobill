import Link from 'next/link';
import { MarketingNav } from '@/components/marketing-nav';
import s from './blog.module.css';

export default function BlogLayout({
  children,
}: {
  children: React.ReactNode;
}): JSX.Element {
  return (
    <div className={s.shell}>
      <MarketingNav activePath="/blog" />

      <main className={s.main}>
        {children}
      </main>

      <footer className={s.footer}>
        <div className={s.footerInner}>
          <span className={s.footerNote}>© {new Date().getFullYear()} Clarobill. All rights reserved.</span>
          <nav className={s.footerLinks}>
            <Link href="/legal/terms" className={s.footerLink}>Terms</Link>
            <Link href="/legal/privacy" className={s.footerLink}>Privacy</Link>
            <Link href="/legal/disclaimer" className={s.footerLink}>Disclaimer</Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}
