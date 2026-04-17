import { NextResponse } from 'next/server';
import { getAuthenticatedUser } from '@/lib/supabase/server';
import { getCloudRunIdToken } from '@/lib/gcp-auth';
import type { ApiErrorResponse } from '@clarobill/shared';

export interface InsuranceCardExtraction {
  payerName:  string | null;
  planName:   string | null;
  memberId:   string | null;
  groupId:    string | null;
  planType:   string | null;
  confident:  boolean;
  note:       string | null;
}

// POST /api/insurance-card/extract
// Accepts a multipart/form-data image, forwards to the engine for Claude vision
// extraction, and returns structured insurance plan fields.
// The image is never stored — this endpoint is stateless.
export async function POST(
  request: Request
): Promise<NextResponse<InsuranceCardExtraction | ApiErrorResponse>> {
  const user = await getAuthenticatedUser();
  if (!user) {
    return NextResponse.json(
      { error: { code: 'UNAUTHORIZED', detail: 'Authentication required.' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 401 }
    );
  }

  // Forward the raw multipart body straight to the engine — no repacking needed
  const contentType = request.headers.get('content-type') ?? '';
  if (!contentType.startsWith('multipart/form-data')) {
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Expected multipart/form-data with an image field.', step: 'card_extract_validate' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 400 }
    );
  }

  const engineUrl = process.env.ENGINE_URL ?? 'http://localhost:8000';
  const idToken = await getCloudRunIdToken(engineUrl);

  const engineResponse = await fetch(`${engineUrl}/api/v1/insurance-card/extract`, {
    method: 'POST',
    headers: {
      'content-type': contentType,
      ...(idToken ? { 'Authorization': `Bearer ${idToken}` } : {}),
      ...(process.env.ENGINE_API_KEY ? { 'X-Engine-Api-Key': process.env.ENGINE_API_KEY } : {}),
    },
    body: request.body,
    // @ts-expect-error — Next.js requires this for streaming request bodies
    duplex: 'half',
  });

  if (!engineResponse.ok) {
    const detail = engineResponse.status === 415
      ? 'Unsupported image type. Use JPEG, PNG, or WebP.'
      : engineResponse.status === 413
      ? 'Image is too large. Please use a photo under 5 MB.'
      : 'Could not read the card. Please try again or fill in the fields manually.';

    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail, step: 'card_extract_engine' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: engineResponse.status >= 500 ? 502 : engineResponse.status }
    );
  }

  // Snake_case → camelCase conversion from engine response
  const raw = await engineResponse.json() as {
    payer_name: string | null;
    plan_name: string | null;
    member_id: string | null;
    group_id: string | null;
    plan_type: string | null;
    confident: boolean;
    note: string | null;
  };

  return NextResponse.json({
    payerName: raw.payer_name,
    planName:  raw.plan_name,
    memberId:  raw.member_id,
    groupId:   raw.group_id,
    planType:  raw.plan_type,
    confident: raw.confident,
    note:      raw.note,
  } satisfies InsuranceCardExtraction);
}
