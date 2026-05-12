import type { Metadata } from 'next';
import Link from 'next/link';
import { LogoWithMark } from '@/components/logo';
import { PrintButton } from '@/components/print-button';
import s from './guide.module.css';

// Unlisted. Shared only via the Loops transactional email.
// noindex keeps it out of search results.
export const metadata: Metadata = {
  title: '8 Common Billing Traps | ClaroBill',
  description:
    'The ClaroBill guide to common medical billing errors: how to spot them and how to dispute them.',
  robots: { index: false, follow: false },
};

const TRAPS = [
  {
    number: '01',
    title: 'Duplicate Charges',
    what:
      'The same CPT code appears more than once on the same date of service, or a line item shows a quantity greater than what you actually received.',
    howToSpot:
      'Request your itemized bill and look for the same code on the same date. Also check line items for medications, lab panels, or supplies with quantities that seem higher than what you recall.',
    whatToDo:
      'Call the billing department and say: "I see CPT code [X] billed twice on [date]. Can you confirm the service was performed twice and provide the documentation?" If they cannot confirm it, request a corrected claim.',
  },
  {
    number: '02',
    title: 'Upcoding',
    what:
      'The provider bills for a more complex or more expensive version of a service than what was actually performed. The most common form is an office visit coded at the highest complexity level when the visit was routine.',
    howToSpot:
      'Look for evaluation and management codes (99202 through 99215). Code 99215 is the highest-complexity office visit and requires documented high-complexity medical decision-making or at least 40 minutes of total time. If your visit was 15 minutes for a routine concern, it should not be coded 99215.',
    whatToDo:
      'Request the visit note (you are entitled to it). Compare the documentation to the CMS coding guidelines for that CPT code. If the note does not support the code level, write to the billing department citing the specific guideline and asking for a downcode review.',
  },
  {
    number: '03',
    title: 'Unbundling',
    what:
      'A provider bills multiple component codes separately for procedures that CMS rules require to be billed as a single bundled code. Each component code has a lower reimbursement rate, but together they exceed the bundled rate.',
    howToSpot:
      'Look for multiple surgical or procedural codes on the same date that seem related to the same body site. The CMS National Correct Coding Initiative (NCCI) maintains a public list of code pairs that cannot be billed together.',
    whatToDo:
      'Ask the billing office whether a modifier (such as modifier 59 or XS) was used and why. If the procedures were performed on the same anatomical site in the same session, the bundled code applies. Request a corrected claim citing NCCI policy.',
  },
  {
    number: '04',
    title: 'Charges for Services Not Rendered',
    what:
      'A line item appears on your bill for a service, test, or supply you did not receive. This is one of the most common errors and is rarely intentional.',
    howToSpot:
      'Compare your itemized bill to your own notes about what happened during your visit or hospital stay. Cross-reference with your explanation of benefits (EOB) from your insurer. Look especially at medication charges, supply charges, and ancillary service codes.',
    whatToDo:
      'Write to the hospital billing department identifying each disputed line item by date and code. State that you have no record of receiving the service and request supporting documentation. Under HIPAA, you are entitled to your complete medical record. The itemized bill and the medical record should be consistent.',
  },
  {
    number: '05',
    title: 'Balance Billing',
    what:
      'An out-of-network provider charges you the difference between their billed rate and what your insurer paid. The No Surprises Act (effective January 1, 2022) prohibits this in many situations.',
    howToSpot:
      'If you received care in an emergency or if an out-of-network provider treated you at an in-network facility without your knowledge or meaningful consent, you may be protected. Check whether the provider is in-network. Check whether the bill came from a provider (anesthesiologist, radiologist, pathologist, or assistant surgeon) you did not personally choose.',
    whatToDo:
      'File a complaint with your state insurance commissioner and with the federal No Surprises Help Desk (1-800-985-3059). Send a certified letter to the provider stating you are invoking your rights under the No Surprises Act and requesting they bill at the in-network rate.',
  },
  {
    number: '06',
    title: 'Facility Fees on Outpatient Visits',
    what:
      'When a hospital acquires a previously independent doctor practice, it can reclassify the office as a hospital outpatient department. Visits there then incur a separate facility fee on top of the physician fee, even though the experience is identical.',
    howToSpot:
      'Look for two separate bills from what you thought was a single doctor visit: one from the physician and one from the hospital. Look for a revenue code in the 510-519 range on the facility side, which indicates outpatient clinic services.',
    whatToDo:
      'Call the billing office and ask whether the site of service is coded as a hospital outpatient department (place of service code 22) or a physician office (place of service code 11). Ask for an itemized breakdown of the facility fee. If the charges were not disclosed in advance, you can dispute them on that basis in many states.',
  },
  {
    number: '07',
    title: 'Incorrect Room and Board Charges',
    what:
      'Hospital room charges are billed by the day, but the admission and discharge dates can shift the count. You are typically not charged for the day of discharge. Billing systems sometimes include it anyway.',
    howToSpot:
      'Count the nights you slept in the hospital. Compare that count to the number of room-and-board days on your itemized bill. Check for ICU or step-down unit charges on days you were in a standard room.',
    whatToDo:
      'Request the nursing notes or a census printout showing your unit and room assignment for each day of your stay. These are part of your medical record and you are entitled to them. If the room type billed does not match your records, ask for a corrected claim.',
  },
  {
    number: '08',
    title: 'Timely Filing Denials Passed to You',
    what:
      'If your insurer denies a claim because the provider submitted it after the insurer deadline, the provider may attempt to bill you for the full amount. This is not your responsibility in most cases.',
    howToSpot:
      'Check your EOB for denial reason codes. CO-29 or PR-29 indicates a timely filing denial. If you see this and the provider is in-network, the contract between the provider and insurer generally prohibits passing that denial to you.',
    whatToDo:
      'Write to the provider stating that a timely filing denial is a provider-side contractual issue and does not create a patient liability under the terms of the provider network agreement. Include a copy of the EOB. If the provider continues to bill you, contact your insurer and ask them to intervene with the provider.',
  },
];

export default function BillingTrapsGuidePage(): JSX.Element {
  return (
    <div className={s.page}>
      <header className={s.header}>
        <div className={s.headerInner}>
          <Link href="/" className={s.logoLink}>
            <LogoWithMark size="md" variant="dark" />
          </Link>
          <PrintButton />
        </div>
      </header>

      <main className={s.document}>
        {/* Visible only when printing — keeps branding on saved PDFs */}
        <div className={s.printBrand}>
          <LogoWithMark size="md" variant="dark" />
          <span className={s.printBrandUrl}>clarobill.com</span>
        </div>

        <div className={s.coverBlock}>
          <p className={s.coverLabel}>ClaroBill Patient Guide</p>
          <h1 className={s.coverTitle}>8 Common Billing Traps</h1>
          <p className={s.coverSub}>
            How to find them on your bill and what to do when you do.
          </p>
        </div>

        <div className={s.intro}>
          <p>
            Billing errors appear on more than 80 percent of hospital bills reviewed by patient advocates.
            They are rarely the result of fraud. Most come from the complexity of a coding system with over
            10,000 procedure codes, thousands of diagnosis codes, and a web of rules that even experienced
            coders get wrong.
          </p>
          <p>
            The problem is that when a mistake happens, it almost always runs in the provider direction. The
            traps below are the ones that appear most often. For each one, you will find what it is, how to
            find it, and exactly what to say when you dispute it.
          </p>
        </div>

        <ol className={s.trapList}>
          {TRAPS.map((trap) => (
            <li key={trap.number} className={s.trap}>
              <div className={s.trapNumber}>{trap.number}</div>
              <div className={s.trapBody}>
                <h2 className={s.trapTitle}>{trap.title}</h2>
                <div className={s.trapSection}>
                  <p className={s.sectionLabel}>What it is</p>
                  <p className={s.sectionText}>{trap.what}</p>
                </div>
                <div className={s.trapSection}>
                  <p className={s.sectionLabel}>How to spot it</p>
                  <p className={s.sectionText}>{trap.howToSpot}</p>
                </div>
                <div className={s.trapSection}>
                  <p className={s.sectionLabel}>What to do</p>
                  <p className={s.sectionText}>{trap.whatToDo}</p>
                </div>
              </div>
            </li>
          ))}
        </ol>

        <div className={s.cta}>
          <p className={s.ctaHeadline}>
            Want to know if your specific bill has any of these errors?
          </p>
          <p className={s.ctaBody}>
            Upload your itemized bill at ClaroBill and we will check every line for errors, overcharges,
            and codes that should not have been billed together, then write the dispute letter for you.
          </p>
          <Link href="https://www.clarobill.com" className={s.ctaButton}>
            Analyze my bill at clarobill.com
          </Link>
        </div>

        <footer className={s.docFooter}>
          <span>&copy; 2026 ClaroBill</span>
          <span aria-hidden="true">·</span>
          <span>clarobill.com</span>
          <span aria-hidden="true">·</span>
          <span>This guide is for informational purposes only and does not constitute legal or financial advice.</span>
        </footer>
      </main>
    </div>
  );
}
