import { NextResponse } from 'next/server';
import { cookies } from 'next/headers';

// GET /ref/[code]
//
// Referral link landing page. Sets an httpOnly cookie with the referral code
// and redirects to sign-in so the user can create an account.
//
// Must be a Route Handler (not a Server Component page) — cookies().set() is
// only available in Route Handlers and Server Actions, not Server Components.
export async function GET(
  request: Request,
  { params }: { params: Promise<{ code: string }> },
): Promise<NextResponse> {
  const { code } = await params;
  const cookieStore = await cookies();

  // Store the code for up to 7 days — enough time to sign up
  cookieStore.set('referral_code', code.toUpperCase(), {
    maxAge: 60 * 60 * 24 * 7,
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    path: '/',
  });

  return NextResponse.redirect(new URL('/auth/sign-in', request.url));
}
