import { createBrowserClient } from '@supabase/ssr';

// Browser-side Supabase client — safe to use in Client Components.
// Uses NEXT_PUBLIC_ env vars which are exposed to the browser.
export function createSupabaseBrowserClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  );
}
