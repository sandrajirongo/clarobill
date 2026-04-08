import type { Metadata } from 'next';
import Link from 'next/link';
import s from '../blog.module.css';

export const metadata: Metadata = {
  title: 'How to Read an Itemized Medical Bill — Clarobill',
  description: 'What the columns, codes, and dollar amounts on your itemized medical bill actually mean — and how to find the errors hiding in plain sight.',
};

export default function Article(): JSX.Element {
  return (
    <article>
      <div className={s.articleByline}>
        <span>April 7, 2026</span>
        <span>·</span>
        <span>7 min read</span>
        <span>·</span>
        <span>Clarobill Team</span>
      </div>

      <h1 className={s.articleH1}>How to Read an Itemized Medical Bill</h1>

      <p className={s.articleLead}>
        What the columns, codes, and dollar amounts actually mean — and how to spot the line items that should not be there.
      </p>

      <div className={s.articleBody}>

        <p>
          The bill arrived six weeks after the procedure. Three pages, single-spaced, $28,000. Out of 41 line
          items, I recognized maybe four. The rest looked like a ransom note written in a medical coding
          dialect nobody teaches you.
        </p>

        <p>
          That experience is nearly universal. Hospitals are not legally required to send you an itemized bill
          unless you ask for one — and most patients never do, which is exactly how billing departments prefer it.
          The summary statement that arrives automatically just shows a total. The itemized version shows you
          everything, line by line, and that is where the errors live.
        </p>

        <h2>First: get the right document</h2>

        <p>
          There are three documents most patients confuse. An <strong>Explanation of Benefits (EOB)</strong> comes
          from your insurance company — it shows what was billed, what they agreed to pay, and what you owe after
          their negotiated discount. A <strong>summary bill</strong> comes from the hospital or provider and
          shows a single total. An <strong>itemized bill</strong> — sometimes called an itemized statement or
          UB-04 form — lists every charge individually with the specific procedure codes attached.
        </p>

        <p>
          You want the itemized bill. Call the hospital's billing department and ask for it directly. Say:
          "I'd like a complete itemized statement listing all charges with CPT and revenue codes." They are
          required to provide it. Some will email it same-day; others take up to two weeks.
        </p>

        <h2>What each column means</h2>

        <p>Itemized bills vary in format, but most share the same core columns. Here is what each one tells you:</p>

        <div className={s.glossaryBox}>
          <div>
            <p className={s.glossaryTerm}>Date of service</p>
            <p className={s.glossaryDef}>
              The date the service was performed. Check this carefully if you had a multi-day hospital stay —
              being charged for a day you were discharged is one of the most common errors on inpatient bills.
            </p>
          </div>
          <div style={{ marginTop: '1rem' }}>
            <p className={s.glossaryTerm}>Revenue code</p>
            <p className={s.glossaryDef}>
              A four-digit code used by hospitals to categorize the type of service (room charges, pharmacy,
              lab, radiology, etc.). Revenue code 0250 means pharmacy. Code 0301 is laboratory.
            </p>
          </div>
          <div style={{ marginTop: '1rem' }}>
            <p className={s.glossaryTerm}>CPT / HCPCS code</p>
            <p className={s.glossaryDef}>
              A five-digit code describing the exact procedure or service. This is the most important field
              on the bill. CPT 99214 means "established patient office visit, moderate-to-high complexity."
              CPT 93000 is an EKG. These codes directly determine what insurance pays — and what you owe.
            </p>
          </div>
          <div style={{ marginTop: '1rem' }}>
            <p className={s.glossaryTerm}>Description</p>
            <p className={s.glossaryDef}>
              A text label for the service. The description and the CPT code should match. If the description
              says "basic office visit" but the CPT code is 99215 (the highest-complexity visit level), that
              discrepancy is worth questioning.
            </p>
          </div>
          <div style={{ marginTop: '1rem' }}>
            <p className={s.glossaryTerm}>Units / quantity</p>
            <p className={s.glossaryDef}>
              How many times the service was performed. A quantity of 2 for a procedure you had once is a
              duplicate charge. A quantity of 14 for a medication you took for three days is worth scrutinizing.
            </p>
          </div>
          <div style={{ marginTop: '1rem' }}>
            <p className={s.glossaryTerm}>Billed amount</p>
            <p className={s.glossaryDef}>
              What the provider charged before any discounts or insurance adjustments. This number is almost
              always higher than what anyone actually pays — it is the starting point for negotiation.
            </p>
          </div>
          <div style={{ marginTop: '1rem' }}>
            <p className={s.glossaryTerm}>Allowed amount / adjusted amount</p>
            <p className={s.glossaryDef}>
              The negotiated rate between the provider and your insurer. The difference between the billed
              amount and the allowed amount is written off — you are not responsible for it.
            </p>
          </div>
          <div style={{ marginTop: '1rem' }}>
            <p className={s.glossaryTerm}>Patient responsibility</p>
            <p className={s.glossaryDef}>
              What you actually owe after insurance. Reconcile this with your EOB — if the two documents show
              different amounts for the same service, one of them is wrong.
            </p>
          </div>
        </div>

        <h2>Four things to check before you pay anything</h2>

        <p>
          You do not need a medical background to catch the most common errors. Most of them are visible to
          anyone who knows what to look for.
        </p>

        <p>
          <strong>1. Duplicate line items.</strong> Search the bill for the same CPT code appearing twice on
          the same date. CPT 85025 (complete blood count) listed twice on the same day is a duplicate. You pay for it once.
        </p>

        <p>
          <strong>2. Services on dates you were not there.</strong> Cross-reference every date of service
          against your actual visit dates. A room charge on your discharge day is a common error.
        </p>

        <p>
          <strong>3. The description does not match what happened.</strong> If you had a 15-minute follow-up
          but the bill shows CPT 99215 (requiring at least 40 minutes of total time), that is upcoding — the
          difference between a 99213 ($90) and a 99215 ($182) visit under the 2026 Medicare fee schedule.
        </p>

        <p>
          <strong>4. Charges for things you do not recognize.</strong> Make a list of every line item you
          cannot match to something that actually happened. Call the billing department and ask for a
          plain-English explanation. "I cannot verify this service was provided" is a complete sentence.
        </p>

        <h2>When to push back</h2>

        <p>
          Billing departments are not adversaries, but they do make mistakes — and they are not going to audit
          their own work for your benefit. If something looks wrong, ask for it in writing. If a charge is
          removed verbally but does not disappear from the next statement, follow up with a reference number.
        </p>

        <p>
          Most hospitals give you 60 to 180 days from the statement date to dispute. Request an extension in
          writing if you are waiting on your EOB.
        </p>

        <p>
          Billing errors are not rare edge cases. Studies consistently find errors in the majority of hospital
          bills. The patients who catch them are not smarter — they just looked.
        </p>

      </div>

      <Citations sources={[
        { label: 'CMS — 2026 Medicare Physician Fee Schedule Final Rule', url: 'https://www.cms.gov/newsroom/fact-sheets/calendar-year-cy-2026-medicare-physician-fee-schedule-final-rule-cms-1832-f' },
        { label: 'CMS — Physician Fee Schedule Lookup Tool', url: 'https://www.cms.gov/medicare/physician-fee-schedule/search' },
        { label: "Medical Billing Advocates of America — Billing Error Statistics (via Becker's Hospital Review)", url: 'https://www.beckershospitalreview.com/finance/medical-billing-errors-growing-says-medical-billing-advocates-of-america.html' },
        { label: 'CMS — UB-04 Claim Form Instructions', url: 'https://www.cms.gov/medicare/billing/electronicbillingediinstances/ub04' },
      ]} />

      <Cta />

      <RelatedArticles current="how-to-read-an-itemized-medical-bill" />
    </article>
  );
}

function Cta(): JSX.Element {
  return (
    <div className={s.ctaBox}>
      <p className={s.ctaTitle}>Let Claro<em style={{ fontStyle: 'italic' }}>Bill</em> read it for you</p>
      <p className={s.ctaNote}>
        Upload your bill and we'll check every CPT code against Medicare rates, flag duplicates,
        and generate a dispute letter — in minutes.
      </p>
      <Link href="/auth/sign-in" className={s.ctaBtn}>
        Analyze my bill — it's free
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
];

function RelatedArticles({ current }: { current: string }): JSX.Element {
  const related = allArticles.filter((a) => a.slug !== current);
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
