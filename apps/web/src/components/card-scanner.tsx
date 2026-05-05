'use client';

import { useRef, useState, useEffect, useCallback } from 'react';
import type { InsuranceCardExtraction } from '@/lib/api/parsers';
import { InsuranceCardExtractionSchema, parseJsonResponse } from '@/lib/api/parsers';
import type { PlanType } from '@clarobill/shared';
import s from './card-scanner.module.css';

export interface CardScannerLabels {
  // Camera viewfinder hints
  hint: string;           // "Align card within frame"
  hintLocked: string;     // "Hold still…"
  hintStarting: string;   // "Starting camera…"
  // Capture state labels
  capturing: string;      // "Reading card…"
  autoCapturing: string;  // "Auto-capturing…"
  holdOrTap: string;      // "Hold steady or tap to capture"
  // Buttons
  uploadPhoto: string;    // "Upload a photo instead"
  tryAgain: string;       // "Try again"
  cancel: string;         // "Cancel"
  // Error messages (frontend-owned — never use server strings)
  scanFailed: string;     // "Could not read the card. Please try again."
  imageTooLarge: string;  // "Image is too large. Please use a photo under 10 MB."
  // Permission denied screen
  permissionDenied: string; // "Camera access was denied..."
  // Confirmation step
  confirmTitle: string;     // "Review card details"
  confirmSubtitle: string;  // "Check the extracted details before saving"
  confirmInsurer: string;   // "Insurer"
  confirmPlan: string;      // "Plan"
  confirmMemberId: string;  // "Member ID"
  confirmGroupId: string;   // "Group #"
  confirmPlanType: string;  // "Plan type"
  confirmRxBin: string;     // "Rx BIN"
  confirmBtn: string;       // "Confirm"
  retakeBtn: string;        // "Retake"
  notDetected: string;      // "—" (placeholder for missing fields)
  lowConfidence: string;    // "Some fields may need review"
}

const DEFAULT_LABELS: CardScannerLabels = {
  hint: 'Align card within frame',
  hintLocked: 'Hold still\u2026',
  hintStarting: 'Starting camera\u2026',
  capturing: 'Reading card\u2026',
  autoCapturing: 'Auto-capturing\u2026',
  holdOrTap: 'Hold steady or tap to capture',
  uploadPhoto: 'Upload a photo instead',
  tryAgain: 'Try again',
  cancel: 'Cancel',
  scanFailed: 'Could not read the card. Please try again.',
  imageTooLarge: 'Image is too large. Please use a photo under 10\u00a0MB.',
  permissionDenied: 'Camera access was denied. Allow camera access in your browser settings, or upload a photo instead.',
  confirmTitle: 'Review card details',
  confirmSubtitle: 'Check the details below before saving',
  confirmInsurer: 'Insurer',
  confirmPlan: 'Plan',
  confirmMemberId: 'Member ID',
  confirmGroupId: 'Group #',
  confirmPlanType: 'Plan type',
  confirmRxBin: 'Rx BIN',
  confirmBtn: 'Confirm',
  retakeBtn: 'Retake',
  notDetected: '\u2014',
  lowConfidence: 'Some fields may be incorrect \u2014 please review carefully',
};

interface CardScannerProps {
  onExtracted: (result: InsuranceCardExtraction) => void;
  onClose: () => void;
  labels?: Partial<CardScannerLabels>;
}

type ScannerState =
  | { phase: 'starting' }
  | { phase: 'ready' }
  | { phase: 'capturing' }
  | { phase: 'confirming'; result: InsuranceCardExtraction }
  | { phase: 'error'; message: string }
  | { phase: 'permission_denied' };

const CARD_WIDTH_RATIO = 0.72;
const CARD_ASPECT = 1.586;
const CAPTURE_WIDTH = 1200;
const CAPTURE_HEIGHT = Math.round(CAPTURE_WIDTH / CARD_ASPECT);

const SHARPNESS_THRESHOLD = 6;
const STABLE_FRAMES_NEEDED = 2;

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
  const px = (o: number): number => data[o]! * 0.299 + data[o + 1]! * 0.587 + data[o + 2]! * 0.114;
  for (let y = 1; y < H - 1; y++) {
    for (let x = 1; x < W - 1; x++) {
      const i = y * stride + x * 4;
      const lap = 4 * px(i) - px(i - stride) - px(i + stride) - px(i - 4) - px(i + 4);
      sum += Math.abs(lap);
    }
  }
  return sum / ((W - 2) * (H - 2));
}

async function toJpeg(file: File): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      const c = document.createElement('canvas');
      c.width = img.naturalWidth; c.height = img.naturalHeight;
      const ctx2d = c.getContext('2d');
      if (ctx2d) ctx2d.drawImage(img, 0, 0);
      URL.revokeObjectURL(url);
      c.toBlob(
        (blob) => { if (blob) { resolve(blob); } else { reject(new Error('toBlob returned null')); } },
        'image/jpeg',
        0.92,
      );
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('Image load failed')); };
    img.src = url;
  });
}

interface ConfirmStepProps {
  result: InsuranceCardExtraction;
  labels: CardScannerLabels;
  onConfirm: (result: InsuranceCardExtraction) => void;
  onRetake: () => void;
  onClose: () => void;
}

const PLAN_TYPE_OPTIONS = [
  { value: 'commercial', label: 'Commercial' },
  { value: 'medicare',   label: 'Medicare'   },
  { value: 'medicaid',   label: 'Medicaid'   },
  { value: 'tricare',    label: 'TRICARE'    },
  { value: 'self_pay',   label: 'Self-Pay'   },
] as const;

function ConfirmStep({ result, labels, onConfirm, onRetake, onClose }: ConfirmStepProps): JSX.Element {
  const [payerName, setPayerName] = useState(result.payerName ?? '');
  const [planName,  setPlanName]  = useState(result.planName  ?? '');
  const [memberId,  setMemberId]  = useState(result.memberId  ?? '');
  const [groupId,   setGroupId]   = useState(result.groupId   ?? '');
  const [planType,  setPlanType]  = useState<PlanType>(result.planType ?? 'commercial');
  const [rxBin,     setRxBin]     = useState(result.rxBin     ?? '');

  function handleConfirm(): void {
    onConfirm({
      ...result,
      payerName: payerName.trim() || null,
      planName:  planName.trim()  || null,
      memberId:  memberId.trim()  || null,
      groupId:   groupId.trim()   || null,
      planType:  planType         || null,
      rxBin:     rxBin.trim()     || null,
    });
  }

  return (
    <div className={s.overlay}>
      <button className={s.closeBtn} onClick={onClose} aria-label="Close">✕</button>
      <div className={s.confirmCard}>
        <p className={s.confirmTitle}>{labels.confirmTitle}</p>
        <p className={s.confirmSubtitle}>{labels.confirmSubtitle}</p>
        {!result.confident && result.note && (
          <p className={s.confirmWarn}>{labels.lowConfidence}</p>
        )}
        <dl className={s.confirmFields}>
          <dt>{labels.confirmInsurer}</dt>
          <dd>
            <input className={s.confirmInput} value={payerName} onChange={(e) => setPayerName(e.target.value)} />
          </dd>
          <dt>{labels.confirmPlan}</dt>
          <dd>
            <input className={s.confirmInput} value={planName} onChange={(e) => setPlanName(e.target.value)} />
          </dd>
          <dt>{labels.confirmMemberId}</dt>
          <dd>
            <input className={s.confirmInput} value={memberId} onChange={(e) => setMemberId(e.target.value)} />
          </dd>
          <dt>{labels.confirmGroupId}</dt>
          <dd>
            <input className={s.confirmInput} value={groupId} onChange={(e) => setGroupId(e.target.value)} />
          </dd>
          <dt>{labels.confirmPlanType}</dt>
          <dd>
            <select className={s.confirmInput} value={planType} onChange={(e) => setPlanType(e.target.value as PlanType)}>
              {PLAN_TYPE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </dd>
          {(result.rxBin || rxBin) && (
            <>
              <dt>{labels.confirmRxBin}</dt>
              <dd>
                <input className={s.confirmInput} value={rxBin} onChange={(e) => setRxBin(e.target.value)} />
              </dd>
            </>
          )}
        </dl>
        <div className={s.confirmActions}>
          <button className={s.retryBtn} onClick={onRetake}>{labels.retakeBtn}</button>
          <button className={s.confirmBtn} onClick={handleConfirm}>{labels.confirmBtn}</button>
        </div>
      </div>
    </div>
  );
}

export function CardScanner({ onExtracted, onClose, labels: labelOverrides }: CardScannerProps): JSX.Element {
  const labels: CardScannerLabels = { ...DEFAULT_LABELS, ...labelOverrides };

  const videoRef     = useRef<HTMLVideoElement>(null);
  const streamRef    = useRef<MediaStream | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [state, setState]         = useState<ScannerState>({ phase: 'starting' });
  const [cardLocked, setCardLocked] = useState(false);

  // ── Camera setup ──────────────────────────────────────────────────────────
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
        setState(denied
          ? { phase: 'permission_denied' }
          : { phase: 'error', message: 'Camera unavailable. Use the upload option below.' });
      });
    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  // ── Submit image → show confirmation step ─────────────────────────────────
  const submitImage = useCallback(async (blob: Blob, filename: string, mimeType: string): Promise<void> => {
    const formData = new FormData();
    formData.append('image', new File([blob], filename, { type: mimeType }));
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30_000);
    try {
      const res = await fetch('/api/insurance-card/extract', {
        method: 'POST',
        body: formData,
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      if (!res.ok) {
        const message = res.status === 413 ? labels.imageTooLarge : labels.scanFailed;
        setState({ phase: 'error', message });
        return;
      }
      const result: InsuranceCardExtraction = await parseJsonResponse(
        res, InsuranceCardExtractionSchema,
      );
      // Stop the camera stream while the user reviews extracted details
      streamRef.current?.getTracks().forEach((t) => t.stop());
      setState({ phase: 'confirming', result });
    } catch {
      clearTimeout(timeoutId);
      setState({ phase: 'error', message: labels.scanFailed });
    }
  }, [labels.imageTooLarge, labels.scanFailed]);

  // ── Camera capture — crops to the card overlay region ────────────────────
  const doCapture = useCallback(async (): Promise<void> => {
    const video = videoRef.current;
    if (!video) return;
    setState({ phase: 'capturing' });
    setCardLocked(false);
    const vw = video.videoWidth  || 1280;
    const vh = video.videoHeight || 720;
    const cardW = vw * CARD_WIDTH_RATIO;
    const cardH = cardW / CARD_ASPECT;
    const cardX = (vw - cardW) / 2;
    const cardY = (vh - cardH) / 2;
    const canvas = document.createElement('canvas');
    canvas.width  = CAPTURE_WIDTH;
    canvas.height = CAPTURE_HEIGHT;
    const ctx = canvas.getContext('2d');
    if (!ctx) { setState({ phase: 'error', message: 'Could not capture frame.' }); return; }
    ctx.drawImage(video, cardX, cardY, cardW, cardH, 0, 0, CAPTURE_WIDTH, CAPTURE_HEIGHT);
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.92));
    if (!blob) { setState({ phase: 'error', message: 'Could not capture frame.' }); return; }
    await submitImage(blob, 'card.jpg', 'image/jpeg');
  }, [submitImage]);

  // ── File upload fallback ──────────────────────────────────────────────────
  const handleUploadFile = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setState({ phase: 'capturing' });
    const supported = ['image/jpeg', 'image/png', 'image/webp'];
    if (!supported.includes(file.type)) {
      toJpeg(file)
        .then((blob) => submitImage(blob, 'card.jpg', 'image/jpeg'))
        .catch(() => setState({ phase: 'error', message: 'Could not read the image file.' }));
    } else {
      void submitImage(file, file.name, file.type);
    }
  }, [submitImage]);

  // ── Auto-capture polling ──────────────────────────────────────────────────
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
        if (stableCount >= STABLE_FRAMES_NEEDED) { clearInterval(id); void doCaptureRef.current(); }
      } else { stableCount = 0; setCardLocked(false); }
    }, 700);
    return () => clearInterval(id);
  }, [state.phase]);

  // ── Confirmation: user reviews extracted data then confirms ───────────────
  if (state.phase === 'confirming') {
    return (
      <ConfirmStep
        result={state.result}
        labels={labels}
        onConfirm={(edited) => { onExtracted(edited); onClose(); }}
        onRetake={() => setState({ phase: 'ready' })}
        onClose={onClose}
      />
    );
  }

  // ── Permission denied ─────────────────────────────────────────────────────
  if (state.phase === 'permission_denied') {
    return (
      <div className={s.overlay}>
        <button className={s.closeBtn} onClick={onClose} aria-label="Close">✕</button>
        <div className={s.permissionError}>
          <p>{labels.permissionDenied}</p>
          <input ref={fileInputRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={handleUploadFile} />
          <button className={s.uploadFallback} onClick={() => fileInputRef.current?.click()}>{labels.uploadPhoto}</button>
          <button className={s.cancelBtn} onClick={onClose}>{labels.cancel}</button>
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
              {cardLocked ? labels.hintLocked : state.phase === 'starting' ? labels.hintStarting : labels.hint}
            </span>
          )}
          {isCapturing && <span className={s.hint}>{labels.capturing}</span>}
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
          {isCapturing ? labels.capturing
            : cardLocked ? labels.autoCapturing
            : state.phase === 'starting' ? labels.hintStarting
            : labels.holdOrTap}
        </span>

        {state.phase === 'error' && (
          <div className={s.errorBlock}>
            <p className={s.statusError}>{state.message}</p>
            <div className={s.errorActions}>
              <button className={s.retryBtn} onClick={() => setState({ phase: 'ready' })}>{labels.tryAgain}</button>
              <button className={s.cancelBtn} onClick={onClose}>{labels.cancel}</button>
            </div>
          </div>
        )}

        <input ref={fileInputRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={handleUploadFile} />
        <button className={s.uploadFallback} onClick={() => fileInputRef.current?.click()}>
          {labels.uploadPhoto}
        </button>
      </div>
    </div>
  );
}
