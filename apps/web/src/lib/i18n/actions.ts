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
  // Optional scanned details from the card scanner confirmation step
  scannedPayerName?: string | null;
  scannedPlanName?: string | null;
  scannedMemberId?: string | null;
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

  // Pre-fill known payer/plan names for government plan types; commercial is
  // left blank since there are too many plans to enumerate.
  const planDefaults: Record<string, { payerName: string; planName: string }> = {
    medicare: { payerName: 'Medicare', planName: 'Medicare Fee-for-Service' },
    medicaid: { payerName: 'Medicaid', planName: 'State Medicaid' },
    tricare:  { payerName: 'TRICARE',  planName: 'TRICARE Standard' },
    self_pay: { payerName: 'Self-Pay', planName: 'Self-Pay' },
  };

  // Scanned details override defaults; for commercial, scanned data is the only source.
  const defaults = planDefaults[data.insuranceType];
  const resolvedPayerName = data.scannedPayerName ?? defaults?.payerName ?? null;
  const resolvedPlanName  = data.scannedPlanName  ?? defaults?.planName  ?? null;

  if (resolvedPayerName || resolvedPlanName) {
    await supabase.from('insurance_plans').insert({
      profile_member_id: member.id,
      payer_name:      resolvedPayerName ?? 'Unknown',
      plan_name:       resolvedPlanName  ?? 'Unknown',
      plan_type:       data.insuranceType || 'commercial',
      member_id:       data.scannedMemberId ?? null,
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
