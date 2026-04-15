import { NextResponse } from 'next/server';
import { createSupabaseServerClient, getAuthenticatedUser } from '@/lib/supabase/server';
import { getCloudRunIdToken } from '@/lib/gcp-auth';
import type { ApiErrorResponse } from '@clarobill/shared';

// POST /api/bills/[billId]/analyze
// Forwards the analysis request to the FastAPI engine.
// The engine handles OCR, parsing, rules engine, and Claude AI analysis.
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

  // Forward to Python engine — fire and forget (engine updates bill status async)
  const engineUrl = process.env.ENGINE_URL ?? 'http://localhost:8000';
  const idToken = await getCloudRunIdToken(engineUrl);
  const engineResponse = await fetch(`${engineUrl}/api/v1/bills/${billId}/analyze`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(idToken ? { 'Authorization': `Bearer ${idToken}` } : {}),
      ...(process.env.ENGINE_API_KEY ? { 'X-Engine-Api-Key': process.env.ENGINE_API_KEY } : {}),
    },
    body: JSON.stringify({ bill_id: billId, file_path: bill.file_path, user_id: user.id, state, county }),
  });

  if (!engineResponse.ok) {
    console.error('[analyze] Engine rejected analysis request', { billId, status: engineResponse.status });
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Analysis service unavailable. Please try again.', step: 'engine_dispatch' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 502 }
    );
  }

  return NextResponse.json({ accepted: true });
}
