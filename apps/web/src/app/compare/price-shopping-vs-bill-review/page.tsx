import type { Metadata } from 'next';
import Link from 'next/link';
import { JsonLd } from '@/components/json-ld';
import s from '../../blog/blog.module.css';
import c from '../compare.module.css';

export const metadata: Metadata = {
  title: 'Hospital Price Shopping vs Medical Bill Review: Two Different Tools | ClaroBill',
  description:
    'Price shopping tools help you choose a lower-cost provider before care. Bill review finds errors after you have been charged. Both are useful. They are not the same thing.',
  alternates: {
    canonical: 'https://www.clarobill.com/compare/price-shopping-vs-bill-review',
    languages: { en: 'https://www.clarobill.com/compare/price-shopping-vs-bill-review', 'x-default': 'https://www.clarobill.com/compare/price-shopping-vs-bill-review' },
  },
};

const ARTICLE_SCHEMA = {
  '@type': 'Article' as const,
  headline: 'Hospital Price Shopping vs Medical Bill Review: Two Different Tools',
  description: 'Price shopping tools help you choose a lower-cost provider before care. Bill review finds errors after you have been charged.',
  url: 'https://www.clarobill.com/compare/price-shopping-vs-bill-review',
  datePublished: '2026-05-07',
  dateModified: '2026-05-07',
  author: { '@type': 'Person' as const, name: 'Sandra Jirongo', url: 'https://www.clarobill.com/authors/sandra-jirongo' },
  publisher: { '@type': 'Organization' as const, name: 'ClaroBill' },
};

const BREADCRUMB_SCHEMA = {
  '@type': 'BreadcrumbList' as const,
  itemListElement: [
    { '@type': 'ListItem' as const, position: 1, name: 'Home', item: 'https://www.clarobill.com' },
    { '@type': 'ListItem' as const, position: 2, name: 'Compare', item: 'https://www.clarobill.com/compare' },
    { '@type': 'ListItem' as const, position: 3, name: 'Price Shopping vs Bill Review', item: 'https://www.clarobill.com/compare/price-shopping-vs-bill-review' },
  ],
};

const FAQ_SCHEMA = {
  '@type': 'FAQPage' as const,
  mainEntity: [
    {
      '@type': 'Question' as const,
      name: 'What is the difference between hospital price shopping and medical bill review?',
      acceptedAnswer: { '@type': 'Answer' as const, text: 'Hospital price shopping is prospective: you compare provider prices before receiving care to find lower-cost options. Medical bill review is retrospective: you audit a bill you have already received to find errors and overcharges. Price shopping tools like Healthcare Bluebook help before care. Bill review tools like ClaroBill help after.' },
    },
    {
      '@type': 'Question' as const,
      name: 'Can I use price shopping data to dispute a bill after the fact?',
      acceptedAnswer: { '@type': 'Answer' as const, text: 'Sometimes. If you were charged significantly more than the published rate for your insurer in the hospital\'s machine-readable file, that discrepancy is disputable. For most billing errors, however, the dispute is based on NCCI rules, fee schedule rates, and duplicate detection rather than price comparison.' },
    },
    {
      '@type': 'Question' as const,
      name: 'Should I use both price shopping and bill review?',
      acceptedAnswer: { '@type': 'Answer' as const, text: 'Yes, at different stages. Use price shopping tools before scheduling elective procedures to compare facility and provider costs. Use bill review after receiving your itemized bill to check for errors. They are complementary, not competing.' },
    },
  ],
};

export default function PriceShoppingVsBillReview(): JSX.Element {
  return (
    <article>
      <JsonLd schema={[ARTICLE_SCHEMA, BREADCRUMB_SCHEMA, FAQ_SCHEMA]} />

      <div className={s.articleByline}>
        <span>Last reviewed: May 2026</span>
        <span>&middot;</span>
        <span>Sandra Jirongo</span>
      </div>

      <h1 className={s.articleH1}>Hospital Price Shopping vs Medical Bill Review</h1>

      <p className={s.articleLead}>
        Price shopping tools like Healthcare Bluebook help you find lower-cost providers before
        you receive care. Medical bill review tools like ClaroBill find errors in the bill after
        you have received care. These are different problems. Both matter.
      </p>

      <div className={s.articleBody}>
        <table className={c.scorecard}>
          <thead>
            <tr>
              <th>Dimension</th>
              <th>Price shopping tools</th>
              <th>Medical bill review</th>
            </tr>
          </thead>
          <tbody>
            <tr><td>When to use</td><td className={c.neutral}>Before care</td><td className={c.neutral}>After care</td></tr>
            <tr><td>What it does</td><td className={c.neutral}>Compare provider costs prospectively</td><td className={c.neutral}>Find errors in existing bill</td></tr>
            <tr><td>Finds billing errors</td><td className={c.lose}>No</td><td className={c.win}>Yes</td></tr>
            <tr><td>Generates dispute letter</td><td className={c.lose}>No</td><td className={c.win}>Yes, with citations</td></tr>
            <tr><td>Works on emergency care</td><td className={c.lose}>Limited — no choice of provider</td><td className={c.win}>Yes</td></tr>
            <tr><td>Requires advance planning</td><td className={c.lose}>Yes</td><td className={c.win}>No</td></tr>
            <tr><td>Uses MRF pricing data</td><td className={c.win}>Yes</td><td className={c.win}>Yes (ClaroBill)</td></tr>
            <tr><td>Catches duplicate charges</td><td className={c.lose}>No</td><td className={c.win}>Yes</td></tr>
          </tbody>
        </table>

        <div className={c.verdict}>
          <strong>The ideal sequence:</strong> Use a price shopping tool when scheduling elective
          procedures to pick a lower-cost facility or provider. Then use ClaroBill after care to
          check the bill you actually received for errors. Most billing errors cannot be prevented
          by shopping around in advance — they happen in the billing department regardless of
          which provider you chose.
        </div>

        <h2>What price shopping tools do</h2>
        <p>
          Tools like Healthcare Bluebook, Castlight, and ClearHealth Costs help patients compare
          estimated costs across providers before scheduling care. They pull from insurer negotiated
          rate databases and, since 2021, from hospital machine-readable files.
        </p>
        <p>
          Price shopping is most effective for elective, schedulable procedures: imaging, lab work,
          outpatient surgery, and specialist consultations. For emergency care, where you have no
          meaningful choice of provider, price shopping is not applicable. The No Surprises Act
          provides the relevant protection in that context.
        </p>
        <p>
          Price shopping does not help after the bill arrives. It cannot catch duplicate charges,
          upcoded visit levels, or unbundled procedures in an existing bill.
        </p>

        <h2>What medical bill review does</h2>
        <p>
          Medical bill review operates on the bill you already have. A tool like ClaroBill takes
          your itemized statement and runs it through a rules engine checking each CPT code against
          federal fee schedules, NCCI edit tables, and duplicate detection logic.
        </p>
        <p>
          Unlike price shopping, bill review catches errors that were introduced in the billing
          process itself: a coder who assigned the wrong complexity level, a billing system that
          double-charged a lab test, a procedure that should have been bundled but was not. These
          errors are independent of which provider you chose. They happen to patients at
          high-cost and low-cost hospitals alike.
        </p>
        <p>
          For a complete understanding of how hospital pricing data works and how it can be used
          both before and after care, see our guide to{' '}
          <Link href="/learn/hospital-machine-readable-files-explained">hospital machine-readable files</Link>.
        </p>

        <h2>Frequently asked questions</h2>
        {FAQ_SCHEMA.mainEntity.map((item) => (
          <div key={item.name}>
            <h3>{item.name}</h3>
            <p>{item.acceptedAnswer.text}</p>
          </div>
        ))}
      </div>

      <Cta />
    </article>
  );
}

function Cta(): JSX.Element {
  return (
    <div className={s.ctaBox}>
      <p className={s.ctaTitle}>Already received your bill? Check it for errors.</p>
      <p className={s.ctaNote}>ClaroBill finds errors in the bill you already have. Free analysis, flat fee only on findings.</p>
      <Link href="/auth/sign-in" className={s.ctaBtn}>Check my bill for free</Link>
    </div>
  );
}
