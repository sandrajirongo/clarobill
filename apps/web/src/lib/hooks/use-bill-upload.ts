'use client';

import { useState } from 'react';
import { validateUploadedFile } from '@/lib/utils/file-validation';
import { Analytics } from '@/lib/analytics';
import type { ClarobillError } from '@clarobill/shared';

export type UploadState =
  | { status: 'idle' }
  | { status: 'validating' }
  // File passed validation — waiting for user to confirm display name before upload starts.
  // The component shows a name input pre-filled with the filename stem.
  | { status: 'staged'; file: File; displayName: string }
  | { status: 'uploading'; progress: number }
  | { status: 'ready'; billId: string }   // upload complete — waiting to navigate to /verify
  | { status: 'error'; error: ClarobillError };

export function useBillUpload() {
  const [uploadState, setUploadState] = useState<UploadState>({ status: 'idle' });

  // Called when a file is dropped or selected. Validates and stages it.
  async function stage(file: File): Promise<void> {
    setUploadState({ status: 'validating' });
    const validation = await validateUploadedFile(file);
    if (!validation.valid) {
      setUploadState({
        status: 'error',
        error: { code: 'INVALID_FILE_TYPE', detail: validation.error, receivedType: file.type },
      });
      return;
    }
    // Pre-fill display name with the filename stem (strip extension)
    const stem = file.name.replace(/\.[^.]+$/, '');
    setUploadState({ status: 'staged', file, displayName: stem });
  }

  // Called when the user confirms the name and clicks "Upload →".
  async function upload(file: File, displayName: string): Promise<void> {
    setUploadState({ status: 'validating' });

    // File was already validated in stage() — re-validate to get the mimeType
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
        displayName: displayName.trim() || null,
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
    Analytics.billUploaded(billId);
    setUploadState({ status: 'ready', billId });
  }

  function reset(): void {
    setUploadState({ status: 'idle' });
  }

  return { uploadState, stage, upload, reset };
}
