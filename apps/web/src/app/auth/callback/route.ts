import { NextResponse } from 'next/server';
import { createSupabaseServerClient } from '@/lib/supabase/server';
import type { EmailOtpType } from '@supabase/supabase-js';

// Handles two Supabase auth redirect flows:
//
// 1. PKCE magic link — Supabase sends ?code=... and we exchange it for a session.
// 2. Email confirmation — Supabase sends ?token_hash=...&type=signup (or recovery,
//    invite, etc.) and we verify the OTP directly. This flow is used when a new user
//    confirms their account via the "confirm your email" link.
//
// Both flows land here because emailRedirectTo is set to /auth/callback in signInWithOtp.
export async function GET(request: Request): Promise<NextResponse> {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get('code');
  const tokenHash = searchParams.get('token_hash');
  const type = searchParams.get('type') as EmailOtpType | null;
  const redirectTo = searchParams.get('redirect') ?? '/dashboard';

  const supabase = await createSupabaseServerClient();

  if (code) {
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) {
      return NextResponse.redirect(`${origin}${redirectTo}`);
    }
  } else if (tokenHash && type) {
    // Email confirmation / OTP verification flow
    const { error } = await supabase.auth.verifyOtp({ token_hash: tokenHash, type });
    if (!error) {
      return NextResponse.redirect(`${origin}${redirectTo}`);
    }
  }

  return NextResponse.redirect(`${origin}/auth/sign-in?error=auth_failed`);
}
