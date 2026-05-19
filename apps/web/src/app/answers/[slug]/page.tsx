import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { JsonLd } from '@/components/json-ld';
import { ArticleBreadcrumb } from '@/components/article-breadcrumb';
import { ANSWERS, type AnswerPage } from '@/lib/answers-data';
import s from '../../blog/blog.module.css';

const BASE = 'https://answers.clarobill.com';

export function generateStaticParams(): { slug: string }[] {
  return ANSWERS.map((a) => ({ slug: a.slug }));
}

export function generateMetadata({ params }: { params: { slug: string } }): Metadata {
  const article = ANSWERS.find((a) => a.slug === params.slug);
  if (!article) return {};
  const url = `${BASE}/${article.slug}`;
  return {
    title: article.metaTitle,
    description: article.description,
    alternates: {
      canonical: url,
      languages: { en: url, 'x-default': url },
    },
  };
}

export default function AnswerArticlePage({ params }: { params: { slug: string } }): JSX.Element {
  const article = ANSWERS.find((a) => a.slug === params.slug);
  if (!article) notFound();
  return <AnswerArticle article={article} />;
}

function AnswerArticle({ article }: { article: AnswerPage }): JSX.Element {
  const url = `${BASE}/${article.slug}`;

  const articleSchema = {
    '@type': 'Article' as const,
    headline: article.h1,
    description: article.description,
    url,
    datePublished: article.date,
    dateModified: article.date,
    author: { '@type': 'Person' as const, name: 'ClaroBill Team', url: 'https://www.clarobill.com/about' },
    publisher: { '@type': 'Organization' as const, name: 'ClaroBill' },
  };

  const breadcrumbSchema = {
    '@type': 'BreadcrumbList' as const,
    itemListElement: [
      { '@type': 'ListItem' as const, position: 1, name: 'Home', item: BASE },
      { '@type': 'ListItem' as const, position: 2, name: article.h1, item: url },
    ],
  };

  const faqSchema = {
    '@type': 'FAQPage' as const,
    mainEntity: article.faqs.map((f) => ({
      '@type': 'Question' as const,
      name: f.q,
      acceptedAnswer: { '@type': 'Answer' as const, text: f.a },
    })),
  };

  return (
    <article>
      <JsonLd schema={[articleSchema, breadcrumbSchema, faqSchema]} />

      <ArticleBreadcrumb
        items={[
          { label: 'Home', href: '/' },
          { label: article.h1 },
        ]}
      />

      <div className={s.articleByline}>
        <span>{article.date}</span>
        <span>·</span>
        <span>{article.readTime}</span>
        <span>·</span>
        <span>ClaroBill Team</span>
      </div>

      <h1 className={s.articleH1}>{article.h1}</h1>

      <p className={s.articleLead}>{article.lead}</p>

      <div className={s.articleBody}>
        {article.sections.map((section) => (
          <div key={section.h2}>
            <h2>{section.h2}</h2>
            {section.paragraphs.map((p, i) => (
              <p key={i}>{p}</p>
            ))}
            {section.list && (
              section.list.type === 'ul' ? (
                <ul>
                  {section.list.items.map((item, i) => <li key={i}>{item}</li>)}
                </ul>
              ) : (
                <ol>
                  {section.list.items.map((item, i) => <li key={i}>{item}</li>)}
                </ol>
              )
            )}
            {section.paragraphsAfter?.map((p, i) => (
              <p key={`after-${i}`}>{p}</p>
            ))}
          </div>
        ))}

        <h2>Frequently asked questions</h2>
        {article.faqs.map((f) => (
          <div key={f.q}>
            <h3>{f.q}</h3>
            <p>{f.a}</p>
          </div>
        ))}
      </div>

      <Sources sources={article.sources} />
      <Cta />
      <Related items={article.related} />
    </article>
  );
}

function Sources({ sources }: { sources: AnswerPage['sources'] }): JSX.Element {
  return (
    <div className={s.sourcesSection}>
      <p className={s.sourcesLabel}>Sources</p>
      <ol style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {sources.map((src, i) => (
          <li key={src.url} className={s.sourceItem}>
            <span style={{ marginRight: '.4rem', opacity: .5 }}>{i + 1}.</span>
            <a href={src.url} target="_blank" rel="noopener noreferrer" className={s.sourceLink}>
              {src.label}
            </a>
          </li>
        ))}
      </ol>
    </div>
  );
}

function Cta(): JSX.Element {
  return (
    <div className={s.ctaBox}>
      <p className={s.ctaTitle}>Check your bill for errors</p>
      <p className={s.ctaNote}>
        Upload your itemized bill and get a plain-English report showing every
        charge that looks wrong and exactly how to dispute it.
      </p>
      <Link href="https://www.clarobill.com/auth/sign-in" className={s.ctaBtn}>
        Check my bill for free
      </Link>
    </div>
  );
}

function Related({ items }: { items: AnswerPage['related'] }): JSX.Element {
  return (
    <div className={s.relatedSection}>
      <p className={s.relatedLabel}>Related guides</p>
      <div>
        {items.map((item) => (
          <Link
            key={item.href}
            href={`https://www.clarobill.com${item.href}`}
            className={s.relatedLink}
          >
            {item.label} →
          </Link>
        ))}
      </div>
    </div>
  );
}
