'use client';

import { useState } from 'react';
import s from '@/app/page.module.css';

const FAQS = [
  {
    q: 'What does ClaroBill do?',
    a: 'ClaroBill uses AI to scan your medical bill for billing errors — duplicate charges, upcoding, unbundled procedures, and charges for services not rendered. We produce a plain-English error report and a ready-to-send dispute letter you submit directly to your insurer or hospital.',
    defaultOpen: true,
  },
  {
    q: 'How does ClaroBill work?',
    a: 'Upload your medical bill as a PDF or image. Our AI cross-references every charge against Medicare fee schedules and NCCI billing rules. Within minutes you receive a detailed error report and a professionally written dispute letter citing every violation by name.',
  },
  {
    q: 'Do you negotiate on my behalf or contact the hospital?',
    a: 'No — ClaroBill gives you the report and the letter; you send it. We believe patients should stay in control of their own disputes. Our job is to arm you with documentation so precise and well-cited that billing departments have no choice but to take it seriously.',
  },
  {
    q: 'Do you support my insurance plan?',
    a: 'Yes — we connect with over 1,300 insurers and patient portals including BlueCross BlueShield, Aetna, Cigna, UnitedHealth, Oscar, and MyChart. We can also review bills for uninsured patients.',
  },
  {
    q: 'What does it cost?',
    a: 'Your first scan is completely free — you see exactly how many errors were found before paying anything. The full report and dispute letter are available for a flat fee. No hidden costs, no percentage of savings taken.',
  },
  {
    q: 'Can I add my partner, kids, or parents?',
    a: 'Yes. You can upload and review bills for any family member. Each bill is reviewed separately and generates its own report and dispute letter.',
  },
  {
    q: 'Is my information safe with ClaroBill?',
    a: 'Absolutely. We are HIPAA-aligned with end-to-end encryption on all uploads. Your bill is processed securely and never sold or shared with third parties.',
  },
] as const;

export function FaqAccordion(): JSX.Element {
  const [openIndex, setOpenIndex] = useState<number>(0);

  function toggle(i: number): void {
    setOpenIndex((prev) => (prev === i ? -1 : i));
  }

  return (
    <div className={s.faqList}>
      {FAQS.map((faq, i) => {
        const isOpen = openIndex === i;
        return (
          <div key={faq.q} className={s.faqItem}>
            <button
              className={`${s.faqQ} ${isOpen ? s.faqQOpen : ''}`}
              onClick={() => toggle(i)}
              aria-expanded={isOpen}
            >
              {faq.q}
              <svg
                className={`${s.faqChevron} ${isOpen ? s.faqChevronOpen : ''}`}
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                aria-hidden="true"
              >
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </button>
            <div className={`${s.faqA} ${isOpen ? s.faqAOpen : ''}`}>
              <div className={s.faqAInner}>{faq.a}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
