'use server';

import { cookies } from 'next/headers';
import { createSupabaseServerClient } from '@/lib/supabase/server';
import { LOCALES } from '../../../i18n/routing';

export type OnboardingData = {
  fullName: string;
  dateOfBirth: string;
  state: string;
  zipCode: string;
  insuranceType: string; // empty string means the user skipped insurance setup
  locale: string;
};

// Saves profile member + primary insurance plan and persists the user's chosen
// locale. Called once at the end of the onboarding wizard.
export async function saveOnboarding(
  data: OnboardingData,
): Promise<{ error?: string }> {
  const supabase = await createSupabaseServerClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { error: 'Not authenticated' };

  const { data: member, error: memberError } = await supabase
    .from('profile_members')
    .insert({
      user_id: user.id,
      full_name: data.fullName,
      date_of_birth: data.dateOfBirth,
      state: data.state,
      zip_code: data.zipCode,
      is_primary: true,
    })
    .select('id')
    .single();

  if (memberError) return { error: memberError.message };

  // Pre-fill known plan names for government/standardised payer types so the
  // user doesn't have to type them. Commercial is left blank — too many plans.
  const planDefaults: Record<string, { payerName: string; planName: string }> =
    {
      medicare: { payerName: 'Medicare', planName: 'Medicare Fee-for-Service' },
      medicaid: { payerName: 'Medicaid', planName: 'State Medicaid' },
      tricare: { payerName: 'TRICARE', planName: 'TRICARE Standard' },
      self_pay: { payerName: 'Self-Pay', planName: 'Self-Pay' },
    };

  const defaults = planDefaults[data.insuranceType];
  if (defaults) {
    await supabase.from('insurance_plans').insert({
      profile_member_id: member.id,
      payer_name: defaults.payerName,
      plan_name: defaults.planName,
      plan_type: data.insuranceType,
      is_primary_plan: true,
    });
  }

  const validLocale = (LOCALES as readonly string[]).includes(data.locale)
    ? data.locale
    : 'en';
  const cookieStore = await cookies();
  cookieStore.set('cb_locale', validLocale, {
    maxAge: 60 * 60 * 24 * 365,
    path: '/',
    sameSite: 'lax',
  });

  return {};
}

// Updates the user's preferred locale cookie — called from the profile language switcher.
export async function updateLocale(locale: string): Promise<void> {
  const validLocale = (LOCALES as readonly string[]).includes(locale) ? locale : 'en';
  const cookieStore = await cookies();
  cookieStore.set('cb_locale', validLocale, {
    maxAge: 60 * 60 * 24 * 365,
    path: '/',
    sameSite: 'lax',
  });
}
