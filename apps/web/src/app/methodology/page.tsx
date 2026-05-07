import type { Metadata } from 'next';
import Link from 'next/link';
import { JsonLd } from '@/components/json-ld';
import s from '../blog/blog.module.css';

export const metadata: Metadata = {
  title: 'How ClaroBill Analyzes Your Medical Bill: Methodology',
  description:
    'ClaroBill runs 13 deterministic checks against every line item on your bill. Each finding cites a specific federal rule, an exact dollar discrepancy, and the authority behind the flag.',
  alternates: {
    canonical: 'https://www.clarobill.com/methodology',
    languages: {
      'en': 'https://www.clarobill.com/methodology',
      'x-default': 'https://www.clarobill.com/methodology',
    },
  },
};

const BREADCRUMB = {
  '@type': 'BreadcrumbList' as const,
  itemListElement: [
    { '@type': 'ListItem' as const, position: 1, name: 'Home', item: 'https://www.clarobill.com' },
    { '@type': 'ListItem' as const, position: 2, name: 'Methodology', item: 'https://www.clarobill.com/methodology' },
  ],
};

const HOWTO: import('@/components/json-ld').HowToSchema = {
  '@type': 'HowTo',
  name: 'How ClaroBill Audits a Medical Bill',
  description: '13 deterministic checks run against every line item. Each check cites a specific federal rule and produces an exact dollar discrepancy.',
  step: [
    { '@type': 'HowToStep', name: 'Duplicate charge detection', text: 'Identifies CPT or HCPCS codes that appear more than once on the same date of service with no clinical justification. Authority: CMS Claims Processing Manual, Chapter 4.', url: 'https://www.clarobill.com/methodology#duplicate-charge-detection' },
    { '@type': 'HowToStep', name: 'Price outlier detection', text: 'Compares each billed charge to the Medicare Physician Fee Schedule benchmark for the same code and locality. Flags charges that materially exceed the published rate. Authority: CMS MPFS.', url: 'https://www.clarobill.com/methodology#price-outlier-detection' },
    { '@type': 'HowToStep', name: 'NCCI Procedure-to-Procedure unbundling', text: 'Checks every code pair against the CMS NCCI PTP edit table. Flags pairs where one code should be bundled into the other with no overriding modifier. Authority: CMS NCCI Policy Manual.', url: 'https://www.clarobill.com/methodology#ncci-unbundling' },
    { '@type': 'HowToStep', name: 'NCCI Medically Unlikely Edits', text: 'Verifies that the units billed for each code do not exceed the CMS Medically Unlikely Edit (MUE) threshold for that code and service setting. Authority: CMS NCCI MUE table.', url: 'https://www.clarobill.com/methodology#ncci-mue' },
    { '@type': 'HowToStep', name: 'Balance billing — No Surprises Act', text: 'Checks whether out-of-network charges at in-network facilities exceed the patient\'s in-network cost-sharing, which is prohibited under the No Surprises Act (42 U.S.C. § 300gg-111).', url: 'https://www.clarobill.com/methodology#balance-billing' },
    { '@type': 'HowToStep', name: 'Charges for services not rendered', text: 'Cross-references billed line items against the itemized bill and any available clinical records for discrepancies between what was billed and what was documented as performed.', url: 'https://www.clarobill.com/methodology#services-not-rendered' },
    { '@type': 'HowToStep', name: 'Outpatient facility fee misclassification', text: 'Verifies that the place-of-service modifier matches the actual care setting. An office-visit code billed with a facility modifier generates a higher payment rate and may be incorrect. Authority: CMS Place of Service code set.', url: 'https://www.clarobill.com/methodology#facility-fee-misclassification' },
    { '@type': 'HowToStep', name: 'Global surgery period violations', text: 'Flags post-operative services billed separately within the global surgery period for the primary procedure code. Authority: CMS Global Surgery policy (Medicare Claims Processing Manual, Chapter 12).', url: 'https://www.clarobill.com/methodology#global-surgery' },
    { '@type': 'HowToStep', name: 'Modifier misuse', text: 'Verifies that modifiers appended to procedure codes are clinically appropriate and do not override NCCI edits without valid justification. Authority: CMS Modifier guidelines.', url: 'https://www.clarobill.com/methodology#modifier-misuse' },
    { '@type': 'HowToStep', name: 'Fragmented billing — 72-hour rule', text: 'Detects pre-admission outpatient services billed separately within 72 hours of an inpatient admission when they should be included in the DRG payment. Authority: CMS 3-day payment window policy.', url: 'https://www.clarobill.com/methodology#72-hour-rule' },
    { '@type': 'HowToStep', name: 'Units and quantity errors', text: 'Checks whether the number of units billed for drugs, supplies, or time-based services is consistent with the documented administration or clinical records.', url: 'https://www.clarobill.com/methodology#units-errors' },
    { '@type': 'HowToStep', name: 'Invalid or obsolete codes', text: 'Validates every CPT and HCPCS code against the code set effective for the date of service. Codes that were retired or not yet effective on the service date are flagged. Authority: AMA CPT annual release; CMS HCPCS.', url: 'https://www.clarobill.com/methodology#invalid-codes' },
    { '@type': 'HowToStep', name: 'Negotiated rate excess', text: 'Where the insurer\'s negotiated rate is available via hospital machine-readable files, checks whether the patient was billed more than the contracted rate for their plan. Authority: CMS Price Transparency Rule (45 CFR Part 180).', url: 'https://www.clarobill.com/methodology#negotiated-rate-excess' },
  ],
};

const DEFINED_TERMS: import('@/components/json-ld').DefinedTermSetSchema = {
  '@type': 'DefinedTermSet',
  name: 'Medical Billing Terms',
  hasDefinedTerm: [
    { '@type': 'DefinedTerm', name: 'CPT code', description: 'Current Procedural Terminology code. A 5-digit numeric code maintained by the AMA that identifies a medical procedure or service billed to an insurer.', inDefinedTermSet: 'https://www.clarobill.com/methodology' },
    { '@type': 'DefinedTerm', name: 'NCCI', description: 'National Correct Coding Initiative. A CMS program that publishes edit tables defining which procedure code pairs may not be billed together and the maximum units allowed per code.', inDefinedTermSet: 'https://www.clarobill.com/methodology' },
    { '@type': 'DefinedTerm', name: 'Medicare Physician Fee Schedule', description: 'The CMS schedule of payment amounts for over 10,000 procedures covered under Medicare Part B, updated quarterly. Used as the national benchmark for detecting price outliers.', inDefinedTermSet: 'https://www.clarobill.com/methodology' },
    { '@type': 'DefinedTerm', name: 'Modifier', description: 'A 2-digit code appended to a CPT code to indicate that a service was altered in some way without changing its definition. Some modifiers can override NCCI bundling edits when clinically justified.', inDefinedTermSet: 'https://www.clarobill.com/methodology' },
    { '@type': 'DefinedTerm', name: 'Global surgery period', description: 'The pre- and post-operative window during which follow-up services are considered included in the payment for the primary surgical procedure and may not be billed separately.', inDefinedTermSet: 'https://www.clarobill.com/methodology' },
    { '@type': 'DefinedTerm', name: 'Medically Unlikely Edit (MUE)', description: 'A CMS-published maximum unit value for a CPT or HCPCS code per date of service. Billing units that exceed the MUE threshold are flagged as unlikely to be medically necessary.', inDefinedTermSet: 'https://www.clarobill.com/methodology' },
    { '@type': 'DefinedTerm', name: 'Balance billing', description: 'The practice of billing a patient for the difference between a provider\'s charge and the amount paid by the insurer. Prohibited in most circumstances under the No Surprises Act for emergency and certain OON services.', inDefinedTermSet: 'https://www.clarobill.com/methodology' },
    { '@type': 'DefinedTerm', name: 'DRG', description: 'Diagnosis-Related Group. A classification system used for inpatient hospital billing under Medicare that groups diagnoses into fixed-payment categories, bundling most services into a single payment.', inDefinedTermSet: 'https://www.clarobill.com/methodology' },
  ],
};

const ARTICLE = {
  '@type': 'Article' as const,
  headline: 'How ClaroBill Analyzes Your Medical Bill',
  description:
    'ClaroBill runs 13 deterministic checks against every line item on your bill. Each finding cites a specific federal rule, an exact dollar discrepancy, and the authority behind the flag.',
  url: 'https://www.clarobill.com/methodology',
  datePublished: '2026-05-07',
  dateModified: '2026-05-07',
  author: { '@type': 'Person' as const, name: 'Sandra Jirongo', url: 'https://www.clarobill.com/about' },
  publisher: { '@type': 'Organization' as const, name: 'ClaroBill' },
};

export default function MethodologyPage(): JSX.Element {
  return (
    <article>
      <JsonLd schema={[BREADCRUMB, ARTICLE, HOWTO, DEFINED_TERMS]} />

      <div className={s.articleByline}>
        <span>Last reviewed: May 2026</span>
        <span>·</span>
        <span>Sandra Jirongo</span>
      </div>

      <h1 className={s.articleH1}>
        How ClaroBill Analyzes Your Medical Bill
      </h1>

      <p className={s.articleLead}>
        ClaroBill runs 13 deterministic checks against every line item. Each check is grounded in a specific
        federal rule or published benchmark. When a check flags something, the report shows the CPT code,
        the exact dollar discrepancy, and the authority behind the finding — so you can verify it
        independently before sending a dispute letter.
      </p>

      <div className={s.articleBody}>

        <p>
          Most billing errors are not random. The same mistakes recur across hospitals and billing systems
          because the coding framework — over 10,000 CPT codes, thousands of diagnosis codes, dozens of
          modifier rules — is complex enough that even experienced coders get it wrong. ClaroBill's checks
          target the categories where errors are most frequent and most costly.
        </p>

        <p>
          Every check is deterministic: given the same input, it produces the same output. There is no
          ambiguity in the findings. When a rule is violated, the report states which rule, which code,
          which date of service, the billed amount, the expected amount, and the dollar difference. That
          specificity is what makes a dispute letter effective.
        </p>

        <h2>1. Duplicate charge detection</h2>

        <p>
          <strong>What it checks:</strong> Whether the same CPT or HCPCS code appears more than once on
          the same date of service with no clinical documentation supporting multiple instances.
        </p>
        <p>
          <strong>Federal authority:</strong> CMS Claims Processing Manual, Chapter 4 (Part B Technical
          Claims Processing Requirements).
        </p>
        <p>
          <strong>Worked example:</strong> CPT 85025 (complete blood count with differential) appears
          twice on September 14th at $52.00 each. ClaroBill flags the duplicate and shows a $52.00
          overcharge.
        </p>

        <h2>2. Price outlier detection</h2>

        <p>
          <strong>What it checks:</strong> Whether the billed charge for a procedure significantly
          exceeds the published Medicare benchmark for that code and locality.
        </p>
        <p>
          <strong>Federal authority:</strong> CMS Medicare Physician Fee Schedule (MPFS), published
          quarterly. The MPFS sets the nationally recognized payment benchmark for over 10,000
          procedures.
        </p>
        <p>
          <strong>Worked example:</strong> CPT 99214 (office visit, moderate complexity) billed at
          $420. The 2026 Medicare rate for the same code is $165.80. ClaroBill flags the $254.20
          excess and cites the applicable MPFS rate.
        </p>

        <h2>3. NCCI unbundling — Procedure-to-Procedure edits</h2>

        <p>
          <strong>What it checks:</strong> Whether two codes are billed together when CMS National
          Correct Coding Initiative (NCCI) rules require one to be bundled into the other.
        </p>
        <p>
          <strong>Federal authority:</strong> CMS NCCI Policy Manual for Medicare Services,
          Procedure-to-Procedure (PTP) edit table, updated quarterly. The NCCI was created by
          CMS in 1996 to prevent improper payment of procedure codes that should not be reported
          together.
        </p>
        <p>
          <strong>Worked example:</strong> CPT 29881 (knee arthroscopy with meniscectomy) and CPT
          29877 (arthroscopic debridement) billed on the same date without a valid NCCI override
          modifier. The NCCI PTP table lists 29877 as a component of 29881 when performed in the
          same session. ClaroBill flags the unbundled 29877 charge and cites the NCCI edit pair.
        </p>

        <h2>4. NCCI Medically Unlikely Edits</h2>

        <p>
          <strong>What it checks:</strong> Whether the quantity billed for a code in a single
          session exceeds the limit defined in CMS Medically Unlikely Edits (MUE) tables.
        </p>
        <p>
          <strong>Federal authority:</strong> CMS NCCI MUE table, updated quarterly. MUEs set
          maximum units per day per provider for each procedure or service code.
        </p>
        <p>
          <strong>Worked example:</strong> CPT 93000 (routine ECG) billed with a quantity of 4
          on the same date of service. The MUE for 93000 is 1 per date of service. ClaroBill
          flags the excess 3 units and cites the applicable MUE limit.
        </p>

        <h2>5. Balance billing — No Surprises Act</h2>

        <p>
          <strong>What it checks:</strong> Whether an out-of-network provider billed the patient
          directly for services received at an in-network facility where the patient had no
          meaningful choice of provider — a practice prohibited by federal law since January 2022.
        </p>
        <p>
          <strong>Federal authority:</strong> No Surprises Act (Consolidated Appropriations Act,
          2021, Division BB, §101–116), effective January 1, 2022. Codified at 45 C.F.R. §
          149.410–149.430.
        </p>
        <p>
          <strong>Worked example:</strong> Patient received care at an in-network hospital. A
          subsequent bill arrives from an out-of-network anesthesiologist for $2,400 — a provider
          the patient had no ability to select. ClaroBill flags the balance bill and cites the
          No Surprises Act prohibition.
        </p>

        <h2>6. Charges for services not rendered</h2>

        <p>
          <strong>What it checks:</strong> Whether a billed service is inconsistent with the
          documented admission timeline — for example, a therapy session billed on the date of
          discharge before discharge time, or a procedure billed for a date the patient was not
          present.
        </p>
        <p>
          <strong>Federal authority:</strong> 42 C.F.R. § 415.172 (physician documentation
          requirements); CMS Claims Processing Manual, Chapter 1 (General Billing Requirements).
        </p>
        <p>
          <strong>Worked example:</strong> Physical therapy CPT 97110 (therapeutic exercise)
          billed on October 7th, the documented date of discharge at 8:00 AM. ClaroBill flags
          the charge as inconsistent with the discharge record.
        </p>

        <h2>7. Outpatient facility fee misclassification</h2>

        <p>
          <strong>What it checks:</strong> Whether a routine service billed under a hospital
          outpatient revenue code carries a facility markup that would not apply if the service
          had been performed in a physician office or independent clinic setting.
        </p>
        <p>
          <strong>Federal authority:</strong> CMS Outpatient Prospective Payment System (OPPS)
          regulations, 42 C.F.R. § 419; CMS revenue code classification guidelines.
        </p>
        <p>
          <strong>Worked example:</strong> Routine venipuncture CPT 36415 billed at $195 under
          revenue code 0301 (laboratory). The Medicare non-facility rate for 36415 is $3.52.
          ClaroBill flags the markup and identifies the facility fee classification.
        </p>

        <h2>8. Global surgery period violations</h2>

        <p>
          <strong>What it checks:</strong> Whether routine post-operative follow-up visits or
          related services are billed separately within the global surgery period — the period
          during which such services are already included in the surgical payment.
        </p>
        <p>
          <strong>Federal authority:</strong> CMS Medicare Physician Fee Schedule global surgical
          package policy; MPFS Global Days file. Global periods are 0, 10, or 90 days depending
          on the procedure.
        </p>
        <p>
          <strong>Worked example:</strong> Cholecystectomy CPT 47600 (90-day global period)
          performed March 1. An office visit CPT 99213 is billed March 20 for a post-operative
          check. Under the global surgical package, the March 20 visit is already included in
          the March 1 surgical payment. ClaroBill flags the separate charge.
        </p>

        <h2>9. Modifier misuse</h2>

        <p>
          <strong>What it checks:</strong> Whether a modifier (25, 57, 59, 76, 79, XE, XS, XP,
          or XU) has been appended to override a bundling rule or authorize a separate charge
          without documented clinical justification.
        </p>
        <p>
          <strong>Federal authority:</strong> CMS NCCI modifier override guidelines; AMA CPT
          manual editorial guidelines for modifier 25 (significant, separately identifiable E&M)
          and modifier 59 (distinct procedural service).
        </p>
        <p>
          <strong>Worked example:</strong> Dermatology office visit CPT 99213 billed with
          modifier 25 alongside a shave removal CPT 11300 on the same date. Modifier 25 requires
          a separately identifiable, documented E&M service unrelated to the procedure. Without
          supporting documentation, the modifier is invalid and the E&M charge is duplicative.
          ClaroBill flags the application and cites the modifier 25 documentation standard.
        </p>

        <h2>10. Fragmented billing — 72-hour rule</h2>

        <p>
          <strong>What it checks:</strong> Whether pre-admission services billed separately by
          the hospital fall within the 3-day window before an inpatient admission and should be
          bundled into the inpatient DRG payment.
        </p>
        <p>
          <strong>Federal authority:</strong> CMS 3-day (72-hour) payment window rule, 42
          C.F.R. § 412.2(c)(5). Applies to diagnostic services provided by the admitting hospital
          or entities wholly owned or operated by it within 3 days before admission.
        </p>
        <p>
          <strong>Worked example:</strong> Hospital bills a CT scan on October 11. Patient is
          admitted to the same hospital on October 12. Under the 72-hour rule, the October 11
          scan is included in the inpatient DRG payment. Billing it separately as an outpatient
          service is a double-payment violation. ClaroBill flags the pre-admission claim.
        </p>

        <h2>11. Units and quantity errors</h2>

        <p>
          <strong>What it checks:</strong> Whether the quantity billed for a supply, medication,
          or service exceeds clinical plausibility given the documented length of stay and
          standard dosing or administration intervals.
        </p>
        <p>
          <strong>Federal authority:</strong> CMS NCCI MUE guidelines; MAC local coverage
          determinations; CMS Drug Administration code billing guidance.
        </p>
        <p>
          <strong>Worked example:</strong> Acetaminophen 500mg billed with a quantity of 32 for
          a 1-day admission. At standard 4-hour dosing intervals, 32 doses represents 128 hours
          of administration. ClaroBill flags the implausible quantity and shows the expected
          maximum for the documented stay duration.
        </p>

        <h2>12. Invalid or obsolete codes</h2>

        <p>
          <strong>What it checks:</strong> Whether a CPT or HCPCS code appearing on the bill
          was active on the date of service, or has since been deleted, merged, or replaced.
        </p>
        <p>
          <strong>Federal authority:</strong> AMA CPT code cycle (updated January 1 annually);
          CMS HCPCS Level II quarterly update schedule.
        </p>
        <p>
          <strong>Worked example:</strong> CPT 99201 (new patient, minimal complexity office
          visit) was deleted by the AMA effective January 1, 2021 as part of the E&M coding
          restructure. A bill dated February 2022 using 99201 is billing against a deleted
          code. ClaroBill flags it and notes the deletion effective date.
        </p>

        <h2>13. Negotiated rate excess</h2>

        <p>
          <strong>What it checks:</strong> Whether the charge billed to the patient is consistent
          with the payer-specific negotiated rate the hospital is required by law to publish.
        </p>
        <p>
          <strong>Federal authority:</strong> Hospital Price Transparency Rule (45 C.F.R. § 180),
          effective January 1, 2021. Requires hospitals to publish payer-specific negotiated rates
          for all standard charges in machine-readable format, updated annually.
        </p>
        <p>
          <strong>Worked example:</strong> A hospital's published negotiated rate for CPT 27447
          (total knee replacement) with a specific insurer is $24,200. The patient's itemized bill
          shows $33,800 for the same procedure under the same insurer. ClaroBill flags the
          $9,600 discrepancy and cites the applicable published rate.
        </p>

        <h2>What the report includes</h2>

        <p>
          For every flagged finding, the ClaroBill report provides:
        </p>

        <ul>
          <li>The CPT or HCPCS code and a plain-English description of the service</li>
          <li>The date of service and the billed amount</li>
          <li>The expected amount and the exact dollar discrepancy</li>
          <li>The specific rule violated and the federal authority cited</li>
          <li>Draft dispute letter language you can send directly to the billing department</li>
        </ul>

        <p>
          The dispute letter is generated automatically from the findings. It is written to cite
          specific rules rather than to plead — because billing departments respond to documented
          rule violations, not general complaints.
        </p>

        <p>
          If you want to understand any of the underlying rules in more depth before sending a
          dispute letter, our{' '}
          <Link href="/learn">medical billing guides</Link> cover each category with real
          examples and exact dispute language.
        </p>

      </div>

      <Citations />
      <Cta />
    </article>
  );
}

function Citations(): JSX.Element {
  const sources = [
    { label: 'CMS: National Correct Coding Initiative (NCCI) Policy Manual', url: 'https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits' },
    { label: 'CMS: Medicare Physician Fee Schedule (MPFS) Search', url: 'https://www.cms.gov/medicare/physician-fee-schedule/search' },
    { label: 'CMS: No Surprises Act Overview', url: 'https://www.cms.gov/nosurprises' },
    { label: 'CMS: Hospital Price Transparency Final Rule (45 C.F.R. § 180)', url: 'https://www.cms.gov/hospital-price-transparency' },
    { label: 'CMS: Claims Processing Manual, Chapter 4', url: 'https://www.cms.gov/regulations-guidance/guidance/manuals/internet-only-manuals-ioms-items/cms018912' },
    { label: 'CMS: Global Surgery Booklet (MLN Matters)', url: 'https://www.cms.gov/outreach-and-education/medicare-learning-network-mln/mlnproducts/downloads/globalsurgery-icn907166.pdf' },
  ];
  return (
    <div className={s.sourcesSection}>
      <p className={s.sourcesLabel}>Federal authorities cited</p>
      <ol style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {sources.map((src, i) => (
          <li key={src.url} className={s.sourceItem}>
            <span style={{ marginRight: '.4rem', opacity: .5 }}>{i + 1}.</span>
            <a href={src.url} target="_blank" rel="noopener noreferrer" className={s.sourceLink}>
              {src.label}
            </a>
          </li>
        ))}
      </ol>
    </div>
  );
}

function Cta(): JSX.Element {
  return (
    <div className={s.ctaBox}>
      <p className={s.ctaTitle}>See these checks applied to your bill</p>
      <p className={s.ctaNote}>
        Upload your itemized bill and ClaroBill will run all 13 checks, flag every error,
        and write the dispute letter for you.
      </p>
      <Link href="/auth/sign-in" className={s.ctaBtn}>Check my bill for free</Link>
    </div>
  );
}
