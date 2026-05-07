import type { Metadata } from 'next';
import Link from 'next/link';
import s from '../../blog/blog.module.css';
import { JsonLd } from '@/components/json-ld';

const ARTICLE_SCHEMA = {
  '@type': 'Article' as const,
  headline: 'How to Read an Itemized Medical Bill',
  description: 'What the columns, codes, and dollar amounts on your itemized medical bill actually mean. Plus how to find the errors hiding in plain sight.',
  url: 'https://www.clarobill.com/learn/how-to-read-an-itemized-medical-bill',
  datePublished: '2026-04-07',
  dateModified: '2026-05-07',
  author: { '@type': 'Person' as const, name: 'Sandra Jirongo', url: 'https://www.clarobill.com/about' },
  publisher: { '@type': 'Organization' as const, name: 'ClaroBill' },
};

const BREADCRUMB_SCHEMA = {
  '@type': 'BreadcrumbList' as const,
  itemListElement: [
    { '@type': 'ListItem' as const, position: 1, name: 'Home', item: 'https://www.clarobill.com' },
    { '@type': 'ListItem' as const, position: 2, name: 'Guides', item: 'https://www.clarobill.com/learn' },
    { '@type': 'ListItem' as const, position: 3, name: 'How to Read an Itemized Medical Bill', item: 'https://www.clarobill.com/learn/how-to-read-an-itemized-medical-bill' },
  ],
};

const FAQ_SCHEMA = {
  '@type': 'FAQPage' as const,
  mainEntity: [
    {
      '@type': 'Question' as const,
      name: 'What is an itemized medical bill?',
      acceptedAnswer: { '@type': 'Answer' as const, text: 'An itemized medical bill, sometimes called an itemized statement or UB-04 form, lists every charge individually with the specific procedure code, date of service, quantity, and dollar amount attached. Most patients only receive a summary bill automatically. You must specifically request the itemized version from the hospital billing department.' },
    },
    {
      '@type': 'Question' as const,
      name: 'How do I request an itemized hospital bill?',
      acceptedAnswer: { '@type': 'Answer' as const, text: 'Call the hospital billing department and ask for a complete itemized statement listing all charges with CPT and revenue codes. In most states, itemized bills must be provided free of charge. You can also ask for the UB-04 claim form, which is the form submitted to your insurer and contains all codes, dates, and charge amounts.' },
    },
    {
      '@type': 'Question' as const,
      name: 'What is a CPT code on a medical bill?',
      acceptedAnswer: { '@type': 'Answer' as const, text: 'CPT codes are five-digit numbers that describe the exact procedure or service performed. They directly determine how much your insurance pays and what you owe. If the description on your bill does not match your experience of the visit, that discrepancy may indicate upcoding — billing for a more complex service than what occurred.' },
    },
    {
      '@type': 'Question' as const,
      name: 'What is the difference between billed amount and allowed amount on a medical bill?',
      acceptedAnswer: { '@type': 'Answer' as const, text: 'The billed amount is what the provider charged before any discounts or adjustments. The allowed amount is the negotiated rate between your insurer and the provider. The difference is written off by the provider. You are not responsible for the difference — you only owe your share of the allowed amount, such as your copay or coinsurance.' },
    },
    {
      '@type': 'Question' as const,
      name: 'How can I tell if there are errors on my itemized bill?',
      acceptedAnswer: { '@type': 'Answer' as const, text: 'Look for the same CPT code appearing twice on the same date (duplicate charges), services billed on dates you were not at the facility, a visit complexity code that does not match how long or involved your appointment was, and charges you cannot match to anything that actually happened during your care.' },
    },
  ],
};

export const metadata: Metadata = {
  title: 'How to Read an Itemized Medical Bill: ClaroBill',
  description: 'What the columns, codes, and dollar amounts on your itemized medical bill actually mean. Plus how to find the errors hiding in plain sight.',
  alternates: {
    canonical: 'https://www.clarobill.com/learn/how-to-read-an-itemized-medical-bill',
    languages: { en: 'https://www.clarobill.com/learn/how-to-read-an-itemized-medical-bill', 'x-default': 'https://www.clarobill.com/learn/how-to-read-an-itemized-medical-bill' },
  },
};

export default function Article(): JSX.Element {
  return (
    <article>
      <JsonLd schema={[ARTICLE_SCHEMA, BREADCRUMB_SCHEMA, FAQ_SCHEMA]} />

      <div className={s.articleByline}>
        <span>April 7, 2026</span>
        <span>·</span>
        <span>7 min read</span>
        <span>·</span>
        <span>Sandra Jirongo</span>
      </div>

      <h1 className={s.articleH1}>How to Read an Itemized Medical Bill</h1>

      <p className={s.articleLead}>
        What the columns, codes, and dollar amounts actually mean. Plus how to spot the line items that should not be there.
      </p>

      <div className={s.articleBody}>
        <p>The bill arrived six weeks after the procedure. Three pages, single-spaced, $28,000. Out of 41 line items, I recognized maybe four. The rest looked like a ransom note written in a medical coding dialect nobody teaches you.</p>
        <p>That experience is nearly universal. Hospitals are not legally required to send you an itemized bill unless you ask for one. And most patients never do, which is exactly how billing departments prefer it. The summary statement that arrives automatically just shows a total. The itemized version shows you everything, line by line, and that is where the errors live.</p>

        <h2>First: get the right document</h2>
        <p>There are three documents most patients confuse. An <strong>Explanation of Benefits (EOB)</strong> comes from your insurance company. It shows what was billed, what they agreed to pay, and what you owe after their negotiated discount. A <strong>summary bill</strong> comes from the hospital or provider and shows a single total. An <strong>itemized bill</strong> (sometimes called an itemized statement or UB-04 form) lists every charge individually with the specific procedure codes attached.</p>
        <p>You want the itemized bill. Call the hospital's billing department and ask for it directly. Say: "I'd like a complete itemized statement listing all charges with CPT and revenue codes." They are required to provide it. Some will email it same-day; others take up to two weeks.</p>

        <h2>What each column means</h2>
        <p>Itemized bills vary in format, but most share the same core columns. Here is what each one tells you:</p>

        <div className={s.glossaryBox}>
          <div><p className={s.glossaryTerm}>Date of service</p><p className={s.glossaryDef}>The date the service was performed. Check this carefully if you had a multi-day hospital stay. Being charged for a day you were discharged is one of the most common errors on inpatient bills.</p></div>
          <div style={{ marginTop: '1rem' }}><p className={s.glossaryTerm}>Revenue code</p><p className={s.glossaryDef}>A four-digit code used by hospitals to categorize the type of service (room charges, pharmacy, lab, radiology, etc.). Revenue code 0250 means pharmacy. Code 0301 is laboratory.</p></div>
          <div style={{ marginTop: '1rem' }}><p className={s.glossaryTerm}>CPT / HCPCS code</p><p className={s.glossaryDef}>A five-digit code describing the exact procedure or service. This is the most important field on the bill. CPT 99214 means "established patient office visit, moderate-to-high complexity." These codes directly determine what insurance pays.{' '}<Link href="/learn/what-are-cpt-codes">Our CPT code guide</Link> walks through the codes patients see most often.</p></div>
          <div style={{ marginTop: '1rem' }}><p className={s.glossaryTerm}>Description</p><p className={s.glossaryDef}>A text label for the service. The description and the CPT code should match. If the description says "basic office visit" but the CPT code is 99215 (the highest-complexity visit level), that discrepancy is worth questioning.</p></div>
          <div style={{ marginTop: '1rem' }}><p className={s.glossaryTerm}>Units / quantity</p><p className={s.glossaryDef}>How many times the service was performed. A quantity of 2 for a procedure you had once is a duplicate charge. A quantity of 14 for a medication you took for three days is worth scrutinizing.</p></div>
          <div style={{ marginTop: '1rem' }}><p className={s.glossaryTerm}>Billed amount</p><p className={s.glossaryDef}>What the provider charged before any discounts or insurance adjustments. This number is almost always higher than what anyone actually pays. It is the starting point for negotiation.</p></div>
          <div style={{ marginTop: '1rem' }}><p className={s.glossaryTerm}>Allowed amount / adjusted amount</p><p className={s.glossaryDef}>The negotiated rate between the provider and your insurer. The difference between the billed amount and the allowed amount is written off. You are not responsible for it.</p></div>
          <div style={{ marginTop: '1rem' }}><p className={s.glossaryTerm}>Patient responsibility</p><p className={s.glossaryDef}>What you actually owe after insurance. Reconcile this with your EOB. If the two documents show different amounts for the same service, one of them is wrong.</p></div>
        </div>

        <h2>Four things to check before you pay anything</h2>
        <p>You do not need a medical background to catch the most common errors. Most of them are visible to anyone who knows what to look for.</p>
        <p><strong>1. Duplicate line items.</strong> Search the bill for the same CPT code appearing twice on the same date. CPT 85025 (complete blood count) listed twice on the same day is a duplicate. You pay for it once.</p>
        <p><strong>2. Services on dates you were not there.</strong> Cross-reference every date of service against your actual visit dates. A room charge on your discharge day is a common error.</p>
        <p><strong>3. The description does not match what happened.</strong> If you had a 15-minute follow-up but the bill shows CPT 99215 (requiring at least 40 minutes of total time), that is upcoding. The difference between a 99213 ($90) and a 99215 ($182) visit under the 2026 Medicare fee schedule. Upcoding is one of several{' '}
          <Link href="/learn/common-medical-billing-errors">common billing errors with specific dispute strategies</Link>.
        </p>
        <p><strong>4. Charges for things you do not recognize.</strong> Make a list of every line item you cannot match to something that actually happened. Call the billing department and ask for a plain-English explanation.</p>

        <h2>When to push back</h2>
        <p>Billing departments are not adversaries, but they do make mistakes. And they are not going to audit their own work for your benefit. If something looks wrong, ask for it in writing. For the exact steps, from writing the dispute letter to escalating when the hospital pushes back, see{' '}
          <Link href="/learn/how-to-dispute-a-hospital-bill">our step-by-step hospital bill dispute guide</Link>.
        </p>
        <p>Most hospitals give you 60 to 180 days from the statement date to dispute. Request an extension in writing if you are waiting on your EOB.</p>
        <p>Billing errors are not rare edge cases. Studies consistently find errors in the majority of hospital bills. The patients who catch them are not smarter. They just looked.</p>
      </div>

      <Citations sources={[
        { label: 'CMS: 2026 Medicare Physician Fee Schedule Final Rule', url: 'https://www.cms.gov/newsroom/fact-sheets/calendar-year-cy-2026-medicare-physician-fee-schedule-final-rule-cms-1832-f' },
        { label: 'CMS: Physician Fee Schedule Lookup Tool', url: 'https://www.cms.gov/medicare/physician-fee-schedule/search' },
        { label: "Medical Billing Advocates of America: Billing Error Statistics (via Becker's)", url: 'https://www.beckershospitalreview.com/finance/medical-billing-errors-growing-says-medical-billing-advocates-of-america.html' },
        { label: 'CMS: UB-04 Claim Form Instructions', url: 'https://www.cms.gov/medicare/billing/electronicbillingediinstances/ub04' },
      ]} />
      <Cta />
      <RelatedArticles current="how-to-read-an-itemized-medical-bill" />
    </article>
  );
}

function Cta(): JSX.Element {
  return (
    <div className={s.ctaBox}>
      <p className={s.ctaTitle}>Let ClaroBill read it for you</p>
      <p className={s.ctaNote}>Upload your bill and we'll run a deep audit, flag every error, and generate a ready-to-send dispute letter in minutes.</p>
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
      <div>{related.map((a) => <Link key={a.slug} href={`/learn/${a.slug}`} className={s.relatedLink}>{a.title} →</Link>)}</div>
    </div>
  );
}

const ALL_ARTICLES = [
  { slug: 'how-to-read-an-itemized-medical-bill', title: 'How to Read an Itemized Medical Bill' },
  { slug: 'common-medical-billing-errors', title: 'The Most Common Medical Billing Errors' },
  { slug: 'what-are-cpt-codes', title: "What Are CPT Codes? A Patient's Guide" },
  { slug: 'how-to-dispute-a-hospital-bill', title: 'How to Dispute a Hospital Bill' },
  { slug: 'medical-billing-advocates', title: 'Medical Billing Advocates: What They Do and What They Charge' },
  { slug: 'why-bill-exceeds-insurer-negotiated-rate', title: 'Why Your Bill Is Higher Than What Your Insurer Pays' },
  { slug: 'hospital-machine-readable-files-explained', title: 'Hospital Machine-Readable Files Explained' },
  { slug: 'ncci-edits-explained-for-patients', title: 'NCCI Edits: The Federal Rules That Prevent Billing Abuse' },
];
