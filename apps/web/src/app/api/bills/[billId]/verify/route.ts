import { NextResponse } from 'next/server';
import { createSupabaseServerClient, getAuthenticatedUser } from '@/lib/supabase/server';
import { getCloudRunIdToken } from '@/lib/gcp-auth';
import type { ApiErrorResponse } from '@clarobill/shared';

interface VerifyBody {
  profileMemberId: string;
  payerName: string;
  planName: string;
  hospitalName?: string | null;
}

// POST /api/bills/[billId]/verify
// Saves user-confirmed context to the bill record, then triggers engine analysis.
// Called by the verification step after the user selects member + insurance plan.
export async function POST(
  request: Request,
  { params }: { params: Promise<{ billId: string }> }
): Promise<NextResponse<{ accepted: true } | ApiErrorResponse>> {
  const user = await getAuthenticatedUser();
  if (!user) {
    return NextResponse.json(
      { error: { code: 'UNAUTHORIZED', detail: 'Authentication required.' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 401 }
    );
  }

  const { billId } = await params;
  const body = await request.json() as VerifyBody;

  if (!body.profileMemberId || !body.payerName?.trim() || !body.planName?.trim()) {
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Member, insurer, and plan are required to run analysis.', step: 'verify_validate' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 400 }
    );
  }

  const supabase = await createSupabaseServerClient();

  // Verify bill ownership
  const { data: bill, error: billError } = await supabase
    .from('bills')
    .select('id, status, file_path, hospital_npi, hospital_name')
    .eq('id', billId)
    .single();

  if (billError || !bill) {
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Bill not found.', step: 'verify_bill' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 404 }
    );
  }

  if (bill.status !== 'uploading') {
    // Already verified or in progress — idempotent
    return NextResponse.json({ accepted: true });
  }

  // Load the selected profile member to get their state/county/zip for rate lookup
  const { data: member } = await supabase
    .from('profile_members')
    .select('id, state, county, zip_code')
    .eq('id', body.profileMemberId)
    .eq('user_id', user.id)
    .single();

  if (!member) {
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Profile member not found.', step: 'verify_member' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 404 }
    );
  }

  // Persist confirmed context to the bill record.
  // confirmed_at marks that the user completed verification — used for tracking.
  await supabase
    .from('bills')
    .update({
      profile_member_id: body.profileMemberId,
      payer_name: body.payerName.trim(),
      plan_name: body.planName.trim(),
      // If user provided a hospital name override, use it; otherwise keep OCR-extracted value
      hospital_name: body.hospitalName?.trim() || bill.hospital_name || null,
      confirmed_at: new Date().toISOString(),
    })
    .eq('id', billId);

  // Forward to engine with all confirmed context
  const engineUrl = process.env.ENGINE_URL ?? 'http://localhost:8000';
  const idToken = await getCloudRunIdToken(engineUrl);

  const engineResponse = await fetch(`${engineUrl}/api/v1/bills/${billId}/analyze`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(idToken ? { 'Authorization': `Bearer ${idToken}` } : {}),
      ...(process.env.ENGINE_API_KEY ? { 'X-Engine-Api-Key': process.env.ENGINE_API_KEY } : {}),
    },
    body: JSON.stringify({
      bill_id: billId,
      file_path: bill.file_path,
      user_id: user.id,
      state: member.state ?? null,
      county: member.county ?? null,
      zip_code: member.zip_code ?? null,
      payer_name: body.payerName.trim(),
      plan_name: body.planName.trim(),
    }),
  });

  if (!engineResponse.ok) {
    console.error('[verify] Engine rejected analysis request', { billId, status: engineResponse.status });
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Analysis service unavailable. Please try again.', step: 'verify_engine' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 502 }
    );
  }

  return NextResponse.json({ accepted: true });
}
