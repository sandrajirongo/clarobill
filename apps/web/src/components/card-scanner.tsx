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

// Laplacian mean threshold — below this the frame is too blurry to read
const SHARPNESS_THRESHOLD = 8;
// Consecutive sharp frames required before auto-capture fires (~1.4 s at 700 ms interval)
const STABLE_FRAMES_NEEDED = 2;

/**
 * Mean absolute Laplacian of the central card region of a video frame.
 * High value = sharp edges = legible text. Same focus metric used by
 * Stripe, Plaid, and Onfido for their document capture flows.
 */
function measureSharpness(video: HTMLVideoElement): number {
  const W = 160, H = 100;
  const sc = document.createElement('canvas');
  sc.width = W; sc.height = H;
  const ctx = sc.getContext('2d', { willReadFrequently: true });
  if (!ctx) return 0;
  const vw = video.videoWidth || 640;
  const vh = video.videoHeight || 360;
  ctx.drawImage(video, vw * 0.2, vh * 0.15, vw * 0.6, vh * 0.7, 0, 0, W, H);
  const { data } = ctx.getImageData(0, 0, W, H);
  const stride = W * 4;
  let sum = 0;
  // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
  const px = (offset: number): number =>
    data[offset]! * 0.299 + data[offset + 1]! * 0.587 + data[offset + 2]! * 0.114;
  for (let y = 1; y < H - 1; y++) {
    for (let x = 1; x < W - 1; x++) {
      const i = y * stride + x * 4;
      const lap = 4 * px(i) - px(i - stride) - px(i + stride) - px(i - 4) - px(i + 4);
      sum += Math.abs(lap);
    }
  }
  return sum / ((W - 2) * (H - 2));
}

/** Draw any image file through a canvas to guarantee a JPEG output. */
async function toJpeg(file: File): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      const c = document.createElement('canvas');
      c.width = img.naturalWidth; c.height = img.naturalHeight;
      c.getContext('2d')!.drawImage(img, 0, 0);
      URL.revokeObjectURL(url);
      c.toBlob((blob) => {
        if (blob) resolve(blob);
        else reject(new Error('canvas.toBlob returned null'));
      }, 'image/jpeg', 0.95);
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('Image load failed')); };
    img.src = url;
  });
}

export function CardScanner({ onExtracted, onClose }: CardScannerProps): JSX.Element {
  const videoRef    = useRef<HTMLVideoElement>(null);
  const streamRef   = useRef<MediaStream | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [state, setState] = useState<ScannerState>({ phase: 'starting' });
  const [cardLocked, setCardLocked] = useState(false);

  // ── Camera setup ─────────────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 } } })
      .then((stream) => {
        if (cancelled) { stream.getTracks().forEach((t) => t.stop()); return; }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          videoRef.current.play().catch(() => {/* autoplay policy */});
        }
        setState({ phase: 'ready' });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const denied = err instanceof DOMException &&
          (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError');
        setState(denied ? { phase: 'permission_denied' } : { phase: 'error', message: 'Camera unavailable. Use the upload option below.' });
      });
    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  // ── Core API submission ───────────────────────────────────────────────────
  const submitImage = useCallback(async (blob: Blob, filename: string, mimeType: string): Promise<void> => {
    const formData = new FormData();
    formData.append('image', new File([blob], filename, { type: mimeType }));
    try {
      const res = await fetch('/api/insurance-card/extract', { method: 'POST', body: formData });
      if (!res.ok) {
        const body = await res.json() as { error?: { detail?: string } };
        setState({ phase: 'error', message: body?.error?.detail ?? 'Could not read the card. Try uploading instead.' });
        return;
      }
      const result = await res.json() as InsuranceCardExtraction;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      onExtracted(result);
      onClose();
    } catch {
      setState({ phase: 'error', message: 'Network error. Check your connection and try again.' });
    }
  }, [onExtracted, onClose]);

  // ── Camera capture ────────────────────────────────────────────────────────
  const doCapture = useCallback(async (): Promise<void> => {
    const video = videoRef.current;
    if (!video) return;
    setState({ phase: 'capturing' });
    setCardLocked(false);
    const canvas = document.createElement('canvas');
    canvas.width  = video.videoWidth  || 1920;
    canvas.height = video.videoHeight || 1080;
    const ctx = canvas.getContext('2d');
    if (!ctx) { setState({ phase: 'error', message: 'Could not capture frame.' }); return; }
    ctx.drawImage(video, 0, 0);
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.95));
    if (!blob) { setState({ phase: 'error', message: 'Could not capture frame.' }); return; }
    await submitImage(blob, 'card.jpg', 'image/jpeg');
  }, [submitImage]);

  // ── File upload fallback ──────────────────────────────────────────────────
  const handleUploadFile = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setState({ phase: 'capturing' });

    const supported = ['image/jpeg', 'image/png', 'image/webp', 'image/gif'];
    if (!supported.includes(file.type)) {
      // HEIC or unknown — convert via canvas
      toJpeg(file)
        .then((blob) => submitImage(blob, 'card.jpg', 'image/jpeg'))
        .catch(() => setState({ phase: 'error', message: 'Could not read the image file.' }));
    } else {
      void submitImage(file, file.name, file.type);
    }
  }, [submitImage]);

  // ── Auto-capture: Laplacian sharpness polling ─────────────────────────────
  // Keep a ref so the interval always calls the latest doCapture without
  // restarting the interval when doCapture identity changes
  const doCaptureRef = useRef(doCapture);
  useEffect(() => { doCaptureRef.current = doCapture; }, [doCapture]);

  useEffect(() => {
    if (state.phase !== 'ready') { setCardLocked(false); return; }
    let stableCount = 0;
    const id = setInterval(() => {
      const video = videoRef.current;
      if (!video || video.videoWidth === 0) return;
      const score = measureSharpness(video);
      if (score >= SHARPNESS_THRESHOLD) {
        stableCount++;
        if (stableCount >= 1) setCardLocked(true);
        if (stableCount >= STABLE_FRAMES_NEEDED) {
          clearInterval(id);
          void doCaptureRef.current();
        }
      } else {
        stableCount = 0;
        setCardLocked(false);
      }
    }, 700);
    return () => clearInterval(id);
  }, [state.phase]);

  const handleRetry = useCallback(() => setState({ phase: 'ready' }), []);

  // ── Permission denied ─────────────────────────────────────────────────────
  if (state.phase === 'permission_denied') {
    return (
      <div className={s.overlay}>
        <button className={s.closeBtn} onClick={onClose} aria-label="Close">✕</button>
        <div className={s.permissionError}>
          <p>Camera access was denied. Please allow camera access in your browser settings, or upload a photo instead.</p>
          <input ref={fileInputRef} type="file" accept="image/*,application/pdf" style={{ display: 'none' }} onChange={handleUploadFile} />
          <button className={s.uploadFallback} onClick={() => fileInputRef.current?.click()}>Upload a photo instead</button>
          <button className={s.cancelBtn} onClick={onClose}>Cancel</button>
        </div>
      </div>
    );
  }

  const isCapturing = state.phase === 'capturing';

  return (
    <div className={s.overlay}>
      <button className={s.closeBtn} onClick={onClose} aria-label="Close">✕</button>

      <div className={s.videoWrap}>
        {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
        <video ref={videoRef} className={s.video} playsInline muted autoPlay />
        <div className={s.mask} />
        <div className={`${s.cardFrame} ${cardLocked ? s.cardFrameLocked : ''}`}>
          {(state.phase === 'ready' || state.phase === 'starting') && (
            <span className={s.hint}>
              {cardLocked ? 'Hold still\u2026' : state.phase === 'starting' ? 'Starting camera\u2026' : 'Align card within frame'}
            </span>
          )}
        </div>
      </div>

      <div className={s.controls}>
        <button
          className={`${s.captureBtn} ${cardLocked ? s.captureBtnLocked : ''}`}
          onClick={() => void doCapture()}
          disabled={isCapturing || state.phase === 'starting'}
          aria-label="Capture card"
        />
        <span className={s.captureLabel}>
          {isCapturing
            ? 'Reading card\u2026'
            : cardLocked
            ? 'Auto-capturing\u2026'
            : state.phase === 'starting'
            ? 'Starting camera\u2026'
            : 'Hold steady or tap to capture'}
        </span>

        {state.phase === 'error' && (
          <div className={s.errorBlock}>
            <p className={s.statusError}>{state.message}</p>
            <div className={s.errorActions}>
              <button className={s.retryBtn} onClick={handleRetry}>Try again</button>
              <button className={s.cancelBtn} onClick={onClose}>Cancel</button>
            </div>
          </div>
        )}

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
