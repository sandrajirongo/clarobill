import { NextResponse } from 'next/server';
import { getAuthenticatedUser, createSupabaseServiceClient } from '@/lib/supabase/server';

// DELETE /api/user
// Permanently deletes the authenticated user's account and all associated data.
// Deletion order: payments → bills (cascades line_items + analysis_results) → auth user
export async function DELETE(): Promise<NextResponse> {
  const user = await getAuthenticatedUser();
  if (!user) {
    return NextResponse.json({ error: 'Authentication required.' }, { status: 401 });
  }

  const service = createSupabaseServiceClient();

  // Bills have ON DELETE CASCADE to line_items and analysis_results.
  // Payments reference bills with ON DELETE SET NULL (migration 20260408000001),
  // so we can delete bills first then the auth user.
  const { error: billsError } = await service
    .from('bills')
    .delete()
    .eq('user_id', user.id);

  if (billsError) {
    console.error('[delete-account] Failed to delete bills for user %s: %s', user.id, billsError.message);
    return NextResponse.json({ error: 'Failed to delete account data.' }, { status: 500 });
  }

  const { error: authError } = await service.auth.admin.deleteUser(user.id);
  if (authError) {
    console.error('[delete-account] Failed to delete auth user %s: %s', user.id, authError.message);
    return NextResponse.json({ error: 'Failed to delete account.' }, { status: 500 });
  }

  return NextResponse.json({ success: true });
}
