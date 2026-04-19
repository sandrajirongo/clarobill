'use client';

import Link from 'next/link';
import { useState, useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';
import { LogoWithMark } from '@/components/logo';
import { BookOpenIcon, LogOutIcon, MoreIcon, PersonIcon } from '@/components/icons';
import s from '@/app/dashboard/dashboard.module.css';

interface DashboardNavProps {
  email: string;
}

const NAV_LINKS_CONFIG: Array<{
  href: string;
  labelKey: 'myBills' | 'reports' | 'billing' | 'profile';
  mobileTab: boolean;
  icon: JSX.Element;
}> = [
  {
    href: '/dashboard',
    labelKey: 'myBills',
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
    labelKey: 'reports',
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
    labelKey: 'billing',
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
    labelKey: 'profile',
    mobileTab: false,
    icon: (
      <svg className={s.mobileNavIcon} viewBox="0 0 24 24" fill="none" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="12" cy="8" r="4"/>
        <path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/>
      </svg>
    ),
  },
];

const FIRST_VISIT_HINT_KEYS: Record<string, { storageKey: string; tKey: 'hintReports' | 'hintBilling' }> = {
  '/dashboard/reports': { storageKey: 'cb_seen_reports', tKey: 'hintReports' },
  '/dashboard/billing': { storageKey: 'cb_seen_billing', tKey: 'hintBilling' },
};

export function DashboardNav({ email }: DashboardNavProps): JSX.Element {
  const t = useTranslations('nav');
  const pathname = usePathname();
  const router = useRouter();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [avatarMenuOpen, setAvatarMenuOpen] = useState(false);
  const [unseenHints, setUnseenHints] = useState<Set<string>>(new Set());

  useEffect(() => {
    const unseen = new Set(
      Object.entries(FIRST_VISIT_HINT_KEYS)
        .filter(([, { storageKey }]) => !localStorage.getItem(storageKey))
        .map(([href]) => href),
    );
    setUnseenHints(unseen);
  }, []);

  useEffect(() => {
    const hint = FIRST_VISIT_HINT_KEYS[pathname];
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
          {NAV_LINKS_CONFIG.map(({ href, labelKey }) => {
            const label = t(labelKey);
            const active = href === '/dashboard'
              ? pathname === '/dashboard'
              : pathname.startsWith(href);
            const hint = FIRST_VISIT_HINT_KEYS[href];
            const showDot = !!hint && unseenHints.has(href) && !active;
            return (
              <Link
                key={href}
                href={href}
                className={`${s.navLink} ${active ? s.navLinkActive : ''} ${showDot ? s.navLinkHint : ''}`}
                title={showDot ? t(hint.tKey) : undefined}
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
            {t('resources')}
            <svg width="9" height="9" viewBox="0 0 10 10" fill="none" aria-hidden="true">
              <path d="M1 9L9 1M9 1H3M9 1V7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </a>
        </nav>

        <div className={s.navRight}>
          <button
            className={`${s.avatarBtn} ${avatarMenuOpen ? s.avatarBtnActive : ''}`}
            onClick={() => setAvatarMenuOpen((v) => !v)}
            aria-label={t('accountMenu')}
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
                  {t('profile')}
                </Link>
                <a
                  href="/blog"
                  className={s.avatarMenuItem}
                  onClick={() => setAvatarMenuOpen(false)}
                  role="menuitem"
                >
                  <BookOpenIcon size={15} />
                  {t('resources')}
                </a>
                <div className={s.avatarMenuDivider} />
                <button
                  className={`${s.avatarMenuItem} ${s.avatarMenuSignOut}`}
                  onClick={handleSignOut}
                  role="menuitem"
                >
                  <LogOutIcon size={15} />
                  {t('signOut')}
                </button>
              </div>
            </>
          )}
        </div>
      </header>

      <nav className={s.mobileNav}>
        {NAV_LINKS_CONFIG.filter((l) => l.mobileTab).map(({ href, labelKey, icon }) => {
          const label = t(labelKey);
          const active = href === '/dashboard'
            ? pathname === '/dashboard'
            : pathname.startsWith(href);
          const hint = FIRST_VISIT_HINT_KEYS[href];
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
        <button
          onClick={() => setDrawerOpen(true)}
          className={`${s.mobileNavItem} ${drawerOpen ? s.mobileNavItemActive : ''}`}
          style={{ background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--fb)' }}
          aria-label={t('moreOptions')}
        >
          <MoreIcon size={22} aria-hidden />
          {t('more')}
        </button>
      </nav>

      {drawerOpen && (
        <>
          <div
            className={s.drawerBackdrop}
            onClick={() => setDrawerOpen(false)}
            aria-hidden="true"
          />
          <div className={s.drawer} role="dialog" aria-modal="true" aria-label={t('moreOptions')}>
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
                <span className={s.drawerItemLabel}>{t('profile')}</span>
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
                <span className={s.drawerItemLabel}>{t('resources')}</span>
                <svg className={s.drawerChevron} viewBox="0 0 10 10" fill="none" aria-hidden="true">
                  <path d="M3 2l4 3-4 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </a>
              <div className={s.drawerDivider} />
              <button className={s.drawerItem} onClick={handleSignOut}>
                <span className={s.drawerItemIcon}><LogOutIcon size={20} /></span>
                <span className={s.drawerItemLabel}>{t('signOut')}</span>
              </button>
            </nav>
          </div>
        </>
      )}
    </>
  );
}
