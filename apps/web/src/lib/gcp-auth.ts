/**
 * GCP Workload Identity Federation — Vercel → Cloud Run authentication.
 *
 * Uses @vercel/oidc to get the Vercel OIDC token, then exchanges it for a
 * GCP federated access token via STS, then generates a Cloud Run identity
 * token for the Authorization: Bearer header.
 *
 * Returns null when not running on Vercel (local dev) so the engine can be
 * called without auth during development.
 */

import { getVercelOidcToken } from '@vercel/oidc';

const WIF_AUDIENCE =
  `//iam.googleapis.com/projects/${process.env.GCP_PROJECT_NUMBER}/locations/global` +
  `/workloadIdentityPools/${process.env.GCP_WORKLOAD_IDENTITY_POOL_ID ?? 'clarobill-vercel-pool'}` +
  `/providers/${process.env.GCP_WORKLOAD_IDENTITY_POOL_PROVIDER_ID ?? 'vercel-provider'}`;

const SA_EMAIL =
  process.env.GCP_SERVICE_ACCOUNT_EMAIL ?? 'clarobill-vercel-sa@clarobill-prd.iam.gserviceaccount.com';

export async function getCloudRunIdToken(cloudRunUrl: string): Promise<string | null> {
  // Not running on Vercel — local dev, skip auth
  if (!process.env.VERCEL) return null;

  const oidcToken = await getVercelOidcToken();

  // Step 1: Exchange Vercel OIDC token for a GCP federated access token
  const stsParams = new URLSearchParams({
    grant_type: 'urn:ietf:params:oauth:grant-type:token-exchange',
    audience: WIF_AUDIENCE,
    subject_token: oidcToken,
    subject_token_type: 'urn:ietf:params:oauth:token-type:jwt',
    requested_token_type: 'urn:ietf:params:oauth:token-type:access_token',
    scope: 'https://www.googleapis.com/auth/cloud-platform',
  });

  const stsRes = await fetch('https://sts.googleapis.com/v1/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: stsParams.toString(),
  });

  if (!stsRes.ok) {
    throw new Error(`GCP STS exchange failed: ${stsRes.status} ${await stsRes.text()}`);
  }

  const { access_token: federatedToken } = await stsRes.json() as { access_token: string };

  // Step 2: Impersonate the SA to get a Cloud Run identity token
  const idTokenRes = await fetch(
    `https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/${SA_EMAIL}:generateIdToken`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${federatedToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ audience: cloudRunUrl, includeEmail: true }),
    }
  );

  if (!idTokenRes.ok) {
    throw new Error(`GCP generateIdToken failed: ${idTokenRes.status} ${await idTokenRes.text()}`);
  }

  const { token } = await idTokenRes.json() as { token: string };
  return token;
}
