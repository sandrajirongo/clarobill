import { createBrowserClient } from '@supabase/ssr';

// Browser-side Supabase client — safe to use in Client Components.
// Uses NEXT_PUBLIC_ env vars which are exposed to the browser.
//
// autoRefreshToken: proactively refreshes the JWT before it expires while the
// tab is open — prevents mid-session logouts during active use.
// persistSession: stores the session in localStorage so it survives page reloads
// and short tab-switches (the server-side cookie handles SSR; this backs it up).
export function createSupabaseBrowserClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
      },
    }
  );
}
