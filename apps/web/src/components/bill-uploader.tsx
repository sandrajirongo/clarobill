'use client';

import { useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useBillUpload } from '@/lib/hooks/use-bill-upload';
import { useRouter } from 'next/navigation';
import { UploadIcon } from '@/components/icons';
import s from '@/app/dashboard/dashboard.module.css';

export function BillUploader(): JSX.Element {
  const t = useTranslations('dashboard.uploader');
  const { uploadState, stage, upload, reset } = useBillUpload();
  const [editedName, setEditedName] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  // Extract billId as a stable primitive so the effect dep is a string|null,
  // not the whole uploadState object (which changes reference on every state update).
  const readyBillId = uploadState.status === 'ready' ? uploadState.billId : null;

  // Navigate in an effect — calling router.push during render causes a React warning
  // and can trigger additional renders before navigation completes.
  useEffect(() => {
    if (readyBillId) {
      router.push(`/dashboard/bills/${readyBillId}/verify`);
    }
  }, [readyBillId, router]);

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

  if (uploadState.status === 'staged' && editedName !== uploadState.displayName) {
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
          <p className={s.uploadLabel}>{t('dropLabel')}</p>
          <button onClick={() => inputRef.current?.click()} className={s.uploadBtn}>
            {t('chooseFile')}
          </button>
          <p className={s.uploadHint}>{t('hint')}</p>
          <p className={s.uploadItemizedTip}>{t('itemizedTip')}</p>
        </>
      )}

      {uploadState.status === 'validating' && (
        <p className={s.uploadStatusText}>{t('checking')}</p>
      )}

      {uploadState.status === 'staged' && (
        <div className={s.uploadStagedWrap}>
          <p className={s.uploadStagedFile}>{uploadState.file.name}</p>
          <div className={s.uploadNameRow}>
            <label className={s.uploadNameLabel}>{t('nameBill')}</label>
            <input
              className={s.uploadNameInput}
              type="text"
              value={editedName}
              onChange={(e) => setEditedName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleUpload(); }}
              placeholder={t('namePlaceholder')}
              autoFocus
            />
          </div>
          <div className={s.uploadStagedActions}>
            <button onClick={handleReset} className={s.uploadCancelBtn}>{t('cancel')}</button>
            <button onClick={handleUpload} className={s.uploadBtn}>{t('uploadAnalyze')}</button>
          </div>
        </div>
      )}

      {uploadState.status === 'uploading' && (
        <p className={s.uploadStatusText}>{t('uploading')}</p>
      )}

      {uploadState.status === 'ready' && (
        <>
          <div className={s.uploadSpinner} />
          <p className={s.uploadStatusText}>{t('uploadComplete')}</p>
        </>
      )}

      {uploadState.status === 'error' && (
        <>
          <p className={s.uploadError}>{uploadState.error.detail}</p>
          <button onClick={handleReset} className={s.retryBtn}>{t('tryAgain')}</button>
        </>
      )}
    </div>
  );
}
