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
    payerName?: string | null;
    planName?: string | null;
    memberId?: string | null;
    planType?: string;
    isPrimaryPlan?: boolean;
  };

  // Government programs don't have a distinct insurer name — use the program name
  // as the default so payer_name/plan_name stay non-null in the DB.
  const PLAN_DEFAULTS: Record<string, { payer: string; plan: string }> = {
    medicare: { payer: 'Medicare',  plan: 'Medicare Fee-for-Service' },
    medicaid: { payer: 'Medicaid',  plan: 'State Medicaid'           },
    tricare:  { payer: 'TRICARE',   plan: 'TRICARE Standard'         },
    self_pay: { payer: 'Self-Pay',  plan: 'Self-Pay'                 },
  };
  const planType = body.planType ?? 'commercial';
  const defaults = PLAN_DEFAULTS[planType];
  const payerName = body.payerName?.trim() || defaults?.payer || '';
  const planName  = body.planName?.trim()  || defaults?.plan  || '';

  if (!payerName || !planName) {
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Insurer name and plan name are required.', step: 'validate' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
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

  // If this plan is being set as primary, clear the flag on all other plans for
  // this member first so only one plan can be primary at a time.
  if (body.isPrimaryPlan) {
    await supabase
      .from('insurance_plans')
      .update({ is_primary_plan: false })
      .eq('profile_member_id', memberId);
  }

  const { data: plan, error } = await supabase
    .from('insurance_plans')
    .insert({
      profile_member_id: memberId,
      payer_name: payerName,
      plan_name: planName,
      member_id: body.memberId ?? null,
      plan_type: planType,
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
