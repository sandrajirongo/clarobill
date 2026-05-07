import type { Metadata } from 'next';
import Link from 'next/link';
import { MarketingNav } from '@/components/marketing-nav';
import { JsonLd } from '@/components/json-ld';
import s from './about.module.css';

export const metadata: Metadata = {
  title: 'About ClaroBill: AI Medical Bill Error Finder',
  description:
    'ClaroBill was built to fix a broken system. Learn about our mission, how the rules engine works, and why the hospital machine-readable file dataset is the foundation of every dispute letter we generate.',
  alternates: {
    canonical: 'https://www.clarobill.com/about',
    languages: {
      'en': 'https://www.clarobill.com/about',
      'x-default': 'https://www.clarobill.com/about',
    },
  },
};

const FOUNDER_SCHEMA = {
  '@type': 'Person' as const,
  name: 'Sandra Jirongo',
  url: 'https://www.clarobill.com/about',
  jobTitle: 'Founder',
  description:
    'Founder of ClaroBill. Built the rules engine and hospital MRF ingestion pipeline to give patients the same data their insurers have at the negotiating table.',
};

const ORG_SCHEMA = {
  '@type': 'Organization' as const,
  name: 'ClaroBill',
  url: 'https://www.clarobill.com',
  description:
    'AI-powered medical bill error finder. ClaroBill analyzes hospital bills against 13 deterministic rule checks and hospital machine-readable files to find overcharges, duplicate charges, and coding errors.',
  sameAs: [
    'https://www.instagram.com/clarobill/',
    'https://x.com/clarobillai',
    'https://www.linkedin.com/company/clarobill/',
  ],
};

export default function AboutPage(): JSX.Element {
  return (
    <div className={s.shell}>
      <JsonLd schema={[FOUNDER_SCHEMA, ORG_SCHEMA]} />
      <MarketingNav activePath="/about" />

      <main className={s.main}>
        <p className={s.eyebrow}>About ClaroBill</p>
        <h1 className={s.pageTitle}>A rules engine built to read the bill the way your hospital does.</h1>
        <p className={s.lead}>
          Roughly 80 percent of US medical bills contain at least one error. The problem is not malice. It is
          complexity: thousands of CPT codes, insurer-specific contract rates, unbundling rules, and
          machine-readable files that hospitals publish but patients have never had tools to read. ClaroBill
          closes that gap.
        </p>

        <section className={s.section}>
          <h2 className={s.sectionTitle}>Why we built this</h2>
          <p className={s.body}>
            The US hospital billing system is designed to be opaque. Patients receive bills weeks after
            discharge with codes they cannot decode, amounts that differ from their EOB, and no way to
            verify whether the charges are correct. Most patients pay without question. Those who dispute
            often do so without the data their insurer already has.
          </p>
          <p className={s.body}>
            ClaroBill was built to put that data in the hands of the patient. Every analysis runs the same
            13 deterministic checks that a hospital billing auditor would run, then compares each line item
            against what the hospital published in their federally mandated machine-readable file.
          </p>
        </section>

        <section className={s.section}>
          <h2 className={s.sectionTitle}>Founder</h2>
          <div className={s.founderCard}>
            <div className={s.founderAvatar} aria-hidden="true">SJ</div>
            <div>
              <p className={s.founderName}>Sandra Jirongo</p>
              <p className={s.founderRole}>Founder</p>
              <p className={s.founderBio}>
                Sandra built ClaroBill after encountering the gap between what hospitals charge and what
                the public data says they should. She designed the rules engine and the hospital
                machine-readable file ingestion pipeline that powers every ClaroBill analysis.
              </p>
            </div>
          </div>
        </section>

        <section className={s.section}>
          <h2 className={s.sectionTitle}>Data sources</h2>
          <p className={s.body}>
            Every finding ClaroBill surfaces has a traceable source. The four primary datasets:
          </p>
          <ul className={s.sourceList}>
            <li className={s.sourceItem}>
              <span className={s.sourceLabel}>CMS Medicare Physician Fee Schedule</span>
              <span className={s.sourceDesc}>National and locality-adjusted Medicare rates for 10,000+ CPT codes. Updated annually.</span>
            </li>
            <li className={s.sourceItem}>
              <span className={s.sourceLabel}>CMS Hospital Outpatient Prospective Payment</span>
              <span className={s.sourceDesc}>Medicare rates for hospital outpatient services. The benchmark for facility-fee disputes.</span>
            </li>
            <li className={s.sourceItem}>
              <span className={s.sourceLabel}>CMS NCCI Edit Tables</span>
              <span className={s.sourceDesc}>
                Procedure-to-procedure and medically unlikely edit pairs. The federal authority for
                unbundling detection.
              </span>
            </li>
            <li className={s.sourceItem}>
              <span className={s.sourceLabel}>Hospital Machine-Readable Files</span>
              <span className={s.sourceDesc}>
                Negotiated rates published by 13,000+ US hospitals under the Hospital Price Transparency
                Rule (45 CFR 180). The only public source of insurer-specific contracted rates.
              </span>
            </li>
            <li className={s.sourceItem}>
              <span className={s.sourceLabel}>NPPES NPI Registry</span>
              <span className={s.sourceDesc}>Provider identity and specialty data. Used to validate provider codes on each bill.</span>
            </li>
          </ul>
        </section>

        <section className={s.section}>
          <h2 className={s.sectionTitle}>How the analysis works</h2>
          <p className={s.body}>
            ClaroBill does not use a black-box AI model to decide whether a charge is wrong. Every finding
            is produced by a deterministic rule with a named federal authority and a specific data source.
            The dispute letter we generate cites the rule, the authority, and the exact dollar discrepancy.
            That citation trail is what gets hospitals to correct bills.
          </p>
          <p className={s.body}>
            <Link href="/methodology" className={s.methLink}>Read the full methodology</Link>
          </p>
        </section>

        <section className={s.section}>
          <h2 className={s.sectionTitle}>What we are not</h2>
          <p className={s.body}>
            ClaroBill is a billing analysis tool. We are not a medical practice, law firm, or financial
            advisor. Our output is a report that identifies potential errors and a draft dispute letter for
            your personal use. See our{' '}
            <Link href="/legal/disclaimer" className={s.methLink}>Medical and Legal Disclaimer</Link>.
          </p>
        </section>
      </main>

      <footer className={s.footer}>
        <div className={s.footerInner}>
          <span className={s.footerNote}>
            &copy; {new Date().getFullYear()} ClaroBill. All rights reserved.
          </span>
          <nav className={s.footerLinks}>
            <Link href="/legal/terms" className={s.footerLink}>Terms</Link>
            <Link href="/legal/privacy" className={s.footerLink}>Privacy</Link>
            <Link href="/legal/disclaimer" className={s.footerLink}>Disclaimer</Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}
