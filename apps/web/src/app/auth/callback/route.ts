import { NextResponse } from 'next/server';
import { cookies } from 'next/headers';
import { createSupabaseServerClient, createSupabaseServiceClient } from '@/lib/supabase/server';
import { sendLoopsEvent } from '@/lib/loops';
import { captureServerEvent } from '@/lib/analytics-server';
import type { EmailOtpType } from '@supabase/supabase-js';

// Handles two Supabase auth redirect flows:
//
// 1. PKCE magic link — Supabase sends ?code=... and we exchange it for a session.
// 2. Email confirmation — Supabase sends ?token_hash=...&type=signup (or recovery,
//    invite, etc.) and we verify the OTP directly.
//
// After either flow succeeds, we apply any pending referral code from the cookie.
export async function GET(request: Request): Promise<NextResponse> {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get('code');
  const tokenHash = searchParams.get('token_hash');
  const type = searchParams.get('type') as EmailOtpType | null;
  const redirectTo = searchParams.get('redirect') ?? '/dashboard';

  const supabase = await createSupabaseServerClient();

  let authSuccess = false;

  if (code) {
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) authSuccess = true;
  } else if (tokenHash && type) {
    const { error } = await supabase.auth.verifyOtp({ token_hash: tokenHash, type });
    if (!error) authSuccess = true;
  }

  if (!authSuccess) {
    return NextResponse.redirect(`${origin}/auth/sign-in?error=auth_failed`);
  }

  // Apply referral code if one was set before sign-in
  const cookieStore = await cookies();
  const referralCode = cookieStore.get('referral_code')?.value;
  if (referralCode) {
    await applyReferral(supabase, referralCode);
    // Clear the referral cookie — it's single-use
    cookieStore.delete('referral_code');
  }

  // Sync new sign-ups to Loops and PostHog.
  // type==='signup' covers email-confirmation flows (password + OTP sign-up).
  // For PKCE magic-link flows (code param, no type), we detect new users by
  // checking whether created_at is within the last 60 seconds.
  const { data: { user } } = await supabase.auth.getUser();
  if (user?.email) {
    const createdRecently = user.created_at
      ? Date.now() - new Date(user.created_at).getTime() < 60_000
      : false;
    const isNewUser = type === 'signup' || (!!code && createdRecently);

    if (isNewUser) {
      // Supabase integration owns contact creation — we only fire the journey trigger.
      await Promise.all([
        sendLoopsEvent(user.email, 'user_signed_up'),
        captureServerEvent(user.id, 'user_signed_up', { email: user.email }),
      ]);
    }
  }

  const response = NextResponse.redirect(`${origin}${redirectTo}`);
  return response;
}

async function applyReferral(
  supabase: Awaited<ReturnType<typeof createSupabaseServerClient>>,
  code: string,
): Promise<void> {
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return;

  // Look up who owns this referral code
  const service = createSupabaseServiceClient();
  const { data: referralCode } = await service
    .from('referral_codes')
    .select('user_id')
    .eq('code', code)
    .maybeSingle();

  // Don't let users refer themselves
  if (!referralCode || referralCode.user_id === user.id) return;

  // Create the referral record — unique on referred_user_id so this is idempotent
  await service.from('referrals').upsert(
    {
      referrer_user_id: referralCode.user_id,
      referred_user_id: user.id,
      status: 'pending',
    },
    { onConflict: 'referred_user_id', ignoreDuplicates: true }
  );
}
