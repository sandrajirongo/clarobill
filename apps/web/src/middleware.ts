import { createServerClient } from '@supabase/ssr';
import { NextResponse, type NextRequest } from 'next/server';

// Routes that do NOT require authentication
const PUBLIC_ROUTES = ['/', '/auth/sign-in', '/auth/sign-up', '/auth/callback', '/legal', '/logo-test', '/pricing'];

export async function middleware(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          // IMPORTANT: must call both request and response setters so the
          // refreshed session is available to downstream Server Components.
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value)
          );
          supabaseResponse = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, {
              ...options,
              // Persist auth cookies across browser restarts so users aren't
              // logged out after idle periods shorter than the JWT lifetime.
              maxAge: options.maxAge ?? 60 * 60 * 24 * 7,
            })
          );
        },
      },
    }
  );

  // Refresh the session — this is the primary reason this middleware exists.
  // Do NOT remove this call.
  const { data: { user } } = await supabase.auth.getUser();

  const { pathname } = request.nextUrl;

  // If Supabase redirected a ?code= to a non-callback route (e.g. homepage),
  // forward it to /auth/callback so the session can be established.
  //
  // Exception: /auth/update-password handles its own code exchange — the code
  // there is a password-reset recovery token, not a sign-in code. Redirecting
  // it to /auth/callback would silently log the user in and skip the
  // "set new password" form entirely.
  const code = request.nextUrl.searchParams.get('code');
  if (code && pathname !== '/auth/callback' && pathname !== '/auth/update-password') {
    const callbackUrl = request.nextUrl.clone();
    callbackUrl.pathname = '/auth/callback';
    return NextResponse.redirect(callbackUrl);
  }

  // Authenticated users visiting the landing page or sign-in page go straight
  // to their dashboard (or onboarding — the dashboard page handles that check).
  // This handles both the "open new tab → homepage" case and the "click blog
  // CTA while already signed in" case.
  const AUTH_ENTRY_POINTS = ['/', '/auth/sign-in', '/auth/sign-up'];
  if (user && AUTH_ENTRY_POINTS.includes(pathname)) {
    const dashboardUrl = request.nextUrl.clone();
    dashboardUrl.pathname = '/dashboard';
    dashboardUrl.search = '';
    return NextResponse.redirect(dashboardUrl);
  }

  const isPublicRoute = PUBLIC_ROUTES.some(
    (route) => pathname === route || pathname.startsWith('/auth/') || pathname.startsWith('/legal/')
  )
    || pathname === '/icon'
    || pathname === '/apple-icon'
    // /opengraph-image is fetched by social scrapers (iMessage, WhatsApp, Slack,
    // Twitter, Facebook) when a URL is shared. Auth-redirecting it returns a 307
    // which scrapers don't follow → blank preview cards. Must stay public.
    || pathname === '/opengraph-image'
    || pathname.startsWith('/blog')
    || pathname.startsWith('/ref/');

  if (!user && !isPublicRoute) {
    const signInUrl = request.nextUrl.clone();
    signInUrl.pathname = '/auth/sign-in';
    signInUrl.searchParams.set('redirect', pathname);
    return NextResponse.redirect(signInUrl);
  }

  return supabaseResponse;
}

export const config = {
  matcher: [
    // Run on all routes except Next.js internals and static files
    '/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)',
  ],
};
