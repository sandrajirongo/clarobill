import type { Metadata } from 'next';
import Link from 'next/link';
import s from '../../blog/blog.module.css';
import { JsonLd } from '@/components/json-ld';
import { ArticleBreadcrumb } from '@/components/article-breadcrumb';

const ARTICLE_SCHEMA = {
  '@type': 'Article' as const,
  headline: 'The No Surprises Act: What It Covers, What It Does Not, and How to Use It',
  description: 'The No Surprises Act bans most surprise bills from out-of-network providers. Here is exactly what it covers, what the exceptions are, and what to do if you receive a bill it prohibits.',
  url: 'https://www.clarobill.com/learn/no-surprises-act',
  datePublished: '2026-05-18',
  dateModified: '2026-05-18',
  author: { '@type': 'Person' as const, name: 'ClaroBill Team', url: 'https://www.clarobill.com/about' },
  publisher: { '@type': 'Organization' as const, name: 'ClaroBill' },
};

const BREADCRUMB_SCHEMA = {
  '@type': 'BreadcrumbList' as const,
  itemListElement: [
    { '@type': 'ListItem' as const, position: 1, name: 'Home', item: 'https://www.clarobill.com' },
    { '@type': 'ListItem' as const, position: 2, name: 'Guides', item: 'https://www.clarobill.com/learn' },
    { '@type': 'ListItem' as const, position: 3, name: 'The No Surprises Act', item: 'https://www.clarobill.com/learn/no-surprises-act' },
  ],
};

const FAQ_SCHEMA = {
  '@type': 'FAQPage' as const,
  mainEntity: [
    {
      '@type': 'Question' as const,
      name: 'What is the No Surprises Act?',
      acceptedAnswer: {
        '@type': 'Answer' as const,
        text: 'The No Surprises Act is a federal law that took effect January 1, 2022. It prohibits out-of-network providers from billing patients more than their in-network cost-sharing amount in two situations: emergency care at any facility, and non-emergency care at an in-network facility where the patient had no meaningful choice of provider. It applies to most private insurance plans, including employer-sponsored plans and marketplace plans.',
      },
    },
    {
      '@type': 'Question' as const,
      name: 'What is balance billing and is it legal?',
      acceptedAnswer: {
        '@type': 'Answer' as const,
        text: 'Balance billing is when an out-of-network provider bills you the difference between their full charge and what your insurer pays. Before the No Surprises Act, this was legal in most states for many types of care. Since January 1, 2022, the No Surprises Act prohibits balance billing for emergency services at any facility, and for non-emergency services at in-network facilities where you could not reasonably choose an in-network provider (such as when an out-of-network anesthesiologist is assigned at an in-network hospital).',
      },
    },
    {
      '@type': 'Question' as const,
      name: 'Does the No Surprises Act cover elective or scheduled procedures?',
      acceptedAnswer: {
        '@type': 'Answer' as const,
        text: 'The No Surprises Act covers non-emergency care at in-network facilities only when you had no meaningful choice of provider. For scheduled procedures where you can choose your providers in advance, the act requires out-of-network providers to give you a written notice and obtain your signed consent before they can bill you at out-of-network rates. If you did not receive and sign that notice at least 72 hours before the procedure, the provider cannot legally bill you more than the in-network rate.',
      },
    },
    {
      '@type': 'Question' as const,
      name: 'How do I file a No Surprises Act complaint?',
      acceptedAnswer: {
        '@type': 'Answer' as const,
        text: 'File a complaint at the federal level through CMS at www.cms.gov/nosurprises or by calling 1-800-985-3059. You can also file with your state insurance commissioner if your state has its own balance billing protections. File in writing, include the bill, your explanation of benefits, and a description of why you believe the charge violates the No Surprises Act. Keep copies of everything.',
      },
    },
    {
      '@type': 'Question' as const,
      name: 'What is a Good Faith Estimate under the No Surprises Act?',
      acceptedAnswer: {
        '@type': 'Answer' as const,
        text: 'Providers are required to give uninsured or self-pay patients a Good Faith Estimate of expected costs before scheduled services. If your final bill exceeds the Good Faith Estimate by more than $400, you can dispute it through the Patient-Provider Dispute Resolution process. For insured patients, providers must give a cost estimate on request, and your insurer must provide an Advanced Explanation of Benefits for scheduled services.',
      },
    },
  ],
};

export const metadata: Metadata = {
  title: 'The No Surprises Act: What It Covers, What It Does Not, and How to Use It | ClaroBill',
  description: 'The No Surprises Act bans most surprise bills from out-of-network providers. Here is exactly what it covers, what the exceptions are, and what to do if you receive a bill it prohibits.',
  alternates: {
    canonical: 'https://www.clarobill.com/learn/no-surprises-act',
    languages: {
      en: 'https://www.clarobill.com/learn/no-surprises-act',
      'x-default': 'https://www.clarobill.com/learn/no-surprises-act',
    },
  },
};

export default function Article(): JSX.Element {
  return (
    <article>
      <JsonLd schema={[ARTICLE_SCHEMA, BREADCRUMB_SCHEMA, FAQ_SCHEMA]} />

      <ArticleBreadcrumb
        items={[
          { label: 'Home', href: '/' },
          { label: 'Medical Billing Guides', href: '/learn' },
          { label: 'The No Surprises Act: What It Covers, What It Does Not, and How to Use It' },
        ]}
      />

      <div className={s.articleByline}>
        <span>May 18, 2026</span>
        <span>·</span>
        <span>8 min read</span>
        <span>·</span>
        <span>ClaroBill Team</span>
      </div>

      <h1 className={s.articleH1}>The No Surprises Act: What It Covers, What It Does Not, and How to Use It</h1>

      <p className={s.articleLead}>
        The No Surprises Act bans most surprise bills from out-of-network providers. But it has specific
        conditions, real exceptions, and a complaint process most patients never use. Here is what the
        law actually says and what to do when a provider violates it.
      </p>

      <div className={s.articleBody}>
        <p>
          Before January 1, 2022, it was entirely legal for an out-of-network anesthesiologist to bill
          you thousands of dollars after a surgery at an in-network hospital — even though you never
          chose that provider and had no way to know they were out of network. The No Surprises Act
          made that illegal. But the law only covers specific situations, and understanding the
          boundaries matters when you are looking at a bill you did not expect.
        </p>

        <h2>What the law prohibits</h2>
        <p>
          The No Surprises Act bans balance billing — charging patients more than their in-network
          cost-sharing amount — in two categories of care:
        </p>
        <ul>
          <li>
            <strong>Emergency services at any facility.</strong> If you go to an emergency room or
            receive emergency care, providers cannot bill you more than your in-network cost-sharing
            even if the facility or the treating physician is out of network. This applies regardless
            of whether you chose the facility or were taken there by ambulance.
          </li>
          <li>
            <strong>Non-emergency services at an in-network facility where you had no meaningful
            choice of provider.</strong> The most common example: an out-of-network anesthesiologist,
            radiologist, or assistant surgeon is assigned to your care at an in-network hospital. You
            did not choose them and could not reasonably have chosen an alternative. The No Surprises
            Act covers these providers.
          </li>
        </ul>
        <p>
          In both cases, your insurer pays the out-of-network provider at a rate negotiated through
          an independent dispute resolution process. Your responsibility is capped at your in-network
          cost-sharing. The provider cannot bill you for the rest.
        </p>

        <h2>Who is covered</h2>
        <p>
          The law applies to most private health insurance plans, including employer-sponsored plans
          (including self-insured plans), individual and family plans purchased through the marketplace,
          and student health plans. It does not apply to short-term health plans, health care sharing
          ministries, or retiree-only plans. Medicare and Medicaid have separate protections.
        </p>
        <p>
          Uninsured and self-pay patients are covered by a related provision: providers must give you
          a written Good Faith Estimate of expected costs before any scheduled service. If your final
          bill exceeds that estimate by more than $400, you can dispute it through the federal
          Patient-Provider Dispute Resolution process.
        </p>

        <h2>The consent exception</h2>
        <p>
          This is the part most patients do not know. For non-emergency, scheduled care at an
          in-network facility, an out-of-network provider can opt out of the law's protections
          and bill you at out-of-network rates, but only if:
        </p>
        <ul>
          <li>They give you a written notice at least 72 hours before the service explaining that they
          are out of network and what the estimated cost will be</li>
          <li>You sign a consent form acknowledging you understand you will be billed at out-of-network
          rates and waiving your protections under the No Surprises Act</li>
        </ul>
        <p>
          If you did not receive that written notice at least 72 hours in advance, and you did not
          sign a consent form, the provider cannot legally bill you more than your in-network
          cost-sharing. A bill that arrives without this prior consent process is a No Surprises Act
          violation.
        </p>
        <div className={s.glossaryBox}>
          <p className={s.glossaryTerm}>What the consent notice must include</p>
          <p className={s.glossaryDef}>
            The written notice must state the provider is out of network, list the provider's
            estimated charge and your estimated out-of-pocket cost, include a list of in-network
            providers at the facility who could perform the service, and state that you can choose
            an in-network provider instead. A generic financial responsibility form is not
            sufficient. The notice must be service-specific and signed.
          </p>
        </div>

        <h2>What the law does not cover</h2>
        <p>
          Knowing the exclusions is just as important as knowing the protections.
        </p>
        <ul>
          <li>
            <strong>Out-of-network facilities.</strong> If you choose to receive care at an
            out-of-network hospital or facility, the No Surprises Act generally does not apply.
            The protections are designed for situations where you received care at an in-network
            facility but were unknowingly treated by out-of-network providers within it.
          </li>
          <li>
            <strong>Ground ambulance services.</strong> Ambulance transport is explicitly excluded
            from the No Surprises Act. Several states have enacted their own ambulance balance billing
            protections, but there is no federal prohibition.
          </li>
          <li>
            <strong>Air ambulance from non-participating providers.</strong> Air ambulance from
            providers that do not participate in any insurance network is excluded, though the law
            does limit cost-sharing for air ambulance from participating providers.
          </li>
          <li>
            <strong>Dental and vision care.</strong> Stand-alone dental and vision plans are excluded.
          </li>
        </ul>

        <h2>How to dispute a bill that violates the No Surprises Act</h2>
        <p>
          If you receive a bill you believe violates the No Surprises Act, the dispute process is
          separate from a standard hospital bill dispute. Phone calls are ineffective here. Do this
          in writing.
        </p>
        <p>
          First, gather your documentation: the bill itself, your explanation of benefits from your
          insurer, and any consent forms you were given before the procedure. If you were not given
          a consent form, note that explicitly.
        </p>
        <p>
          Second, contact your insurer. Tell them you received a bill you believe violates the
          No Surprises Act and ask them to initiate the insurer-provider dispute resolution process.
          Insurers are required to handle these disputes directly with the provider. Your cost-sharing
          cannot exceed the in-network amount while the dispute is pending.
        </p>
        <p>
          Third, file a federal complaint at CMS. The federal portal handles complaints against
          providers who violate the law. Violations can result in a civil monetary penalty of up to
          $10,000 per violation. CMS investigates complaints and can compel providers to refund
          excess charges.
        </p>
        <div className={s.glossaryBox}>
          <p className={s.glossaryTerm}>Sample dispute language</p>
          <p className={s.glossaryDef}>
            "I received a bill for [service] on [date] from [provider name], an out-of-network
            provider, for services performed at [facility name], an in-network facility. I did not
            receive the required 72-hour written notice or sign a consent form waiving my No
            Surprises Act protections. Under 42 U.S.C. § 300gg-111, this charge is prohibited.
            I am requesting that you correct my balance to reflect my in-network cost-sharing only
            and confirm in writing that the remaining balance has been waived."
          </p>
        </div>
        <p>
          For the full dispute process from requesting an itemized bill through sending a formal
          letter and escalating if needed, see{' '}
          <Link href="/learn/how-to-dispute-a-hospital-bill">our step-by-step hospital bill
          dispute guide</Link>. Once you have sent a dispute letter,{' '}
          <Link href="/learn/what-happens-after-you-dispute-a-medical-bill">here is what to
          expect in the 30 days after</Link>.
        </p>

        <h2>State-level balance billing protections</h2>
        <p>
          Many states had their own balance billing laws before the federal law passed. Where state
          law provides stronger protections than the No Surprises Act, state law applies. Where
          federal law is stronger, federal law applies. The practical result is that patients in
          states with robust balance billing laws get the benefit of both.
        </p>
        <p>
          States with notable balance billing protections include New York, California, Texas,
          Colorado, and Illinois. Your state insurance commissioner is the right contact for
          state-level violations. The NAIC maintains a directory of state insurance departments
          at naic.org.
        </p>

        <h2>How common are No Surprises Act violations</h2>
        <p>
          In the first two years after the law took effect, CMS received tens of thousands of
          complaints. A 2024 report from the Department of Health and Human Services found that
          surprise billing complaints were concentrated in emergency medicine, anesthesiology,
          radiology, and pathology — the specialties most likely to involve providers patients
          cannot choose in advance.
        </p>
        <p>
          If you received emergency care or had surgery at an in-network facility and received a
          separate bill from a provider you did not recognize, it is worth checking whether that
          bill is permitted.{' '}
          <Link href="/learn/common-medical-billing-errors">Our guide to common billing
          errors</Link>{' '}covers the other patterns to look for on the same bill.
        </p>
      </div>

      <Citations sources={[
        { label: 'CMS: No Surprises Act Overview and Complaint Portal', url: 'https://www.cms.gov/nosurprises' },
        { label: 'CMS: No Surprises Act — Federal Independent Dispute Resolution', url: 'https://www.cms.gov/regulations-and-guidance/legislation/paperwork-reduction-act-of-1995/pra-listing/cms-10791' },
        { label: 'HHS: Report on No Surprises Act Implementation (2024)', url: 'https://www.hhs.gov/sites/default/files/no-surprises-act-report-congress-2024.pdf' },
        { label: 'CMS: Good Faith Estimate for Uninsured Patients', url: 'https://www.cms.gov/healthplan/gfe' },
        { label: 'NAIC: State Insurance Department Directory', url: 'https://content.naic.org/state-insurance-departments' },
      ]} />
      <Cta />
      <RelatedArticles current="no-surprises-act" />
    </article>
  );
}

function Cta(): JSX.Element {
  return (
    <div className={s.ctaBox}>
      <p className={s.ctaTitle}>Check if your bill violates the No Surprises Act</p>
      <p className={s.ctaNote}>ClaroBill reads your itemized bill, flags charges that may violate federal balance billing rules, and writes the dispute letter for you.</p>
      <Link href="/auth/sign-in" className={s.ctaBtn}>Analyze my bill. It&apos;s free</Link>
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
  { slug: 'no-surprises-act', title: 'The No Surprises Act: What It Covers and How to Use It' },
  { slug: 'what-happens-after-you-dispute-a-medical-bill', title: 'What Happens After You Send a Medical Bill Dispute Letter' },
  { slug: 'how-to-dispute-a-hospital-bill', title: 'How to Dispute a Hospital Bill: A Step-by-Step Guide' },
  { slug: 'common-medical-billing-errors', title: 'The Most Common Medical Billing Errors' },
  { slug: 'medical-billing-advocates', title: 'Medical Billing Advocates: What They Do and What They Charge' },
  { slug: 'how-to-read-an-itemized-medical-bill', title: 'How to Read an Itemized Medical Bill' },
  { slug: 'why-bill-exceeds-insurer-negotiated-rate', title: 'Why Your Bill Is Higher Than What Your Insurer Pays' },
  { slug: 'hospital-machine-readable-files-explained', title: 'Hospital Machine-Readable Files Explained' },
  { slug: 'ncci-edits-explained-for-patients', title: 'NCCI Edits: The Federal Rules That Prevent Billing Abuse' },
  { slug: 'what-are-cpt-codes', title: "What Are CPT Codes? A Patient's Guide" },
];
