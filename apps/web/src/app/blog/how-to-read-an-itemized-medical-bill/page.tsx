import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'How to Read an Itemized Medical Bill — Clarobill',
  description: 'What the columns, codes, and dollar amounts on your itemized medical bill actually mean — and how to find the errors hiding in plain sight.',
};

export default function Article(): JSX.Element {
  return (
    <article>
      <div className="mb-4 flex items-center gap-3 text-sm text-gray-400">
        <span>April 7, 2026</span>
        <span>·</span>
        <span>7 min read</span>
        <span>·</span>
        <span>Clarobill Team</span>
      </div>

      <h1 className="text-4xl font-bold text-gray-900 mb-6 leading-tight">
        How to Read an Itemized Medical Bill
      </h1>

      <p className="text-xl text-gray-500 mb-10 leading-relaxed">
        What the columns, codes, and dollar amounts actually mean — and how to spot the line items that should not be there.
      </p>

      <div className="prose-content space-y-6 text-gray-700 leading-relaxed">

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

        <h2 className="text-2xl font-bold text-gray-900 mt-10 mb-4">First: get the right document</h2>

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

        <h2 className="text-2xl font-bold text-gray-900 mt-10 mb-4">What each column means</h2>

        <p>
          Itemized bills vary in format, but most share the same core columns. Here is what each one tells you:
        </p>

        <div className="bg-gray-50 rounded-xl p-6 space-y-4 my-6">
          <div>
            <p className="font-semibold text-gray-900">Date of service</p>
            <p className="text-sm text-gray-600 mt-1">
              The date the service was performed. Check this carefully if you had a multi-day hospital stay —
              being charged for a day you were discharged is one of the most common errors on inpatient bills.
            </p>
          </div>
          <div>
            <p className="font-semibold text-gray-900">Revenue code</p>
            <p className="text-sm text-gray-600 mt-1">
              A four-digit code used by hospitals to categorize the type of service (room charges, pharmacy,
              lab, radiology, etc.). Revenue code 0250 means pharmacy. Code 0301 is laboratory. These codes
              tell you the department — not what was done specifically.
            </p>
          </div>
          <div>
            <p className="font-semibold text-gray-900">CPT / HCPCS code</p>
            <p className="text-sm text-gray-600 mt-1">
              A five-digit code describing the exact procedure or service. This is the most important field
              on the bill. CPT 99214 means "established patient office visit, moderate-to-high complexity."
              CPT 93000 is an EKG. These codes directly determine what insurance pays — and what you owe.
            </p>
          </div>
          <div>
            <p className="font-semibold text-gray-900">Description</p>
            <p className="text-sm text-gray-600 mt-1">
              A text label for the service. The description and the CPT code should match. If the description
              says "basic office visit" but the CPT code is 99215 (the highest-complexity visit level), that
              discrepancy is worth questioning.
            </p>
          </div>
          <div>
            <p className="font-semibold text-gray-900">Units / quantity</p>
            <p className="text-sm text-gray-600 mt-1">
              How many times the service was performed or how many units were dispensed. A quantity of 2 for
              a procedure you had once is a duplicate charge. A quantity of 14 for a medication you took for
              three days is worth scrutinizing.
            </p>
          </div>
          <div>
            <p className="font-semibold text-gray-900">Billed amount</p>
            <p className="text-sm text-gray-600 mt-1">
              What the provider charged before any discounts or insurance adjustments. This number is almost
              always higher than what anyone actually pays — it is the starting point for negotiation, not
              the final word.
            </p>
          </div>
          <div>
            <p className="font-semibold text-gray-900">Allowed amount / adjusted amount</p>
            <p className="text-sm text-gray-600 mt-1">
              The negotiated rate between the provider and your insurer. This is what the insurer considers
              a fair price for the service. The difference between the billed amount and the allowed amount
              is written off — you are not responsible for it.
            </p>
          </div>
          <div>
            <p className="font-semibold text-gray-900">Patient responsibility</p>
            <p className="text-sm text-gray-600 mt-1">
              What you actually owe after insurance. This is the number you need to reconcile with your EOB
              from the insurer — if the two documents show different amounts for the same service, one of
              them is wrong.
            </p>
          </div>
        </div>

        <h2 className="text-2xl font-bold text-gray-900 mt-10 mb-4">Four things to check before you pay anything</h2>

        <p>
          You do not need a medical background to catch the most common errors. Most of them are visible to
          anyone who knows what to look for.
        </p>

        <p>
          <strong>1. Duplicate line items.</strong> Search the bill for the same CPT code appearing twice on
          the same date. This happens more than you would expect — especially for lab work, where multiple
          specimens from a single blood draw sometimes get entered as separate charges. CPT 85025 (complete
          blood count) listed twice on the same day is a duplicate. You pay for it once.
        </p>

        <p>
          <strong>2. Services on dates you were not there.</strong> Cross-reference every date of service
          against your actual visit dates. For inpatient stays, check the admit date and discharge date on
          your paperwork. A room charge on your discharge day is a common error — you left in the morning,
          but the system charged for a full day.
        </p>

        <p>
          <strong>3. The description does not match what happened.</strong> If you had a 15-minute follow-up
          but the bill shows CPT 99215 (a visit code that requires at least 40 minutes of total time), that
          is upcoding. It is one of the most financially significant errors on outpatient bills — the
          difference between a 99213 ($90) and a 99215 ($182) visit is over $90 under the 2026 Medicare fee schedule — and proportionally more with private insurance.
        </p>

        <p>
          <strong>4. Charges for things you do not recognize at all.</strong> Make a list of every line item
          you cannot match to something that actually happened during your visit. Then call the billing
          department and ask for a plain-English explanation of each one. If they cannot explain it, ask to
          have it reviewed. "I cannot verify this service was provided" is a complete sentence.
        </p>

        <h2 className="text-2xl font-bold text-gray-900 mt-10 mb-4">When to push back</h2>

        <p>
          Billing departments are not adversaries, but they do make mistakes — and they are also not going
          to audit their own work for your benefit. The burden of catching errors falls on you. If something
          looks wrong, ask for it in writing. If a charge is removed verbally but does not disappear from
          the next statement, follow up in writing with a reference number.
        </p>

        <p>
          The window to dispute matters too. Most hospitals give you 60 to 180 days from the statement date.
          If you are waiting on your EOB from the insurer before comparing, do not wait too long — request
          an extension in writing if needed.
        </p>

        <p>
          Billing errors are not rare edge cases. Studies consistently find errors in the majority of
          hospital bills. The patients who catch them are not smarter — they just looked.
        </p>

      </div>

      <Citations sources={[
        { label: 'CMS — 2026 Medicare Physician Fee Schedule Final Rule', url: 'https://www.cms.gov/newsroom/fact-sheets/calendar-year-cy-2026-medicare-physician-fee-schedule-final-rule-cms-1832-f' },
        { label: 'CMS — Physician Fee Schedule Lookup Tool', url: 'https://www.cms.gov/medicare/physician-fee-schedule/search' },
        { label: 'Medical Billing Advocates of America — Billing Error Statistics (via Becker\'s Hospital Review)', url: 'https://www.beckershospitalreview.com/finance/medical-billing-errors-growing-says-medical-billing-advocates-of-america.html' },
        { label: 'CMS — UB-04 Claim Form Instructions', url: 'https://www.cms.gov/medicare/billing/electronicbillingediinstances/ub04' },
      ]} />

      <Cta />

      <RelatedArticles current="how-to-read-an-itemized-medical-bill" />
    </article>
  );
}

function Cta(): JSX.Element {
  return (
    <div className="mt-14 bg-gray-900 rounded-2xl p-8 text-center">
      <p className="text-white font-semibold text-xl mb-2">Let Clarobill read it for you</p>
      <p className="text-gray-400 text-sm mb-6 max-w-md mx-auto">
        Upload your bill and we'll check every CPT code against Medicare rates, flag duplicates,
        and generate a dispute letter — in minutes.
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
