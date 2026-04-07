'use client';

import { useState } from 'react';
import { validateUploadedFile } from '@/lib/utils/file-validation';
import type { ClarobillError } from '@clarobill/shared';

export type UploadState =
  | { status: 'idle' }
  | { status: 'validating' }
  | { status: 'uploading'; progress: number }
  | { status: 'analyzing' }
  | { status: 'complete'; billId: string }
  | { status: 'error'; error: ClarobillError };

export function useBillUpload() {
  const [uploadState, setUploadState] = useState<UploadState>({ status: 'idle' });

  async function upload(file: File): Promise<void> {
    setUploadState({ status: 'validating' });

    // 1. Validate file on the client (magic bytes + size)
    const validation = await validateUploadedFile(file);
    if (!validation.valid) {
      setUploadState({
        status: 'error',
        error: { code: 'INVALID_FILE_TYPE', detail: validation.error, receivedType: file.type },
      });
      return;
    }

    // 2. Request a signed upload URL and bill ID from our API
    const uploadInitResponse = await fetch('/api/bills/upload', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        fileName: file.name,
        fileSize: file.size,
        mimeType: validation.mimeType,
      }),
    });

    if (!uploadInitResponse.ok) {
      const { error } = await uploadInitResponse.json();
      setUploadState({ status: 'error', error });
      return;
    }

    const { billId, uploadUrl } = await uploadInitResponse.json();

    // 3. Upload file directly to Supabase Storage using the signed URL
    setUploadState({ status: 'uploading', progress: 0 });
    const uploadResponse = await fetch(uploadUrl, {
      method: 'PUT',
      headers: { 'Content-Type': validation.mimeType },
      body: file,
    });

    if (!uploadResponse.ok) {
      setUploadState({
        status: 'error',
        error: { code: 'ANALYSIS_FAILED', detail: 'File upload to storage failed. Please try again.', step: 'storage_put' },
      });
      return;
    }

    setUploadState({ status: 'analyzing' });

    // 4. Trigger analysis and track to completion
    // TODO: Implement triggerAnalysis — this is where your input shapes the feature.
    // Consider: polling vs Realtime subscription, error handling, timeout behavior.
    await triggerAnalysis(billId, setUploadState);
  }

  function reset(): void {
    setUploadState({ status: 'idle' });
  }

  return { uploadState, upload, reset };
}

const POLL_INTERVAL_MS = 2000;
const MAX_POLLS = 90; // 3 minutes max (90 × 2s)

async function triggerAnalysis(
  billId: string,
  setState: (state: UploadState) => void
): Promise<void> {
  // Kick off the engine — 202 Accepted means it's running in the background
  const analyzeResponse = await fetch(`/api/bills/${billId}/analyze`, { method: 'POST' });
  if (!analyzeResponse.ok) {
    const { error } = await analyzeResponse.json();
    setState({ status: 'error', error });
    return;
  }

  // Poll until complete, failed, or timeout
  let polls = 0;
  await new Promise<void>((resolve) => {
    const interval = setInterval(async () => {
      polls += 1;

      if (polls > MAX_POLLS) {
        clearInterval(interval);
        setState({
          status: 'error',
          error: { code: 'ANALYSIS_FAILED', detail: 'Analysis is taking longer than expected. Check back shortly or contact support.', step: 'timeout' },
        });
        resolve();
        return;
      }

      const statusResponse = await fetch(`/api/bills/${billId}`);
      if (!statusResponse.ok) {
        // Transient network error — keep polling, don't abort yet
        return;
      }

      const { status } = await statusResponse.json() as { status: string };

      if (status === 'complete') {
        clearInterval(interval);
        setState({ status: 'complete', billId });
        resolve();
      } else if (status === 'failed') {
        clearInterval(interval);
        setState({
          status: 'error',
          error: { code: 'ANALYSIS_FAILED', detail: 'We could not analyze your bill. Please ensure you uploaded a clear image or PDF and try again.', step: 'engine' },
        });
        resolve();
      }
    }, POLL_INTERVAL_MS);
  });
}
