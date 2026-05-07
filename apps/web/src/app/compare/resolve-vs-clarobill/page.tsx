import type { Metadata } from 'next';
import Link from 'next/link';
import { JsonLd } from '@/components/json-ld';
import s from '../../blog/blog.module.css';
import c from '../compare.module.css';

export const metadata: Metadata = {
  title: 'Resolve Medical Debt vs ClaroBill: Error Detection vs Debt Negotiation | ClaroBill',
  description:
    'Resolve helps negotiate down existing medical debt. ClaroBill finds billing errors before you pay. Different tools for different situations — here is how to choose.',
  alternates: {
    canonical: 'https://www.clarobill.com/compare/resolve-vs-clarobill',
    languages: { en: 'https://www.clarobill.com/compare/resolve-vs-clarobill', 'x-default': 'https://www.clarobill.com/compare/resolve-vs-clarobill' },
  },
};

const ARTICLE_SCHEMA = {
  '@type': 'Article' as const,
  headline: 'Resolve Medical Debt vs ClaroBill: Error Detection vs Debt Negotiation',
  description: 'Resolve helps negotiate down existing medical debt. ClaroBill finds billing errors before you pay. Different tools for different situations.',
  url: 'https://www.clarobill.com/compare/resolve-vs-clarobill',
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
    { '@type': 'ListItem' as const, position: 3, name: 'Resolve vs ClaroBill', item: 'https://www.clarobill.com/compare/resolve-vs-clarobill' },
  ],
};

const FAQ_SCHEMA = {
  '@type': 'FAQPage' as const,
  mainEntity: [
    {
      '@type': 'Question' as const,
      name: 'What is the difference between Resolve Medical Debt and ClaroBill?',
      acceptedAnswer: { '@type': 'Answer' as const, text: 'Resolve (YC W19) focuses on negotiating down the total amount of existing medical debt, often working with providers to settle accounts for less than the full balance. ClaroBill focuses on identifying billing errors in your itemized bill and generating dispute letters to correct those specific errors. Resolve is debt negotiation; ClaroBill is error detection.' },
    },
    {
      '@type': 'Question' as const,
      name: 'Should I use Resolve or ClaroBill first?',
      acceptedAnswer: { '@type': 'Answer' as const, text: 'Use ClaroBill first. If your bill contains errors, disputing those errors before negotiating the balance means you are negotiating from a corrected starting point, not an inflated one. Once the bill is accurate, if the total is still unaffordable, debt negotiation services become relevant.' },
    },
    {
      '@type': 'Question' as const,
      name: 'Can I use both Resolve and ClaroBill?',
      acceptedAnswer: { '@type': 'Answer' as const, text: 'Yes. They address different problems. ClaroBill finds errors in the bill itself. Resolve negotiates the total balance. Using ClaroBill first ensures that any debt negotiation starts from an accurate balance rather than one inflated by billing errors.' },
    },
  ],
};

export default function ResolveVsClarobill(): JSX.Element {
  return (
    <article>
      <JsonLd schema={[ARTICLE_SCHEMA, BREADCRUMB_SCHEMA, FAQ_SCHEMA]} />

      <div className={s.articleByline}>
        <span>Last reviewed: May 2026</span>
        <span>&middot;</span>
        <span>Sandra Jirongo</span>
      </div>

      <h1 className={s.articleH1}>Resolve Medical Debt vs ClaroBill</h1>

      <p className={s.articleLead}>
        Resolve negotiates down existing medical debt. ClaroBill finds billing errors before you
        pay. They solve different problems. In most cases, you want ClaroBill first.
      </p>

      <div className={s.articleBody}>
        <table className={c.scorecard}>
          <thead>
            <tr>
              <th>Dimension</th>
              <th>Resolve</th>
              <th>ClaroBill</th>
            </tr>
          </thead>
          <tbody>
            <tr><td>Primary purpose</td><td className={c.neutral}>Debt negotiation</td><td className={c.neutral}>Error detection</td></tr>
            <tr><td>When to use</td><td className={c.neutral}>After bill is final</td><td className={c.win}>Before paying anything</td></tr>
            <tr><td>Finds specific billing errors</td><td className={c.lose}>Not primary focus</td><td className={c.win}>Yes — line-by-line audit</td></tr>
            <tr><td>Dispute letter</td><td className={c.lose}>No</td><td className={c.win}>Yes, with citations</td></tr>
            <tr><td>Handles accounts in collections</td><td className={c.win}>Yes</td><td className={c.lose}>No</td></tr>
            <tr><td>Works on overdue accounts</td><td className={c.win}>Yes</td><td className={c.neutral}>Best before account ages</td></tr>
            <tr><td>Free to start</td><td className={c.neutral}>Varies by product</td><td className={c.win}>Yes — analysis always free</td></tr>
            <tr><td>Speed</td><td className={c.lose}>Days to weeks</td><td className={c.win}>Minutes</td></tr>
          </tbody>
        </table>

        <div className={c.verdict}>
          <strong>The right sequence:</strong> Use ClaroBill first to find and dispute billing errors.
          If the corrected bill is still unaffordable, Resolve or a financial assistance program
          (most hospitals offer charity care) is the next step. Negotiating an inflated bill is
          less effective than disputing it first and then negotiating the accurate balance.
        </div>

        <h2>What Resolve does</h2>
        <p>
          Resolve Medical Debt (YC W19) focuses on negotiating medical debt, typically for accounts
          that are already past due or in collections. Their service is positioned around making
          medical bills manageable through negotiated settlements, payment plans, and charity care
          enrollment.
        </p>
        <p>
          Resolve is valuable when you have a final bill you cannot pay in full and need someone
          to negotiate with the provider on your behalf. It does not identify line-by-line billing
          errors or generate dispute letters.
        </p>

        <h2>What ClaroBill does</h2>
        <p>
          ClaroBill analyzes the itemized bill itself, looking for errors in the charges before
          a dollar is paid. If a charge is a duplicate, incorrect, or overpriced, ClaroBill flags
          it with a specific citation and generates the dispute letter. This happens
          before the bill reaches final status.
        </p>
        <p>
          ClaroBill does not negotiate debt, work with collections agencies, or handle accounts
          that have been sent to collections. For that situation, see our guide to{' '}
          <Link href="/learn/medical-billing-advocates">medical billing advocates</Link>,
          some of whom specialize in collections-stage disputes.
        </p>

        <h2>Frequently asked questions</h2>
        {FAQ_SCHEMA.mainEntity.map((item) => (
          <div key={item.name}>
            <h3>{item.name}</h3>
            <p>{item.acceptedAnswer.text}</p>
          </div>
        ))}
      </div>

      <div className={c.disclaimer}>
        Competitor information is based on publicly available sources as of May 2026. ClaroBill
        has no relationship with Resolve and cannot guarantee the accuracy of third-party
        descriptions. Verify current information at resolve.com.
      </div>

      <Cta />
    </article>
  );
}

function Cta(): JSX.Element {
  return (
    <div className={s.ctaBox}>
      <p className={s.ctaTitle}>Check for errors before you negotiate</p>
      <p className={s.ctaNote}>ClaroBill finds what is wrong with the bill itself. Free analysis, flat fee only on findings.</p>
      <Link href="/auth/sign-in" className={s.ctaBtn}>Check my bill for free</Link>
    </div>
  );
}
