'use client';

import { useEffect } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';
import { initPostHog, posthog } from '@/lib/posthog';

export function PostHogProvider({ children }: { children: React.ReactNode }): JSX.Element {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  // Capture page views on route change — strip any sensitive query params
  useEffect(() => {
    if (!pathname) return;

    // Initialise first, then capture — avoids race condition on first render
    initPostHog();

    const safeUrl = pathname.replace(
      /\/bills\/[a-f0-9-]{36}/g,
      '/bills/[billId]'
    );

    posthog.capture('$pageview', { $current_url: safeUrl });
  }, [pathname, searchParams]);

  return <>{children}</>;
}
