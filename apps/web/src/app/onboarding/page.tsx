import { redirect } from 'next/navigation';
import { getAuthenticatedUser, createSupabaseServerClient } from '@/lib/supabase/server';
import { OnboardingWizard } from './OnboardingWizard';

export const metadata = { title: 'Welcome — ClaroBill' };

export default async function OnboardingPage(): Promise<JSX.Element> {
  const user = await getAuthenticatedUser();
  if (!user) redirect('/auth/sign-in');

  const supabase = await createSupabaseServerClient();
  const { count } = await supabase
    .from('profile_members')
    .select('id', { count: 'exact', head: true })
    .eq('user_id', user.id);

  // Skip wizard if user already completed onboarding
  if (count && count > 0) redirect('/dashboard');

  return <OnboardingWizard />;
}
