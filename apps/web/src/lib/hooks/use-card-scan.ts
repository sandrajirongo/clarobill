'use client';

import { useRef, useState } from 'react';
import type { InsuranceCardExtraction } from '@/app/api/insurance-card/extract/route';

export type CardScanState =
  | { status: 'idle' }
  | { status: 'scanning' }
  | { status: 'done'; result: InsuranceCardExtraction }
  | { status: 'error'; message: string };

export function useCardScan() {
  const [scanState, setScanState] = useState<CardScanState>({ status: 'idle' });
  const inputRef = useRef<HTMLInputElement>(null);

  function openFilePicker(): void {
    inputRef.current?.click();
  }

  async function handleFile(file: File): Promise<void> {
    setScanState({ status: 'scanning' });

    const formData = new FormData();
    formData.append('image', file);

    try {
      const res = await fetch('/api/insurance-card/extract', {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const { error } = await res.json() as { error: { detail: string } };
        setScanState({ status: 'error', message: error?.detail ?? 'Could not read the card. Try again or fill in manually.' });
        return;
      }

      const result = await res.json() as InsuranceCardExtraction;
      setScanState({ status: 'done', result });
    } catch {
      setScanState({ status: 'error', message: 'Network error. Please try again.' });
    }
  }

  function reset(): void {
    setScanState({ status: 'idle' });
    // Clear the file input so the same file can be re-selected
    if (inputRef.current) inputRef.current.value = '';
  }

  return { scanState, inputRef, openFilePicker, handleFile, reset };
}
