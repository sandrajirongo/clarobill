import type { Metadata } from 'next';
import Link from 'next/link';
import { MarketingNav } from '@/components/marketing-nav';
import { JsonLd } from '@/components/json-ld';
import { isBetaMode } from '@/lib/beta';
import s from './free-check.module.css';

export const metadata: Metadata = {
  title: 'Free Medical Bill Check: Find Errors Before You Pay | ClaroBill',
  description:
    'Run a free medical bill check in minutes. ClaroBill audits every line item for duplicate charges, upcoding, unbundling, and overcharges, then generates a dispute letter with a citation for every finding.',
  alternates: {
    canonical: 'https://www.clarobill.com/free-medical-bill-check',
    languages: {
      en: 'https://www.clarobill.com/free-medical-bill-check',
      'x-default': 'https://www.clarobill.com/free-medical-bill-check',
    },
  },
};

const BREADCRUMB_SCHEMA = {
  '@type': 'BreadcrumbList' as const,
  itemListElement: [
    { '@type': 'ListItem' as const, position: 1, name: 'Home', item: 'https://www.clarobill.com' },
    { '@type': 'ListItem' as const, position: 2, name: 'Free Medical Bill Check', item: 'https://www.clarobill.com/free-medical-bill-check' },
  ],
};

const PAGE_SCHEMA = {
  '@type': 'WebPage' as const,
  name: 'Free Medical Bill Check',
  description:
    'Upload your medical bill for a free error audit. ClaroBill checks every line item for duplicate charges, upcoding, unbundling, and overcharges. You only pay if errors are found.',
  url: 'https://www.clarobill.com/free-medical-bill-check',
  author: { '@type': 'Organization' as const, name: 'ClaroBill', url: 'https://www.clarobill.com' },
};

const FAQ_SCHEMA = {
  '@type': 'FAQPage' as const,
  mainEntity: [
    {
      '@type': 'Question' as const,
      name: 'Is the medical bill check really free?',
      acceptedAnswer: {
        '@type': 'Answer' as const,
        text: 'Yes. ClaroBill runs the full analysis at no cost. You only pay a one-time flat fee if errors worth disputing are found. If the analysis finds nothing actionable, you owe nothing.',
      },
    },
    {
      '@type': 'Question' as const,
      name: 'What types of medical bills can ClaroBill check?',
      acceptedAnswer: {
        '@type': 'Answer' as const,
        text: 'ClaroBill analyzes hospital bills, physician bills, outpatient facility bills, and Explanations of Benefits. It checks for duplicate charges, upcoded visit levels, unbundled CPT codes, price outliers against the Medicare fee schedule, and charges for services not rendered.',
      },
    },
    {
      '@type': 'Question' as const,
      name: 'How accurate is the medical bill check?',
      acceptedAnswer: {
        '@type': 'Answer' as const,
        text: 'Every finding is deterministic: each flag references a specific federal rule, a specific CPT code pair, or a specific published rate. ClaroBill does not flag subjective guesses. Every item in the report comes with a citation you can use directly in a dispute letter.',
      },
    },
    {
      '@type': 'Question' as const,
      name: 'How long does the bill check take?',
      acceptedAnswer: {
        '@type': 'Answer' as const,
        text: 'Most bills are analyzed within a few minutes. Complex inpatient bills with hundreds of line items may take slightly longer. You receive a notification when the report is ready.',
      },
    },
    {
      '@type': 'Question' as const,
      name: 'Is my medical bill data kept private?',
      acceptedAnswer: {
        '@type': 'Answer' as const,
        text: 'Yes. Uploads are encrypted in transit and at rest. ClaroBill does not sell, share, or use your bill to train AI models. Your data is used only to produce your audit report and dispute letter, and you can delete it at any time.',
      },
    },
    {
      '@type': 'Question' as const,
      name: 'What do I get in the dispute letter?',
      acceptedAnswer: {
        '@type': 'Answer' as const,
        text: 'The dispute letter is ready to send. For each error found, it includes the specific CPT code, the date of service, the charge amount, the rule being violated (NCCI edit, Medicare fee schedule, duplicate charge), and the corrected amount you should owe. It is formatted for submission by certified mail or email.',
      },
    },
  ],
};

const CHECKS = [
  {
    label: 'Duplicate charges',
    detail: 'The same CPT code billed twice on the same date.',
  },
  {
    label: 'Upcoded visits',
    detail: 'Office or ED visit level coded higher than documentation supports.',
  },
  {
    label: 'Unbundled procedures',
    detail: 'Component codes billed separately instead of as a single bundled code under NCCI rules.',
  },
  {
    label: 'Price outliers',
    detail: 'Charges that significantly exceed the Medicare fee schedule rate for the same service.',
  },
  {
    label: 'Phantom charges',
    detail: 'Charges for services with no supporting documentation or on dates not matching your stay.',
  },
  {
    label: 'Incorrect facility fees',
    detail: 'Outpatient services billed at inpatient or hospital outpatient rates without clinical justification.',
  },
  {
    label: 'Balance billing violations',
    detail: 'Out-of-network charges prohibited by the No Surprises Act.',
  },
  {
    label: 'Medically unlikely quantities',
    detail: 'Service units that exceed CMS Medically Unlikely Edit thresholds for the procedure.',
  },
];

export default function FreeCheckPage(): JSX.Element {
  const beta = isBetaMode();

  return (
    <div className={s.shell}>
      <JsonLd schema={[BREADCRUMB_SCHEMA, PAGE_SCHEMA, FAQ_SCHEMA]} />
      <MarketingNav />

      <section className={s.hero}>
        <div className={s.heroInner}>
          <div className={s.eyebrow}>No credit card required</div>
          <h1 className={s.h1}>Free medical bill check</h1>
          <p className={s.lead}>
            A free medical bill check is a line-by-line audit of every charge on your hospital or
            physician bill. ClaroBill runs the check automatically, flags errors backed by federal
            rule citations, and generates a ready-to-send dispute letter. Analysis is always free.
            {beta
              ? ' Everything is free during the beta.'
              : ' You only pay a one-time flat fee if errors worth disputing are found.'}
          </p>
          <Link href="/auth/sign-in" className={s.ctaBtn}>
            Check my bill. It&apos;s free.
          </Link>
          <p className={s.trustLine}>
            HIPAA-aligned &nbsp;&middot;&nbsp; Encrypted &nbsp;&middot;&nbsp; No auto-charges
          </p>
        </div>
      </section>

      <section className={s.checksSection}>
        <div className={s.checksInner}>
          <h2 className={s.sectionH2}>What the check looks for</h2>
          <p className={s.sectionSub}>
            Every flag in the report references a specific federal rule, CPT code pair, or published
            rate. Nothing is flagged without a citation you can use in a dispute.
          </p>
          <div className={s.checksGrid}>
            {CHECKS.map((c) => (
              <div key={c.label} className={s.checkCard}>
                <div className={s.checkMark}>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                </div>
                <div>
                  <p className={s.checkLabel}>{c.label}</p>
                  <p className={s.checkDetail}>{c.detail}</p>
                </div>
              </div>
            ))}
          </div>
          <p className={s.methodologyLink}>
            For the full methodology, federal citations, and worked examples for each check,
            see the{' '}
            <Link href="/methodology">methodology page</Link>.
          </p>
        </div>
      </section>

      <section className={s.howSection}>
        <div className={s.howInner}>
          <h2 className={s.sectionH2}>How it works</h2>
          <div className={s.howSteps}>
            <div className={s.howStep}>
              <div className={s.howNum}>1</div>
              <p className={s.howTitle}>Upload your bill</p>
              <p className={s.howBody}>PDF, photo, or EOB. We accept most formats.</p>
            </div>
            <div className={s.howStep}>
              <div className={s.howNum}>2</div>
              <p className={s.howTitle}>We audit every line item</p>
              <p className={s.howBody}>Each charge is checked against federal rules and published rates.</p>
            </div>
            <div className={s.howStep}>
              <div className={s.howNum}>3</div>
              <p className={s.howTitle}>You get a report and dispute letter</p>
              <p className={s.howBody}>Every finding cites the specific rule violated. The letter is ready to send.</p>
            </div>
          </div>
        </div>
      </section>

      <section className={s.faqSection}>
        <div className={s.faqInner}>
          <h2 className={s.sectionH2}>Common questions</h2>
          <div className={s.faqList}>
            {FAQ_SCHEMA.mainEntity.map((item) => (
              <div key={item.name} className={s.faqItem}>
                <p className={s.faqQ}>{item.name}</p>
                <p className={s.faqA}>{item.acceptedAnswer.text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className={s.ctaSection}>
        <h2 className={s.ctaH2}>Run the check now. It takes minutes.</h2>
        <Link href="/auth/sign-in" className={s.ctaBtn}>Upload your bill. It&apos;s free.</Link>
        <p className={s.trustLine}>No credit card &nbsp;&middot;&nbsp; HIPAA-aligned &nbsp;&middot;&nbsp; Encrypted</p>
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
