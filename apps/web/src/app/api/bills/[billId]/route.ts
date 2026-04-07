import { NextResponse } from 'next/server';
import { createSupabaseServerClient, getAuthenticatedUser } from '@/lib/supabase/server';
import type { Bill, ApiErrorResponse } from '@clarobill/shared';

// GET /api/bills/[billId]
// Returns the bill status — used by the polling loop in useBillUpload.
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ billId: string }> }
): Promise<NextResponse<Pick<Bill, 'id' | 'status'> | ApiErrorResponse>> {
  const user = await getAuthenticatedUser();
  if (!user) {
    return NextResponse.json(
      { error: { code: 'UNAUTHORIZED', detail: 'Authentication required.' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 401 }
    );
  }

  const { billId } = await params;
  const supabase = await createSupabaseServerClient();

  // RLS ensures users can only fetch their own bills
  const { data: bill, error } = await supabase
    .from('bills')
    .select('id, status')
    .eq('id', billId)
    .single();

  if (error || !bill) {
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Bill not found.', step: 'fetch' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 404 }
    );
  }

  return NextResponse.json({ id: bill.id, status: bill.status });
}
