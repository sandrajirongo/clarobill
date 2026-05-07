import type { Metadata } from 'next';
import Link from 'next/link';
import { JsonLd } from '@/components/json-ld';
import s from '../../blog/blog.module.css';

export const metadata: Metadata = {
  title: 'Sandra Jirongo: Founder, ClaroBill | Medical Billing Guides',
  description:
    'Sandra Jirongo is the founder of ClaroBill. Seasoned data engineer based in Silicon Valley. She built the tool she needed after navigating a complex hospital bill herself.',
  alternates: {
    canonical: 'https://www.clarobill.com/authors/sandra-jirongo',
    languages: {
      en: 'https://www.clarobill.com/authors/sandra-jirongo',
      'x-default': 'https://www.clarobill.com/authors/sandra-jirongo',
    },
  },
};

const PERSON_SCHEMA = {
  '@type': 'Person' as const,
  name: 'Sandra Jirongo',
  url: 'https://www.clarobill.com/authors/sandra-jirongo',
  jobTitle: 'Founder, ClaroBill',
  description:
    'Seasoned data engineer based in Silicon Valley. Founded ClaroBill to give patients access to the same pricing data their insurers use at the negotiating table.',
  sameAs: [
    'https://www.linkedin.com/in/sandrajirongo/',
    'https://x.com/clarobillai',
  ],
  worksFor: {
    '@type': 'Organization' as const,
    name: 'ClaroBill',
    url: 'https://www.clarobill.com',
  },
  knowsAbout: [
    'Medical billing',
    'Hospital price transparency',
    'Medical billing error detection',
    'Patient billing rights',
    'Healthcare payment systems',
    'Healthcare data engineering',
  ],
};

const BREADCRUMB_SCHEMA = {
  '@type': 'BreadcrumbList' as const,
  itemListElement: [
    { '@type': 'ListItem' as const, position: 1, name: 'Home', item: 'https://www.clarobill.com' },
    { '@type': 'ListItem' as const, position: 2, name: 'Authors', item: 'https://www.clarobill.com/authors' },
    { '@type': 'ListItem' as const, position: 3, name: 'Sandra Jirongo', item: 'https://www.clarobill.com/authors/sandra-jirongo' },
  ],
};

const PUBLISHED_ARTICLES = [
  {
    slug: 'how-to-dispute-a-hospital-bill',
    title: 'How to Dispute a Hospital Bill: A Step-by-Step Guide',
    date: 'April 17, 2026',
    readMins: 9,
  },
  {
    slug: 'medical-billing-advocates',
    title: 'Medical Billing Advocates: What They Do, What They Charge, and Whether You Need One',
    date: 'April 17, 2026',
    readMins: 7,
  },
  {
    slug: 'how-to-read-an-itemized-medical-bill',
    title: 'How to Read an Itemized Medical Bill',
    date: 'April 7, 2026',
    readMins: 7,
  },
  {
    slug: 'common-medical-billing-errors',
    title: 'The Most Common Medical Billing Errors (And How to Dispute Them)',
    date: 'April 7, 2026',
    readMins: 8,
  },
  {
    slug: 'what-are-cpt-codes',
    title: "What Are CPT Codes? A Patient's Guide",
    date: 'April 7, 2026',
    readMins: 6,
  },
  {
    slug: 'why-bill-exceeds-insurer-negotiated-rate',
    title: 'Why Your Bill Is Higher Than What Your Insurer Pays',
    date: 'May 7, 2026',
    readMins: 9,
  },
  {
    slug: 'hospital-machine-readable-files-explained',
    title: 'Hospital Machine-Readable Files: What They Are and How to Use Them',
    date: 'May 7, 2026',
    readMins: 8,
  },
  {
    slug: 'ncci-edits-explained-for-patients',
    title: 'NCCI Edits: The Federal Rules That Prevent Billing Abuse',
    date: 'May 7, 2026',
    readMins: 7,
  },
];

export default function AuthorPage(): JSX.Element {
  return (
    <article>
      <JsonLd schema={[PERSON_SCHEMA, BREADCRUMB_SCHEMA]} />

      <h1 className={s.articleH1}>Sandra Jirongo</h1>

      <p className={s.articleLead}>
        Founder of ClaroBill. Seasoned data engineer based in Silicon Valley.
        Built the tool she needed.
      </p>

      <div className={s.articleBody}>
        <p>
          Sandra Jirongo founded ClaroBill after navigating a hospital bill that was wrong in three
          separate ways and took six months to correct. The experience convinced her that the tools
          patients need to audit their own bills should not require a coding background, a billing
          advocate on retainer, or six months of persistence.
        </p>
        <p>
          With a background in data engineering and large-scale data pipelines, she built the
          infrastructure to process publicly available hospital pricing data at scale and apply it
          automatically to individual patient bills. Every finding ClaroBill surfaces includes
          a specific citation and the exact dollar discrepancy for each error found.
        </p>
        <p>
          The guides below reflect what she learned while building ClaroBill and what she wishes
          she had known before the six-month detour.
        </p>

        <h2>Published guides</h2>
      </div>

      <div className={s.articleGrid}>
        {PUBLISHED_ARTICLES.map((article) => (
          <div key={article.slug} className={s.articleCard}>
            <Link href={`/learn/${article.slug}`} className={s.articleCardTitle}>
              {article.title}
            </Link>
            <div className={s.byline}>
              <span>{article.date}</span>
              <span>&middot;</span>
              <span>{article.readMins} min read</span>
            </div>
          </div>
        ))}
      </div>
    </article>
  );
}
