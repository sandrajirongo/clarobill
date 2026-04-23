import { NextResponse } from 'next/server';
import { createSupabaseServerClient, getAuthenticatedUser } from '@/lib/supabase/server';
import type { ApiErrorResponse } from '@clarobill/shared';

// PATCH /api/profile/members/[memberId]
// Updates a profile member. RLS ensures the member belongs to the user.
export async function PATCH(
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
    fullName?: string;
    dateOfBirth?: string;
    state?: string | null;
    county?: string | null;
    zipCode?: string | null;
    isPrimary?: boolean;
  };

  const supabase = await createSupabaseServerClient();

  const updates: Record<string, unknown> = {};
  if (body.fullName !== undefined) updates.full_name = body.fullName.trim();
  if (body.dateOfBirth !== undefined) updates.date_of_birth = body.dateOfBirth;
  if (body.state !== undefined) updates.state = body.state;
  if (body.county !== undefined) updates.county = body.county;
  if (body.zipCode !== undefined) updates.zip_code = body.zipCode;
  if (body.isPrimary !== undefined) updates.is_primary = body.isPrimary;

  if (Object.keys(updates).length === 0) {
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'No fields to update.', step: 'update' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 400 }
    );
  }

  if (body.isPrimary) {
    await supabase
      .from('profile_members')
      .update({ is_primary: false })
      .eq('user_id', user.id)
      .eq('is_primary', true)
      .neq('id', memberId);
  }

  const { data: member, error } = await supabase
    .from('profile_members')
    .update(updates)
    .eq('id', memberId)
    .select()
    .single();

  if (error || !member) {
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Member not found or update failed.', step: 'update' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 404 }
    );
  }

  return NextResponse.json({ member });
}

// DELETE /api/profile/members/[memberId]
// Removes a profile member and all their insurance plans (cascaded by FK).
export async function DELETE(
  _request: Request,
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
  const supabase = await createSupabaseServerClient();

  const { error } = await supabase
    .from('profile_members')
    .delete()
    .eq('id', memberId);

  if (error) {
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Failed to delete member.', step: 'delete' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 500 }
    );
  }

  return NextResponse.json({ deleted: true });
}
