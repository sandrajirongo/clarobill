'use client';

import s from '@/app/billing-traps-guide/guide/guide.module.css';

export function PrintButton(): JSX.Element {
  return (
    <button
      onClick={() => window.print()}
      className={s.printBtn}
      aria-label="Print or save as PDF"
    >
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
        <path
          d="M4 6V1h8v5M4 12H2a1 1 0 01-1-1V7a1 1 0 011-1h12a1 1 0 011 1v4a1 1 0 01-1 1h-2M4 9h8v6H4V9z"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      Save as PDF
    </button>
  );
}
