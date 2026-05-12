import type { Metadata } from 'next';
import Link from 'next/link';
import { BillingTrapsForm } from '@/components/billing-traps-form';
import s from './billing-traps-guide.module.css';

export const metadata: Metadata = {
  title: 'Free Guide: 8 Common Medical Billing Traps | ClaroBill',
  description:
    'Download the free ClaroBill guide to the most common medical billing errors. Learn how to spot duplicate charges, upcoding, unbundling, and more.',
  openGraph: {
    title: 'Free Guide: 8 Common Medical Billing Traps',
    description:
      'Download our free guide to see if your hospital is using these same tactics on your bill.',
    type: 'website',
  },
};

const WHAT_INSIDE = [
  'The 3 billing errors that appear on over half of hospital bills',
  'How to read a CPT code and catch upcoding in 60 seconds',
  'When balance billing is illegal and what to do about it',
  'The exact script for disputing each type of error',
  'How to request documents providers are required by law to give you',
  'A line-by-line checklist for reviewing any itemized bill',
];

export default function BillingTrapsGuidePage(): JSX.Element {
  return (
    <main className={s.page}>
      <header className={s.siteHeader}>
        <Link href="/" className={s.wordmark}>
          Claro<em>Bill</em><span className={s.dot}>.</span>
        </Link>
      </header>

      <section className={s.hero}>
        <div className={s.badge}>Free download</div>

        <h1 className={s.headline}>
          8 Billing Traps That Cost Patients Thousands
        </h1>

        <p className={s.subhead}>
          Download our guide to see if your hospital is using these same tactics on your bill.
        </p>

        <div className={s.card}>
          <div className={s.cardPreview}>
            <div className={s.guideThumb}>
              <span className={s.thumbWordmark}>Claro<em>Bill</em><span className={s.thumbDot}>.</span></span>
              <span className={s.thumbTitle}>8 Common<br/>Billing Traps</span>
              <div className={s.thumbLines}>
                <span /><span /><span /><span /><span />
              </div>
            </div>
          </div>

          <div className={s.cardContent}>
            <p className={s.whatsInside}>What is inside</p>
            <ul className={s.checklist}>
              {WHAT_INSIDE.map((item) => (
                <li key={item} className={s.checkItem}>
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                    <circle cx="8" cy="8" r="8" fill="var(--sage, #2D4A2A)" />
                    <path d="M4.5 8.5l2.5 2.5 4.5-5" stroke="var(--accent, #C8F060)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  {item}
                </li>
              ))}
            </ul>

            <div className={s.formSection}>
              <p className={s.formLabel}>Enter your email to get instant access</p>
              <BillingTrapsForm />
              <p className={s.disclaimer}>No spam. Unsubscribe anytime.</p>
            </div>
          </div>
        </div>
      </section>

      <footer className={s.footer}>
        <Link href="/" className={s.footerLink}>clarobill.com</Link>
        <span className={s.footerSep} aria-hidden="true">·</span>
        <Link href="/legal/privacy" className={s.footerLink}>Privacy</Link>
      </footer>
    </main>
  );
}
