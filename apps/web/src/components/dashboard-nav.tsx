'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';
import { LogoWithMark } from '@/components/logo';
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

  async function handleSignOut(): Promise<void> {
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
        <button
          onClick={handleSignOut}
          className={`${s.mobileNavItem}`}
          style={{ background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--fb)' }}
        >
          <svg className={s.mobileNavIcon} viewBox="0 0 24 24" fill="none" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>
          </svg>
          Sign out
        </button>
      </nav>
    </>
  );
}
