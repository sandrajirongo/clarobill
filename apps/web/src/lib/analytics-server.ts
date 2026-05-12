// Server-side PostHog capture via HTTP API. Import only in Server Components and API routes.
// Uses the same project token as the client SDK — PostHog API keys are write-only.
// All calls are fire-and-forget: analytics must never block or break a request.

const POSTHOG_HOST = process.env.NEXT_PUBLIC_POSTHOG_HOST ?? 'https://us.i.posthog.com';

export async function captureServerEvent(
  distinctId: string,
  event: string,
  properties: Record<string, unknown> = {}
): Promise<void> {
  const apiKey = process.env.NEXT_PUBLIC_POSTHOG_PROJECT_TOKEN;
  if (!apiKey) return;

  await fetch(`${POSTHOG_HOST}/capture/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: apiKey, distinct_id: distinctId, event, properties }),
  }).catch((err) => console.error('[analytics] captureServerEvent failed:', err));
}
