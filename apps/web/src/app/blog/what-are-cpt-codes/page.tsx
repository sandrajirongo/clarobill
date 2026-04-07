import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'What Are CPT Codes? A Patient\'s Guide — Clarobill',
  description: 'CPT codes are the five-digit numbers that determine what your medical care costs. Here is how they work, how they get abused, and how to check whether yours are right.',
};

export default function Article(): JSX.Element {
  return (
    <article>
      <div className="mb-4 flex items-center gap-3 text-sm text-gray-400">
        <span>April 7, 2026</span>
        <span>·</span>
        <span>6 min read</span>
        <span>·</span>
        <span>Clarobill Team</span>
      </div>

      <h1 className="text-4xl font-bold text-gray-900 mb-6 leading-tight">
        What Are CPT Codes? A Patient's Guide
      </h1>

      <p className="text-xl text-gray-500 mb-10 leading-relaxed">
        The five-digit numbers on your bill determine what you pay. Here is how they work, why they
        get abused, and how to check whether yours are right.
      </p>

      <div className="space-y-6 text-gray-700 leading-relaxed">

        <p>
          Somewhere on your medical bill, there are five-digit numbers that most patients ignore. They look
          like serial codes — 99213, 93000, 80053 — and they are easy to skip past when you are trying to
          make sense of a bill that already feels overwhelming.
        </p>

        <p>
          Those numbers are CPT codes, and they are arguably the most important field on the entire document.
          Every CPT code maps to a specific dollar amount. Get the code wrong — intentionally or not — and
          the charge attached to it changes. That is where a lot of billing errors originate.
        </p>

        <h2 className="text-2xl font-bold text-gray-900 mt-10 mb-4">Where CPT codes come from</h2>

        <p>
          CPT stands for Current Procedural Terminology. The American Medical Association owns and maintains
          the codebook, which has been updated annually since 1966. The current edition contains over 10,000
          codes covering every medical, surgical, and diagnostic service a provider might perform.
        </p>

        <p>
          When a doctor sees you, they (or their billing staff) select the CPT code that best describes what
          happened during the visit. That code goes on the claim submitted to your insurer. The insurer checks
          the code against their fee schedule — a table of what they have agreed to pay for each service —
          and pays accordingly. The code is the mechanism that converts a clinical event into a dollar amount.
        </p>

        <p>
          Physicians do not have much flexibility here. The code has to match the documentation in the medical
          record. If a coder selects a higher-level code than the notes support, that is a compliance
          violation. In theory. In practice, audits are infrequent and the financial incentive to code high
          is real.
        </p>

        <h2 className="text-2xl font-bold text-gray-900 mt-10 mb-4">The codes you will actually see</h2>

        <p>
          Most patients encounter a handful of code ranges repeatedly. Here is what the common ones mean:
        </p>

        <div className="bg-gray-50 rounded-xl p-6 space-y-5 my-6">
          <div>
            <p className="font-semibold text-gray-900">99202 – 99215 &nbsp;·&nbsp; Office and outpatient visits</p>
            <p className="text-sm text-gray-600 mt-1">
              These are the codes for clinic visits with a physician or qualified provider. The number
              indicates complexity: 99202 is a straightforward new patient visit; 99215 is a complex
              established-patient visit requiring high-level medical decision-making. The Medicare
              The 2026 Medicare fee schedule puts reimbursement at roughly $70 for a 99202 and $182 for
              a 99215. Most routine follow-ups should be coded at 99213 ($90) or 99214 ($128). If you
              see 99215 for a brief check-in, that warrants a closer look.
            </p>
          </div>
          <div>
            <p className="font-semibold text-gray-900">99281 – 99285 &nbsp;·&nbsp; Emergency department visits</p>
            <p className="text-sm text-gray-600 mt-1">
              Same structure as the office visit codes, but for emergency care. Level 1 (99281) is
              minimal-severity; Level 5 (99285) is high-severity with a threat to life or function.
              Emergency visits are frequently coded at 99284 or 99285 regardless of the actual
              presenting complaint — upcoding is especially common in ED billing.
            </p>
          </div>
          <div>
            <p className="font-semibold text-gray-900">85025 &nbsp;·&nbsp; Complete Blood Count (CBC)</p>
            <p className="text-sm text-gray-600 mt-1">
              One of the most ordered lab tests in medicine. If you had blood drawn, this code will likely
              appear. It should appear once per blood draw, not multiple times. Medicare pays around $12
              for this test under the Clinical Laboratory Fee Schedule — charges on hospital bills can run far higher.
            </p>
          </div>
          <div>
            <p className="font-semibold text-gray-900">80053 &nbsp;·&nbsp; Comprehensive Metabolic Panel (CMP)</p>
            <p className="text-sm text-gray-600 mt-1">
              A panel of 14 blood chemistry tests commonly ordered during hospital admissions and
              physicals. Covers kidney function, liver function, electrolytes, and blood glucose.
              Should be billed as a single panel code — not as 14 individual test codes.
            </p>
          </div>
          <div>
            <p className="font-semibold text-gray-900">93000 &nbsp;·&nbsp; Electrocardiogram (EKG/ECG)</p>
            <p className="text-sm text-gray-600 mt-1">
              A 12-lead EKG with interpretation and report. If you had heart monitoring done,
              this code should appear once. The 2026 Medicare rate is $15.36. Hospital charges for the
              same test routinely run $200–$500.
            </p>
          </div>
          <div>
            <p className="font-semibold text-gray-900">71046 &nbsp;·&nbsp; Chest X-ray, 2 views</p>
            <p className="text-sm text-gray-600 mt-1">
              Standard two-view chest radiograph. One of the most-ordered imaging studies in
              medicine. The 2026 Medicare rate is approximately $33. Hospital charges vary widely —
              anywhere from $200 to over $1,000 at some facilities for the identical study.
            </p>
          </div>
        </div>

        <h2 className="text-2xl font-bold text-gray-900 mt-10 mb-4">Why the same code costs different amounts</h2>

        <p>
          CPT codes standardize what was done. They do not standardize what anyone charges for it.
          A provider sets their own "chargemaster" rate — the billed amount before any negotiation.
          Your insurer then applies their contracted discount, resulting in the "allowed amount."
          If you are uninsured or the provider is out-of-network, you may be on the hook for
          something much closer to the chargemaster rate.
        </p>

        <p>
          This is why the same CPT 93000 EKG can show a billed amount of $150 at one facility and
          $600 at another. The procedure is identical. The CPT code is identical. The price has
          almost nothing to do with either.
        </p>

        <p>
          Medicare's published fee schedule is the most useful benchmark for patients. It represents
          what the federal government — the largest single payer in US healthcare — considers a
          reasonable payment for each procedure in each region. When a provider's charge for a
          service is two, three, or five times the Medicare rate, that is not automatically wrong,
          but it is worth noting.
        </p>

        <h2 className="text-2xl font-bold text-gray-900 mt-10 mb-4">Modifiers: the asterisks of medical billing</h2>

        <p>
          CPT codes sometimes appear with two-digit suffixes called modifiers. These modify the meaning
          of the base code — indicating, for example, that a procedure was performed on the left side
          vs. the right side (modifier LT or RT), or that two distinct procedures were performed during
          the same session (modifier 59).
        </p>

        <p>
          Modifier 59 deserves special attention. It is used to override National Correct Coding
          Initiative (NCCI) edits — the rules that prevent certain code combinations from being billed
          together. Used legitimately, it documents that two procedures really were separate and distinct.
          Used improperly, it is a tool for billing code pairs that should not be billed separately.
          When you see modifier 59 on your bill, it is worth understanding what it is overriding
          and whether the documentation supports it.
        </p>

        <h2 className="text-2xl font-bold text-gray-900 mt-10 mb-4">You are allowed to question the codes</h2>

        <p>
          Patients rarely ask about CPT codes because the system is not designed to be legible. The
          AMA charges licensing fees to access the complete code descriptions. Insurance companies
          process claims in proprietary systems. Billing departments are not trained to explain codes
          to patients — they are trained to collect balances.
        </p>

        <p>
          None of that changes the fact that you are entitled to know exactly what you are being charged
          for and why. If a code on your bill does not match your experience of the visit — if the
          complexity level seems wrong, if a procedure code appears for something you do not recall
          having — ask. Request the documentation. Ask for a plain-English explanation of the code.
          The codes are not obscure by necessity. They are just not typically explained to the person
          who pays the bill.
        </p>

      </div>

      <Citations sources={[
        { label: 'CMS — 2026 Medicare Physician Fee Schedule Final Rule', url: 'https://www.cms.gov/newsroom/fact-sheets/calendar-year-cy-2026-medicare-physician-fee-schedule-final-rule-cms-1832-f' },
        { label: 'CMS — Physician Fee Schedule Lookup Tool', url: 'https://www.cms.gov/medicare/physician-fee-schedule/search' },
        { label: 'CMS — Clinical Laboratory Fee Schedule', url: 'https://www.cms.gov/medicare/payment/fee-schedules/clinical-laboratory-fee-schedule-clfs' },
        { label: 'AMA — CPT Code Overview', url: 'https://www.ama-assn.org/practice-management/cpt/cpt-overview-and-code-approval' },
        { label: 'CMS — National Correct Coding Initiative (NCCI) Edits', url: 'https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits' },
        { label: 'MedFeeSchedule — CPT 93000 2026 Rate', url: 'https://www.medfeeschedule.com/code/93000' },
      ]} />

      <Cta />

      <RelatedArticles current="what-are-cpt-codes" />
    </article>
  );
}

function Cta(): JSX.Element {
  return (
    <div className="mt-14 bg-gray-900 rounded-2xl p-8 text-center">
      <p className="text-white font-semibold text-xl mb-2">We check every CPT code for you</p>
      <p className="text-gray-400 text-sm mb-6 max-w-md mx-auto">
        Clarobill compares each code on your bill against Medicare rates, flags upcoding and
        unbundled procedures, and writes your dispute letter automatically.
      </p>
      <Link
        href="/auth/sign-in"
        className="inline-block bg-white text-gray-900 font-semibold px-6 py-3 rounded-xl hover:bg-gray-100 transition-colors"
      >
        Analyze my bill — $9.99
      </Link>
    </div>
  );
}

function Citations({ sources }: { sources: { label: string; url: string }[] }): JSX.Element {
  return (
    <div className="mt-14 border-t border-gray-100 pt-8">
      <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-4">Sources</p>
      <ol className="space-y-2">
        {sources.map((source, i) => (
          <li key={source.url} className="text-sm text-gray-500">
            <span className="mr-2 text-gray-300">{i + 1}.</span>
            <a href={source.url} target="_blank" rel="noopener noreferrer" className="hover:text-teal-600 underline underline-offset-2">
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
  { slug: 'what-are-cpt-codes', title: 'What Are CPT Codes? A Patient\'s Guide' },
];

function RelatedArticles({ current }: { current: string }): JSX.Element {
  const related = allArticles.filter((a) => a.slug !== current);
  return (
    <div className="mt-14 border-t border-gray-100 pt-10">
      <p className="text-sm font-semibold text-gray-500 uppercase tracking-widest mb-6">More guides</p>
      <div className="space-y-4">
        {related.map((article) => (
          <Link
            key={article.slug}
            href={`/blog/${article.slug}`}
            className="block text-gray-900 font-medium hover:text-teal-600 transition-colors"
          >
            {article.title} →
          </Link>
        ))}
      </div>
    </div>
  );
}
