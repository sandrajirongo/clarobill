import type { Metadata } from 'next';
import Link from 'next/link';
import { MarketingNav } from '@/components/marketing-nav';
import { JsonLd } from '@/components/json-ld';
import { MethodologyTrustBlock } from '@/components/methodology-trust-block';
import s from '../free-medical-bill-check/free-check.module.css';
import u from './upload.module.css';

export const metadata: Metadata = {
  title: 'Upload Your Medical Bill for a Free Error Check | ClaroBill',
  description:
    'Upload your hospital or physician bill and get a line-by-line audit in minutes. ClaroBill checks for duplicate charges, upcoding, unbundling, and overcharges, then writes your dispute letter.',
  alternates: {
    canonical: 'https://www.clarobill.com/upload',
    languages: {
      en: 'https://www.clarobill.com/upload',
      'x-default': 'https://www.clarobill.com/upload',
    },
  },
};

const BREADCRUMB_SCHEMA = {
  '@type': 'BreadcrumbList' as const,
  itemListElement: [
    { '@type': 'ListItem' as const, position: 1, name: 'Home', item: 'https://www.clarobill.com' },
    { '@type': 'ListItem' as const, position: 2, name: 'Upload Your Bill', item: 'https://www.clarobill.com/upload' },
  ],
};

const HOW_TO_SCHEMA = {
  '@type': 'HowTo' as const,
  name: 'How to upload a medical bill for a free error check',
  description:
    'Upload your hospital or physician bill to ClaroBill for a free line-by-line audit. The process takes under two minutes.',
  step: [
    { '@type': 'HowToStep' as const, name: 'Create a free account', text: 'Sign in or create a free ClaroBill account. No credit card required.' },
    { '@type': 'HowToStep' as const, name: 'Upload your bill', text: 'Upload your bill as a PDF or photo. We accept hospital bills, physician bills, and Explanations of Benefits.' },
    { '@type': 'HowToStep' as const, name: 'Get your audit report', text: 'ClaroBill analyzes every line item and flags errors with federal rule citations. You receive a full report and a ready-to-send dispute letter.' },
  ],
};

const ACCEPTED_FORMATS = [
  { label: 'PDF', detail: 'Hospital or physician bill, EOB, or itemized statement' },
  { label: 'JPG / PNG', detail: 'Clear photo of your printed bill' },
  { label: 'HEIC', detail: 'iPhone photo — converted automatically' },
];

const TRUST_ITEMS = [
  'Encrypted in transit and at rest',
  'HIPAA-aligned data handling',
  'Never used to train AI models',
  'Never sold to third parties',
  'Delete your data at any time',
];

export default function UploadPage(): JSX.Element {
  return (
    <div className={s.shell}>
      <JsonLd schema={[BREADCRUMB_SCHEMA, HOW_TO_SCHEMA]} />
      <MarketingNav />

      <section className={s.hero}>
        <div className={s.heroInner}>
          <div className={s.eyebrow}>Free analysis &middot; No credit card</div>
          <h1 className={s.h1}>Upload your medical bill</h1>
          <p className={s.lead}>
            ClaroBill audits every line item for errors and overcharges. Each finding references
            the specific federal rule violated. If no errors are found, you pay nothing.
          </p>
          <Link href="/auth/sign-in" className={s.ctaBtn}>
            Upload my bill. It&apos;s free.
          </Link>
          <p className={s.trustLine}>
            HIPAA-aligned &nbsp;&middot;&nbsp; Encrypted &nbsp;&middot;&nbsp; No auto-charges
          </p>
        </div>
      </section>

      <section className={s.checksSection}>
        <div className={s.checksInner}>
          <h2 className={s.sectionH2}>Accepted formats</h2>
          <div className={u.formatsGrid}>
            {ACCEPTED_FORMATS.map((f) => (
              <div key={f.label} className={u.formatCard}>
                <span className={u.formatLabel}>{f.label}</span>
                <p className={u.formatDetail}>{f.detail}</p>
              </div>
            ))}
          </div>

          <h2 className={s.sectionH2} style={{ marginTop: '3rem' }}>Your data stays yours</h2>
          <ul className={u.trustList}>
            {TRUST_ITEMS.map((item) => (
              <li key={item} className={u.trustItem}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
                {item}
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className={s.howSection}>
        <div className={s.howInner}>
          <h2 className={s.sectionH2}>What happens after you upload</h2>
          <div className={s.howSteps}>
            <div className={s.howStep}>
              <div className={s.howNum}>1</div>
              <p className={s.howTitle}>OCR reads your bill</p>
              <p className={s.howBody}>Every charge is extracted with its CPT code, date, quantity, and amount.</p>
            </div>
            <div className={s.howStep}>
              <div className={s.howNum}>2</div>
              <p className={s.howTitle}>Rules engine checks each line</p>
              <p className={s.howBody}>Each charge is compared against federal fee schedules, NCCI edit tables, and duplicate detection.</p>
            </div>
            <div className={s.howStep}>
              <div className={s.howNum}>3</div>
              <p className={s.howTitle}>Report and dispute letter generated</p>
              <p className={s.howBody}>Every error flagged includes the specific rule violated and the corrected amount. The letter is ready to send.</p>
            </div>
          </div>
        </div>
      </section>

      <section className={s.checksSection}>
        <div className={s.checksInner}>
          <MethodologyTrustBlock />
        </div>
      </section>

      <section className={s.ctaSection}>
        <h2 className={s.ctaH2}>Ready to check your bill?</h2>
        <Link href="/auth/sign-in" className={s.ctaBtn}>Upload my bill. It&apos;s free.</Link>
        <p className={s.trustLine}>
          No credit card &nbsp;&middot;&nbsp; HIPAA-aligned &nbsp;&middot;&nbsp; Encrypted
        </p>
      </section>

      <footer className={s.footer}>
        <div className={s.footerInner}>
          <span>&copy; {new Date().getFullYear()} ClaroBill</span>
          <nav className={s.footerLinks}>
            <Link href="/legal/privacy">Privacy</Link>
            <Link href="/legal/terms">Terms</Link>
            <Link href="/legal/disclaimer">Disclaimer</Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}
