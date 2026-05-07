import type { Metadata } from 'next';
import Link from 'next/link';
import { MarketingNav } from '@/components/marketing-nav';
import { JsonLd } from '@/components/json-ld';
import { isBetaMode, BETA_COPY } from '@/lib/beta';
import { PricingFaq } from './pricing-faq';
import { TIERS, HOW_STEPS, FAQS } from './pricing-data';
import s from './pricing.module.css';

const PRICING_SCHEMAS = [
  {
    '@type': 'BreadcrumbList' as const,
    itemListElement: [
      { '@type': 'ListItem' as const, position: 1, name: 'Home', item: 'https://www.clarobill.com' },
      { '@type': 'ListItem' as const, position: 2, name: 'Pricing', item: 'https://www.clarobill.com/pricing' },
    ],
  },
  {
    '@type': 'Product' as const,
    name: 'ClaroBill Medical Bill Analysis',
    description:
      'AI-powered medical bill error detection and dispute letter generation. Free analysis on every bill. Pay a one-time flat fee only when errors worth disputing are found.',
    url: 'https://www.clarobill.com/pricing',
    offers: [
      { '@type': 'Offer' as const, name: 'Clean Bill', price: '0', priceCurrency: 'USD', description: 'No billing errors found worth disputing. Free, always.' },
      { '@type': 'Offer' as const, name: 'Small Win', price: '14.99', priceCurrency: 'USD', description: '$21 to $100 in billing errors found.' },
      { '@type': 'Offer' as const, name: 'Standard Fix', price: '79.99', priceCurrency: 'USD', description: '$101 to $500 in billing errors found.' },
      { '@type': 'Offer' as const, name: 'Major Fix', price: '129.99', priceCurrency: 'USD', description: '$501 to $1,500 in billing errors found.' },
      { '@type': 'Offer' as const, name: 'Heavy Hitter', price: '199.99', priceCurrency: 'USD', description: 'Over $1,500 in billing errors found.' },
    ],
  },
  {
    '@type': 'FAQPage' as const,
    mainEntity: FAQS.map((f) => ({
      '@type': 'Question' as const,
      name: f.q,
      acceptedAnswer: { '@type': 'Answer' as const, text: f.a },
    })),
  },
];

export const metadata: Metadata = {
  title: 'Pricing: ClaroBill',
  description: 'Simple, transparent pricing for medical bill analysis. Find errors in your bill and dispute them with a professional letter.',
  alternates: {
    canonical: 'https://www.clarobill.com/pricing',
    languages: { 'en': 'https://www.clarobill.com/pricing', 'x-default': 'https://www.clarobill.com/pricing' },
  },
};

export default function PricingPage(): JSX.Element {
  const beta = isBetaMode();
  return (
    <div className={s.shell}>
      <JsonLd schema={PRICING_SCHEMAS} />

      <MarketingNav activePath="/pricing" />

      {beta && (
        <section className={s.betaCallout}>
          <div className={s.betaCalloutInner}>
            <span className={s.betaCalloutEyebrow}>{BETA_COPY.pricingCallout.eyebrow}</span>
            <h2 className={s.betaCalloutTitle}>{BETA_COPY.pricingCallout.title}</h2>
            <p className={s.betaCalloutBody}>{BETA_COPY.pricingCallout.body}</p>
          </div>
        </section>
      )}

      <section className={s.hero}>
        <div className={s.heroInner}>
          <div className={s.heroEyebrow}>Transparent pricing</div>
          <h1 className={s.heroH1}>
            Pay only when we find <em>real savings</em>
          </h1>
          <p className={s.heroSub}>
            Every bill analysis is free to run. If our AI finds no errors worth disputing,
            you owe nothing. Simple, performance-based pricing aligned with your outcome.
          </p>
          <div className={s.heroGuarantee}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <polyline points="20 6 9 17 4 12" />
            </svg>
            No errors found = no charge. Guaranteed.
          </div>
          <div className={s.heroCtaRow}>
            <Link className={s.btnSage} href="/auth/sign-in">
              Upload your bill. It&apos;s free.
            </Link>
            <span className={s.heroMicro}>
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
                <rect x="3" y="11" width="18" height="11" rx="2" />
                <path d="M7 11V7a5 5 0 0 1 10 0v4" />
              </svg>
              HIPAA-aligned · No credit card needed to start
            </span>
          </div>
        </div>
      </section>

      <section className={s.howSection}>
        <div className={s.howInner}>
          <span className={s.sectionLabel}>How it works</span>
          <h2 className={s.howH2}>Analysis first. Payment only on results.</h2>
          <div className={s.howGrid}>
            {HOW_STEPS.map((step) => (
              <div key={step.num} className={s.howCard}>
                <div className={s.howNum}>{step.num}</div>
                <p className={s.howTitle}>{step.title}</p>
                <p className={s.howBody}>{step.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className={s.tiersSection}>
        <div className={s.tiersInner}>
          <div className={s.tiersHeader}>
            <span className={s.sectionLabel}>Pricing tiers</span>
            <h2 className={s.howH2}>Your fee scales with your savings</h2>
            <p className={s.tiersSubtitle}>
              Tiers are assigned automatically after analysis. You always keep
              significantly more than you pay.
            </p>
            <div className={s.tiersTrustStrip}>
              <span>Analysis always free</span>
              <span className={s.dot} />
              <span>No credit card to start</span>
              <span className={s.dot} />
              <span>Pay only on results</span>
            </div>
          </div>

          <div className={s.tiersGrid}>
            {TIERS.map((tier) => {
              const isPaidTier = tier.price !== 'Free';
              const showStrikethrough = beta && isPaidTier;
              return (
                <div
                  key={tier.tag}
                  className={`${s.tierCard} ${showStrikethrough ? s.tierCardBeta : ''}`}
                >
                  {showStrikethrough && (
                    <span className={s.tierBetaBadge}>{BETA_COPY.paywall.badge}</span>
                  )}
                  <span className={s.rangePill}>
                    {tier.range} found
                  </span>
                  <div className={s.priceRow}>
                    {showStrikethrough ? (
                      <>
                        <span className={s.priceStrike}>{tier.price}</span>
                        <span className={s.price}>Free</span>
                      </>
                    ) : (
                      <>
                        <span className={s.price}>{tier.price}</span>
                        {tier.priceSub && (
                          <span className={s.priceSub}>{tier.priceSub}</span>
                        )}
                      </>
                    )}
                  </div>
                  <p className={s.tierTag}>{tier.tag}</p>
                  <p className={s.tierTagline}>{tier.tagline}</p>
                  <div className={s.keepLine}>
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                    {showStrikethrough ? 'You keep 100% during beta' : tier.keepNote}
                  </div>
                  <Link className={s.tierBtn} href="/auth/sign-in">
                    Upload your bill
                  </Link>
                </div>
              );
            })}
          </div>

          <p className={s.tiersNote}>
            Tier is assigned automatically after analysis. Every paid tier includes a full error report and a ready-to-send dispute letter.
          </p>
        </div>
      </section>

      <section className={s.compSection}>
        <div className={s.compInner}>
          <span className={s.sectionLabel}>How we compare</span>
          <h2 className={s.compH2}>ClaroBill vs. the alternatives</h2>
          <table className={s.compTable}>
            <thead>
              <tr>
                <th>Option</th>
                <th>Typical cost</th>
                <th>Speed</th>
                <th>Dispute letter</th>
              </tr>
            </thead>
            <tbody>
              <tr className={s.compHighlight}>
                <td>ClaroBill</td>
                <td>$0 – $199.99 flat</td>
                <td>Minutes</td>
                <td className={s.compCheck}>Included</td>
              </tr>
              <tr>
                <td>Medical billing advocate</td>
                <td>25–35% of savings</td>
                <td>Days to weeks</td>
                <td className={s.compCheck}>Yes</td>
              </tr>
              <tr>
                <td>Do it yourself</td>
                <td>Free</td>
                <td>Hours of research</td>
                <td className={s.compX}>Write your own</td>
              </tr>
              <tr>
                <td>Do nothing</td>
                <td>Full bill amount</td>
                <td>—</td>
                <td className={s.compX}>None</td>
              </tr>
            </tbody>
          </table>
          <p style={{ fontSize: '.75rem', color: 'var(--txt3)', marginTop: '1rem', lineHeight: '1.6' }}>
            Advocate fee estimate based on industry standard 25–35% contingency model.
          </p>
        </div>
      </section>

      <section className={s.faqSection}>
        <div className={s.faqInner}>
          <h2 className={s.faqH2}>Pricing questions, answered.</h2>
          <PricingFaq />
        </div>
      </section>

      <section className={s.ctaSection}>
        <h2 className={s.ctaH2}>Your bill deserves a second opinion</h2>
        <p className={s.ctaP}>Free to analyze. You only pay when we save you money.</p>
        <Link className={s.btnCtaLime} href="/auth/sign-in">
          Upload your bill. It&apos;s free.
        </Link>
        <p className={s.ctaNote}>HIPAA-aligned &nbsp;·&nbsp; Encrypted &nbsp;·&nbsp; No credit card to start</p>
      </section>

      <footer className={s.footer}>
        <span className={s.flo}>Claro<em>Bill</em></span>
        <div className={s.fli}>
          <a href="/legal/privacy">Privacy</a>
          <a href="/legal/terms">Terms</a>
          <a href="mailto:support@clarobill.com">Contact</a>
        </div>
        <span className={s.fco}>© 2026 ClaroBill</span>
      </footer>

    </div>
  );
}
