'use client';

import { useRef, useState, useEffect, useCallback } from 'react';
import type { InsuranceCardExtraction } from '@/app/api/insurance-card/extract/route';
import s from './card-scanner.module.css';

interface CardScannerProps {
  onExtracted: (result: InsuranceCardExtraction) => void;
  onClose: () => void;
}

type ScannerState =
  | { phase: 'starting' }
  | { phase: 'ready' }
  | { phase: 'capturing' }
  | { phase: 'error'; message: string }
  | { phase: 'permission_denied' };

export function CardScanner({ onExtracted, onClose }: CardScannerProps): JSX.Element {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [state, setState] = useState<ScannerState>({ phase: 'starting' });

  // Start the back camera when the component mounts
  useEffect(() => {
    let cancelled = false;

    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 } } })
      .then((stream) => {
        if (cancelled) { stream.getTracks().forEach((t) => t.stop()); return; }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          videoRef.current.play().catch(() => {/* autoplay blocked — user interaction needed */});
        }
        setState({ phase: 'ready' });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const isDenied = err instanceof DOMException &&
          (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError');
        setState(isDenied ? { phase: 'permission_denied' } : { phase: 'error', message: 'Camera unavailable. Use the upload option below.' });
      });

    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  // Capture current video frame, convert to JPEG blob, send to extraction API
  const handleCapture = useCallback(async (): Promise<void> => {
    const video = videoRef.current;
    if (!video || state.phase !== 'ready') return;

    setState({ phase: 'capturing' });

    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth || 1280;
    canvas.height = video.videoHeight || 720;
    const ctx = canvas.getContext('2d');
    if (!ctx) { setState({ phase: 'error', message: 'Could not capture frame.' }); return; }
    ctx.drawImage(video, 0, 0);

    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, 'image/jpeg', 0.92)
    );
    if (!blob) { setState({ phase: 'error', message: 'Could not capture frame.' }); return; }

    const formData = new FormData();
    formData.append('image', new File([blob], 'card.jpg', { type: 'image/jpeg' }));

    try {
      const res = await fetch('/api/insurance-card/extract', { method: 'POST', body: formData });
      if (!res.ok) {
        const { error } = await res.json() as { error: { detail: string } };
        setState({ phase: 'error', message: error?.detail ?? 'Could not read the card. Try again.' });
        return;
      }
      const result = await res.json() as InsuranceCardExtraction;
      // Stop camera before handing off
      streamRef.current?.getTracks().forEach((t) => t.stop());
      onExtracted(result);
      onClose();
    } catch {
      setState({ phase: 'error', message: 'Network error. Please try again.' });
    }
  }, [state.phase, onExtracted, onClose]);

  // Retry after an error
  const handleRetry = useCallback(() => setState({ phase: 'ready' }), []);

  // Upload fallback — regular file input
  const handleUploadFile = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setState({ phase: 'capturing' });
    const formData = new FormData();
    formData.append('image', file);

    fetch('/api/insurance-card/extract', { method: 'POST', body: formData })
      .then(async (res) => {
        if (!res.ok) {
          const { error } = await res.json() as { error: { detail: string } };
          setState({ phase: 'error', message: error?.detail ?? 'Could not read the card.' });
          return;
        }
        const result = await res.json() as InsuranceCardExtraction;
        streamRef.current?.getTracks().forEach((t) => t.stop());
        onExtracted(result);
        onClose();
      })
      .catch(() => setState({ phase: 'error', message: 'Network error. Please try again.' }));
  }, [onExtracted, onClose]);

  const isCapturing = state.phase === 'capturing';

  if (state.phase === 'permission_denied') {
    return (
      <div className={s.overlay}>
        <button className={s.closeBtn} onClick={onClose} aria-label="Close">✕</button>
        <div className={s.permissionError}>
          <p>Camera access was denied. Please allow camera access in your browser settings, or upload a photo instead.</p>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*,application/pdf"
            style={{ display: 'none' }}
            onChange={handleUploadFile}
          />
          <button className={s.uploadFallback} onClick={() => fileInputRef.current?.click()}>
            Upload a photo instead
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={s.overlay}>
      <button className={s.closeBtn} onClick={onClose} aria-label="Close">✕</button>

      <div className={s.videoWrap}>
        {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
        <video ref={videoRef} className={s.video} playsInline muted autoPlay />
        <div className={s.mask} />
        <div className={s.cardFrame}>
          {state.phase === 'ready' && (
            <span className={s.hint}>Align card within frame</span>
          )}
        </div>
      </div>

      <div className={s.controls}>
        <button
          className={s.captureBtn}
          onClick={handleCapture}
          disabled={isCapturing || state.phase === 'starting'}
          aria-label="Capture card"
        />
        <span className={s.captureLabel}>
          {state.phase === 'starting' ? 'Starting camera\u2026' : 'Tap to capture'}
        </span>

        {state.phase === 'error' && (
          <p className={`${s.status} ${s.statusError}`}>
            {state.message}{' '}
            <button
              style={{ background: 'none', border: 'none', color: '#FCA5A5', cursor: 'pointer', fontWeight: 700, textDecoration: 'underline', padding: 0, font: 'inherit' }}
              onClick={handleRetry}
            >
              Try again
            </button>
          </p>
        )}
        {isCapturing && <p className={s.status}>Reading card\u2026</p>}

        <input
          ref={fileInputRef}
          type="file"
          accept="image/*,application/pdf"
          style={{ display: 'none' }}
          onChange={handleUploadFile}
        />
        <button className={s.uploadFallback} onClick={() => fileInputRef.current?.click()}>
          Upload a photo instead
        </button>
      </div>
    </div>
  );
}
