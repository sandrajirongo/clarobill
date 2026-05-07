import type { Metadata } from 'next';
import Link from 'next/link';
import { JsonLd } from '@/components/json-ld';
import s from '../../blog/blog.module.css';
import c from '../compare.module.css';

export const metadata: Metadata = {
  title: 'Goodbill vs ClaroBill: Which Medical Bill Review Service Is Right for You? | ClaroBill',
  description:
    'Goodbill uses human expert coders on contingency. ClaroBill uses deterministic AI with a flat fee. Here is an honest head-to-head on cost, speed, accuracy, and use case.',
  alternates: {
    canonical: 'https://www.clarobill.com/compare/goodbill-vs-clarobill',
    languages: { en: 'https://www.clarobill.com/compare/goodbill-vs-clarobill', 'x-default': 'https://www.clarobill.com/compare/goodbill-vs-clarobill' },
  },
};

const ARTICLE_SCHEMA = {
  '@type': 'Article' as const,
  headline: 'Goodbill vs ClaroBill: Which Medical Bill Review Service Is Right for You?',
  description: 'Goodbill uses human expert coders on contingency. ClaroBill uses deterministic AI with a flat fee. An honest head-to-head on cost, speed, accuracy, and use case.',
  url: 'https://www.clarobill.com/compare/goodbill-vs-clarobill',
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
    { '@type': 'ListItem' as const, position: 3, name: 'Goodbill vs ClaroBill', item: 'https://www.clarobill.com/compare/goodbill-vs-clarobill' },
  ],
};

const FAQ_SCHEMA = {
  '@type': 'FAQPage' as const,
  mainEntity: [
    {
      '@type': 'Question' as const,
      name: 'What is the difference between Goodbill and ClaroBill?',
      acceptedAnswer: { '@type': 'Answer' as const, text: 'Goodbill uses human medical billing experts who review your bill manually, typically on a contingency fee of around 50% of savings. ClaroBill uses a deterministic rules engine that checks every line item against federal rules and published rates, charges a flat one-time fee, and completes the analysis in minutes rather than days.' },
    },
    {
      '@type': 'Question' as const,
      name: 'Is Goodbill or ClaroBill better for large bills?',
      acceptedAnswer: { '@type': 'Answer' as const, text: "For very large bills (over $20,000) involving denied insurance claims or complex medical necessity disputes, Goodbill's human expert review and insurer negotiation experience may be worth the higher contingency fee. For common billing errors on bills of any size, ClaroBill's deterministic analysis is faster and significantly cheaper." },
    },
    {
      '@type': 'Question' as const,
      name: 'Does ClaroBill handle denied insurance claims?',
      acceptedAnswer: { '@type': 'Answer' as const, text: 'ClaroBill identifies billing errors and generates dispute letters for those errors. It does not handle insurance claim denials or medical necessity appeals, which require human advocates who can conduct peer-to-peer reviews with the insurer.' },
    },
  ],
};

export default function GoodbillVsClarobill(): JSX.Element {
  return (
    <article>
      <JsonLd schema={[ARTICLE_SCHEMA, BREADCRUMB_SCHEMA, FAQ_SCHEMA]} />

      <div className={s.articleByline}>
        <span>Last reviewed: May 2026</span>
        <span>&middot;</span>
        <span>Sandra Jirongo</span>
      </div>

      <h1 className={s.articleH1}>Goodbill vs ClaroBill</h1>

      <p className={s.articleLead}>
        Goodbill uses human medical coding experts on a contingency fee. ClaroBill uses a
        deterministic rules engine with a flat fee. Both find billing errors. The right choice
        depends on your bill size, error type, and how much you want to pay.
      </p>

      <div className={s.articleBody}>
        <table className={c.scorecard}>
          <thead>
            <tr>
              <th>Dimension</th>
              <th>Goodbill</th>
              <th>ClaroBill</th>
            </tr>
          </thead>
          <tbody>
            <tr><td>Cost</td><td className={c.lose}>~50% of savings</td><td className={c.win}>$0–$199.99 flat</td></tr>
            <tr><td>Speed</td><td className={c.lose}>Days to weeks</td><td className={c.win}>Minutes</td></tr>
            <tr><td>Error detection method</td><td className={c.neutral}>Human expert review</td><td className={c.neutral}>Deterministic rules engine</td></tr>
            <tr><td>Dispute letter included</td><td className={c.win}>Yes</td><td className={c.win}>Yes</td></tr>
            <tr><td>Citation for every finding</td><td className={c.neutral}>Varies by reviewer</td><td className={c.win}>Always — specific rule cited</td></tr>
            <tr><td>Handles denied claims</td><td className={c.win}>Yes</td><td className={c.lose}>No</td></tr>
            <tr><td>Insurer negotiation</td><td className={c.win}>Yes</td><td className={c.lose}>No</td></tr>
            <tr><td>Free to analyze</td><td className={c.lose}>No — contingency applies</td><td className={c.win}>Yes — analysis always free</td></tr>
            <tr><td>Works on bills under $5,000</td><td className={c.neutral}>Yes, but fee may be high</td><td className={c.win}>Yes — flat fee scales well</td></tr>
            <tr><td>HIPAA-aligned data handling</td><td className={c.win}>Yes</td><td className={c.win}>Yes</td></tr>
          </tbody>
        </table>

        <div className={c.verdict}>
          <strong>When to choose Goodbill:</strong> Your bill exceeds $20,000, involves a denied
          insurance claim, or requires a human to negotiate directly with your insurer. The 50%
          contingency fee is expensive, but human expertise in insurer negotiation is genuinely
          valuable for complex cases.
          <br /><br />
          <strong>When to choose ClaroBill:</strong> You have a bill of any size with mechanical
          billing errors (duplicates, upcoding, unbundling, price outliers). ClaroBill is
          significantly faster, cheaper, and provides a citation for every finding. If the analysis
          finds nothing, you pay nothing.
        </div>

        <h2>How Goodbill works</h2>
        <p>
          Goodbill was founded around 2020 and is backed by Google Ventures. Their model pairs you
          with a human medical billing expert who reviews your bill, identifies errors, and
          negotiates with your provider and insurer on your behalf. The fee is approximately 50% of
          whatever they recover. For a $10,000 error, Goodbill keeps around $5,000. You net $5,000.
        </p>
        <p>
          The human review model has genuine advantages: experienced coders catch nuanced errors
          that rules-based systems can miss, and they can conduct peer-to-peer insurer negotiations
          that software cannot. For denied claims and complex surgical bills, those advantages are
          worth the premium.
        </p>

        <h2>How ClaroBill works</h2>
        <p>
          ClaroBill processes your bill through a deterministic rules engine that checks every CPT
          code against federal fee schedules, NCCI edit tables, and published hospital rates. Every
          finding is a verifiable fact, not an interpretation. The analysis completes in minutes,
          not days, and generates a dispute letter with a specific citation for each error.
        </p>
        <p>
          The flat fee structure means ClaroBill is cheaper than Goodbill on almost any bill where
          errors are found. On a $500 correction: Goodbill keeps $250, you net $250. ClaroBill
          charges $79.99, you net $420. On a $1,500 correction: Goodbill keeps $750, you net $750.
          ClaroBill charges $199.99, you net $1,300.
        </p>
        <p>
          What ClaroBill does not do: insurer negotiation, peer-to-peer reviews, or handling denied
          claims. If those are what you need, Goodbill or a human advocate is the better choice.
          See our guide to{' '}
          <Link href="/learn/medical-billing-advocates">medical billing advocates</Link>{' '}
          for help deciding.
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
        has no relationship with Goodbill and cannot guarantee the accuracy of third-party
        pricing or feature descriptions. Verify current information at goodbill.com.
      </div>

      <Cta />
    </article>
  );
}

function Cta(): JSX.Element {
  return (
    <div className={s.ctaBox}>
      <p className={s.ctaTitle}>See what ClaroBill finds in your bill</p>
      <p className={s.ctaNote}>Free analysis. Flat fee only if errors are found. Every finding comes with a citation.</p>
      <Link href="/auth/sign-in" className={s.ctaBtn}>Check my bill for free</Link>
    </div>
  );
}
