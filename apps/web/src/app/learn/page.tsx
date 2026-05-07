import type { Metadata } from 'next';
import Link from 'next/link';
import { JsonLd } from '@/components/json-ld';
import s from './learn.module.css';

export const metadata: Metadata = {
  title: 'Medical Billing Guides: Understand Your Bill and Fight Errors | ClaroBill',
  description:
    'Plain-English guides on reading medical bills, understanding your rights under federal law, disputing charges, and finding billing errors. Built on CMS fee schedules and hospital machine-readable files.',
  alternates: {
    canonical: 'https://www.clarobill.com/learn',
    languages: {
      'en': 'https://www.clarobill.com/learn',
      'x-default': 'https://www.clarobill.com/learn',
    },
  },
};

const BREADCRUMB = {
  '@type': 'BreadcrumbList' as const,
  itemListElement: [
    { '@type': 'ListItem' as const, position: 1, name: 'Home', item: 'https://www.clarobill.com' },
    { '@type': 'ListItem' as const, position: 2, name: 'Medical Billing Guides', item: 'https://www.clarobill.com/learn' },
  ],
};

const HUB_ARTICLE = {
  '@type': 'Article' as const,
  headline: 'Medical Billing Guides: Understand Your Bill and Fight Errors',
  description:
    'Plain-English guides on reading medical bills, understanding your rights, disputing charges, and finding billing errors.',
  url: 'https://www.clarobill.com/learn',
  datePublished: '2026-05-07',
  dateModified: '2026-05-07',
  author: { '@type': 'Person' as const, name: 'Sandra Jirongo', url: 'https://www.clarobill.com/about' },
  publisher: { '@type': 'Organization' as const, name: 'ClaroBill' },
};

const PILLARS = [
  {
    id: 'billing-errors',
    title: 'Billing errors',
    description:
      'The most common errors on hospital and physician bills, how to identify them on your itemized statement, and what each error means for what you owe. Duplicate charges, upcoded visits, and unbundled procedures together account for the majority of actionable disputes.',
    topics: [
      'Common medical billing errors',
      'Duplicate charges',
      'Upcoding',
      'Unbundling',
      'Balance billing',
      'Phantom charges',
    ],
  },
  {
    id: 'disputing',
    title: 'Disputing and negotiating',
    description:
      'How to dispute charges, from requesting your itemized bill through sending a formal dispute letter. Covers state-specific timelines, how to escalate to your state insurance commissioner, and what to do when a hospital sends your account to collections.',
    topics: [
      'How to dispute a medical bill',
      'Dispute letter templates',
      'How to negotiate a hospital bill',
      'Medical debt and credit reports',
      'Medical debt collections rights',
    ],
  },
  {
    id: 'patient-rights',
    title: 'Patient rights',
    description:
      'Federal and state laws that protect you as a patient. The No Surprises Act, the Hospital Price Transparency Rule, and your statutory right to an itemized bill are legal tools most patients never use because they do not know they exist.',
    topics: [
      'No Surprises Act',
      'Hospital Price Transparency Rule',
      'Right to an itemized bill',
      'Charity care and financial assistance',
      'State patient billing rights',
    ],
  },
  {
    id: 'reading-bills',
    title: 'Reading your bill',
    description:
      'What the columns, codes, and dollar amounts on a medical bill actually mean. CPT codes, revenue codes, the difference between billed charges and allowed amounts, and how to read an Explanation of Benefits (EOB) alongside the itemized bill.',
    topics: [
      'How to read an itemized hospital bill',
      'CPT codes explained',
      'Explanation of Benefits (EOB)',
      'Medicare fee schedule vs. billed charges',
      'Revenue codes and facility fees',
    ],
  },
  {
    id: 'scenarios',
    title: 'Specific billing scenarios',
    description:
      'Billing errors look different depending on the type of care. Emergency room bills, surgery bills, childbirth bills, and surprise anesthesiology charges each have their own error patterns and dispute paths.',
    topics: [
      'Emergency room bills',
      'Surprise anesthesiology bills',
      'Childbirth and maternity billing',
      'Surgery bill errors',
      'Ambulance billing',
    ],
  },
  {
    id: 'hospital-pricing-data',
    title: 'Hospital pricing data',
    description:
      'Under the Hospital Price Transparency Rule, every US hospital is required to publish a machine-readable file listing their negotiated rates. ClaroBill ingests these files for over 13,000 hospitals so your bill can be compared against what your insurer actually agreed to pay. These guides explain the data, how it is structured, and what discrepancies mean.',
    topics: [
      'Hospital machine-readable files explained',
      'Negotiated rate vs. chargemaster vs. Medicare',
      'NCCI edits for patients',
      'CMS Medicare fee schedule vs. your bill',
      'How to build an audit trail for a bill dispute',
      'Chargemaster effective dating',
    ],
  },
] as const;

export default function LearnPage(): JSX.Element {
  return (
    <>
      <JsonLd schema={[BREADCRUMB, HUB_ARTICLE]} />

      <div className={s.hero}>
        <p className={s.eyebrow}>Medical billing guides</p>
        <h1 className={s.title}>Understand your bill. Know your rights. Fight errors.</h1>
        <p className={s.lead}>
          Roughly 80 percent of medical bills contain at least one error. These guides cover every stage
          of the billing dispute process, from reading your itemized statement to sending a dispute letter
          backed by federal law. Every article draws on CMS fee schedules, NCCI edit tables, and
          negotiated-rate machine-readable files from over 13,000 US hospitals.
        </p>
      </div>

      <div className={s.pillars}>
        {PILLARS.map((pillar) => (
          <section key={pillar.id} id={pillar.id} className={s.pillar}>
            <h2 className={s.pillarTitle}>{pillar.title}</h2>
            <p className={s.pillarDesc}>{pillar.description}</p>
            <ul className={s.topics}>
              {pillar.topics.map((topic) => (
                <li key={topic} className={s.topic}>{topic}</li>
              ))}
            </ul>
          </section>
        ))}
      </div>

      <div className={s.cta}>
        <p className={s.ctaTitle}>Have a bill you need to check now?</p>
        <p className={s.ctaBody}>
          ClaroBill runs 13 deterministic rule checks against CMS data and your hospital&apos;s
          published rates, then generates a dispute letter with a citation for every finding.
        </p>
        <Link href="/auth/sign-up" className={s.ctaLink}>Check my bill for free</Link>
      </div>
    </>
  );
}
