import Link from 'next/link';
import type { Metadata } from 'next';
import s from './page.module.css';
import { Reveal } from '@/components/landing/reveal';
import { FaqAccordion } from '@/components/landing/faq';
import { ReportIcon, LetterIcon, SpeedIcon } from '@/components/icons';
import { MarketingNav } from '@/components/marketing-nav';
import { SocialsRow } from '@/components/socials-row';

export const metadata: Metadata = {
  title: 'ClaroBill — Find Errors in Your Medical Bill',
  description: 'AI-powered medical bill analysis. Find overcharges, duplicate charges, and billing errors in minutes.',
};

const LOGOS = [
  'BlueCross BlueShield', 'MyChart', 'Oscar Health', 'Aetna',
  'Cigna', 'UnitedHealthcare', 'Humana', 'Kaiser Permanente',
  'Anthem', 'Molina Healthcare', 'Centene', 'WellCare',
];

const TESTIMONIALS = [
  { initials: 'RJ', name: 'Ron J.', bg: '#C8F060', fg: '#1E3019', quote: '"Found three duplicate charges I never would have caught. Bill dropped overnight."', saved: '$1,421' },
  { initials: 'SM', name: 'Sarah M.', bg: '#B8E0F5', fg: '#1E3019', quote: '"The dispute letter was so professional. The hospital corrected the bill immediately."', saved: '$2,850' },
  { initials: 'JO', name: 'Jenny O.', bg: '#F5DFC8', fg: '#1E3019', quote: '"Mt. Sinai bill was confusing. ClaroBill explained every charge and flagged what was wrong."', saved: '$310' },
  { initials: 'DK', name: 'David K.', bg: '#E0D5F5', fg: '#1E3019', quote: '"Was about to pay $1,100 without question. ClaroBill showed me it was wrong. Paid $460."', saved: '$640' },
];

export default function LandingPage(): JSX.Element {
  return (
    <>
      <MarketingNav activePath="/" />

      {/* HERO */}
      <section className={s.hero}>
        <div className={s.heroInner}>
          <div className={s.heroEyebrow}>AI Medical Bill Review</div>
          <h1 className={s.heroH1}>
            Medical bills are <em>wrong</em>{' '}80% of the time
          </h1>
          <p className={s.heroSub}>
            ClaroBill uses AI to find duplicate charges, upcoding errors, and billing
            violations — then gives you the exact words to dispute them and save money.
          </p>
          <div className={s.heroCtaRow}>
            <Link className={s.btnSageLg} href="/auth/sign-in">
              Upload your bill — it&apos;s free
            </Link>
            <span className={s.heroMicro}>
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
                <rect x="3" y="11" width="18" height="11" rx="2" />
                <path d="M7 11V7a5 5 0 0 1 10 0v4" />
              </svg>
              HIPAA-aligned · You only pay if we save you money
            </span>
          </div>
        </div>
      </section>

      {/* PARTNERS CAROUSEL */}
      <div className={s.partnersStrip}>
        <div className={s.partnersTop}>
          <span className={s.psLabel}>Works with</span>
          <span className={s.hipaaPill}>
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
              <rect x="3" y="11" width="18" height="11" rx="2" />
              <path d="M7 11V7a5 5 0 0 1 10 0v4" />
            </svg>
            HIPAA-aligned
          </span>
        </div>
        <div className={s.carouselTrackWrap}>
          <div
            className={s.carouselTrack}
            style={{ animation: 'scroll-logos 22s linear infinite' }}
          >
            {/* Duplicate set for seamless infinite loop */}
            {[...LOGOS, ...LOGOS].map((name, i) => (
              <span key={i} className={s.clogo}>{name}</span>
            ))}
          </div>
        </div>
      </div>

      {/* STATS + REVIEWS */}
      <section className={s.statsSection}>
        <Reveal className={s.statsInner}>
          <div className={s.statsCard}>
            <div className={s.statRow}>
              <div className={s.statBox}>
                <div className={s.statNum}>80%</div>
                <div className={s.statLbl}>of medical bills contain at least one error</div>
              </div>
              <div className={s.statBox}>
                <div className={s.statNum}>$1,300</div>
                <div className={s.statLbl}>average error value found on bills over $10K</div>
              </div>
            </div>
            <div className={s.testiScroll}>
              {TESTIMONIALS.map((t) => (
                <div key={t.initials} className={s.tcard}>
                  <div className={s.tcardTop}>
                    <div className={s.av} style={{ background: t.bg, color: t.fg }}>{t.initials}</div>
                    <div>
                      <div className={s.tname}>{t.name}</div>
                      <div className={s.stars}>★★★★★</div>
                    </div>
                  </div>
                  <p className={s.tquote}>{t.quote}</p>
                  <div className={s.savedLine}>
                    Successfully saved <span className={s.sbadge}>{t.saved}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </Reveal>
      </section>

      {/* HOW IT WORKS */}
      <section className={s.howSection}>
        <Reveal className={s.howInner}>
          <span className={s.secPill}>How it works</span>
          <h2 className={s.secH2}>Review your bill and reduce what you owe</h2>
          <div className={s.stepsList}>
            <div className={s.step}>
              <div className={s.snum}>1</div>
              <div><div className={s.st}>Upload your medical bill</div></div>
            </div>
            <div className={`${s.step} ${s.stepHiLime}`}>
              <div className={s.snum}>2</div>
              <div>
                <div className={s.st}>ClaroBill AI reviews your bill</div>
                <div className={s.sd}>Our AI cross-references every charge against Medicare fee schedules and NCCI billing rules — catching what humans miss.</div>
              </div>
            </div>
            <div className={s.step}>
              <div className={s.snum}>3</div>
              <div><div className={s.st}>Receive your detailed error report</div></div>
            </div>
            <div className={`${s.step} ${s.stepHiLime}`}>
              <div className={s.snum}>4</div>
              <div>
                <div className={s.st}>Get clear results and next steps</div>
                <div className={s.sd}>We explain every finding and give you dispute letters and next steps to get your bill corrected.</div>
              </div>
            </div>
          </div>
        </Reveal>
      </section>

      {/* WHAT YOU GET */}
      <section className={s.whatSection}>
        <Reveal className={s.whatInner}>
          <span className={s.secPill}>What you get</span>
          <h2 className={s.secH2}>Two things that actually move the needle</h2>
          <div className={s.whatGrid}>
            <div className={s.wcard}>
              <div className={s.wi}><ReportIcon size={20} /></div>
              <h4 className={s.wcardH4}>A detailed error report</h4>
              <p className={s.wcardP}>Every charge is reviewed and flagged — duplicate line items, upcoding, unbundled procedures, and charges for services not provided — explained clearly, without medical jargon.</p>
            </div>
            <div className={s.wcard}>
              <div className={s.wi}><LetterIcon size={20} /></div>
              <h4 className={s.wcardH4}>A ready-to-send dispute letter</h4>
              <p className={s.wcardP}>A professional letter citing every billing violation by name with regulatory references — the same documentation that compels billing departments to act.</p>
            </div>
            <div className={`${s.wcard} ${s.wcardFull}`}>
              <div className={s.wi}><SpeedIcon size={20} /></div>
              <h4 className={s.wcardH4}>Results in minutes, not weeks</h4>
              <p className={s.wcardP}>No waiting for a human advocate. No back-and-forth calls. Upload your bill and get your full report and dispute letter the same day — ready to send immediately.</p>
            </div>
          </div>
        </Reveal>
      </section>

      {/* FAQ */}
      <section className={s.faqSection}>
        <Reveal className={s.faqInner}>
          <h2 className={s.faqH2}>Your questions, answered.</h2>
          <FaqAccordion />
        </Reveal>
      </section>

      {/* FOOTER CTA */}
      <section className={s.ctaSection}>
        <h2 className={s.ctaH2}>Your medical bill deserves a second opinion</h2>
        <p className={s.ctaP}>Free to start. Get your error report and dispute letter today.</p>
        <Link className={s.btnCta} href="/auth/sign-in">
          Upload your bill — it&apos;s free
        </Link>
        <p className={s.ctaNote}>HIPAA-aligned &nbsp;·&nbsp; Encrypted &nbsp;·&nbsp; No credit card required</p>
      </section>

      {/* FOOTER */}
      <footer className={s.footer}>
        <span className={s.flo}>Claro<em>Bill</em></span>
        <div className={s.fli}>
          <a href="/legal/privacy">Privacy</a>
          <a href="/legal/terms">Terms</a>
          <a href="mailto:support@clarobill.com">Contact</a>
        </div>
        <SocialsRow />
        <span className={s.fco}>© 2026 ClaroBill</span>
      </footer>
    </>
  );
}
