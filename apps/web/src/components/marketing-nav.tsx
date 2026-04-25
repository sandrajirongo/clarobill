'use client';

import { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import { LogoWithMark } from '@/components/logo';
import { BetaBanner } from '@/components/beta-banner';
import s from './marketing-nav.module.css';

interface MarketingNavProps {
  activePath?: string;
}

export function MarketingNav({ activePath }: MarketingNavProps): JSX.Element {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    if (!menuOpen) return;
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [menuOpen]);

  // Close on ESC
  useEffect(() => {
    if (!menuOpen) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setMenuOpen(false);
    }
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [menuOpen]);

  // Prevent body scroll while menu is open
  useEffect(() => {
    document.body.style.overflow = menuOpen ? 'hidden' : '';
    return () => { document.body.style.overflow = ''; };
  }, [menuOpen]);

  const links = [
    { href: '/',         label: 'Home'      },
    { href: '/pricing',  label: 'Pricing'   },
    { href: '/blog',     label: 'Resources' },
  ];

  // /pricing already has its own dedicated beta callout under the nav,
  // so suppress the banner CTA there to avoid two beta CTAs on the same page.
  const isPricingPage = activePath === '/pricing';

  return (
    <>
      <BetaBanner showCta={!isPricingPage} />
      <nav className={s.nav} ref={menuRef}>
      <Link href="/" className={s.logo}>
        <LogoWithMark size="md" />
      </Link>

      {/* Desktop links */}
      <div className={s.desktopLinks}>
        {links.map((l) => (
          <Link
            key={l.href}
            href={l.href}
            className={`${s.navLink} ${activePath === l.href ? s.navLinkActive : ''}`}
          >
            {l.label}
          </Link>
        ))}
      </div>

      {/* Desktop CTA */}
      <Link className={`${s.navCta} ${s.desktopCta}`} href="/auth/sign-in">
        Get started
      </Link>

      {/* Mobile burger */}
      <button
        className={s.burger}
        onClick={() => setMenuOpen((v) => !v)}
        aria-label={menuOpen ? 'Close menu' : 'Open menu'}
        aria-expanded={menuOpen}
        type="button"
      >
        <span className={`${s.burgerLine} ${menuOpen ? s.burgerLineTopOpen : ''}`} />
        <span className={`${s.burgerLine} ${menuOpen ? s.burgerLineMidOpen : ''}`} />
        <span className={`${s.burgerLine} ${menuOpen ? s.burgerLineBotOpen : ''}`} />
      </button>

      {/* Mobile drawer */}
      <div className={`${s.drawer} ${menuOpen ? s.drawerOpen : ''}`} aria-hidden={!menuOpen}>
        <div className={s.drawerLinks}>
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={`${s.drawerLink} ${activePath === l.href ? s.drawerLinkActive : ''}`}
              onClick={() => setMenuOpen(false)}
            >
              {l.label}
            </Link>
          ))}
        </div>
        <Link href="/auth/sign-in" className={s.drawerCta} onClick={() => setMenuOpen(false)}>
          Get started
        </Link>
      </div>
    </nav>
    </>
  );
}
