import { NextResponse } from 'next/server';
import { createSupabaseServerClient, getAuthenticatedUser } from '@/lib/supabase/server';
import type { ApiErrorResponse } from '@clarobill/shared';

// PATCH /api/profile/plans/[planId]
// Updates an insurance plan. RLS ensures the plan's member belongs to the user.
export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ planId: string }> }
): Promise<NextResponse> {
  const user = await getAuthenticatedUser();
  if (!user) {
    return NextResponse.json(
      { error: { code: 'UNAUTHORIZED', detail: 'Authentication required.' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 401 }
    );
  }

  const { planId } = await params;
  const body = await request.json() as {
    payerName?: string;
    planName?: string;
    memberId?: string | null;
    planType?: string;
    isPrimaryPlan?: boolean;
  };

  const supabase = await createSupabaseServerClient();

  const updates: Record<string, unknown> = {};
  if (body.payerName !== undefined) updates.payer_name = body.payerName.trim();
  if (body.planName !== undefined) updates.plan_name = body.planName.trim();
  if (body.memberId !== undefined) updates.member_id = body.memberId;
  if (body.planType !== undefined) updates.plan_type = body.planType;
  if (body.isPrimaryPlan !== undefined) updates.is_primary_plan = body.isPrimaryPlan;

  if (Object.keys(updates).length === 0) {
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'No fields to update.', step: 'update' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 400 }
    );
  }

  // When promoting a plan to primary, demote any other primary plan for the same member first.
  // Fetch member_id from the plan being updated so we don't rely on the client sending it.
  if (body.isPrimaryPlan) {
    const { data: existing } = await supabase
      .from('insurance_plans')
      .select('member_id')
      .eq('id', planId)
      .single();
    if (existing?.member_id) {
      await supabase
        .from('insurance_plans')
        .update({ is_primary_plan: false })
        .eq('member_id', existing.member_id)
        .eq('is_primary_plan', true)
        .neq('id', planId);
    }
  }

  const { data: plan, error } = await supabase
    .from('insurance_plans')
    .update(updates)
    .eq('id', planId)
    .select()
    .single();

  if (error || !plan) {
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Plan not found or update failed.', step: 'update' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 404 }
    );
  }

  return NextResponse.json({ plan });
}

// DELETE /api/profile/plans/[planId]
export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ planId: string }> }
): Promise<NextResponse> {
  const user = await getAuthenticatedUser();
  if (!user) {
    return NextResponse.json(
      { error: { code: 'UNAUTHORIZED', detail: 'Authentication required.' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 401 }
    );
  }

  const { planId } = await params;
  const supabase = await createSupabaseServerClient();

  const { error } = await supabase
    .from('insurance_plans')
    .delete()
    .eq('id', planId);

  if (error) {
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Failed to delete plan.', step: 'delete' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 500 }
    );
  }

  return NextResponse.json({ deleted: true });
}
