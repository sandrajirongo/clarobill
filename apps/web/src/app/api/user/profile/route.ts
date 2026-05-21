import { NextResponse } from 'next/server';
import { z } from 'zod';
import { getAuthenticatedUser, createSupabaseServerClient } from '@/lib/supabase/server';
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

  const supabase = await createSupabaseServerClient();
  const { error } = await supabase
    .from('user_profiles')
    .update({
      first_name: parsed.data.first_name,
      last_name: parsed.data.last_name,
    })
    .eq('id', user.id);

  if (error) {
    console.error('[profile PATCH] update error', { code: error.code, message: error.message, hint: error.hint, userId: user.id });
    return NextResponse.json(
      { error: { code: 'DB_ERROR', detail: 'Unable to save profile. Please try again.' } },
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
