'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Logo } from '@/components/logo';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';

interface DashboardNavProps {
  email: string;
}

const NAV_LINKS = [
  { href: '/dashboard',          label: 'My Bills' },
  { href: '/dashboard/reports',  label: 'Reports'  },
  { href: '/dashboard/billing',  label: 'Billing'  },
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

  // Avatar initials from email
  const initial = email.charAt(0).toUpperCase();

  return (
    <header className="bg-white border-b border-slate-100">
      <div className="max-w-5xl mx-auto px-6 h-14 flex items-center justify-between gap-8">

        {/* Left: logo + nav */}
        <div className="flex items-center gap-8 min-w-0">
          <Link href="/dashboard" className="shrink-0">
            <Logo size="sm" />
          </Link>
          <nav className="hidden sm:flex items-center gap-1">
            {NAV_LINKS.map(({ href, label }) => {
              // Active if path matches exactly (dashboard) or starts with (sub-pages)
              const active = href === '/dashboard'
                ? pathname === '/dashboard'
                : pathname.startsWith(href);
              return (
                <NavLink key={href} href={href} active={active}>
                  {label}
                </NavLink>
              );
            })}
            <a
              href="/blog"
              target="_blank"
              rel="noopener noreferrer"
              className="px-3 py-1.5 rounded-md text-sm font-medium text-slate-500 hover:text-slate-900 hover:bg-slate-50 transition-colors flex items-center gap-1"
            >
              Resources
              <svg width="10" height="10" viewBox="0 0 10 10" fill="none" xmlns="http://www.w3.org/2000/svg" className="opacity-40">
                <path d="M1 9L9 1M9 1H3M9 1V7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </a>
          </nav>
        </div>

        {/* Right: profile + sign out */}
        <div className="flex items-center gap-2 shrink-0">
          <Link
            href="/dashboard/profile"
            className={`flex items-center gap-2 px-2 py-1.5 rounded-lg transition-colors hover:bg-slate-50 ${
              pathname === '/dashboard/profile' ? 'bg-slate-100' : ''
            }`}
          >
            <span className="w-7 h-7 rounded-full bg-brand-600 text-white text-xs font-bold flex items-center justify-center shrink-0">
              {initial}
            </span>
            <span className="text-sm text-slate-600 hidden md:block max-w-[160px] truncate">{email}</span>
          </Link>
          <button
            onClick={handleSignOut}
            className="text-sm text-slate-400 hover:text-slate-700 transition-colors px-2 py-1.5 rounded-lg hover:bg-slate-50"
          >
            Sign out
          </button>
        </div>
      </div>
    </header>
  );
}

function NavLink({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <Link
      href={href}
      className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
        active
          ? 'bg-slate-100 text-slate-900'
          : 'text-slate-500 hover:text-slate-900 hover:bg-slate-50'
      }`}
    >
      {children}
    </Link>
  );
}
