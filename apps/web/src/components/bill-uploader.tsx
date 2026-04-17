'use client';

import { useRef, useState } from 'react';
import { useBillUpload } from '@/lib/hooks/use-bill-upload';
import { useRouter } from 'next/navigation';
import { UploadIcon } from '@/components/icons';
import s from '@/app/dashboard/dashboard.module.css';

export function BillUploader(): JSX.Element {
  const { uploadState, stage, upload, reset } = useBillUpload();
  const [editedName, setEditedName] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  if (uploadState.status === 'ready') {
    router.push(`/dashboard/bills/${uploadState.billId}/verify`);
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>): void {
    const file = e.target.files?.[0];
    if (!file) return;
    void stage(file);
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>): void {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) void stage(file);
  }

  // When stage() completes and sets 'staged' status, sync the editable name
  if (uploadState.status === 'staged' && editedName !== uploadState.displayName) {
    // Only sync on first entry to 'staged' — don't override user edits
    if (editedName === '') setEditedName(uploadState.displayName);
  }

  function handleUpload(): void {
    if (uploadState.status !== 'staged') return;
    const name = editedName.trim() || uploadState.displayName;
    void upload(uploadState.file, name);
  }

  function handleReset(): void {
    setEditedName('');
    reset();
  }

  const isActive = uploadState.status !== 'idle' && uploadState.status !== 'error' && uploadState.status !== 'staged';

  return (
    <div
      onDrop={uploadState.status === 'idle' ? handleDrop : undefined}
      onDragOver={uploadState.status === 'idle' ? (e) => e.preventDefault() : undefined}
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
          <div className={s.uploadIcon}><UploadIcon size={28} /></div>
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

      {uploadState.status === 'staged' && (
        <div className={s.uploadStagedWrap}>
          <p className={s.uploadStagedFile}>{uploadState.file.name}</p>
          <div className={s.uploadNameRow}>
            <label className={s.uploadNameLabel}>Name this bill</label>
            <input
              className={s.uploadNameInput}
              type="text"
              value={editedName}
              onChange={(e) => setEditedName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleUpload(); }}
              placeholder="e.g. January ER Visit"
              autoFocus
            />
          </div>
          <div className={s.uploadStagedActions}>
            <button onClick={handleReset} className={s.uploadCancelBtn}>Cancel</button>
            <button onClick={handleUpload} className={s.uploadBtn}>
              Upload & Analyze →
            </button>
          </div>
        </div>
      )}

      {uploadState.status === 'uploading' && (
        <p className={s.uploadStatusText}>Uploading…</p>
      )}

      {uploadState.status === 'ready' && (
        <>
          <div className={s.uploadSpinner} />
          <p className={s.uploadStatusText}>Upload complete — preparing analysis…</p>
        </>
      )}

      {uploadState.status === 'error' && (
        <>
          <p className={s.uploadError}>{uploadState.error.detail}</p>
          <button onClick={handleReset} className={s.retryBtn}>Try again</button>
        </>
      )}
    </div>
  );
}
