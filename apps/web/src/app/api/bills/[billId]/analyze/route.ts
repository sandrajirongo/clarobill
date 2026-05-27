import { NextResponse } from 'next/server';
import { createSupabaseServerClient, getAuthenticatedUser } from '@/lib/supabase/server';
import { getCloudRunIdToken } from '@/lib/gcp-auth';
import type { ApiErrorResponse } from '@clarobill/shared';

// POST /api/bills/[billId]/analyze
// Forwards the analysis request to the FastAPI engine.
// The engine handles OCR, parsing, rules engine, and AI analysis (Gemini primary, Claude fallback).
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
  const supabase = await createSupabaseServerClient();

  // Optional geography for GPCI-adjusted rate benchmarking
  let state: string | null = null;
  let county: string | null = null;
  try {
    const body = await request.json() as { state?: string; county?: string };
    state = body.state ?? null;
    county = body.county ?? null;
  } catch {
    // No body or non-JSON body — geography defaults to national rates
  }

  // Confirm bill ownership before forwarding to engine
  const { data: bill, error } = await supabase
    .from('bills')
    .select('id, status, file_path')
    .eq('id', billId)
    .single();

  if (error || !bill) {
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Bill not found.', step: 'preflight' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 404 }
    );
  }

  if (bill.status !== 'uploading') {
    // Idempotent — if already analyzing or complete, don't restart
    return NextResponse.json({ accepted: true });
  }

  if (!bill.file_path) {
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'The uploaded bill file has been removed per our 60-day retention policy and can no longer be analyzed. Please upload the bill again.', step: 'preflight' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 410 }
    );
  }

  // Forward to Python engine — fire and forget (engine updates bill status async)
  const engineUrl = process.env.ENGINE_URL ?? 'http://localhost:8000';

  // Vercel → Cloud Run via Workload Identity Federation. If WIF env is
  // misconfigured the helper throws; match the verify route's pattern and
  // continue without an auth header so the engine can reject with a clear
  // 401/403 instead of bubbling a generic 500 up to clients.
  let idToken: string | null = null;
  try {
    idToken = await getCloudRunIdToken(engineUrl);
  } catch (e) {
    console.error('[analyze] getCloudRunIdToken failed', { billId, error: e instanceof Error ? e.message : e });
  }

  let engineResponse: Response;
  try {
    engineResponse = await fetch(`${engineUrl}/api/v1/bills/${billId}/analyze`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(idToken ? { 'Authorization': `Bearer ${idToken}` } : {}),
        ...(process.env.ENGINE_API_KEY ? { 'X-Engine-Api-Key': process.env.ENGINE_API_KEY } : {}),
      },
      body: JSON.stringify({ bill_id: billId, file_path: bill.file_path, user_id: user.id, state, county }),
    });
  } catch (e) {
    // Network-level failure (engine unreachable, DNS failure, etc.). Return a
    // structured 502 so the mobile/web client can surface a useful message
    // instead of "500 internal server error".
    console.error('[analyze] Engine fetch failed', { billId, error: e instanceof Error ? e.message : e });
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Analysis service unreachable. Please try again.', step: 'engine_fetch' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 502 }
    );
  }

  if (!engineResponse.ok) {
    const engineBody = await engineResponse.text().catch(() => '');
    console.error('[analyze] Engine rejected analysis request', {
      billId,
      status: engineResponse.status,
      body: engineBody.slice(0, 500),
    });
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: `Analysis service rejected the request (${engineResponse.status}). Please try again.`, step: 'engine_dispatch' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 502 }
    );
  }

  return NextResponse.json({ accepted: true });
}
