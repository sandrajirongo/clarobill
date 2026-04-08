'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';
import s from '@/app/dashboard/dashboard.module.css';

interface DashboardNavProps {
  email: string;
}

const NAV_LINKS = [
  { href: '/dashboard',         label: 'My Bills' },
  { href: '/dashboard/reports', label: 'Reports'  },
  { href: '/dashboard/billing', label: 'Billing'  },
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
    <header className={s.nav}>
      <Link href="/dashboard" className={s.navLogo}>
        Claro<em style={{ fontStyle: 'italic' }}>Bill</em>.
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
          <span className={`${s.avatarEmail} hidden-mobile`}>{email}</span>
        </Link>
        <button onClick={handleSignOut} className={s.signOutBtn}>
          Sign out
        </button>
      </div>
    </header>
  );
}
