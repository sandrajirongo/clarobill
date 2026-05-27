import type { BillUploadResponse } from '@clarobill/shared';
import { File, UploadType } from 'expo-file-system';
import { apiFetch, ApiError } from './client';

/**
 * Step 1 of bill upload: ask the ClaroBill API for a signed Supabase Storage
 * URL we can PUT the file bytes to.
 *
 * Mirrors the web app's `/api/bills/upload` endpoint contract.
 */
export async function initBillUpload(params: {
  fileName: string;
  fileSize: number;
  mimeType: 'application/pdf' | 'image/jpeg' | 'image/png';
  displayName?: string;
}): Promise<BillUploadResponse> {
  return apiFetch<BillUploadResponse>('/api/bills/upload', {
    method: 'POST',
    body: params,
  });
}

/**
 * Step 2 of bill upload: PUT the file bytes to the signed URL returned by
 * `initBillUpload`. The signed URL belongs to Supabase Storage; it does NOT
 * accept an Authorization header (it's pre-authenticated via the URL itself).
 *
 * Uses `expo-file-system`'s native `uploadAsync` rather than `fetch(blob)`
 * because React Native's blob implementation does not support binary file
 * payloads from `file://` URIs ("Creating blobs from ArrayBuffer ... not
 * supported"). The native uploader streams bytes directly off disk into the
 * HTTP request, which works for any size up to the Supabase 50 MB limit.
 */
export async function putBillFile(params: {
  uploadUrl: string;
  fileUri: string;
  mimeType: string;
}): Promise<void> {
  const file = new File(params.fileUri);
  const result = await file.upload(params.uploadUrl, {
    httpMethod: 'PUT',
    uploadType: UploadType.BINARY_CONTENT,
    headers: { 'Content-Type': params.mimeType },
  });
  if (result.status < 200 || result.status >= 300) {
    throw new ApiError(
      result.status,
      'STORAGE_PUT_FAILED',
      `Failed to upload file to storage (${result.status})`,
      result.body,
    );
  }
}

/**
 * Step 3 of bill upload: kick off the analysis pipeline.
 *
 * Fire-and-forget on the server side — the engine processes asynchronously
 * and updates `bills.status` as it progresses ('uploading' → 'analyzing'
 * → 'complete' or 'error'). The mobile UI polls `getBill()` to track.
 *
 * Optional `state` + `county` adjust Medicare GPCI locality benchmarks.
 * Mobile defaults to national rates by omitting both — the bill verification
 * screen (future step) will collect this when the user confirms the bill.
 */
export async function triggerAnalysis(
  billId: string,
  options: { state?: string; county?: string } = {},
): Promise<{ accepted?: boolean } | unknown> {
  return apiFetch(`/api/bills/${billId}/analyze`, {
    method: 'POST',
    body: {
      state: options.state ?? null,
      county: options.county ?? null,
    },
  });
}
