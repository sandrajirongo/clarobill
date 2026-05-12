// Server-side Loops helpers. Import only in Server Components and API routes.
const LOOPS_API = 'https://app.loops.so/api/v1';

function headers(): Record<string, string> {
  const key = process.env.LOOPS_API_KEY;
  if (!key) throw new Error('LOOPS_API_KEY is not set');
  return { 'Content-Type': 'application/json', Authorization: `Bearer ${key}` };
}

// Create or update a contact in Loops. 409 = already exists; that's fine.
export async function createLoopsContact(
  email: string,
  properties: Record<string, string | boolean> = {}
): Promise<void> {
  if (!process.env.LOOPS_API_KEY) return;
  await fetch(`${LOOPS_API}/contacts/create`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify({ email, subscribed: true, ...properties }),
  }).catch((err) => console.error('[loops] createContact failed:', err));
}

// Update properties on an existing Loops contact.
export async function updateLoopsContact(
  email: string,
  properties: Record<string, string | boolean>
): Promise<void> {
  if (!process.env.LOOPS_API_KEY) return;
  await fetch(`${LOOPS_API}/contacts/update`, {
    method: 'PUT',
    headers: headers(),
    body: JSON.stringify({ email, ...properties }),
  }).catch((err) => console.error('[loops] updateContact failed:', err));
}

// Send a transactional email. The template must be set up in the Loops dashboard.
export async function sendLoopsTransactional(
  transactionalId: string,
  email: string,
  dataVariables: Record<string, string> = {}
): Promise<void> {
  if (!process.env.LOOPS_API_KEY || !transactionalId) return;
  const res = await fetch(`${LOOPS_API}/transactional`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify({ transactionalId, email, dataVariables }),
  }).catch((err) => { console.error('[loops] sendTransactional failed:', err); return null; });
  if (res && !res.ok) {
    console.error('[loops] sendTransactional returned %d for %s', res.status, transactionalId);
  }
}
