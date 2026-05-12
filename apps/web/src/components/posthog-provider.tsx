'use client';

import { useEffect } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';
import { initPostHog, posthog } from '@/lib/posthog';

export function PostHogProvider({ children }: { children: React.ReactNode }): JSX.Element {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  // Identify the logged-in user once on mount.
  // PostHog uses this to link anonymous pre-auth events to the user, and
  // the Loops Data Pipeline destination uses it to create/update contacts.
  useEffect(() => {
    initPostHog();
    const supabase = createSupabaseBrowserClient();
    supabase.auth.getSession().then(({ data }) => {
      const user = data.session?.user;
      if (!user) return;
      posthog.identify(user.id, {
        email: user.email,
        created_at: user.created_at,
      });
    });
  // Run once on mount only — re-identifying on every route change is unnecessary.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Capture page views on route change — strip any sensitive query params
  useEffect(() => {
    if (!pathname) return;
    initPostHog();
    const safeUrl = pathname.replace(/\/bills\/[a-f0-9-]{36}/g, '/bills/[billId]');
    posthog.capture('$pageview', { $current_url: safeUrl });
  }, [pathname, searchParams]);

  return <>{children}</>;
}
