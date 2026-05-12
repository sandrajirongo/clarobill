'use client';

import s from '@/app/billing-traps-guide/guide/guide.module.css';

export function PrintButton(): JSX.Element {
  return (
    <button
      onClick={() => window.print()}
      className={s.printBtn}
      aria-label="Download as PDF"
    >
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
        <path
          d="M8 1v9M5 7l3 3 3-3M2 11v2a1 1 0 001 1h10a1 1 0 001-1v-2"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      Download PDF
    </button>
  );
}
