import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Medical Billing Resources — Clarobill',
  description: 'Guides on reading medical bills, understanding CPT codes, and disputing billing errors. Plain English, no jargon.',
};

const articles = [
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
    title: 'What Are CPT Codes? A Patient\'s Guide',
    description: 'The five-digit numbers on your bill determine what you pay. Here is how they work, why they get abused, and how to check whether yours are right.',
    date: 'April 7, 2026',
    readTime: '6 min read',
  },
];

export default function BlogIndexPage(): JSX.Element {
  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900 mb-2">Medical Billing Resources</h1>
      <p className="text-gray-500 mb-12">
        Plain-English guides to understanding and disputing your medical bills.
      </p>
      <div className="space-y-10">
        {articles.map((article) => (
          <article key={article.slug} className="border-b border-gray-100 pb-10 last:border-0">
            <Link href={`/blog/${article.slug}`} className="group">
              <h2 className="text-xl font-semibold text-gray-900 group-hover:text-teal-600 transition-colors mb-2">
                {article.title}
              </h2>
            </Link>
            <p className="text-gray-500 mb-3 leading-relaxed">{article.description}</p>
            <div className="flex items-center gap-3 text-sm text-gray-400">
              <span>{article.date}</span>
              <span>·</span>
              <span>{article.readTime}</span>
              <span>·</span>
              <span>Clarobill Team</span>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
