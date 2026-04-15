/**
 * GCP Workload Identity Federation — Vercel → Cloud Run authentication.
 *
 * Vercel injects an OIDC token (VERCEL_OIDC_TOKEN) into every serverless
 * function. This module exchanges it for a Google identity token that Cloud
 * Run accepts as a Bearer token, with no JSON key files involved.
 *
 * Flow:
 *   1. Exchange VERCEL_OIDC_TOKEN at GCP STS → short-lived federated access token
 *   2. Use federated token to impersonate clarobill-vercel-sa → Cloud Run identity token
 *   3. Caller attaches identity token as Authorization: Bearer header
 *
 * Returns null in local development (VERCEL_OIDC_TOKEN absent) so the engine
 * can be called without auth during development.
 */

const WIF_AUDIENCE =
  `//iam.googleapis.com/projects/${process.env.GCP_PROJECT_NUMBER}/locations/global` +
  `/workloadIdentityPools/clarobill-vercel-pool/providers/vercel-provider`;

const VERCEL_SA_EMAIL = 'clarobill-vercel-sa@clarobill-prd.iam.gserviceaccount.com';

export async function getCloudRunIdToken(cloudRunUrl: string): Promise<string | null> {
  const oidcToken = process.env.VERCEL_OIDC_TOKEN;
  if (!oidcToken) {
    // Local dev — Cloud Run auth not needed, engine accepts unauthenticated calls
    return null;
  }

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
    throw new Error(`GCP STS token exchange failed: ${stsRes.status} ${await stsRes.text()}`);
  }

  const { access_token: federatedToken } = await stsRes.json() as { access_token: string };

  // Step 2: Impersonate clarobill-vercel-sa to get a Cloud Run identity token
  const idTokenRes = await fetch(
    `https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/${VERCEL_SA_EMAIL}:generateIdToken`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${federatedToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        audience: cloudRunUrl,
        includeEmail: true,
      }),
    }
  );

  if (!idTokenRes.ok) {
    throw new Error(`GCP ID token generation failed: ${idTokenRes.status} ${await idTokenRes.text()}`);
  }

  const { token } = await idTokenRes.json() as { token: string };
  return token;
}
