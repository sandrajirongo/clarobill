import type { Metadata } from 'next';
import Link from 'next/link';
import s from './blog.module.css';

export const metadata: Metadata = {
  title: 'Medical Billing Resources — Clarobill',
  description: 'Guides on reading medical bills, understanding CPT codes, and disputing billing errors. Plain English, no jargon.',
};

// Newest first
const articles = [
  {
    slug: 'how-to-dispute-a-hospital-bill',
    title: 'How to Dispute a Hospital Bill: A Step-by-Step Guide',
    description: 'A practical guide to disputing hospital billing errors — from requesting your itemized bill to writing a dispute letter that actually gets results.',
    date: 'April 17, 2026',
    readTime: '9 min read',
  },
  {
    slug: 'medical-billing-advocates',
    title: 'Medical Billing Advocates: What They Do, What They Charge, and Whether You Need One',
    description: 'Advocates can recover real money from billing errors — but they typically keep 25–35% of what they save you. Here is when hiring one makes sense.',
    date: 'April 17, 2026',
    readTime: '7 min read',
  },
  {
    slug: 'how-to-read-an-itemized-medical-bill',
    title: 'How to Read an Itemized Medical Bill',
    description: 'What the columns, codes, and dollar amounts actually mean — and how to spot the line items that should not be there.',
    date: 'April 7, 2026',
    readTime: '7 min read',
  },
  {
    slug: 'common-medical-billing-errors',
    title: 'The Most Common Medical Billing Errors (And How to Dispute Them)',
    description: 'Duplicate charges, upcoded visits, unbundled procedures — here is what each one looks like on a real bill and what to say when you dispute it.',
    date: 'April 7, 2026',
    readTime: '8 min read',
  },
  {
    slug: 'what-are-cpt-codes',
    title: "What Are CPT Codes? A Patient's Guide",
    description: 'The five-digit numbers on your bill determine what you pay. Here is how they work, why they get abused, and how to check whether yours are right.',
    date: 'April 7, 2026',
    readTime: '6 min read',
  },
];

export default function BlogIndexPage(): JSX.Element {
  return (
    <div>
      <h1 className={s.indexH1}>Medical Billing Resources</h1>
      <p className={s.indexSub}>Plain-English guides to understanding and disputing your medical bills.</p>
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
              <span>{article.readTime}</span>
              <span>·</span>
              <span>Clarobill Team</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
