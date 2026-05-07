import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { JsonLd } from '@/components/json-ld';
import { getStateBySlug, STATE_DATA } from '@/lib/state-billing-data';
import s from '../../../../blog/blog.module.css';
import ss from './state-billing.module.css';

const BASE = 'https://www.clarobill.com';

type Props = { params: { state: string } };

export function generateStaticParams() {
  return STATE_DATA.map((d) => ({ state: d.slug }));
}

export function generateMetadata({ params }: Props): Metadata {
  const d = getStateBySlug(params.state);
  if (!d) return {};
  const url = `${BASE}/learn/state/${d.slug}/patient-billing-rights`;
  return {
    title: `${d.name} Patient Billing Rights | ClaroBill`,
    description: `Know your rights when disputing a medical bill in ${d.name}. Federal protections, state-specific laws, and how to contact ${d.agencyName}.`,
    alternates: {
      canonical: url,
      languages: { en: url, 'x-default': url },
    },
  };
}

export default function StateBillingRightsPage({ params }: Props): JSX.Element {
  const d = getStateBySlug(params.state);
  if (!d) notFound();

  const pageUrl = `${BASE}/learn/state/${d.slug}/patient-billing-rights`;

  const ARTICLE_SCHEMA = {
    '@type': 'Article' as const,
    headline: `${d.name} Patient Billing Rights`,
    description: `Federal and state-specific medical billing rights for patients in ${d.name}.`,
    url: pageUrl,
    datePublished: '2026-05-07',
    dateModified: '2026-05-07',
    author: {
      '@type': 'Person' as const,
      name: 'Sandra Jirongo',
      url: `${BASE}/authors/sandra-jirongo`,
    },
    publisher: { '@type': 'Organization' as const, name: 'ClaroBill', url: BASE },
    image: `${BASE}/og-image.png`,
  };

  const BREADCRUMB_SCHEMA = {
    '@type': 'BreadcrumbList' as const,
    itemListElement: [
      { '@type': 'ListItem' as const, position: 1, name: 'Home', item: BASE },
      { '@type': 'ListItem' as const, position: 2, name: 'Guides', item: `${BASE}/learn` },
      { '@type': 'ListItem' as const, position: 3, name: `${d.name} Billing Rights`, item: pageUrl },
    ],
  };

  const FAQ_SCHEMA = {
    '@type': 'FAQPage' as const,
    mainEntity: [
      {
        '@type': 'Question' as const,
        name: `How long do I have to dispute a medical bill in ${d.name}?`,
        acceptedAnswer: {
          '@type': 'Answer' as const,
          text: `Federal law gives you the right to an internal appeal with your insurer. Most plans allow 30 to 180 days from the date on your Explanation of Benefits (EOB) to file a dispute. Check your plan's Evidence of Coverage for your specific deadline. For surprise bills covered by the No Surprises Act, you generally have 120 days from the initial bill.`,
        },
      },
      {
        '@type': 'Question' as const,
        name: `Can a hospital in ${d.name} send me to collections without warning?`,
        acceptedAnswer: {
          '@type': 'Answer' as const,
          text: `Federal CFPB rules require medical debt to be at least 180 days past due before it can be reported to credit bureaus. Providers and collection agencies must send written notice before reporting. ${d.stateProtections.length > 0 ? `${d.name} may have additional state-level protections — contact ${d.agencyName} to verify.` : `Contact ${d.agencyName} to verify any additional state-level notice requirements.`}`,
        },
      },
      {
        '@type': 'Question' as const,
        name: `What is the No Surprises Act and does it apply in ${d.name}?`,
        acceptedAnswer: {
          '@type': 'Answer' as const,
          text: `Yes. The No Surprises Act (effective January 1, 2022) is a federal law that applies in all 50 states. It limits your cost-sharing for emergency care and for out-of-network care received at in-network facilities to the in-network amount. Providers cannot balance-bill you beyond your plan's cost-sharing for covered services.`,
        },
      },
      {
        '@type': 'Question' as const,
        name: `How do I file a complaint about a medical bill in ${d.name}?`,
        acceptedAnswer: {
          '@type': 'Answer' as const,
          text: `Contact ${d.agencyName} at ${d.agencyUrl}${d.agencyPhone ? ` or by phone at ${d.agencyPhone}` : ''}. For No Surprises Act violations, you can also call the federal No Surprises Help Desk at (800) 985-3059 or visit cms.gov/nosurprises.`,
        },
      },
      {
        '@type': 'Question' as const,
        name: `What if my insurance company denies my claim in ${d.name}?`,
        acceptedAnswer: {
          '@type': 'Answer' as const,
          text: `Under the ACA, you have the right to an internal appeal with your insurer and, after exhausting internal appeals, an independent external review. Deadlines vary by plan type — check your EOB or plan documents. ${d.agencyName} can intervene if your insurer is not following the required appeals process.`,
        },
      },
    ],
  };

  return (
    <article>
      <JsonLd schema={[ARTICLE_SCHEMA, BREADCRUMB_SCHEMA, FAQ_SCHEMA]} />

      <div className={s.articleByline}>
        <span>Patient Rights</span>
        <span>·</span>
        <span>{d.name}</span>
        <span>·</span>
        <span>Last reviewed May 2026</span>
      </div>

      <h1 className={s.articleH1}>{d.name} Medical Billing Rights</h1>
      <p className={s.articleLead}>
        Federal law guarantees baseline billing protections for every patient in the US. Here is
        what you are entitled to in {d.name}, how to dispute a bill step by step, and who to
        contact when those rights are violated.
      </p>

      <div className={s.articleBody}>
        <h2>Federal protections (apply in every state)</h2>
        <p>These rights apply regardless of which state you are in or which insurer you have:</p>
        <ul>
          <li>
            <strong>No Surprises Act (2022):</strong> Limits surprise bills from out-of-network
            providers in emergencies and at in-network facilities. Your cost-sharing cannot exceed
            the in-network amount for covered services.
          </li>
          <li>
            <strong>Right to an itemized bill:</strong> Any provider must supply a line-by-line
            itemized bill within 30 days of your written request.
          </li>
          <li>
            <strong>Internal appeal right:</strong> Under the ACA, you may appeal any insurer
            claim denial through your plan&apos;s internal appeals process.
          </li>
          <li>
            <strong>External review right:</strong> After exhausting internal appeals, you may
            request an independent external review of final adverse coverage decisions.
          </li>
          <li>
            <strong>Medical debt credit reporting:</strong> CFPB rules require medical debt to be
            at least 180 days past due before it can appear on a credit report.
          </li>
        </ul>

        <h2>{d.name}-specific protections</h2>
        {d.stateProtections.length > 0 ? (
          <>
            <ul className={ss.protectionsList}>
              {d.stateProtections.map((p, i) => (
                <li key={i}>{p}</li>
              ))}
            </ul>
            <p className={ss.agencyNote}>
              State law changes frequently. Verify current protections with{' '}
              <a href={d.agencyUrl} rel="noopener noreferrer" target="_blank">
                {d.agencyName}
              </a>.
            </p>
          </>
        ) : (
          <p>
            No additional state-specific billing protections beyond the federal minimum have been
            identified for {d.name} at this time. Contact{' '}
            <a href={d.agencyUrl} rel="noopener noreferrer" target="_blank">
              {d.agencyName}
            </a>{' '}
            to verify current state law.
          </p>
        )}

        <h2>How to dispute a medical bill in {d.name}</h2>
        <ol>
          <li>
            <strong>Request an itemized bill.</strong> Contact the provider in writing and ask for a
            line-by-line itemized statement with CPT codes. Providers are required to supply this
            within 30 days.
          </li>
          <li>
            <strong>Review every line item.</strong> Check CPT codes against the actual procedures
            you received. Verify dates, quantities, and that each service listed was genuinely
            rendered.
          </li>
          <li>
            <strong>Compare against your EOB.</strong> Your insurer&apos;s Explanation of Benefits
            shows what was billed vs. what was paid. Discrepancies between the itemized bill and EOB
            are a common sign of billing errors.
          </li>
          <li>
            <strong>Contact your insurer first.</strong> Most billing errors involve incorrect claim
            processing. File a formal dispute using the process described in your EOB or plan
            documents.
          </li>
          <li>
            <strong>Negotiate directly with the provider.</strong> Ask the billing department for a
            reduction or payment plan. Many providers have financial hardship programs that are not
            advertised.
          </li>
          <li>
            <strong>File a state complaint if needed.</strong> If your rights have been violated,
            contact {d.agencyName}
            {d.agencyPhone ? ` at ${d.agencyPhone}` : ''} or submit a federal complaint to the No
            Surprises Help Desk at (800) 985-3059.
          </li>
        </ol>

        <h2>Contact the {d.name} billing rights agency</h2>
        <div className={ss.agencyCard}>
          <p className={ss.agencyCardName}>{d.agencyName}</p>
          <p>
            <a href={d.agencyUrl} rel="noopener noreferrer" target="_blank">
              {d.agencyUrl}
            </a>
          </p>
          {d.agencyPhone && <p>{d.agencyPhone}</p>}
        </div>
        <p>
          For federal No Surprises Act complaints: <strong>(800) 985-3059</strong> or{' '}
          <a href="https://www.cms.gov/nosurprises" rel="noopener noreferrer" target="_blank">
            cms.gov/nosurprises
          </a>
        </p>

        <h2>Frequently asked questions</h2>
        <dl className={ss.faqList}>
          {FAQ_SCHEMA.mainEntity.map((q, i) => (
            <div key={i} className={ss.faqItem}>
              <dt className={ss.faqQ}>{q.name}</dt>
              <dd className={ss.faqA}>{q.acceptedAnswer.text}</dd>
            </div>
          ))}
        </dl>
      </div>

      <div className={s.sourcesSection}>
        <p className={s.sourcesLabel}>Sources</p>
        <ol style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {[
            { label: 'No Surprises Act (42 U.S.C. § 300gg-111)', url: 'https://www.cms.gov/nosurprises' },
            { label: 'ACA §2719: Internal Claims and Appeals (45 CFR §147.136)', url: 'https://www.hhs.gov/healthcare/rights/appeals/index.html' },
            { label: `${d.agencyName}`, url: d.agencyUrl },
          ].map((src, i) => (
            <li key={src.url} className={s.sourceItem}>
              <span style={{ marginRight: '.4rem', opacity: .5 }}>{i + 1}.</span>
              <a href={src.url} target="_blank" rel="noopener noreferrer" className={s.sourceLink}>
                {src.label}
              </a>
            </li>
          ))}
        </ol>
      </div>

      <div className={s.ctaBox}>
        <p className={s.ctaTitle}>Found an error in your {d.name} bill?</p>
        <p className={s.ctaNote}>
          ClaroBill audits your itemized bill line by line, flags every error, and writes the
          dispute letter for you. Free analysis, no percentage cut.
        </p>
        <Link href="/auth/sign-in" className={s.ctaBtn}>Analyze my bill. It&apos;s free</Link>
      </div>

      <div className={s.relatedSection}>
        <p className={s.relatedLabel}>Related guides</p>
        <div>
          {[
            { slug: 'how-to-dispute-a-hospital-bill', title: 'How to dispute a hospital bill' },
            { slug: 'common-medical-billing-errors', title: 'Common medical billing errors and how to spot them' },
            { slug: 'how-to-read-an-itemized-medical-bill', title: 'How to read an itemized medical bill' },
            { slug: 'medical-billing-advocates', title: 'When to hire a medical billing advocate' },
          ].map((a) => (
            <Link key={a.slug} href={`/learn/${a.slug}`} className={s.relatedLink}>
              {a.title} &rarr;
            </Link>
          ))}
        </div>
      </div>

      <p style={{ fontSize: '.75rem', color: 'var(--txt3)', marginTop: '2rem', paddingTop: '1rem', borderTop: '1px solid var(--border)' }}>
        This page is for informational purposes only and does not constitute legal advice. State
        laws change; verify current requirements with {d.agencyName} or a qualified attorney.
      </p>
    </article>
  );
}
