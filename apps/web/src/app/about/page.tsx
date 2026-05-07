import type { Metadata } from 'next';
import Image from 'next/image';
import Link from 'next/link';
import { MarketingNav } from '@/components/marketing-nav';
import { JsonLd } from '@/components/json-ld';
import s from './about.module.css';

export const metadata: Metadata = {
  title: 'About ClaroBill: AI Medical Bill Error Finder',
  description:
    'ClaroBill was built to fix a broken system. Learn about our mission, how we analyze medical bills, and what makes our approach different.',
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
    'Founder of ClaroBill. Built the product to give patients access to the same pricing data their insurers use at the negotiating table.',
};

const ORG_SCHEMA = {
  '@type': 'Organization' as const,
  name: 'ClaroBill',
  url: 'https://www.clarobill.com',
  description:
    'AI-powered medical bill error finder. ClaroBill analyzes hospital bills to find overcharges, duplicate charges, and coding errors, then generates a dispute letter with a citation for every finding.',
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
        <h1 className={s.pageTitle}>Built to read your bill the way your hospital does.</h1>
        <p className={s.lead}>
          Roughly 80 percent of US medical bills contain at least one error. The problem is not malice. It is
          complexity: thousands of CPT codes, insurer-specific contract rates, unbundling rules, and
          machine-readable files that hospitals publish but patients have never had tools to read. ClaroBill
          closes that gap.
        </p>

        <section className={s.section}>
          <h2 className={s.sectionTitle}>Why we built this</h2>
          <p className={s.body}>
            My own medical bill is what kicked this off. The product I wished existed did not, so I built it.
          </p>
          <p className={s.body}>
            In 2021, the federal Hospital Price Transparency Rule came into effect, requiring every US
            hospital to publish their negotiated rates in a machine-readable file. For the first time,
            patients had legal access to the same pricing data their insurers use at the negotiating table.
            Almost no one built on it.
          </p>
          <p className={s.body}>
            ClaroBill does. The full product, from analysis to dispute letter, shipped in three months.
            Every analysis compares your bill against the rates your hospital actually agreed to
            charge your insurer.
          </p>
        </section>

        <section className={s.section}>
          <h2 className={s.sectionTitle}>Founder</h2>
          <div className={s.founderCard}>
            <Image
              src="/team/sandra-jirongo.jpg"
              alt="Sandra Jirongo, Founder of ClaroBill"
              width={52}
              height={52}
              className={s.founderPhoto}
            />
            <div>
              <p className={s.founderName}>Sandra Jirongo</p>
              <p className={s.founderRole}>Founder</p>
              <p className={s.founderBio}>
                Sandra built ClaroBill after her own medical bill sent her through weeks of unanswered
                calls and codes she could not decode. She designed the analysis approach and the
                pricing data infrastructure that powers every ClaroBill report. The full product
                shipped solo in three months.
              </p>
            </div>
          </div>
        </section>

        <section className={s.section}>
          <h2 className={s.sectionTitle}>Our data</h2>
          <p className={s.body}>
            Every finding we surface has a traceable source in federal pricing data, hospital-published
            rate information required by law, and government provider registries. We verify and update
            these sources on a regular basis.
          </p>
          <p className={s.body}>
            Each finding in a ClaroBill report includes the specific federal authority and the rate used
            to calculate the discrepancy, so you can verify it yourself before sending a dispute letter.
          </p>
        </section>

        <section className={s.section}>
          <h2 className={s.sectionTitle}>How the analysis works</h2>
          <p className={s.body}>
            ClaroBill does not guess. Every finding in your report includes the federal authority and
            the specific rate used to calculate the discrepancy, so you can verify it independently
            before sending a dispute letter. That citation trail is what gets hospitals to correct bills.
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
