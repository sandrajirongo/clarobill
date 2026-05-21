'use client';

import { useState } from 'react';
import s from '@/app/page.module.css';

const FAQS = [
  {
    q: 'What does ClaroBill do?',
    a: 'ClaroBill reviews your medical bill for the kinds of errors that quietly inflate what patients pay. That includes duplicate charges, miscoded procedures, services that were never rendered, and amounts that exceed what the hospital or your insurer has agreed to charge. You receive a plain-English report of every finding and a ready-to-send dispute letter you submit directly to your insurer or hospital.',
    defaultOpen: true,
  },
  {
    q: 'How does ClaroBill work?',
    a: 'Upload your bill as a PDF or image. Our analysis engine runs a deep audit across every line item to find errors, duplicates, and overcharges. Within minutes you receive a detailed error report and a tailored dispute letter that names each finding and cites the basis for the dispute.',
  },
  {
    q: 'Do you negotiate on my behalf or contact the hospital?',
    a: "No. ClaroBill gives you the report and the letter; you send it. Patients should stay in control of their own disputes. Our job is to give you documentation so precise and well-cited that billing departments take it seriously.",
  },
  {
    q: 'Do you support my insurance plan?',
    a: 'Yes. We work across every major US health insurer, including BlueCross BlueShield, Aetna, Cigna, UnitedHealthcare, Humana, Kaiser Permanente, Anthem, Oscar, Molina, Centene, and WellCare. We also support Medicare, Medicaid, and TRICARE. And we review bills for self-pay and uninsured patients. Our review works the same regardless of who your insurer is.',
  },
  {
    q: 'What does it cost?',
    a: 'The analysis itself is always free. You see exactly how many errors were found before paying anything. If we find nothing, you pay nothing, ever. If we do find errors, the fee scales with the dollar value of the savings. See the pricing page for full tier details.',
  },
  {
    q: 'Can I add my partner, kids, or parents?',
    a: 'Yes. You can upload and review bills for any family member. Each bill is reviewed separately and generates its own report and dispute letter.',
  },
  {
    q: 'Do you use my bill to train AI models?',
    a: "No. We do not use your bill, your personal information, or any data you upload to train AI models, ours or anyone else's. We do not sell, license, or share your data with advertisers, data brokers, or third parties for marketing. Your bill is used only to produce your audit report and dispute letter.",
  },
  {
    q: 'Is my information safe with ClaroBill?',
    a: 'Yes. Uploads are encrypted in transit and at rest. Access is restricted to the systems that produce your report and is logged for audit. We retain your bill only as long as your account is active; you can delete it at any time. We never sell or share your data.',
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
