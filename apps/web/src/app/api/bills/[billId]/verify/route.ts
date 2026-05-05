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

  // Allow retry from 'failed' status — the user may have hit a transient engine error.
  // Any other status (ocr_processing, analyzing, complete) means analysis is already
  // in flight or done; return accepted idempotently without re-triggering.
  if (bill.status !== 'uploading' && bill.status !== 'failed') {
    return NextResponse.json({ accepted: true });
  }

  if (!bill.file_path) {
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'The uploaded bill file has been removed per our 60-day retention policy and can no longer be analyzed. Please upload the bill again.', step: 'verify_bill' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 410 }
    );
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

  // Look up the confirmed insurance plan to get plan_type for NCCI edit selection.
  // Not a hard failure — plan_type is optional; engine falls back to medicare edits.
  const { data: insurancePlan } = await supabase
    .from('insurance_plans')
    .select('plan_type')
    .eq('profile_member_id', body.profileMemberId)
    .eq('payer_name', body.payerName.trim())
    .eq('plan_name', body.planName.trim())
    .limit(1)
    .single();

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

  let idToken: string | null = null;
  try {
    idToken = await getCloudRunIdToken(engineUrl);
    console.info('[verify] WIF token obtained', { billId, hasToken: !!idToken });
  } catch (authErr) {
    console.error('[verify] WIF auth failed — falling back to no token', { billId, error: String(authErr) });
    // Don't abort — let the engine reject with 401/403 so we get a clear status
  }

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
      // Engine validates state against CMS uppercase pattern (^[A-Z][A-Z\s]{1,49}$)
      // and zip_code against ^\d{5}$. Normalize at the boundary so user-entered
      // mixed-case values (e.g. "California") don't produce 422s.
      state: member.state?.trim().toUpperCase() ?? null,
      county: member.county?.trim() || null,
      zip_code: /^\d{5}/.test(member.zip_code ?? '') ? (member.zip_code as string).slice(0, 5) : null,
      payer_name: body.payerName.trim(),
      plan_name: body.planName.trim(),
      plan_type: insurancePlan?.plan_type ?? null,
    }),
  });

  if (!engineResponse.ok) {
    const engineBody = await engineResponse.text().catch(() => '<unreadable>');
    console.error('[verify] Engine rejected analysis request', {
      billId,
      status: engineResponse.status,
      body: engineBody.slice(0, 500),
      hasIdToken: !!idToken,
      hasApiKey: !!process.env.ENGINE_API_KEY,
      engineUrl,
    });
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Analysis service unavailable. Please try again.', step: 'verify_engine' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 502 }
    );
  }

  return NextResponse.json({ accepted: true });
}
