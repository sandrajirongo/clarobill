import { redirect } from 'next/navigation';
import { cookies } from 'next/headers';

interface PageProps {
  params: Promise<{ code: string }>;
}

// Landing page for referral links: /ref/ABC12345
// Sets an httpOnly cookie and immediately redirects to sign-in.
// The cookie is picked up by the auth callback after the user signs up.
export default async function ReferralLandingPage({ params }: PageProps): Promise<never> {
  const { code } = await params;
  const cookieStore = await cookies();

  cookieStore.set('referral_code', code.toUpperCase(), {
    maxAge: 60 * 60 * 24 * 7, // 7 days — enough time to sign up
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    path: '/',
  });

  redirect('/auth/sign-in');
}
