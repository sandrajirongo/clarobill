import { NextResponse } from 'next/server';
import { createSupabaseServerClient, getAuthenticatedUser } from '@/lib/supabase/server';
import type { ApiErrorResponse } from '@clarobill/shared';

// POST /api/profile/members/[memberId]/plans
// Adds an insurance plan to a profile member.
export async function POST(
  request: Request,
  { params }: { params: Promise<{ memberId: string }> }
): Promise<NextResponse> {
  const user = await getAuthenticatedUser();
  if (!user) {
    return NextResponse.json(
      { error: { code: 'UNAUTHORIZED', detail: 'Authentication required.' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 401 }
    );
  }

  const { memberId } = await params;
  const body = await request.json() as {
    payerName: string;
    planName: string;
    memberId?: string | null;
    planType?: string;
    isPrimaryPlan?: boolean;
  };

  if (!body.payerName?.trim() || !body.planName?.trim()) {
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Payer name and plan name are required.', step: 'validate' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 400 }
    );
  }

  const supabase = await createSupabaseServerClient();

  // Verify the member belongs to this user (RLS covers DB, but let's be explicit)
  const { data: member } = await supabase
    .from('profile_members')
    .select('id')
    .eq('id', memberId)
    .eq('user_id', user.id)
    .single();

  if (!member) {
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Member not found.', step: 'ownership' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 404 }
    );
  }

  const { data: plan, error } = await supabase
    .from('insurance_plans')
    .insert({
      profile_member_id: memberId,
      payer_name: body.payerName.trim(),
      plan_name: body.planName.trim(),
      member_id: body.memberId ?? null,
      plan_type: body.planType ?? 'commercial',
      is_primary_plan: body.isPrimaryPlan ?? false,
    })
    .select()
    .single();

  if (error || !plan) {
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Failed to add insurance plan.', step: 'insert' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 500 }
    );
  }

  return NextResponse.json({ plan }, { status: 201 });
}
