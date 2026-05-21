import { NextResponse } from 'next/server';
import { z } from 'zod';
import { getAuthenticatedUser, createSupabaseServiceClient } from '@/lib/supabase/server';
import { updateLoopsContact } from '@/lib/loops';

const PatchSchema = z.object({
  first_name: z.string().max(100).nullable(),
  last_name: z.string().max(100).nullable(),
});

type SuccessResponse = { ok: true };
type ErrorResponse = { error: { code: string; detail: string } };

// PATCH /api/user/profile
// Updates first_name and last_name on the authenticated user's profile row.
export async function PATCH(
  request: Request
): Promise<NextResponse<SuccessResponse | ErrorResponse>> {
  const user = await getAuthenticatedUser();
  if (!user) {
    return NextResponse.json(
      { error: { code: 'UNAUTHORIZED', detail: 'Authentication required.' } },
      { status: 401 }
    );
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { error: { code: 'BAD_REQUEST', detail: 'Invalid request body.' } },
      { status: 400 }
    );
  }

  const parsed = PatchSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: { code: 'BAD_REQUEST', detail: 'Invalid name values.' } },
      { status: 400 }
    );
  }

  // Use an RPC instead of a direct REST update. PostgREST caches column schemas
  // at startup and does not automatically reload when columns are added via
  // ALTER TABLE — the RPC bypasses that cache entirely.
  const supabase = createSupabaseServiceClient();
  const { error } = await supabase.rpc('update_user_profile_name', {
    p_user_id:    user.id,
    p_first_name: parsed.data.first_name,
    p_last_name:  parsed.data.last_name,
  });

  if (error) {
    console.error('[user-profile] RPC failed for user %s: %s', user.id, error.message);
    return NextResponse.json(
      { error: { code: 'DB_ERROR', detail: 'Could not save profile. Please try again.' } },
      { status: 500 }
    );
  }

  if (user.email) {
    const loopsProps: Record<string, string> = {};
    if (parsed.data.first_name) loopsProps['firstName'] = parsed.data.first_name;
    if (parsed.data.last_name) loopsProps['lastName'] = parsed.data.last_name;
    if (Object.keys(loopsProps).length > 0) {
      void updateLoopsContact(user.email, loopsProps);
    }
  }

  return NextResponse.json({ ok: true });
}
