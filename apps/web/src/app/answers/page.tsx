import type { Metadata } from 'next';
import Link from 'next/link';
import { ANSWERS } from '@/lib/answers-data';
import s from '../blog/blog.module.css';

const BASE = 'https://answers.clarobill.com';

export const metadata: Metadata = {
  title: 'Medical Billing Answers | ClaroBill',
  description:
    'Plain-English answers to the most common medical billing questions. Dispute letters, billing errors, insurance denials, surprise bills, and your legal rights.',
  alternates: {
    canonical: BASE,
  },
};

export default function AnswersHub(): JSX.Element {
  return (
    <>
      <h1 className={s.indexH1}>Medical Billing Answers</h1>
      <p className={s.indexSub}>
        Plain-English answers to the most common questions about medical bills,
        insurance, and your rights as a patient.
      </p>
      <div className={s.articleGrid}>
        {ANSWERS.map((article) => (
          <div key={article.slug} className={s.articleCard}>
            <Link href={`/${article.slug}`} className={s.articleCardTitle}>
              {article.h1}
            </Link>
            <p className={s.articleCardDesc}>{article.description}</p>
            <div className={s.byline}>
              <span>{article.date}</span>
              <span>·</span>
              <span>{article.readTime}</span>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
