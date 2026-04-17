import type { Metadata } from 'next';
import Link from 'next/link';
import s from '../blog.module.css';

export const metadata: Metadata = {
  title: 'How to Dispute a Hospital Bill: A Step-by-Step Guide — Clarobill',
  description: 'A practical guide to disputing hospital billing errors — from requesting your itemized bill to writing a dispute letter that gets results.',
};

export default function Article(): JSX.Element {
  return (
    <article>
      <div className={s.articleByline}>
        <span>April 17, 2026</span>
        <span>·</span>
        <span>9 min read</span>
        <span>·</span>
        <span>Clarobill Team</span>
      </div>

      <h1 className={s.articleH1}>
        How to Dispute a Hospital Bill: A Step-by-Step Guide
      </h1>

      <p className={s.articleLead}>
        Disputing a hospital bill is not complicated — but it does require a specific sequence of steps.
        Most disputes that succeed follow the same pattern. Most that fail skip one of these steps.
      </p>

      <div className={s.articleBody}>

        <p>
          The first thing to understand is that disputes work. Hospitals negotiate. Billing departments
          correct errors. Insurers reprocess claims. The reason most people overpay is not that the system
          is impenetrable — it is that most people do not know what to ask for, or do not ask at all.
        </p>

        <p>
          The second thing to understand is that you are not disputing out of nowhere. You are disputing
          against a published set of rules. The Medicare fee schedule, the National Correct Coding Initiative
          edits, your insurer's explanation of benefits — these are all public documents. When a charge
          violates them, you have a factual basis for your dispute, not just a complaint.
        </p>

        <p>Here is the sequence, start to finish.</p>

        <h2>Step 1: Request the itemized bill</h2>

        <p>
          You are legally entitled to an itemized bill. Call the hospital billing department and ask for one.
          Do not accept the summary bill — the one that shows "hospital services: $14,200" as a single line.
          You need every charge broken out individually, with the CPT or HCPCS code, the date of service,
          the quantity, and the dollar amount.
        </p>

        <p>
          In most states this must be provided free of charge. Some hospitals will try to charge a small
          fee. Decline it and ask for a supervisor if necessary. Federal billing transparency requirements
          that took effect in 2021 require hospitals to provide a machine-readable list of their standard
          charges — your itemized bill falls under the same general transparency mandate.
        </p>

        <p>
          <strong>What to do if they push back:</strong> Ask specifically for the UB-04 claim form or
          the 1500 form (for physician bills). These are the standard forms submitted to your insurer
          and contain all the codes and charges.
        </p>

        <h2>Step 2: Request your Explanation of Benefits</h2>

        <p>
          Your insurer's Explanation of Benefits (EOB) shows what your insurer was billed, what they agreed
          to pay, and what they say you owe. This is a separate document from the hospital bill — and the
          two do not always match.
        </p>

        <p>
          The EOB is typically available in your insurer's online portal within two to four weeks of a claim
          being processed. Download it and keep it. It tells you two things that matter: what your insurer's
          contracted rate is for each service (the "allowed amount"), and whether the claim was processed
          correctly.
        </p>

        <p>
          If you see a service on your hospital bill that does not appear on your EOB, that is a red flag —
          the insurer may not have been billed for it, or it was submitted under a different code.
        </p>

        <h2>Step 3: Identify the errors</h2>

        <p>
          With your itemized bill in hand, look for these patterns:
        </p>

        <ul>
          <li>
            <strong>Duplicate charges:</strong> The same CPT code billed twice on the same date.
            Lab work and medications are the most common categories.
          </li>
          <li>
            <strong>Unbundled codes:</strong> Procedures that should be included in a larger code
            but were billed separately. A colonoscopy (45378) should include the biopsy (45380)
            when performed in the same session — they cannot be billed as two separate items
            without a valid modifier.
          </li>
          <li>
            <strong>Price outliers:</strong> Charges that are two or more times the Medicare rate
            for the same service. The Medicare Physician Fee Schedule is public — you can look
            up the published rate for any CPT code.
          </li>
          <li>
            <strong>Charges for services not received:</strong> A physical therapy session on the
            day you were discharged. A specialist consultation you never had. These often result
            from scheduled services that were cancelled but not removed from the billing queue.
          </li>
          <li>
            <strong>Incorrect facility fees:</strong> Outpatient departments billed at hospital
            outpatient rates when the service should have been billed as a professional service.
          </li>
        </ul>

        <h2>Step 4: Calculate what you should have been charged</h2>

        <p>
          For each error you identify, you need a specific number — not just "this seems high."
          Dispute letters that succeed cite exact amounts and exact rules.
        </p>

        <p>
          For price outliers, the reference point is the Medicare Physician Fee Schedule (PFS) rate for
          your locality. CMS publishes these rates quarterly. If a charge is more than two times the
          Medicare rate with no clinical justification, that is a concrete benchmark to cite.
        </p>

        <p>
          For unbundled codes, the reference is the CMS NCCI edit table — a public list of code pairs
          that cannot be billed together. If two codes on your bill appear in the NCCI edit table without
          a valid modifier, that is a specific, documented rule violation.
        </p>

        <p>
          For duplicate charges, the math is simple: you owe for one instance, not two.
        </p>

        <h2>Step 5: Write the dispute letter</h2>

        <p>
          A dispute letter is more effective than a phone call because it creates a paper trail and triggers
          a formal review process. Most hospitals have a dispute resolution procedure that begins with a
          written request.
        </p>

        <p>
          Your letter should include:
        </p>

        <ul>
          <li>Your name, date of birth, account number, and date of service</li>
          <li>The specific CPT code(s) you are disputing and the exact dollar amounts</li>
          <li>The rule or rate being violated (NCCI edit, Medicare fee schedule, duplicate charge)</li>
          <li>The amount you believe you owe (if you can calculate it)</li>
          <li>A request for a written response within 30 days</li>
        </ul>

        <p>
          Example dispute language for an unbundling error:
        </p>

        <div className={s.glossaryBox}>
          <p className={s.glossaryTerm}>Sample dispute letter paragraph</p>
          <p className={s.glossaryDef}>
            "My bill dated [date] includes a charge for CPT 45380 (colonoscopy with biopsy, $380)
            billed separately from CPT 45378 (diagnostic colonoscopy, $1,240) on the same date of
            service. Per CMS National Correct Coding Initiative (NCCI) edit guidelines, 45380 is a
            component code of 45378 when performed in the same session and may not be billed
            separately without a valid modifier. No modifier is present on my itemized bill.
            I am requesting removal of the CPT 45380 charge and correction of my balance accordingly."
          </p>
        </div>

        <p>
          Send the letter by certified mail or email with a read receipt. Keep a copy. Note the date sent.
        </p>

        <h2>Step 6: Follow up — and escalate if necessary</h2>

        <p>
          Most billing departments have a 30-day review window. If you do not hear back, call and reference
          your written dispute. Ask for the case number or reference number and note the name of the
          person you speak with.
        </p>

        <p>
          If the dispute is not resolved satisfactorily, you have several escalation paths:
        </p>

        <ul>
          <li>
            <strong>Your insurer's appeals process:</strong> If the issue involves incorrect processing
            of a covered claim, your insurer can intervene directly with the provider.
          </li>
          <li>
            <strong>Your state insurance commissioner:</strong> For balance billing violations or
            No Surprises Act issues involving unexpected out-of-network charges.
          </li>
          <li>
            <strong>The hospital's patient advocate or ombudsman:</strong> Most large hospitals have
            a patient financial services advocate whose job is to resolve exactly this type of dispute.
          </li>
        </ul>

        <h2>How much time does this take?</h2>

        <p>
          Reading and annotating an itemized bill manually takes one to three hours depending on the
          length of the stay. Looking up CPT codes and cross-referencing the NCCI edit table takes
          additional time. Writing a well-cited dispute letter takes another hour.
        </p>

        <p>
          That is why most people do not do it. The friction is real, and it is intentional — a system
          that is confusing enough to deter disputes is a system that collects more revenue.
        </p>

        <p>
          The dispute process itself is not hard. It is just tedious. The more of it you can automate,
          the more likely you are to actually follow through.
        </p>

      </div>

      <Citations sources={[
        { label: 'CMS — Medicare Physician Fee Schedule (PFS) Public Files', url: 'https://www.cms.gov/medicare/physician-fee-schedule/search' },
        { label: 'CMS — National Correct Coding Initiative (NCCI) Edits', url: 'https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits' },
        { label: 'CMS — Hospital Price Transparency Final Rule (2021)', url: 'https://www.cms.gov/hospital-price-transparency' },
        { label: 'CMS — No Surprises Act Overview', url: 'https://www.cms.gov/nosurprises' },
      ]} />

      <Cta />

      <RelatedArticles current="how-to-dispute-a-hospital-bill" />
    </article>
  );
}

function Cta(): JSX.Element {
  return (
    <div className={s.ctaBox}>
      <p className={s.ctaTitle}>Skip steps 3–5 — we do them for you</p>
      <p className={s.ctaNote}>
        ClaroBill reads your bill, identifies every error against the Medicare fee schedule and
        NCCI edit rules, and writes the dispute letter for you. Free analysis, no percentage cut.
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
