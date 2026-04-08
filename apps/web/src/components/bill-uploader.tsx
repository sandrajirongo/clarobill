'use client';

import { useRef } from 'react';
import { useBillUpload } from '@/lib/hooks/use-bill-upload';
import { useRouter } from 'next/navigation';

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
      className="bg-white rounded-2xl border-2 border-dashed border-gray-200 shadow-sm p-12 text-center hover:border-teal-400 transition-colors"
    >
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,image/jpeg,image/png"
        className="hidden"
        onChange={handleFileChange}
        disabled={isActive}
      />

      {uploadState.status === 'idle' && (
        <>
          <div className="text-4xl mb-4">📄</div>
          <p className="text-gray-700 font-medium mb-1">Drop your bill here, or</p>
          <button
            onClick={() => inputRef.current?.click()}
            className="mt-2 bg-teal-600 text-white px-5 py-2 rounded-lg text-sm font-semibold hover:bg-teal-700 transition-colors"
          >
            Choose file
          </button>
          <p className="text-xs text-gray-400 mt-3">PDF, JPEG, or PNG — max 20MB</p>
        </>
      )}

      {uploadState.status === 'validating' && <StatusMessage text="Checking file…" />}

      {uploadState.status === 'uploading' && (
        <StatusMessage text={`Uploading… ${uploadState.progress}%`} />
      )}

      {uploadState.status === 'analyzing' && (
        <StatusMessage text="Analyzing your bill — this takes about 30 seconds…" spinner />
      )}

      {uploadState.status === 'error' && (
        <div className="space-y-3">
          <p className="text-red-600 text-sm font-medium">{uploadState.error.detail}</p>
          <button
            onClick={reset}
            className="text-sm text-teal-600 hover:underline"
          >
            Try again
          </button>
        </div>
      )}
    </div>
  );
}

function StatusMessage({ text, spinner = false }: { text: string; spinner?: boolean }): JSX.Element {
  return (
    <div className="flex flex-col items-center gap-3">
      {spinner && (
        <div className="w-8 h-8 border-4 border-teal-200 border-t-teal-600 rounded-full animate-spin" />
      )}
      <p className="text-gray-600 text-sm">{text}</p>
    </div>
  );
}
