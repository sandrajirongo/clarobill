import type { Metadata } from 'next';
import Link from 'next/link';
import s from '../../blog/blog.module.css';

export const metadata: Metadata = {
  title: 'The Most Common Medical Billing Errors (And How to Dispute Them): ClaroBill',
  description: 'Duplicate charges, upcoded visits, unbundled procedures. Here is what each billing error looks like on a real bill and exactly what to say when you dispute it.',
  alternates: {
    canonical: 'https://www.clarobill.com/learn/common-medical-billing-errors',
    languages: { en: 'https://www.clarobill.com/learn/common-medical-billing-errors', 'x-default': 'https://www.clarobill.com/learn/common-medical-billing-errors' },
  },
};

export default function Article(): JSX.Element {
  return (
    <article>
      <div className={s.articleByline}>
        <span>April 7, 2026</span>
        <span>·</span>
        <span>8 min read</span>
        <span>·</span>
        <span>Sandra Jirongo</span>
      </div>

      <h1 className={s.articleH1}>
        The Most Common Medical Billing Errors (And How to Dispute Them)
      </h1>

      <p className={s.articleLead}>
        Duplicate charges, upcoded visits, unbundled procedures. Here is what each one looks like on a real
        bill and what to say when you dispute it.
      </p>

      <div className={s.articleBody}>
        <p>
          According to the Medical Billing Advocates of America, errors appear in over 80% of the hospital bills
          they review. Not occasional errors. Systematic ones. The same mistakes, recurring across different
          hospitals, different states, different patient populations.
        </p>
        <p>
          The errors are not usually the result of fraud. Most come from the complexity of the coding system
          itself: over 10,000 CPT codes, thousands of diagnosis codes, and a web of billing rules that even
          experienced coders get wrong. The problem is that when a mistake happens, it almost always runs
          in the provider's favor.
        </p>
        <p>
          To catch any of these errors, you first need the right document. Most patients never receive an
          itemized bill unless they ask for one.{' '}
          <Link href="/learn/how-to-read-an-itemized-medical-bill">Our guide to reading an itemized bill</Link>{' '}
          explains how to request it and what each column means. Once you have it, look for the following.
        </p>

        <h2>1. Duplicate charges</h2>
        <p>The same service billed twice. It sounds too obvious to happen, but it is one of the most common errors on hospital bills, particularly for lab work and medications administered during a stay.</p>
        <p><strong>What it looks like:</strong> CPT 85025 (complete blood count) appears twice on September 14th. Or "acetaminophen 500mg" shows a quantity of 24 when you were only there for two days.</p>
        <p><strong>How to dispute it:</strong> "I have two charges for CPT 85025 on September 14th. My records show one blood draw that day. Can you show me the documentation for the second charge?" If they cannot produce documentation for both, the duplicate should be removed.</p>

        <h2>2. Upcoding</h2>
        <p>Upcoding is when a provider bills for a more complex, more expensive service than what was actually performed. It is most common with office visit codes (the 99200 series) and emergency department visits (99281–99285).</p>
        <p>The dollar difference matters. A level-3 office visit (99213) reimburses at roughly $90 under the 2026 Medicare fee schedule. A level-5 (99215) is around $182. Upcoding a routine follow-up adds roughly $92 to your bill.</p>
        <p><strong>What it looks like:</strong> You had a 10-minute post-surgical check. Your bill shows CPT 99215, which requires documented high-complexity medical decision-making or at least 40 minutes of total time. The visit note shows three lines.</p>
        <p><strong>How to dispute it:</strong> Request the visit documentation and compare it to the code requirements. "CPT 99215 requires high-complexity medical decision-making or 40+ minutes of total time. The documentation supports 99213 at most. Please review and correct."</p>

        <h2>3. Unbundling</h2>
        <p>Some CPT codes are designed to include related procedures. Billing them separately is called unbundling, and it is prohibited by the National Correct Coding Initiative (NCCI) rules.</p>
        <p>A real example: CPT 29881 covers knee arthroscopy with meniscectomy. CPT 29877 covers arthroscopic debridement. Under NCCI rules, 29877 is included in 29881 when performed during the same surgical session. They cannot be billed separately. If you are unfamiliar with how{' '}
          <Link href="/learn/what-are-cpt-codes">CPT codes work and how they get abused</Link>, that guide covers the system in plain English.
        </p>
        <p><strong>How to dispute it:</strong> "CPT 29877 is a component of CPT 29881 under CMS NCCI edit. These two codes were billed together on [date]. Per NCCI guidelines, they cannot be billed together without a valid modifier. Please review."</p>

        <h2>4. Charges for services not rendered</h2>
        <p>A charge for something that simply did not happen. Physical therapy on a day you were discharged. An MRI you did not receive. A consultation from a specialist you never saw.</p>
        <p>These charges often result from a scheduled service that was cancelled but never removed from the billing queue. The intent is rarely malicious. The charge is still wrong.</p>
        <p><strong>How to dispute it:</strong> "Can you tell me which clinician ordered or performed this service, and on which date?" If they cannot answer, request removal.</p>

        <h2>5. Balance billing from out-of-network providers</h2>
        <p>You chose an in-network hospital but were treated by an out-of-network anesthesiologist or radiologist. Then a second bill arrives from a provider you have never heard of, for a balance your insurer will not cover.</p>
        <p>The No Surprises Act, which took effect in 2022, prohibits this practice for most emergency care and non-emergency care where you had no meaningful choice of provider. If you receive such a balance bill, file a complaint with your state insurance commissioner and reference the No Surprises Act.</p>

        <h2>How to write an effective dispute letter</h2>
        <p>Phone calls get lost. A written dispute creates a paper trail. For the full process, including what to put in the letter, how to cite specific rules, and what to do if the hospital pushes back, see{' '}
          <Link href="/learn/how-to-dispute-a-hospital-bill">our complete hospital bill dispute guide</Link>. In short: cite the exact CPT code, the exact date, the exact dollar amount, and the exact reason the charge is wrong. Reference the rule being violated where applicable.
        </p>
        <p>Send it certified mail or email with read receipt. Keep a copy. Note the date and name of anyone you speak with by phone. Most disputes are resolved within 30 to 60 days. But only if you follow up when you do not hear back.</p>
        <p>The billing department's job is to collect. Your job is to pay what you actually owe. Those are not the same number. And the difference is worth the time it takes to look.</p>
      </div>

      <Citations sources={[
        { label: "Medical Billing Advocates of America: Billing Error Statistics (via Becker's Hospital Review)", url: 'https://www.beckershospitalreview.com/finance/medical-billing-errors-growing-says-medical-billing-advocates-of-america.html' },
        { label: 'CMS: 2026 Medicare Physician Fee Schedule Final Rule', url: 'https://www.cms.gov/newsroom/fact-sheets/calendar-year-cy-2026-medicare-physician-fee-schedule-final-rule-cms-1832-f' },
        { label: 'CMS: National Correct Coding Initiative (NCCI) Edits', url: 'https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits' },
        { label: 'CMS: No Surprises Act Overview', url: 'https://www.cms.gov/nosurprises' },
      ]} />
      <Cta />
      <RelatedArticles current="common-medical-billing-errors" />
    </article>
  );
}

function Cta(): JSX.Element {
  return (
    <div className={s.ctaBox}>
      <p className={s.ctaTitle}>Find these errors in your bill</p>
      <p className={s.ctaNote}>ClaroBill runs a deep audit across every line item, flagging duplicates, upcoding, unbundling, and overcharges. Then it writes your dispute letter automatically.</p>
      <Link href="/auth/sign-in" className={s.ctaBtn}>Analyze my bill. It's free</Link>
    </div>
  );
}

function Citations({ sources }: { sources: { label: string; url: string }[] }): JSX.Element {
  return (
    <div className={s.sourcesSection}>
      <p className={s.sourcesLabel}>Sources</p>
      <ol style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {sources.map((src, i) => (
          <li key={src.url} className={s.sourceItem}>
            <span style={{ marginRight: '.4rem', opacity: .5 }}>{i + 1}.</span>
            <a href={src.url} target="_blank" rel="noopener noreferrer" className={s.sourceLink}>{src.label}</a>
          </li>
        ))}
      </ol>
    </div>
  );
}

function RelatedArticles({ current }: { current: string }): JSX.Element {
  const related = ALL_ARTICLES.filter((a) => a.slug !== current).slice(0, 3);
  return (
    <div className={s.relatedSection}>
      <p className={s.relatedLabel}>More guides</p>
      <div>
        {related.map((a) => (
          <Link key={a.slug} href={`/learn/${a.slug}`} className={s.relatedLink}>{a.title} →</Link>
        ))}
      </div>
    </div>
  );
}

const ALL_ARTICLES = [
  { slug: 'how-to-read-an-itemized-medical-bill', title: 'How to Read an Itemized Medical Bill' },
  { slug: 'common-medical-billing-errors', title: 'The Most Common Medical Billing Errors' },
  { slug: 'what-are-cpt-codes', title: "What Are CPT Codes? A Patient's Guide" },
  { slug: 'how-to-dispute-a-hospital-bill', title: 'How to Dispute a Hospital Bill: A Step-by-Step Guide' },
  { slug: 'medical-billing-advocates', title: 'Medical Billing Advocates: What They Do and What They Charge' },
  { slug: 'why-bill-exceeds-insurer-negotiated-rate', title: 'Why Your Bill Is Higher Than What Your Insurer Pays' },
  { slug: 'hospital-machine-readable-files-explained', title: 'Hospital Machine-Readable Files Explained' },
  { slug: 'ncci-edits-explained-for-patients', title: 'NCCI Edits: The Federal Rules That Prevent Billing Abuse' },
];
