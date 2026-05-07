import type { Metadata } from 'next';
import Image from 'next/image';
import Link from 'next/link';
import { MarketingNav } from '@/components/marketing-nav';
import { JsonLd } from '@/components/json-ld';
import s from './about.module.css';
import bs from '../blog/blog.module.css';

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
        <h1 className={bs.articleH1}>Built to read your bill the way your hospital does.</h1>

        <p className={bs.articleLead}>
          Roughly 80 percent of US medical bills contain at least one error. The problem is not malice. It is
          complexity: thousands of codes, insurer-specific contract rates, and pricing information
          that hospitals hold but patients rarely know how to access. ClaroBill closes that gap.
        </p>

        <div className={bs.articleBody}>
          <h2>Founder</h2>
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
                Seasoned data engineer based in Silicon Valley. Built the tool she needed.
              </p>
            </div>
          </div>

          <h2>Why we built this</h2>
          <p>
            My own medical bill is what kicked this off. The product I wished existed did not, so I built it.
          </p>
          <p>
            In 2021, a federal rule came into effect giving patients new access to pricing information
            their insurers had long relied on at the negotiating table. Almost no one built on it.
            ClaroBill does. Every analysis gives you what you need to dispute a charge with confidence.
          </p>

          <h2>Our data</h2>
          <p>
            Every finding we surface is traceable and verifiable. We maintain and update our
            reference data on a regular basis.
          </p>
          <p>
            Each finding in a ClaroBill report includes a citation and the exact dollar discrepancy,
            so you can verify it yourself before sending a dispute letter.
          </p>

          <h2>How the analysis works</h2>
          <p>
            ClaroBill does not guess. Every finding in your report is backed by a specific citation
            and the exact dollar discrepancy, so you can verify it independently before sending a
            dispute letter. That citation trail is what gets hospitals to correct bills.
          </p>


          <h2>Your data stays yours</h2>
          <p>
            We do not train on your data. We do not sell it. Your bill is used to generate your report
            and nothing else. Trust and transparency are at the heart of what we do.
          </p>

          <h2>What we are not</h2>
          <p>
            ClaroBill is a billing analysis tool. We are not a medical practice, law firm, or financial
            advisor. Our output is a report that identifies potential errors and a draft dispute letter for
            your personal use. See our{' '}
            <Link href="/legal/disclaimer">Medical and Legal Disclaimer</Link>.
          </p>
        </div>

        <Cta />
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

function Cta(): JSX.Element {
  return (
    <div className={bs.ctaBox}>
      <p className={bs.ctaTitle}>Ready to check your bill?</p>
      <p className={bs.ctaNote}>
        Upload your itemized bill and ClaroBill will identify every error, with a citation
        and the exact dollar discrepancy for each finding.
      </p>
      <Link href="/auth/sign-in" className={bs.ctaBtn}>Check my bill for free</Link>
    </div>
  );
}
