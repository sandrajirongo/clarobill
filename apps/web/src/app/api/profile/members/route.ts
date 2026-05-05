import { NextResponse } from 'next/server';
import { createSupabaseServerClient, getAuthenticatedUser } from '@/lib/supabase/server';
import type { ApiErrorResponse } from '@clarobill/shared';
import { mapProfileMember, mapProfileMemberWithPlans } from '@/lib/api/mappers';

// GET /api/profile/members
// Returns all profile members for the authenticated user, each with their insurance plans.
export async function GET(): Promise<NextResponse> {
  const user = await getAuthenticatedUser();
  if (!user) {
    return NextResponse.json(
      { error: { code: 'UNAUTHORIZED', detail: 'Authentication required.' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 401 }
    );
  }

  const supabase = await createSupabaseServerClient();

  const { data: members, error } = await supabase
    .from('profile_members')
    .select(`
      id, full_name, date_of_birth, state, county, zip_code, is_primary, created_at,
      insurance_plans (
        id, profile_member_id, payer_name, plan_name, member_id, plan_type, is_primary_plan, created_at
      )
    `)
    .eq('user_id', user.id)
    .order('is_primary', { ascending: false })
    .order('created_at', { ascending: true });

  if (error) {
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Failed to load profile members.', step: 'fetch' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 500 }
    );
  }

  // M10: map snake_case Supabase rows to the camelCase shared shape so
  // consumers don't redeclare a parallel snake_case type.
  return NextResponse.json({ members: (members ?? []).map(mapProfileMemberWithPlans) });
}

// POST /api/profile/members
// Creates a new profile member for the authenticated user.
export async function POST(request: Request): Promise<NextResponse> {
  const user = await getAuthenticatedUser();
  if (!user) {
    return NextResponse.json(
      { error: { code: 'UNAUTHORIZED', detail: 'Authentication required.' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 401 }
    );
  }

  const body = await request.json() as {
    fullName: string;
    dateOfBirth: string;
    state?: string | null;
    county?: string | null;
    zipCode?: string | null;
    isPrimary?: boolean;
  };

  if (!body.fullName?.trim() || !body.dateOfBirth) {
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Full name and date of birth are required.', step: 'validate' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 400 }
    );
  }

  const supabase = await createSupabaseServerClient();

  // If setting as primary, unset any existing primary first
  if (body.isPrimary) {
    await supabase
      .from('profile_members')
      .update({ is_primary: false })
      .eq('user_id', user.id)
      .eq('is_primary', true);
  }

  const { data: member, error } = await supabase
    .from('profile_members')
    .insert({
      user_id: user.id,
      full_name: body.fullName.trim(),
      date_of_birth: body.dateOfBirth,
      state: body.state ?? null,
      county: body.county ?? null,
      zip_code: body.zipCode ?? null,
      is_primary: body.isPrimary ?? false,
    })
    .select()
    .single();

  if (error || !member) {
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Failed to create profile member.', step: 'insert' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 500 }
    );
  }

  return NextResponse.json({ member: mapProfileMember(member) }, { status: 201 });
}
