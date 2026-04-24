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
  rxBin:      string | null;
  rxPcn:      string | null;
  rxGroup:    string | null;
  confident:  boolean;
  note:       string | null;
}

const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp'] as const;
const MAX_BYTES = 10 * 1024 * 1024;

// POST /api/insurance-card/extract
// Authenticates the user, validates the image, then forwards to the engine.
// The engine handles AI provider selection (Gemini primary, Claude fallback).
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

  let imageFile: File;
  try {
    const formData = await request.formData();
    const entry = formData.get('image');
    if (!(entry instanceof File)) throw new Error('missing');
    imageFile = entry;
  } catch {
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Expected multipart/form-data with an image field.', step: 'validate' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 400 }
    );
  }

  if (!ALLOWED_TYPES.includes(imageFile.type as typeof ALLOWED_TYPES[number])) {
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Unsupported type.', step: 'validate' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 415 }
    );
  }

  if (imageFile.size > MAX_BYTES) {
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Image too large.', step: 'validate' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 413 }
    );
  }

  // Forward to engine — engine handles Gemini primary / Claude fallback
  const engineUrl = process.env.ENGINE_URL ?? 'http://localhost:8000';
  const idToken = await getCloudRunIdToken(engineUrl);

  const forwardForm = new FormData();
  forwardForm.append('image', imageFile);

  let engineResponse: Response;
  try {
    engineResponse = await fetch(`${engineUrl}/insurance-card/extract`, {
      method: 'POST',
      headers: {
        ...(idToken ? { 'Authorization': `Bearer ${idToken}` } : {}),
        ...(process.env.ENGINE_API_KEY ? { 'X-Engine-Api-Key': process.env.ENGINE_API_KEY } : {}),
      },
      body: forwardForm,
    });
  } catch (err) {
    console.error('[insurance-card] Engine unreachable:', err);
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Card extraction service unavailable. Please try again.', step: 'extract' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 502 }
    );
  }

  if (!engineResponse.ok) {
    console.error('[insurance-card] Engine returned', engineResponse.status);
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Could not read the card. Ensure it is well-lit and try again.', step: 'extract' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 502 }
    );
  }

  // Engine returns snake_case — map to camelCase for the frontend
  const raw = await engineResponse.json() as Record<string, unknown>;
  const str = (key: string): string | null => {
    const v = raw[key];
    return typeof v === 'string' && v ? v : null;
  };

  return NextResponse.json({
    payerName: str('payer_name'),
    planName:  str('plan_name'),
    memberId:  str('member_id'),
    groupId:   str('group_id'),
    planType:  str('plan_type') ?? 'commercial',
    rxBin:     str('rx_bin'),
    rxPcn:     str('rx_pcn'),
    rxGroup:   str('rx_group'),
    confident: Boolean(raw['confident']),
    note:      str('note'),
  } satisfies InsuranceCardExtraction);
}
