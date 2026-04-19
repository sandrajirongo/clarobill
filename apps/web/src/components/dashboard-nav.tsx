'use client';

import Link from 'next/link';
import { useState, useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';
import { LogoWithMark } from '@/components/logo';
import { BookOpenIcon, LogOutIcon, MoreIcon, PersonIcon } from '@/components/icons';
import s from '@/app/dashboard/dashboard.module.css';

interface DashboardNavProps {
  email: string;
}

// mobileTab: false = visible in desktop nav but not in the bottom tab bar
const NAV_LINKS: Array<{
  href: string;
  label: string;
  mobileTab: boolean;
  icon: JSX.Element;
}> = [
  {
    href: '/dashboard',
    label: 'My Bills',
    mobileTab: true,
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
    mobileTab: true,
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
    mobileTab: true,
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
    mobileTab: false, // lives in More drawer on mobile
    icon: (
      <svg className={s.mobileNavIcon} viewBox="0 0 24 24" fill="none" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="12" cy="8" r="4"/>
        <path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/>
      </svg>
    ),
  },
];

// Routes that get a first-visit dot until the user navigates there once.
const FIRST_VISIT_HINTS: Record<string, { storageKey: string; tip: string }> = {
  '/dashboard/reports': { storageKey: 'cb_seen_reports', tip: 'Your reports live here' },
  '/dashboard/billing': { storageKey: 'cb_seen_billing', tip: 'Payment receipts are here' },
};

export function DashboardNav({ email }: DashboardNavProps): JSX.Element {
  const pathname = usePathname();
  const router = useRouter();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [avatarMenuOpen, setAvatarMenuOpen] = useState(false);
  // Track which first-visit hints are still unseen. Starts empty (SSR-safe),
  // populated from localStorage on mount.
  const [unseenHints, setUnseenHints] = useState<Set<string>>(new Set());

  useEffect(() => {
    const unseen = new Set(
      Object.entries(FIRST_VISIT_HINTS)
        .filter(([, { storageKey }]) => !localStorage.getItem(storageKey))
        .map(([href]) => href),
    );
    setUnseenHints(unseen);
  }, []);

  // Mark a hint as seen when the user navigates to that route.
  useEffect(() => {
    const hint = FIRST_VISIT_HINTS[pathname];
    if (hint && unseenHints.has(pathname)) {
      localStorage.setItem(hint.storageKey, '1');
      setUnseenHints((prev) => { const next = new Set(prev); next.delete(pathname); return next; });
    }
  }, [pathname, unseenHints]);

  async function handleSignOut(): Promise<void> {
    setDrawerOpen(false);
    setAvatarMenuOpen(false);
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
            const hint = FIRST_VISIT_HINTS[href];
            const showDot = !!hint && unseenHints.has(href) && !active;
            return (
              <Link
                key={href}
                href={href}
                className={`${s.navLink} ${active ? s.navLinkActive : ''} ${showDot ? s.navLinkHint : ''}`}
                title={showDot ? hint?.tip : undefined}
              >
                {label}
                {showDot && <span className={s.navDot} aria-hidden="true" />}
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

        {/* Avatar button — opens dropdown with Profile, Resources, Sign out */}
        <div className={s.navRight}>
          <button
            className={`${s.avatarBtn} ${avatarMenuOpen ? s.avatarBtnActive : ''}`}
            onClick={() => setAvatarMenuOpen((v) => !v)}
            aria-label="Account menu"
            aria-expanded={avatarMenuOpen}
          >
            <span className={s.avatar}>{initial}</span>
            <span className={s.avatarEmail}>{email}</span>
          </button>

          {avatarMenuOpen && (
            <>
              <div className={s.avatarBackdrop} onClick={() => setAvatarMenuOpen(false)} aria-hidden="true" />
              <div className={s.avatarMenu} role="menu">
                <Link
                  href="/dashboard/profile"
                  className={s.avatarMenuItem}
                  onClick={() => setAvatarMenuOpen(false)}
                  role="menuitem"
                >
                  <PersonIcon size={15} />
                  Profile
                </Link>
                <a
                  href="/blog"
                  className={s.avatarMenuItem}
                  onClick={() => setAvatarMenuOpen(false)}
                  role="menuitem"
                >
                  <BookOpenIcon size={15} />
                  Resources
                </a>
                <div className={s.avatarMenuDivider} />
                <button
                  className={`${s.avatarMenuItem} ${s.avatarMenuSignOut}`}
                  onClick={handleSignOut}
                  role="menuitem"
                >
                  <LogOutIcon size={15} />
                  Sign out
                </button>
              </div>
            </>
          )}
        </div>
      </header>

      {/* Mobile bottom tab bar — hidden on desktop via CSS */}
      <nav className={s.mobileNav}>
        {NAV_LINKS.filter((l) => l.mobileTab).map(({ href, label, icon }) => {
          const active = href === '/dashboard'
            ? pathname === '/dashboard'
            : pathname.startsWith(href);
          const hint = FIRST_VISIT_HINTS[href];
          const showDot = !!hint && unseenHints.has(href) && !active;
          return (
            <Link
              key={href}
              href={href}
              className={`${s.mobileNavItem} ${active ? s.mobileNavItemActive : ''}`}
              style={{ position: 'relative' }}
            >
              {icon}
              {label}
              {showDot && <span className={s.mobileNavDot} aria-hidden="true" />}
            </Link>
          );
        })}
        {/* More — opens bottom sheet with Profile, Resources, Sign out */}
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

      {/* Bottom sheet drawer */}
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
              <Link
                href="/dashboard/profile"
                className={s.drawerItem}
                onClick={() => setDrawerOpen(false)}
              >
                <span className={s.drawerItemIcon}><PersonIcon size={20} /></span>
                <span className={s.drawerItemLabel}>Profile</span>
                <svg className={s.drawerChevron} viewBox="0 0 10 10" fill="none" aria-hidden="true">
                  <path d="M3 2l4 3-4 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </Link>
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
              <div className={s.drawerDivider} />
              <button className={s.drawerItem} onClick={handleSignOut}>
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
