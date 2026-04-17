'use client';

import { useState } from 'react';
import { validateUploadedFile } from '@/lib/utils/file-validation';
import type { ClarobillError } from '@clarobill/shared';

export type UploadState =
  | { status: 'idle' }
  | { status: 'validating' }
  | { status: 'uploading'; progress: number }
  | { status: 'ready'; billId: string }   // upload complete — waiting to navigate to /verify
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

    // 4. Upload is done — send user to the verification step.
    //    Analysis is triggered only after the user confirms member, insurance, and hospital.
    setUploadState({ status: 'ready', billId });
  }

  function reset(): void {
    setUploadState({ status: 'idle' });
  }

  return { uploadState, upload, reset };
}
