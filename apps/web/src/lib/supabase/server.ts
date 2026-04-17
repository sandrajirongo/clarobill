import { createServerClient } from '@supabase/ssr';
import { createClient } from '@supabase/supabase-js';
import { cookies } from 'next/headers';

// Server-side Supabase client — use in Server Components, Server Actions,
// and Route Handlers. Reads/writes cookies to maintain the session.
export async function createSupabaseServerClient() {
  const cookieStore = await cookies();

  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) => {
              // Ensure a minimum maxAge so auth cookies are not session cookies
              // (session cookies disappear on browser close, causing spurious logouts).
              // 7 days matches Supabase's default refresh token lifetime — the JWT
              // itself is validated server-side so the longer cookie window is safe.
              cookieStore.set(name, value, {
                ...options,
                maxAge: options.maxAge ?? 60 * 60 * 24 * 7,
              });
            });
          } catch {
            // setAll is called from Server Components where cookies are read-only.
            // The middleware handles token refresh in those cases, so this is safe.
          }
        },
      },
    }
  );
}

// Service role client — bypasses RLS for admin operations (storage signed URLs, etc.)
// Never expose this client to the browser. Server-side only.
export function createSupabaseServiceClient() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
  );
}

// Returns the authenticated user or null. Never throws.
export async function getAuthenticatedUser() {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();
  return user;
}
