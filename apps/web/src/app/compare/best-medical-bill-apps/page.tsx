import type { Metadata } from 'next';
import Link from 'next/link';
import { JsonLd } from '@/components/json-ld';
import s from '../../blog/blog.module.css';
import c from '../compare.module.css';

export const metadata: Metadata = {
  title: 'Best Medical Bill Review Apps in 2026: An Honest Comparison | ClaroBill',
  description:
    'ClaroBill, Goodbill, CheckMedBill, and DIY. An honest comparison of the best tools for finding errors in medical bills, with specific trade-offs on cost, speed, and use case.',
  alternates: {
    canonical: 'https://www.clarobill.com/compare/best-medical-bill-apps',
    languages: { en: 'https://www.clarobill.com/compare/best-medical-bill-apps', 'x-default': 'https://www.clarobill.com/compare/best-medical-bill-apps' },
  },
};

const ARTICLE_SCHEMA = {
  '@type': 'Article' as const,
  headline: 'Best Medical Bill Review Apps in 2026: An Honest Comparison',
  description: 'ClaroBill, Goodbill, CheckMedBill, and DIY. An honest comparison of tools for finding errors in medical bills.',
  url: 'https://www.clarobill.com/compare/best-medical-bill-apps',
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
    { '@type': 'ListItem' as const, position: 3, name: 'Best Medical Bill Apps', item: 'https://www.clarobill.com/compare/best-medical-bill-apps' },
  ],
};

const FAQ_SCHEMA = {
  '@type': 'FAQPage' as const,
  mainEntity: [
    {
      '@type': 'Question' as const,
      name: 'What is the best app to check a medical bill for errors?',
      acceptedAnswer: { '@type': 'Answer' as const, text: 'For most patients, ClaroBill is the best starting point: it analyzes every line item deterministically against federal rules, generates a dispute letter with citations, and charges a flat fee only when errors are found. For very large bills involving denied claims or insurer negotiations, Goodbill\'s human expert model is worth considering despite the higher contingency fee.' },
    },
    {
      '@type': 'Question' as const,
      name: 'Is there a free medical bill review app?',
      acceptedAnswer: { '@type': 'Answer' as const, text: 'ClaroBill runs the analysis for free on every bill. You only pay a flat fee if errors worth disputing are found. CheckMedBill.com offers a free dispute letter generator but does not automatically detect errors. Doing it yourself is also free if you are willing to spend the time researching CPT codes and NCCI rules manually.' },
    },
    {
      '@type': 'Question' as const,
      name: 'How accurate are AI medical bill review apps?',
      acceptedAnswer: { '@type': 'Answer' as const, text: 'Deterministic rules-based systems like ClaroBill are highly accurate for the errors they are designed to detect (duplicates, upcoding, unbundling, price outliers) because each finding is a verifiable fact matched against a federal rule or published rate. AI systems that use generative models to interpret bills are less consistent and may produce false positives. ClaroBill\'s approach is deterministic first, with AI used only for interpretation of complex cases.' },
    },
  ],
};

const OPTIONS = [
  {
    name: 'ClaroBill',
    cost: '$0–$199.99 flat',
    speed: 'Minutes',
    errorDetection: 'Deterministic rules engine',
    disputeLetter: 'Yes — with citations',
    deniedClaims: 'No',
    best: 'Most patients — mechanical errors on any bill size',
  },
  {
    name: 'Goodbill',
    cost: '~50% of savings',
    speed: 'Days to weeks',
    errorDetection: 'Human expert review',
    disputeLetter: 'Yes',
    deniedClaims: 'Yes',
    best: 'Large bills and denied claims requiring negotiation',
  },
  {
    name: 'CheckMedBill.com',
    cost: 'Free',
    speed: 'Manual',
    errorDetection: 'User-driven — no auto-detection',
    disputeLetter: 'Template only',
    deniedClaims: 'No',
    best: 'Patients who have already identified the error and need a letter',
  },
  {
    name: 'DIY',
    cost: 'Free',
    speed: 'Hours of research',
    errorDetection: 'Manual — requires CPT/NCCI knowledge',
    disputeLetter: 'Write your own',
    deniedClaims: 'With enough research',
    best: 'Patients with billing knowledge and time',
  },
];

export default function BestMedicalBillApps(): JSX.Element {
  return (
    <article>
      <JsonLd schema={[ARTICLE_SCHEMA, BREADCRUMB_SCHEMA, FAQ_SCHEMA]} />

      <div className={s.articleByline}>
        <span>Last reviewed: May 2026</span>
        <span>&middot;</span>
        <span>Sandra Jirongo</span>
      </div>

      <h1 className={s.articleH1}>Best Medical Bill Review Apps in 2026</h1>

      <p className={s.articleLead}>
        The options for reviewing a medical bill range from free templates to human experts who
        take 50% of savings. This is an honest comparison of the main options, their trade-offs,
        and the situations each one is built for.
      </p>

      <div className={s.articleBody}>
        <table className={c.scorecard}>
          <thead>
            <tr>
              <th>Option</th>
              <th>Cost</th>
              <th>Speed</th>
              <th>Auto error detection</th>
              <th>Dispute letter</th>
              <th>Denied claims</th>
            </tr>
          </thead>
          <tbody>
            {OPTIONS.map((opt, i) => (
              <tr key={opt.name} className={i === 0 ? 'highlight' : ''}>
                <td style={{ fontWeight: 600 }}>{opt.name}</td>
                <td>{opt.cost}</td>
                <td>{opt.speed}</td>
                <td>{opt.errorDetection}</td>
                <td>{opt.disputeLetter}</td>
                <td>{opt.deniedClaims}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <h2>ClaroBill</h2>
        <p>
          ClaroBill uses a deterministic rules engine to check every CPT code against federal fee
          schedules, NCCI edit tables, and duplicate detection logic. Every finding references the
          specific rule violated. The dispute letter is generated automatically and is ready to send.
        </p>
        <p>
          Cost: free to analyze, flat fee only if errors are found ($0 to $199.99 depending on
          savings). Does not handle denied claims or insurer negotiation.
        </p>
        <p><strong>Best for:</strong> Most patients with billing errors on bills of any size.</p>

        <h2>Goodbill</h2>
        <p>
          Goodbill pairs you with a human medical billing expert who reviews your bill and
          negotiates with your provider and insurer. The contingency fee is approximately 50% of
          savings. The human model is slower than software but adds genuine value for complex
          cases involving denied claims and large surgical bills.
        </p>
        <p><strong>Best for:</strong> Bills over $20,000 with denied claims or insurer negotiations.</p>

        <h2>CheckMedBill.com</h2>
        <p>
          CheckMedBill offers a free dispute letter generator but does not automatically detect
          errors. You need to identify what is wrong with your bill yourself, then use the tool
          to format the letter. Useful if you already know what the error is and just need a
          well-formatted letter.
        </p>
        <p><strong>Best for:</strong> Patients who have already identified the error and need letter formatting.</p>

        <h2>Doing it yourself</h2>
        <p>
          DIY is free and gives you full control. You request the itemized bill, look up CPT codes
          against the Medicare fee schedule, check pairs against the NCCI edit tables, and write
          your own dispute letter. Our{' '}
          <Link href="/learn/common-medical-billing-errors">billing errors guide</Link> and{' '}
          <Link href="/learn/how-to-dispute-a-hospital-bill">dispute guide</Link> cover the full
          process. The downside is time: a thorough manual audit of a complex hospital bill takes
          several hours and requires familiarity with coding rules.
        </p>
        <p><strong>Best for:</strong> Patients with billing knowledge, time, and a specific error they want to dispute.</p>

        <h2>Frequently asked questions</h2>
        {FAQ_SCHEMA.mainEntity.map((item) => (
          <div key={item.name}>
            <h3>{item.name}</h3>
            <p>{item.acceptedAnswer.text}</p>
          </div>
        ))}
      </div>

      <div className={c.disclaimer}>
        Competitor information is based on publicly available sources as of May 2026 and is
        provided for informational purposes only. ClaroBill has no relationship with the companies
        listed and cannot guarantee the accuracy of third-party pricing or features.
        Verify current information at each provider&rsquo;s website.
      </div>

      <Cta />
    </article>
  );
}

function Cta(): JSX.Element {
  return (
    <div className={s.ctaBox}>
      <p className={s.ctaTitle}>See what ClaroBill finds in your bill</p>
      <p className={s.ctaNote}>Free analysis. Flat fee only if errors worth disputing are found. Every finding cited.</p>
      <Link href="/auth/sign-in" className={s.ctaBtn}>Check my bill for free</Link>
    </div>
  );
}
