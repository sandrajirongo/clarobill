import Anthropic from '@anthropic-ai/sdk';
import { NextResponse } from 'next/server';
import { getAuthenticatedUser } from '@/lib/supabase/server';
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

const EXTRACT_PROMPT = `
Extract all insurance card fields from this image.
Return ONLY a JSON object with these exact keys:

- payer_name: The INSURANCE COMPANY brand name (e.g. "Aetna", "Blue Cross Blue Shield", "UnitedHealthcare", "Cigna", "Humana"). This is the health insurer that pays claims — NOT the employer, group sponsor, or company name printed as the group. Look for the insurance brand logo or brand mark. (string or null)
- plan_name: plan or product name such as "Choice POS I", "HMO Gold", "PPO Plus" (string or null)
- member_id: The COMPLETE member or subscriber ID exactly as printed on the card, including any letter prefix or internal spaces (e.g. "W2607 46886", "XYZ123456789"). Do NOT truncate, strip letter prefixes, or remove spaces. Copy character-for-character. (string or null)
- group_id: group number printed on the card (string or null)
- plan_type: one of "commercial", "medicare", "medicaid", "tricare", "self_pay"
- rx_bin: pharmacy BIN number, labeled BIN or RxBIN (string or null)
- rx_pcn: pharmacy PCN number (string or null)
- rx_group: pharmacy group number, distinct from medical group number (string or null)
- confident: true if you could clearly read payer_name or member_id, false otherwise
- note: brief note if confidence is low, null otherwise

Return only the JSON object. No markdown, no explanation.`.trim();

// POST /api/insurance-card/extract
// Accepts a multipart/form-data image, calls Claude Sonnet vision directly,
// and returns structured insurance plan fields. Stateless — image is never stored.
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

  // Check size via the File metadata before allocating the full buffer — arrayBuffer()
  // reads the entire file into memory, so we reject oversized files first.
  if (imageFile.size > MAX_BYTES) {
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Image too large.', step: 'validate' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 413 }
    );
  }

  const imageBytes = await imageFile.arrayBuffer();

  const base64 = Buffer.from(imageBytes).toString('base64');
  const mediaType = imageFile.type as 'image/jpeg' | 'image/png' | 'image/webp';

  const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

  let rawText: string;
  try {
    const response = await client.messages.create({
      model: 'claude-sonnet-4-6',
      max_tokens: 400,
      messages: [{
        role: 'user',
        content: [
          { type: 'image', source: { type: 'base64', media_type: mediaType, data: base64 } },
          { type: 'text', text: EXTRACT_PROMPT },
        ],
      }],
    });
    const block = response.content[0] ?? null;
    if (!block || block.type !== 'text') throw new Error('unexpected block type');
    rawText = block.text.trim();
  } catch {
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Vision call failed.', step: 'extract' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 502 }
    );
  }

  // Strip markdown code fences if the model wraps the JSON
  if (rawText.startsWith('```')) {
    rawText = rawText.split('\n').slice(1).join('\n').split('```')[0]?.trim() ?? rawText;
  }

  let data: Record<string, unknown>;
  try {
    data = JSON.parse(rawText) as Record<string, unknown>;
  } catch {
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Parse failed.', step: 'parse' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 502 }
    );
  }

  const str = (key: string): string | null => {
    const v = data[key];
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
    confident: Boolean(data['confident']),
    note:      str('note'),
  } satisfies InsuranceCardExtraction);
}
