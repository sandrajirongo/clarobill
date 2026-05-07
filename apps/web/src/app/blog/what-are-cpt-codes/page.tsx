import type { Metadata } from 'next';
import Link from 'next/link';
import s from '../blog.module.css';

export const metadata: Metadata = {
  title: "What Are CPT Codes? A Patient's Guide: Clarobill",
  description: 'CPT codes are the five-digit numbers that determine what your medical care costs. Here is how they work, how they get abused, and how to check whether yours are right.',
  alternates: {
    canonical: 'https://www.clarobill.com/blog/what-are-cpt-codes',
    languages: { 'en': 'https://www.clarobill.com/blog/what-are-cpt-codes', 'x-default': 'https://www.clarobill.com/blog/what-are-cpt-codes' },
  },
};

export default function Article(): JSX.Element {
  return (
    <article>
      <div className={s.articleByline}>
        <span>April 7, 2026</span>
        <span>·</span>
        <span>6 min read</span>
        <span>·</span>
        <span>Clarobill Team</span>
      </div>

      <h1 className={s.articleH1}>{"What Are CPT Codes? A Patient's Guide"}</h1>

      <p className={s.articleLead}>
        The five-digit numbers on your bill determine what you pay. Here is how they work, why they
        get abused, and how to check whether yours are right.
      </p>

      <div className={s.articleBody}>

        <p>
          Somewhere on your medical bill, there are five-digit numbers that most patients ignore. They look
          like serial codes (99213, 93000, 80053) and they are easy to skip past when you are trying to
          make sense of a bill that already feels overwhelming. If you are still working through what all
          the columns mean, <Link href="/blog/how-to-read-an-itemized-medical-bill">our itemized bill guide</Link>{' '}
          covers the full layout before you get to the codes.
        </p>

        <p>
          Those numbers are CPT codes, and they are arguably the most important field on the entire document.
          Every CPT code maps to a specific dollar amount. Get the code wrong, intentionally or not, and
          the charge attached to it changes.
        </p>

        <h2>Where CPT codes come from</h2>

        <p>
          CPT stands for Current Procedural Terminology. The American Medical Association owns and maintains
          the codebook, updated annually since 1966. The current edition contains over 10,000 codes covering
          every medical, surgical, and diagnostic service a provider might perform.
        </p>

        <p>
          When a doctor sees you, they (or their billing staff) select the CPT code that best describes what
          happened. That code goes on the claim submitted to your insurer. The insurer checks the code against
          their fee schedule and pays accordingly. The code is the mechanism that converts a clinical event
          into a dollar amount.
        </p>

        <p>
          Physicians do not have much flexibility here. The code has to match the documentation in the medical
          record. If a coder selects a higher-level code than the notes support, that is a compliance
          violation. In theory. In practice, audits are infrequent and the financial incentive to code high
          is real.
        </p>

        <h2>The codes you will actually see</h2>

        <p>Most patients encounter a handful of code ranges repeatedly. Here is what the common ones mean:</p>

        <div className={s.glossaryBox}>
          <div>
            <p className={s.glossaryTerm}>99202 – 99215 · Office and outpatient visits</p>
            <p className={s.glossaryDef}>
              The codes for clinic visits with a physician. The number indicates complexity: 99202 is a
              straightforward new patient visit; 99215 is a complex established-patient visit. The 2026
              Medicare fee schedule puts reimbursement at roughly $70 for a 99202 and $182 for a 99215.
              Most routine follow-ups should be coded at 99213 ($90) or 99214 ($128).
            </p>
          </div>
          <div style={{ marginTop: '1rem' }}>
            <p className={s.glossaryTerm}>99281 – 99285 · Emergency department visits</p>
            <p className={s.glossaryDef}>
              Same structure as the office visit codes, but for emergency care. Level 5 (99285) is
              high-severity with a threat to life or function. ED visits are frequently coded at 99284
              or 99285 regardless of the actual presenting complaint.
            </p>
          </div>
          <div style={{ marginTop: '1rem' }}>
            <p className={s.glossaryTerm}>85025 · Complete Blood Count (CBC)</p>
            <p className={s.glossaryDef}>
              One of the most ordered lab tests. It should appear once per blood draw, not multiple times.
              Medicare pays around $12 for this test. Hospital charges can run far higher.
            </p>
          </div>
          <div style={{ marginTop: '1rem' }}>
            <p className={s.glossaryTerm}>80053 · Comprehensive Metabolic Panel (CMP)</p>
            <p className={s.glossaryDef}>
              A panel of 14 blood chemistry tests. Should be billed as a single panel code, not as 14
              individual test codes.
            </p>
          </div>
          <div style={{ marginTop: '1rem' }}>
            <p className={s.glossaryTerm}>93000 · Electrocardiogram (EKG/ECG)</p>
            <p className={s.glossaryDef}>
              A 12-lead EKG with interpretation. The 2026 Medicare rate is $15.36. Hospital charges for
              the same test routinely run $200–$500.
            </p>
          </div>
          <div style={{ marginTop: '1rem' }}>
            <p className={s.glossaryTerm}>71046 · Chest X-ray, 2 views</p>
            <p className={s.glossaryDef}>
              Standard two-view chest radiograph. The 2026 Medicare rate is approximately $33. Hospital
              charges vary from $200 to over $1,000 at some facilities for the identical study.
            </p>
          </div>
        </div>

        <h2>Why the same code costs different amounts</h2>

        <p>
          CPT codes standardize what was done. They do not standardize what anyone charges for it. A provider
          sets their own "chargemaster" rate before any negotiation. Your insurer then applies their contracted
          discount. If you are uninsured or the provider is out-of-network, you may be on the hook for
          something much closer to the chargemaster rate.
        </p>

        <p>
          This is why the same CPT 93000 EKG can show a billed amount of $150 at one facility and $600 at
          another. The procedure is identical. The CPT code is identical. The price has almost nothing to
          do with either.
        </p>

        <p>
          Medicare's published fee schedule is the most useful benchmark for patients. When a provider's charge
          is two, three, or five times the Medicare rate, that is not automatically wrong. But it is worth noting.
        </p>

        <h2>Modifiers: the asterisks of medical billing</h2>

        <p>
          CPT codes sometimes appear with two-digit suffixes called modifiers that change the meaning of the
          base code, indicating a procedure was performed on the left vs. right side, or that two distinct
          procedures were performed in the same session (modifier 59).
        </p>

        <p>
          Modifier 59 deserves special attention. It is used to override National Correct Coding Initiative
          (NCCI) edits, the rules that prevent certain code combinations from being billed together. Used
          legitimately, it documents that two procedures really were separate and distinct. Used improperly,
          it is a tool for billing code pairs that should not be billed separately. Unbundling is one of the{' '}
          <Link href="/blog/common-medical-billing-errors">most common billing errors</Link>, with a specific
          dispute template you can use when you spot it. When you see modifier 59 with no clear justification,
          that is where to look first.
        </p>

        <h2>You are allowed to question the codes</h2>

        <p>
          Patients rarely ask about CPT codes because the system is not designed to be legible. Billing
          departments are not trained to explain codes to patients. They are trained to collect balances.
        </p>

        <p>
          None of that changes the fact that you are entitled to know exactly what you are being charged for
          and why. If a code on your bill does not match your experience of the visit, if the complexity
          level seems wrong, if a procedure appears for something you do not recall, ask. Request the
          documentation. The codes are not obscure by necessity. They are just not typically explained to
          the person who pays the bill. When you are ready to act on what you find,{' '}
          <Link href="/blog/how-to-dispute-a-hospital-bill">our dispute guide walks through every step</Link>{' '}
          including the specific language to use in a written challenge.
        </p>

      </div>

      <Citations sources={[
        { label: 'CMS: 2026 Medicare Physician Fee Schedule Final Rule', url: 'https://www.cms.gov/newsroom/fact-sheets/calendar-year-cy-2026-medicare-physician-fee-schedule-final-rule-cms-1832-f' },
        { label: 'CMS: Physician Fee Schedule Lookup Tool', url: 'https://www.cms.gov/medicare/physician-fee-schedule/search' },
        { label: 'CMS: Clinical Laboratory Fee Schedule', url: 'https://www.cms.gov/medicare/payment/fee-schedules/clinical-laboratory-fee-schedule-clfs' },
        { label: 'AMA: CPT Code Overview', url: 'https://www.ama-assn.org/practice-management/cpt/cpt-overview-and-code-approval' },
        { label: 'CMS: National Correct Coding Initiative (NCCI) Edits', url: 'https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits' },
      ]} />

      <Cta />

      <RelatedArticles current="what-are-cpt-codes" />
    </article>
  );
}

function Cta(): JSX.Element {
  return (
    <div className={s.ctaBox}>
      <p className={s.ctaTitle}>We check every CPT code for you</p>
      <p className={s.ctaNote}>
        ClaroBill runs a deep audit across every line item, flagging upcoding, unbundled
        procedures, and other errors. Then it writes your dispute letter automatically.
      </p>
      <Link href="/auth/sign-in" className={s.ctaBtn}>
        Analyze my bill. It's free
      </Link>
    </div>
  );
}

function Citations({ sources }: { sources: { label: string; url: string }[] }): JSX.Element {
  return (
    <div className={s.sourcesSection}>
      <p className={s.sourcesLabel}>Sources</p>
      <ol style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {sources.map((source, i) => (
          <li key={source.url} className={s.sourceItem}>
            <span style={{ marginRight: '.4rem', opacity: .5 }}>{i + 1}.</span>
            <a href={source.url} target="_blank" rel="noopener noreferrer" className={s.sourceLink}>
              {source.label}
            </a>
          </li>
        ))}
      </ol>
    </div>
  );
}

const allArticles = [
  { slug: 'how-to-read-an-itemized-medical-bill', title: 'How to Read an Itemized Medical Bill' },
  { slug: 'common-medical-billing-errors', title: 'The Most Common Medical Billing Errors (And How to Dispute Them)' },
  { slug: 'what-are-cpt-codes', title: "What Are CPT Codes? A Patient's Guide" },
  { slug: 'how-to-dispute-a-hospital-bill', title: 'How to Dispute a Hospital Bill: A Step-by-Step Guide' },
  { slug: 'medical-billing-advocates', title: 'Medical Billing Advocates: What They Do, What They Charge, and Whether You Need One' },
];

function RelatedArticles({ current }: { current: string }): JSX.Element {
  const related = allArticles.filter((a) => a.slug !== current).slice(0, 3);
  return (
    <div className={s.relatedSection}>
      <p className={s.relatedLabel}>More guides</p>
      <div>
        {related.map((article) => (
          <Link key={article.slug} href={`/blog/${article.slug}`} className={s.relatedLink}>
            {article.title} →
          </Link>
        ))}
      </div>
    </div>
  );
}
