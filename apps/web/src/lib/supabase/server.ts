import { createServerClient } from '@supabase/ssr';
import { createClient } from '@supabase/supabase-js';
import { cookies, headers } from 'next/headers';

// Server-side Supabase client — use in Server Components, Server Actions,
// and Route Handlers.
//
// Auth resolution:
// 1. `Authorization: Bearer <jwt>` header → builds an RLS-aware client that
//    forwards the JWT on every request (mobile app, service-to-service).
// 2. Supabase auth cookies via @supabase/ssr (web browser sessions).
//
// Bearer takes precedence so a mobile request hitting an endpoint that also
// has cookies set (e.g. via a shared browser) is still authorised as the
// mobile user.
export async function createSupabaseServerClient() {
  const headerList = await headers();
  const authHeader = headerList.get('authorization') ?? headerList.get('Authorization');
  if (authHeader?.startsWith('Bearer ')) {
    const token = authHeader.slice('Bearer '.length).trim();
    if (token) {
      return createClient(
        process.env.NEXT_PUBLIC_SUPABASE_URL!,
        process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
        {
          global: { headers: { Authorization: `Bearer ${token}` } },
          auth: { persistSession: false, autoRefreshToken: false },
        }
      );
    }
  }

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
//
// Auth resolution order:
// 1. Supabase cookies set via @supabase/ssr (web browser sessions)
// 2. `Authorization: Bearer <jwt>` header (mobile app, service-to-service calls)
//
// The Bearer path mirrors what the cookie path does — validates the JWT via
// `supabase.auth.getUser(jwt)`, which checks the signature server-side against
// the Supabase project's JWT secret.
export async function getAuthenticatedUser() {
  const supabase = await createSupabaseServerClient();
  const { data: { user: cookieUser } } = await supabase.auth.getUser();
  if (cookieUser) return cookieUser;

  const headerList = await headers();
  const authHeader = headerList.get('authorization') ?? headerList.get('Authorization');
  if (authHeader?.startsWith('Bearer ')) {
    const token = authHeader.slice('Bearer '.length).trim();
    if (token) {
      const tokenClient = createClient(
        process.env.NEXT_PUBLIC_SUPABASE_URL!,
        process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
      );
      const { data: { user: bearerUser } } = await tokenClient.auth.getUser(token);
      if (bearerUser) return bearerUser;
    }
  }

  return null;
}
