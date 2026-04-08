'use client';

import { useRef } from 'react';
import { useBillUpload } from '@/lib/hooks/use-bill-upload';
import { useRouter } from 'next/navigation';
import s from '@/app/dashboard/dashboard.module.css';

export function BillUploader(): JSX.Element {
  const { uploadState, upload, reset } = useBillUpload();
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  if (uploadState.status === 'complete') {
    router.push(`/dashboard/bills/${uploadState.billId}`);
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>): void {
    const file = e.target.files?.[0];
    if (file) upload(file);
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>): void {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) upload(file);
  }

  const isActive = uploadState.status !== 'idle' && uploadState.status !== 'error';

  return (
    <div
      onDrop={handleDrop}
      onDragOver={(e) => e.preventDefault()}
      className={s.uploadZone}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,image/jpeg,image/png"
        style={{ display: 'none' }}
        onChange={handleFileChange}
        disabled={isActive}
      />

      {uploadState.status === 'idle' && (
        <>
          <div className={s.uploadIcon}>📄</div>
          <p className={s.uploadLabel}>Drop your bill here, or</p>
          <button onClick={() => inputRef.current?.click()} className={s.uploadBtn}>
            Choose file
          </button>
          <p className={s.uploadHint}>PDF, JPEG, or PNG — max 20MB</p>
        </>
      )}

      {uploadState.status === 'validating' && (
        <p className={s.uploadStatusText}>Checking file…</p>
      )}

      {uploadState.status === 'uploading' && (
        <p className={s.uploadStatusText}>Uploading… {uploadState.progress}%</p>
      )}

      {uploadState.status === 'analyzing' && (
        <>
          <div className={s.uploadSpinner} />
          <p className={s.uploadStatusText}>Analyzing your bill — this takes about 30 seconds…</p>
        </>
      )}

      {uploadState.status === 'error' && (
        <>
          <p className={s.uploadError}>{uploadState.error.detail}</p>
          <button onClick={reset} className={s.retryBtn}>Try again</button>
        </>
      )}
    </div>
  );
}
