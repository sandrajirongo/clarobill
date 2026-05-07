import type { Metadata } from 'next';
import Link from 'next/link';
import { JsonLd } from '@/components/json-ld';
import s from '../blog/blog.module.css';
import ls from './learn.module.css';

export const metadata: Metadata = {
  title: 'Medical Billing Guides: Understand Your Bill and Fight Errors | ClaroBill',
  description:
    'Plain-English guides on reading medical bills, understanding your rights under federal law, disputing charges, and finding billing errors.',
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

interface Article {
  slug: string;
  title: string;
  description: string;
  date: string;
  readMins: number;
}

const PUBLISHED_ARTICLES: Article[] = [
  {
    slug: 'how-to-dispute-a-hospital-bill',
    title: 'How to Dispute a Hospital Bill: A Step-by-Step Guide',
    description: 'A practical guide to disputing hospital billing errors. From requesting your itemized bill to writing a dispute letter that actually gets results.',
    date: 'April 17, 2026',
    readMins: 9,
  },
  {
    slug: 'medical-billing-advocates',
    title: 'Medical Billing Advocates: What They Do, What They Charge, and Whether You Need One',
    description: 'Advocates can recover real money from billing errors. But they typically keep 25-35% of what they save you. Here is when hiring one makes sense.',
    date: 'April 17, 2026',
    readMins: 7,
  },
  {
    slug: 'how-to-read-an-itemized-medical-bill',
    title: 'How to Read an Itemized Medical Bill',
    description: 'What the columns, codes, and dollar amounts actually mean. Plus how to spot the line items that should not be there.',
    date: 'April 7, 2026',
    readMins: 7,
  },
  {
    slug: 'common-medical-billing-errors',
    title: 'The Most Common Medical Billing Errors (And How to Dispute Them)',
    description: 'Duplicate charges, upcoded visits, unbundled procedures. Here is what each one looks like on a real bill and what to say when you dispute it.',
    date: 'April 7, 2026',
    readMins: 8,
  },
  {
    slug: 'what-are-cpt-codes',
    title: "What Are CPT Codes? A Patient's Guide",
    description: 'The five-digit numbers on your bill determine what you pay. Here is how they work, why they get abused, and how to check whether yours are right.',
    date: 'April 7, 2026',
    readMins: 6,
  },
  {
    slug: 'why-bill-exceeds-insurer-negotiated-rate',
    title: 'Why Your Bill Is Higher Than What Your Insurer Pays',
    description: 'Chargemaster rates, negotiated rates, and Medicare rates. Understanding the gap between what hospitals charge and what they accept is the first step to disputing it.',
    date: 'May 7, 2026',
    readMins: 9,
  },
  {
    slug: 'hospital-machine-readable-files-explained',
    title: 'Hospital Machine-Readable Files: What They Are and How to Use Them',
    description: 'Every US hospital is required by federal law to publish its negotiated rates. Here is how to find that file, read it, and use the numbers to dispute an overcharge.',
    date: 'May 7, 2026',
    readMins: 8,
  },
  {
    slug: 'ncci-edits-explained-for-patients',
    title: 'NCCI Edits: The Federal Rules That Prevent Billing Abuse',
    description: 'The National Correct Coding Initiative defines which CPT codes can and cannot be billed together. Here is what that means for your bill and how to use it in a dispute.',
    date: 'May 7, 2026',
    readMins: 7,
  },
];

interface Topic {
  label: string;
  href?: string;
}

interface Pillar {
  id: string;
  title: string;
  description: string;
  topics: Topic[];
}

const PILLARS: Pillar[] = [
  {
    id: 'billing-errors',
    title: 'Billing errors',
    description:
      'The most common errors on hospital and physician bills, how to identify them on your itemized statement, and what each error means for what you owe.',
    topics: [
      { label: 'Common medical billing errors', href: '/learn/common-medical-billing-errors' },
      { label: 'Duplicate charges' },
      { label: 'Upcoding' },
      { label: 'Unbundling', href: '/learn/ncci-edits-explained-for-patients' },
      { label: 'Balance billing' },
      { label: 'Phantom charges' },
    ],
  },
  {
    id: 'disputing',
    title: 'Disputing and negotiating',
    description:
      'How to dispute charges, from requesting your itemized bill through sending a formal dispute letter. Covers state-specific timelines, how to escalate to your state insurance commissioner, and what to do when a hospital sends your account to collections.',
    topics: [
      { label: 'How to dispute a medical bill', href: '/learn/how-to-dispute-a-hospital-bill' },
      { label: 'Medical billing advocates', href: '/learn/medical-billing-advocates' },
      { label: 'Dispute letter templates' },
      { label: 'Medical debt and credit reports' },
      { label: 'Medical debt collections rights' },
    ],
  },
  {
    id: 'patient-rights',
    title: 'Patient rights',
    description:
      'Federal and state laws that protect you as a patient. The No Surprises Act, the Hospital Price Transparency Rule, and your statutory right to an itemized bill are legal tools most patients never use because they do not know they exist.',
    topics: [
      { label: 'No Surprises Act' },
      { label: 'Hospital Price Transparency Rule', href: '/learn/hospital-machine-readable-files-explained' },
      { label: 'Right to an itemized bill' },
      { label: 'Charity care and financial assistance' },
      { label: 'State patient billing rights' },
    ],
  },
  {
    id: 'reading-bills',
    title: 'Reading your bill',
    description:
      'What the columns, codes, and dollar amounts on a medical bill actually mean. CPT codes, revenue codes, the difference between billed charges and allowed amounts, and how to read an Explanation of Benefits alongside the itemized bill.',
    topics: [
      { label: 'How to read an itemized hospital bill', href: '/learn/how-to-read-an-itemized-medical-bill' },
      { label: 'CPT codes explained', href: '/learn/what-are-cpt-codes' },
      { label: 'Explanation of Benefits (EOB)' },
      { label: 'Medicare fee schedule vs. billed charges', href: '/learn/why-bill-exceeds-insurer-negotiated-rate' },
      { label: 'Revenue codes and facility fees' },
    ],
  },
  {
    id: 'hospital-pricing-data',
    title: 'Hospital pricing data',
    description:
      'Under the Hospital Price Transparency Rule, every US hospital is required to publish their negotiated rates. These guides explain what that data is, how to read it, and how to use it when disputing a charge.',
    topics: [
      { label: 'Hospital machine-readable files explained', href: '/learn/hospital-machine-readable-files-explained' },
      { label: 'Negotiated rate vs. chargemaster vs. Medicare', href: '/learn/why-bill-exceeds-insurer-negotiated-rate' },
      { label: 'NCCI edits for patients', href: '/learn/ncci-edits-explained-for-patients' },
    ],
  },
];

export default function LearnPage(): JSX.Element {
  return (
    <article>
      <JsonLd schema={[BREADCRUMB, HUB_ARTICLE]} />

      <div className={s.articleByline}>
        <span>Last reviewed: May 2026</span>
        <span>·</span>
        <span>Sandra Jirongo</span>
      </div>

      <h1 className={s.articleH1}>Understand your bill. Know your rights. Fight errors.</h1>

      <p className={s.articleLead}>
        Roughly 80 percent of medical bills contain at least one error. These guides cover every stage
        of the billing dispute process, from reading your itemized statement to sending a dispute letter
        backed by a verifiable citation.
      </p>

      <div className={s.articleGrid}>
        {PUBLISHED_ARTICLES.map((article) => (
          <div key={article.slug} className={s.articleCard}>
            <Link href={`/learn/${article.slug}`} className={s.articleCardTitle}>
              {article.title}
            </Link>
            <p className={s.articleCardDesc}>{article.description}</p>
            <div className={s.byline}>
              <span>{article.date}</span>
              <span>·</span>
              <span>{article.readMins} min read</span>
            </div>
          </div>
        ))}
      </div>

      <div className={s.articleBody}>
        <h2>What these guides cover</h2>
        {PILLARS.map((pillar) => (
          <section key={pillar.id} id={pillar.id}>
            <h3>{pillar.title}</h3>
            <p>{pillar.description}</p>
            <ul className={ls.topics}>
              {pillar.topics.map((topic) => (
                <li key={topic.label} className={ls.topic}>
                  {topic.href ? (
                    <Link href={topic.href} className={ls.topicLink}>{topic.label}</Link>
                  ) : (
                    topic.label
                  )}
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>

      <Cta />
    </article>
  );
}

function Cta(): JSX.Element {
  return (
    <div className={s.ctaBox}>
      <p className={s.ctaTitle}>Have a bill you need to check now?</p>
      <p className={s.ctaNote}>
        ClaroBill analyzes your bill for errors and overcharges, then generates a dispute
        letter with a verifiable citation for every finding.
      </p>
      <Link href="/auth/sign-in" className={s.ctaBtn}>Check my bill for free</Link>
    </div>
  );
}
