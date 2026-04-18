'use client';

import Link from 'next/link';
import { useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';
import { LogoWithMark } from '@/components/logo';
import { BookOpenIcon, LogOutIcon, MoreIcon } from '@/components/icons';
import s from '@/app/dashboard/dashboard.module.css';

interface DashboardNavProps {
  email: string;
}

const NAV_LINKS = [
  {
    href: '/dashboard',
    label: 'My Bills',
    icon: (
      <svg className={s.mobileNavIcon} viewBox="0 0 24 24" fill="none" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M9 12h6M9 16h6M13 4H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-4-4z"/>
        <path d="M13 4v4h4"/>
      </svg>
    ),
  },
  {
    href: '/dashboard/reports',
    label: 'Reports',
    icon: (
      <svg className={s.mobileNavIcon} viewBox="0 0 24 24" fill="none" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <rect x="3" y="3" width="18" height="18" rx="2"/>
        <path d="M3 9h18M9 21V9"/>
      </svg>
    ),
  },
  {
    href: '/dashboard/billing',
    label: 'Billing',
    icon: (
      <svg className={s.mobileNavIcon} viewBox="0 0 24 24" fill="none" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <rect x="2" y="5" width="20" height="14" rx="2"/>
        <path d="M2 10h20"/>
      </svg>
    ),
  },
  {
    href: '/dashboard/profile',
    label: 'Profile',
    icon: (
      <svg className={s.mobileNavIcon} viewBox="0 0 24 24" fill="none" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="12" cy="8" r="4"/>
        <path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/>
      </svg>
    ),
  },
] as const;

export function DashboardNav({ email }: DashboardNavProps): JSX.Element {
  const pathname = usePathname();
  const router = useRouter();
  const [drawerOpen, setDrawerOpen] = useState(false);

  async function handleSignOut(): Promise<void> {
    setDrawerOpen(false);
    const supabase = createSupabaseBrowserClient();
    await supabase.auth.signOut();
    router.push('/');
    router.refresh();
  }

  const initial = email.charAt(0).toUpperCase();

  return (
    <>
      <header className={s.nav}>
        <Link href="/dashboard" className={s.navLogo}>
          <LogoWithMark size="sm" />
        </Link>

        <nav className={s.navLinks}>
          {NAV_LINKS.map(({ href, label }) => {
            const active = href === '/dashboard'
              ? pathname === '/dashboard'
              : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={`${s.navLink} ${active ? s.navLinkActive : ''}`}
              >
                {label}
              </Link>
            );
          })}
          <a
            href="/blog"
            target="_blank"
            rel="noopener noreferrer"
            className={s.navLinkExt}
          >
            Resources
            <svg width="9" height="9" viewBox="0 0 10 10" fill="none" aria-hidden="true">
              <path d="M1 9L9 1M9 1H3M9 1V7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </a>
        </nav>

        <div className={s.navRight}>
          <Link
            href="/dashboard/profile"
            className={`${s.avatarLink} ${pathname === '/dashboard/profile' ? s.avatarActive : ''}`}
          >
            <span className={s.avatar}>{initial}</span>
            <span className={s.avatarEmail}>{email}</span>
          </Link>
          <button onClick={handleSignOut} className={s.signOutBtn}>
            Sign out
          </button>
        </div>
      </header>

      {/* Mobile bottom tab bar — hidden on desktop via CSS */}
      <nav className={s.mobileNav}>
        {NAV_LINKS.map(({ href, label, icon }) => {
          const active = href === '/dashboard'
            ? pathname === '/dashboard'
            : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={`${s.mobileNavItem} ${active ? s.mobileNavItemActive : ''}`}
            >
              {icon}
              {label}
            </Link>
          );
        })}
        {/* More button — opens bottom sheet with Resources + Sign out */}
        <button
          onClick={() => setDrawerOpen(true)}
          className={`${s.mobileNavItem} ${drawerOpen ? s.mobileNavItemActive : ''}`}
          style={{ background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--fb)' }}
          aria-label="More options"
        >
          <MoreIcon size={22} aria-hidden />
          More
        </button>
      </nav>

      {/* Bottom sheet drawer — slides up over the tab bar */}
      {drawerOpen && (
        <>
          <div
            className={s.drawerBackdrop}
            onClick={() => setDrawerOpen(false)}
            aria-hidden="true"
          />
          <div className={s.drawer} role="dialog" aria-modal="true" aria-label="More options">
            <div className={s.drawerHandle} />
            <div className={s.drawerLogoRow}>
              <LogoWithMark size="sm" />
            </div>
            <nav className={s.drawerNav}>
              <a
                href="/blog"
                className={s.drawerItem}
                onClick={() => setDrawerOpen(false)}
              >
                <span className={s.drawerItemIcon}><BookOpenIcon size={20} /></span>
                <span className={s.drawerItemLabel}>Resources</span>
                <svg className={s.drawerChevron} viewBox="0 0 10 10" fill="none" aria-hidden="true">
                  <path d="M3 2l4 3-4 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </a>
              <button
                className={s.drawerItem}
                onClick={handleSignOut}
              >
                <span className={s.drawerItemIcon}><LogOutIcon size={20} /></span>
                <span className={s.drawerItemLabel}>Sign out</span>
              </button>
            </nav>
          </div>
        </>
      )}
    </>
  );
}
