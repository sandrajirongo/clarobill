import { NextResponse } from 'next/server';
import { getAuthenticatedUser } from '@/lib/supabase/server';
import { getCloudRunIdToken } from '@/lib/gcp-auth';
import { InsuranceCardExtractionSchema, parseJsonResponse } from '@/lib/api/parsers';
import type { InsuranceCardExtraction } from '@/lib/api/parsers';
import type { ApiErrorResponse } from '@clarobill/shared';

// T3+T4 (Phase 8.1): the engine emits camelCase via alias_generator and the
// route parses through Zod rather than hand-translating each field. The old
// `as Record<string, unknown>` cast plus snake_case key reads + the
// silent `?? 'commercial'` default for plan_type all moved out — the
// engine and this route now share one schema source of truth.

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

  // Engine emits camelCase + closed-set planType via Pydantic
  // alias_generator. Parse through Zod so any drift (engine adds a field,
  // changes a nullability) fails loudly here, not later in the form.
  let parsed: InsuranceCardExtraction;
  try {
    parsed = await parseJsonResponse(engineResponse, InsuranceCardExtractionSchema);
  } catch (err) {
    console.error('[insurance-card] Engine response shape drift:', err);
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Could not parse card data. Please try again.', step: 'extract' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 502 }
    );
  }
  return NextResponse.json(parsed);
}
