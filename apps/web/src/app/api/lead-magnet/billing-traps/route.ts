import { NextResponse } from 'next/server';
import { z } from 'zod';
import { captureServerEvent } from '@/lib/analytics-server';

const LOOPS_API = 'https://app.loops.so/api/v1';
const GUIDE_URL = `${process.env.NEXT_PUBLIC_SITE_URL ?? 'https://www.clarobill.com'}/billing-traps-guide/guide`;

const RequestSchema = z.object({
  email: z.string().email(),
});

type SuccessResponse = { ok: true };
type ErrorResponse = { error: { code: string; detail: string } };

export async function POST(
  request: Request
): Promise<NextResponse<SuccessResponse | ErrorResponse>> {
  const apiKey = process.env.LOOPS_API_KEY;
  const transactionalId = process.env.LOOPS_BILLING_TRAPS_EMAIL_ID;

  if (!apiKey || !transactionalId) {
    return NextResponse.json(
      { error: { code: 'CONFIG_ERROR', detail: 'Email service is not configured.' } },
      { status: 500 }
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

  const parsed = RequestSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: { code: 'BAD_REQUEST', detail: 'A valid email address is required.' } },
      { status: 400 }
    );
  }

  const { email } = parsed.data;
  const loopsHeaders = {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${apiKey}`,
  };

  // Add contact to Loops (409 = already exists, treat as success)
  const contactRes = await fetch(`${LOOPS_API}/contacts/create`, {
    method: 'POST',
    headers: loopsHeaders,
    body: JSON.stringify({ email, source: 'billing-traps-guide', subscribed: true }),
  });

  if (!contactRes.ok && contactRes.status !== 409) {
    return NextResponse.json(
      { error: { code: 'EMAIL_FAILED', detail: 'Could not subscribe. Please try again.' } },
      { status: 502 }
    );
  }

  // Send transactional email containing the guide link
  const emailRes = await fetch(`${LOOPS_API}/transactional`, {
    method: 'POST',
    headers: loopsHeaders,
    body: JSON.stringify({
      transactionalId,
      email,
      dataVariables: { guideUrl: GUIDE_URL },
    }),
  });

  if (!emailRes.ok) {
    return NextResponse.json(
      { error: { code: 'EMAIL_FAILED', detail: 'Could not send the guide. Please try again.' } },
      { status: 502 }
    );
  }

  void captureServerEvent('anonymous', 'lead_magnet_requested', {
    $process_person_profile: false,
    guide: 'billing_traps',
  });

  return NextResponse.json({ ok: true });
}
