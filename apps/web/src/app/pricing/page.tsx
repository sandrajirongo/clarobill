'use client';

import Link from 'next/link';
import { useState } from 'react';
import { MarketingNav } from '@/components/marketing-nav';
import s from './pricing.module.css';

const TIERS = [
  {
    range: '$0 – $20',
    price: 'Free',
    priceSub: null,
    tag: 'Clean Bill',
    tagline: 'Your bill is clean. Enjoy the peace of mind — no charge, ever.',
    keepNote: 'No charge — ever',
    popular: false,
    featured: false,
  },
  {
    range: '$21 – $100',
    price: '$9.99',
    priceSub: 'one-time',
    tag: 'Small Win',
    tagline: "We've discounted the fee so you keep the lion's share of every dollar saved.",
    keepNote: 'You keep ≥\u202f$11',
    popular: false,
    featured: false,
  },
  {
    range: '$101 – $1,000',
    price: '$49.99',
    priceSub: 'one-time',
    tag: 'The Standard Fix',
    tagline: 'High ROI — a fraction of what a billing advocate charges for the same result.',
    keepNote: 'You keep ≥\u202f$51',
    popular: true,
    featured: true,
  },
  {
    range: '$1,000+',
    price: '$99.99',
    priceSub: 'one-time',
    tag: 'The Heavy Hitter',
    tagline: 'Significant financial impact. Worth every cent on a four-figure correction.',
    keepNote: 'You keep ≥\u202f$900',
    popular: false,
    featured: false,
  },
] as const;

const HOW_STEPS = [
  {
    num: '1',
    title: 'We analyze your bill first',
    body: 'Upload your medical bill or EOB. Our AI benchmarks every line item against Medicare fee schedules and NCCI billing rules. No payment required.',
  },
  {
    num: '2',
    title: 'We calculate potential savings',
    body: 'If errors are found, we calculate the total dollar value of what you could recover and assign your tier automatically.',
  },
  {
    num: '3',
    title: 'You pay only if we found errors',
    body: 'If savings ≥ $21, you pay the one-time tier fee and unlock your full error report + ready-to-send dispute letter. Clean bills cost nothing.',
  },
] as const;

const FAQS = [
  {
    q: 'What if the analysis finds no errors?',
    a: "If savings found are $20 or under, you pay nothing. You'll receive a confirmation that your bill looks clean — no credit card ever charged.",
  },
  {
    q: 'How is my tier determined?',
    a: 'Your tier is set automatically based on the total dollar value of errors our AI finds. You see the tier and fee before any payment is taken.',
  },
  {
    q: 'When am I charged?',
    a: "After the analysis completes and savings are found, you'll see your tier and fee. You choose to pay or walk away — no hidden auto-charges.",
  },
  {
    q: 'What do I get in a paid tier?',
    a: 'Every paid tier includes a full itemized error report, the specific billing codes violated, plain-English explanations, and a ready-to-send dispute letter tailored to your bill.',
  },
  {
    q: 'How does this compare to a billing advocate?',
    a: 'Medical billing advocates typically charge 25–35% of recovered savings. On a $500 correction that would cost $125–175. We charge a flat $49.99. Same outcome, far less cost.',
  },
  {
    q: 'Is my bill data kept private?',
    a: 'Yes. Your bill is encrypted at upload, never stored beyond your session unless you create an account, and never sold or shared. We are HIPAA-aligned.',
  },
] as const;

function PricingFaq(): JSX.Element {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <div className={s.faqList}>
      {FAQS.map((faq, i) => (
        <div key={i} className={s.faqItem}>
          <button
            className={`${s.faqQ} ${open === i ? s.faqQOpen : ''}`}
            onClick={() => setOpen(open === i ? null : i)}
            type="button"
          >
            {faq.q}
            <svg
              className={`${s.faqChevron} ${open === i ? s.faqChevronOpen : ''}`}
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>
          <div className={`${s.faqA} ${open === i ? s.faqAOpen : ''}`}>
            <p className={s.faqAInner}>{faq.a}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

export default function PricingPage(): JSX.Element {
  return (
    <div className={s.shell}>

      <MarketingNav activePath="/pricing" />

      {/* HERO */}
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
              Upload my bill — it&apos;s free
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

      {/* HOW PRICING WORKS */}
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

      {/* TIERS */}
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
            {TIERS.map((tier) => (
              <div
                key={tier.tag}
                className={`${s.tierCard} ${tier.featured ? s.tierCardFeatured : ''}`}
              >
                {tier.popular && (
                  <span className={s.popularBadge}>Most popular</span>
                )}
                <span className={`${s.rangePill} ${tier.featured ? s.rangePillFeatured : ''}`}>
                  {tier.range} found
                </span>
                <div className={s.priceRow}>
                  <span className={`${s.price} ${tier.featured ? s.priceFeatured : ''}`}>
                    {tier.price}
                  </span>
                  {tier.priceSub && (
                    <span className={`${s.priceSub} ${tier.featured ? s.priceSubFeatured : ''}`}>
                      {tier.priceSub}
                    </span>
                  )}
                </div>
                <p className={`${s.tierTag} ${tier.featured ? s.tierTagFeatured : ''}`}>{tier.tag}</p>
                <p className={`${s.tierTagline} ${tier.featured ? s.tierTaglineFeatured : ''}`}>{tier.tagline}</p>
                <div className={`${s.keepLine} ${tier.featured ? s.keepLineFeatured : ''}`}>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                  {tier.keepNote}
                </div>
                <Link
                  className={`${s.tierBtn} ${tier.featured ? s.tierBtnFeatured : ''}`}
                  href="/auth/sign-in"
                >
                  Upload my bill
                </Link>
              </div>
            ))}
          </div>

          <p className={s.tiersNote}>
            Tier is assigned automatically after analysis. Every paid tier includes a full error report and a ready-to-send dispute letter.
          </p>
        </div>
      </section>

      {/* COMPARISON */}
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
                <td>$0 – $99.99 flat</td>
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

      {/* FAQ */}
      <section className={s.faqSection}>
        <div className={s.faqInner}>
          <h2 className={s.faqH2}>Pricing questions, answered.</h2>
          <PricingFaq />
        </div>
      </section>

      {/* CTA */}
      <section className={s.ctaSection}>
        <h2 className={s.ctaH2}>Your bill deserves a second opinion</h2>
        <p className={s.ctaP}>Free to analyze. You only pay when we save you money.</p>
        <Link className={s.btnCtaLime} href="/auth/sign-in">
          Upload my bill — it&apos;s free
        </Link>
        <p className={s.ctaNote}>HIPAA-aligned &nbsp;·&nbsp; Encrypted &nbsp;·&nbsp; No credit card to start</p>
      </section>

      {/* FOOTER */}
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
