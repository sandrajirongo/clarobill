import type { Metadata } from 'next';
import Link from 'next/link';
import { getTranslations } from 'next-intl/server';
import s from './blog.module.css';

export const metadata: Metadata = {
  title: 'Medical Billing Resources — Clarobill',
  description: 'Guides on reading medical bills, understanding CPT codes, and disputing billing errors. Plain English, no jargon.',
};

// Newest first — titles/descriptions stay in English (SEO content)
const articles = [
  {
    slug: 'how-to-dispute-a-hospital-bill',
    title: 'How to Dispute a Hospital Bill: A Step-by-Step Guide',
    description: 'A practical guide to disputing hospital billing errors — from requesting your itemized bill to writing a dispute letter that actually gets results.',
    date: 'April 17, 2026',
    readMins: 9,
  },
  {
    slug: 'medical-billing-advocates',
    title: 'Medical Billing Advocates: What They Do, What They Charge, and Whether You Need One',
    description: 'Advocates can recover real money from billing errors — but they typically keep 25–35% of what they save you. Here is when hiring one makes sense.',
    date: 'April 17, 2026',
    readMins: 7,
  },
  {
    slug: 'how-to-read-an-itemized-medical-bill',
    title: 'How to Read an Itemized Medical Bill',
    description: 'What the columns, codes, and dollar amounts actually mean — and how to spot the line items that should not be there.',
    date: 'April 7, 2026',
    readMins: 7,
  },
  {
    slug: 'common-medical-billing-errors',
    title: 'The Most Common Medical Billing Errors (And How to Dispute Them)',
    description: 'Duplicate charges, upcoded visits, unbundled procedures — here is what each one looks like on a real bill and what to say when you dispute it.',
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
];

export default async function BlogIndexPage(): Promise<JSX.Element> {
  const t = await getTranslations('resources');
  return (
    <div>
      <h1 className={s.indexH1}>{t('title')}</h1>
      <p className={s.indexSub}>{t('subtitle')}</p>
      <div className={s.articleGrid}>
        {articles.map((article) => (
          <div key={article.slug} className={s.articleCard}>
            <Link href={`/blog/${article.slug}`} className={s.articleCardTitle}>
              {article.title}
            </Link>
            <p className={s.articleCardDesc}>{article.description}</p>
            <div className={s.byline}>
              <span>{article.date}</span>
              <span>·</span>
              <span>{t('minRead', { n: article.readMins })}</span>
              <span>·</span>
              <span>{t('team')}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
