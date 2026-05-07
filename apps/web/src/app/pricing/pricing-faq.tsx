'use client';

import { useState } from 'react';
import { FAQS } from './pricing-data';
import s from './pricing.module.css';

export function PricingFaq(): JSX.Element {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <div className={s.faqList}>
      {FAQS.map((faq, i) => (
        <div key={i} className={s.faqItem}>
          <button
            className={`${s.faqQ} ${open === i ? s.faqQOpen : ''}`}
            onClick={() => setOpen(open === i ? null : i)}
            type="button"
          >
            {faq.q}
            <svg
              className={`${s.faqChevron} ${open === i ? s.faqChevronOpen : ''}`}
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>
          <div className={`${s.faqA} ${open === i ? s.faqAOpen : ''}`}>
            <p className={s.faqAInner}>{faq.a}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
