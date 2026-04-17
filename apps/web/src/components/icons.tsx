/**
 * ClaroBill icon library — inline SVG components.
 *
 * All icons use a 24×24 viewBox, 1.75px stroke, rounded caps/joins.
 * Render size is controlled by the parent (width/height props default to 20).
 * Color inherits from CSS `color` via `stroke="currentColor"`.
 *
 * Usage:
 *   import { UploadIcon, CheckIcon } from '@/components/icons';
 *   <UploadIcon size={24} />
 */

interface IconProps {
  size?: number;
  className?: string;
  'aria-hidden'?: boolean | 'true' | 'false';
}

const base: React.SVGProps<SVGSVGElement> = {
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.75,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
};

// ─── Document with upward arrow ───────────────────────────────────────────────
export function UploadIcon({ size = 20, className, 'aria-hidden': ariaHidden = true }: IconProps): JSX.Element {
  return (
    <svg {...base} width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden={ariaHidden}>
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="17 8 12 3 7 8" />
      <line x1="12" y1="3" x2="12" y2="15" />
    </svg>
  );
}

// ─── Document with check (detailed error report) ──────────────────────────────
export function ReportIcon({ size = 20, className, 'aria-hidden': ariaHidden = true }: IconProps): JSX.Element {
  return (
    <svg {...base} width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden={ariaHidden}>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <polyline points="9 15 11 17 15 13" />
    </svg>
  );
}

// ─── Envelope (dispute letter / email) ───────────────────────────────────────
export function LetterIcon({ size = 20, className, 'aria-hidden': ariaHidden = true }: IconProps): JSX.Element {
  return (
    <svg {...base} width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden={ariaHidden}>
      <rect x="2" y="4" width="20" height="16" rx="2" />
      <polyline points="22 7 12 13 2 7" />
    </svg>
  );
}

// ─── Lightning bolt (fast results) ───────────────────────────────────────────
export function SpeedIcon({ size = 20, className, 'aria-hidden': ariaHidden = true }: IconProps): JSX.Element {
  return (
    <svg {...base} width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden={ariaHidden} strokeWidth={1.75}>
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
    </svg>
  );
}

// ─── Checkmark (feature lists, confirmation states) ───────────────────────────
export function CheckIcon({ size = 16, className, 'aria-hidden': ariaHidden = true }: IconProps): JSX.Element {
  return (
    <svg {...base} width={size} height={size} viewBox="0 0 24 24" strokeWidth={2.5} className={className} aria-hidden={ariaHidden}>
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

// ─── File with text lines (bill / document) ───────────────────────────────────
export function FileTextIcon({ size = 20, className, 'aria-hidden': ariaHidden = true }: IconProps): JSX.Element {
  return (
    <svg {...base} width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden={ariaHidden}>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
      <line x1="10" y1="9" x2="8" y2="9" />
    </svg>
  );
}

// ─── Camera (insurance card scan) ────────────────────────────────────────────
export function CameraIcon({ size = 16, className, 'aria-hidden': ariaHidden = true }: IconProps): JSX.Element {
  return (
    <svg {...base} width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden={ariaHidden}>
      <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
      <circle cx="12" cy="13" r="4" />
    </svg>
  );
}
