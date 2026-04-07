import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'The Most Common Medical Billing Errors (And How to Dispute Them) — Clarobill',
  description: 'Duplicate charges, upcoded visits, unbundled procedures — here is what each billing error looks like on a real bill and exactly what to say when you dispute it.',
};

export default function Article(): JSX.Element {
  return (
    <article>
      <div className="mb-4 flex items-center gap-3 text-sm text-gray-400">
        <span>April 7, 2026</span>
        <span>·</span>
        <span>8 min read</span>
        <span>·</span>
        <span>Clarobill Team</span>
      </div>

      <h1 className="text-4xl font-bold text-gray-900 mb-6 leading-tight">
        The Most Common Medical Billing Errors (And How to Dispute Them)
      </h1>

      <p className="text-xl text-gray-500 mb-10 leading-relaxed">
        Duplicate charges, upcoded visits, unbundled procedures — here is what each one looks like on a real
        bill and what to say when you dispute it.
      </p>

      <div className="space-y-6 text-gray-700 leading-relaxed">

        <p>
          According to the Medical Billing Advocates of America, errors appear in over 80% of the hospital bills
          they review. Not occasional errors — systematic ones. The same mistakes, recurring across
          different hospitals, different states, different patient populations.
        </p>

        <p>
          The errors are not usually the result of fraud. Most come from the complexity of the coding system
          itself: over 10,000 CPT codes, thousands of diagnosis codes, and a web of billing rules that even
          experienced coders get wrong. The problem is that when a mistake happens, it almost always runs
          in the provider's favor. You get charged for something you should not have been charged for,
          and nobody tells you.
        </p>

        <p>
          Here are the errors that show up most often — and what to do about each one.
        </p>

        <h2 className="text-2xl font-bold text-gray-900 mt-10 mb-4">1. Duplicate charges</h2>

        <p>
          The same service billed twice. It sounds too obvious to happen, but it is one of the most common
          errors on hospital bills, particularly for lab work and medications administered during a stay.
        </p>

        <p>
          What it looks like: CPT 85025 (complete blood count) appears twice on September 14th. Or
          "acetaminophen 500mg" shows a quantity of 24 when you were only there for two days.
        </p>

        <p>
          How to dispute it: Call the billing department and say: "I have two charges for CPT 85025 on
          September 14th. My records show one blood draw that day. Can you show me the documentation
          for the second charge?" Ask them to pull the nursing notes. If they cannot produce documentation
          for both, the duplicate should be removed.
        </p>

        <h2 className="text-2xl font-bold text-gray-900 mt-10 mb-4">2. Upcoding</h2>

        <p>
          Upcoding is when a provider bills for a more complex — and more expensive — service than what
          was actually performed. It is most common with office visit codes (the 99200 series) and
          emergency department visits (the 99281–99285 series).
        </p>

        <p>
          The dollar difference matters. A level-3 office visit (99213) reimburses at roughly $90 under
          the 2026 Medicare fee schedule. A level-4 visit (99214) reimburses at about $128. A level-5
          (99215) is around $182. Upcoding a routine follow-up to a level-5 visit adds roughly $92 to
          your bill — and that happens across millions of patients.
        </p>

        <p>
          What it looks like: You had a 10-minute post-surgical check. Your bill shows CPT 99215, which
          requires documented medical decision-making of high complexity or at least 40 minutes of total
          time. The visit notes in your patient portal show a brief note with three lines.
        </p>

        <p>
          How to dispute it: Request a copy of the visit documentation (you are entitled to your medical
          records). Compare the note complexity and time documented against the requirements for the billed
          code. If the note does not support the level billed, write to the billing department citing the
          specific CPT requirements: "CPT 99215 requires high-complexity medical decision-making or 40+
          minutes of total time. The documentation supports 99213 at most. Please review and correct."
        </p>

        <h2 className="text-2xl font-bold text-gray-900 mt-10 mb-4">3. Unbundling</h2>

        <p>
          Some CPT codes are designed to include related procedures — billing them separately is called
          unbundling, and it is prohibited by the National Correct Coding Initiative (NCCI) rules that
          Medicare and most insurers follow.
        </p>

        <p>
          A real example: CPT 29881 covers knee arthroscopy with medial or lateral meniscectomy. CPT 29877
          covers arthroscopic debridement of the knee. Under NCCI rules, 29877 is included in 29881 when
          performed during the same surgical session — they cannot be billed separately. But they sometimes
          are, adding several hundred dollars to the bill.
        </p>

        <p>
          What it looks like: Two or more procedure codes from the same surgery, where one should logically
          be included in the other. Unbundling is harder to catch without knowing the specific NCCI edits,
          but if you see multiple codes from the same surgical date that cover overlapping body parts or
          steps of the same procedure, it is worth investigating.
        </p>

        <p>
          How to dispute it: Reference the NCCI edit directly. "CPT 29877 is a component of CPT 29881
          under CMS NCCI edit [pair number]. These two codes were billed together on [date]. Per NCCI
          guidelines, they cannot be billed together without a valid modifier. Please review." If a
          modifier (like modifier 59) was used to override the edit, ask for the documentation supporting
          the modifier's use.
        </p>

        <h2 className="text-2xl font-bold text-gray-900 mt-10 mb-4">4. Charges for services not rendered</h2>

        <p>
          A charge for something that simply did not happen. Physical therapy on a day you were discharged.
          An MRI you did not receive. A consultation from a specialist you never saw.
        </p>

        <p>
          This is the error patients are most reluctant to push back on — it can feel like an accusation.
          It is not. These charges often result from a scheduled service that was cancelled but never removed
          from the billing queue, or from notes being applied to the wrong patient record. The intent is
          rarely malicious. The charge is still wrong.
        </p>

        <p>
          How to dispute it: Keep your own notes during any hospital stay — which tests you had, which
          specialists visited, which medications you received. When you get the bill, go line by line.
          For any charge you cannot account for, ask the billing department: "Can you tell me which
          clinician ordered or performed this service, and on which date?" If they cannot answer, request
          removal.
        </p>

        <h2 className="text-2xl font-bold text-gray-900 mt-10 mb-4">5. Balance billing from out-of-network providers</h2>

        <p>
          You chose an in-network hospital. You did not choose — and in many cases were never told about —
          the out-of-network anesthesiologist, radiologist, or assistant surgeon who also treated you. Then
          a second bill arrives from a provider you have never heard of, for a balance your insurer will not
          cover.
        </p>

        <p>
          The No Surprises Act, which took effect in 2022, prohibits this practice for most emergency care
          and for non-emergency care where you had no meaningful choice of provider. If you receive a
          balance bill for services provided at an in-network facility, you may have legal protection. File
          a complaint with your state insurance commissioner and reference the No Surprises Act.
        </p>

        <h2 className="text-2xl font-bold text-gray-900 mt-10 mb-4">How to write an effective dispute letter</h2>

        <p>
          Phone calls get lost. A written dispute creates a paper trail. When you write, be specific:
          cite the exact CPT code, the exact date, the exact dollar amount, and the exact reason the charge
          is wrong. Reference the rule being violated where applicable (NCCI edit number, No Surprises Act,
          CPT documentation requirements).
        </p>

        <p>
          Send it certified mail or email with read receipt. Keep a copy. Note the date and the name of
          anyone you speak with by phone. Most disputes are resolved within 30 to 60 days — but only if
          you follow up when you do not hear back.
        </p>

        <p>
          The billing department's job is to collect. Your job is to pay what you actually owe. Those are
          not the same number — and the difference is worth the time it takes to look.
        </p>

      </div>

      <Citations sources={[
        { label: 'Medical Billing Advocates of America — Billing Error Statistics (via Becker\'s Hospital Review)', url: 'https://www.beckershospitalreview.com/finance/medical-billing-errors-growing-says-medical-billing-advocates-of-america.html' },
        { label: 'CMS — 2026 Medicare Physician Fee Schedule Final Rule', url: 'https://www.cms.gov/newsroom/fact-sheets/calendar-year-cy-2026-medicare-physician-fee-schedule-final-rule-cms-1832-f' },
        { label: 'CMS — National Correct Coding Initiative (NCCI) Edits', url: 'https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits' },
        { label: 'CMS — No Surprises Act Overview', url: 'https://www.cms.gov/nosurprises' },
      ]} />

      <Cta />

      <RelatedArticles current="common-medical-billing-errors" />
    </article>
  );
}

function Cta(): JSX.Element {
  return (
    <div className="mt-14 bg-gray-900 rounded-2xl p-8 text-center">
      <p className="text-white font-semibold text-xl mb-2">Find these errors in your bill</p>
      <p className="text-gray-400 text-sm mb-6 max-w-md mx-auto">
        Clarobill checks every CPT code against NCCI edit rules, flags duplicates and price outliers,
        and writes your dispute letter automatically.
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
