import type { Metadata } from 'next';
import Link from 'next/link';
import { JsonLd } from '@/components/json-ld';
import s from '../../blog/blog.module.css';

export const metadata: Metadata = {
  title: 'Hospital Machine-Readable Files: What They Are and How to Use Them | ClaroBill',
  description:
    'Every US hospital is required by federal law to publish its negotiated rates. Here is how to find that file, read it, and use the numbers when disputing a charge.',
  alternates: {
    canonical: 'https://www.clarobill.com/learn/hospital-machine-readable-files-explained',
    languages: {
      en: 'https://www.clarobill.com/learn/hospital-machine-readable-files-explained',
      'x-default': 'https://www.clarobill.com/learn/hospital-machine-readable-files-explained',
    },
  },
};

const ARTICLE_SCHEMA = {
  '@type': 'Article' as const,
  headline: 'Hospital Machine-Readable Files: What They Are and How to Use Them',
  description:
    'Every US hospital is required by federal law to publish its negotiated rates. Here is how to find that file, read it, and use the numbers when disputing a charge.',
  url: 'https://www.clarobill.com/learn/hospital-machine-readable-files-explained',
  datePublished: '2026-05-07',
  dateModified: '2026-05-07',
  author: { '@type': 'Person' as const, name: 'Sandra Jirongo', url: 'https://www.clarobill.com/authors/sandra-jirongo' },
  publisher: { '@type': 'Organization' as const, name: 'ClaroBill' },
};

const BREADCRUMB_SCHEMA = {
  '@type': 'BreadcrumbList' as const,
  itemListElement: [
    { '@type': 'ListItem' as const, position: 1, name: 'Home', item: 'https://www.clarobill.com' },
    { '@type': 'ListItem' as const, position: 2, name: 'Guides', item: 'https://www.clarobill.com/learn' },
    { '@type': 'ListItem' as const, position: 3, name: 'Hospital Machine-Readable Files Explained', item: 'https://www.clarobill.com/learn/hospital-machine-readable-files-explained' },
  ],
};

const FAQ_SCHEMA = {
  '@type': 'FAQPage' as const,
  mainEntity: [
    {
      '@type': 'Question' as const,
      name: 'What is a hospital machine-readable file?',
      acceptedAnswer: {
        '@type': 'Answer' as const,
        text: 'A machine-readable file (MRF) is a structured data file that every US hospital is required to publish under the Hospital Price Transparency Rule. It contains the hospital\'s negotiated rates with each insurance plan, gross chargemaster prices, discounted cash prices, and the minimum and maximum negotiated rates across all payers.',
      },
    },
    {
      '@type': 'Question' as const,
      name: 'Where can I find my hospital\'s machine-readable file?',
      acceptedAnswer: {
        '@type': 'Answer' as const,
        text: 'CMS maintains a hospital price transparency page at cms.gov/hospital-price-transparency where you can find links to hospital files. Many hospitals also publish a link directly on their billing or financial assistance pages, often labeled "Price Transparency" or "Standard Charges."',
      },
    },
    {
      '@type': 'Question' as const,
      name: 'What does the machine-readable file contain?',
      acceptedAnswer: {
        '@type': 'Answer' as const,
        text: 'The file must contain five types of standard charges for each item or service: gross charge (chargemaster), discounted cash price, payer-specific negotiated rate (by insurer and plan name), de-identified minimum negotiated rate across all payers, and de-identified maximum negotiated rate across all payers.',
      },
    },
    {
      '@type': 'Question' as const,
      name: 'Can I use the machine-readable file to dispute a charge?',
      acceptedAnswer: {
        '@type': 'Answer' as const,
        text: 'Yes. If your bill shows a charge that exceeds the negotiated rate listed in the file for your insurance plan, that is a disputable discrepancy. Reference 45 CFR Part 180 and cite the specific rate from the published file in your dispute letter.',
      },
    },
  ],
};

export default function Article(): JSX.Element {
  return (
    <article>
      <JsonLd schema={[ARTICLE_SCHEMA, BREADCRUMB_SCHEMA, FAQ_SCHEMA]} />

      <div className={s.articleByline}>
        <span>May 7, 2026</span>
        <span>&middot;</span>
        <span>8 min read</span>
        <span>&middot;</span>
        <span>Sandra Jirongo</span>
      </div>

      <h1 className={s.articleH1}>
        Hospital Machine-Readable Files: What They Are and How to Use Them
      </h1>

      <p className={s.articleLead}>
        Every US hospital is required by federal law to publish its negotiated rates in a structured
        data file. Most patients have never heard of this requirement. Fewer still have used it. But
        the numbers in that file can be the strongest evidence you have when disputing a charge.
      </p>

      <div className={s.articleBody}>
        <h2>What the Hospital Price Transparency Rule requires</h2>
        <p>
          The Hospital Price Transparency Rule (45 CFR Part 180), which took effect January 1, 2021,
          requires every hospital that participates in Medicare to publish a machine-readable file
          containing its standard charges. This is not optional. Hospitals that do not comply face
          civil monetary penalties enforced by the Centers for Medicare and Medicaid Services.
        </p>
        <p>
          The rule defines five categories of standard charge that each file must include for every
          item or service the hospital provides:
        </p>
        <ul>
          <li><strong>Gross charge.</strong> The chargemaster price before any discounts or adjustments. This is the starting number that almost no one actually pays.</li>
          <li><strong>Discounted cash price.</strong> The rate the hospital charges patients who pay out of pocket without using insurance.</li>
          <li><strong>Payer-specific negotiated rate.</strong> The rate the hospital has agreed to accept from a specific insurance plan for a specific service. This is the most useful number for most patients.</li>
          <li><strong>De-identified minimum negotiated rate.</strong> The lowest negotiated rate for this service across all payers, without identifying which payer pays it.</li>
          <li><strong>De-identified maximum negotiated rate.</strong> The highest negotiated rate across all payers.</li>
        </ul>
        <p>
          The payer-specific negotiated rate column is what distinguishes this requirement from earlier
          transparency efforts. For the first time, hospitals are required to disclose not just that
          they have negotiated contracts, but what those contracts actually say, by insurer and by plan.
        </p>

        <h2>What the file looks like</h2>
        <p>
          Hospitals can publish their files in any machine-readable format. JSON and CSV are most
          common. Some hospitals publish JSON files that are hundreds of megabytes. Others publish
          clean spreadsheets organized by CPT code. The format varies significantly by hospital and
          by the vendor they use for compliance.
        </p>
        <p>
          Within the file, each row (or record) typically contains:
        </p>
        <ul>
          <li>A billing code (CPT, HCPCS, DRG, or revenue code)</li>
          <li>A plain-language description of the service</li>
          <li>The five standard charge types listed above</li>
          <li>For payer-specific rates: the payer name, the plan name, and the negotiated rate</li>
        </ul>
        <p>
          For a hospital with 20 insurance contracts and 10,000 service lines, a complete file can
          contain hundreds of thousands of rows. That scale is by design: the rule requires disclosure
          at the plan level, not just by insurer.
        </p>

        <h2>How to find your hospital&rsquo;s file</h2>
        <p>
          CMS maintains a hospital price transparency resource at{' '}
          <a href="https://www.cms.gov/hospital-price-transparency" target="_blank" rel="noopener noreferrer">
            cms.gov/hospital-price-transparency
          </a>,
          which includes guidance on where to look and links to enforcement actions against
          non-compliant hospitals.
        </p>
        <p>
          The most direct path is usually the hospital&rsquo;s own website. Look for:
        </p>
        <ul>
          <li>A page titled &ldquo;Price Transparency,&rdquo; &ldquo;Standard Charges,&rdquo; or &ldquo;Patient Financial Services&rdquo;</li>
          <li>A link in the footer or billing FAQ section</li>
          <li>A direct search on the hospital&rsquo;s domain for &ldquo;machine-readable file&rdquo; or &ldquo;standard charges&rdquo;</li>
        </ul>
        <p>
          If the hospital does not have a clearly accessible file, that may itself be a compliance
          violation. CMS has issued civil monetary penalties to hospitals for failing to publish
          or maintain accessible files.
        </p>

        <h2>How to use the file to dispute a charge</h2>
        <p>
          Once you have the file, the process is straightforward:
        </p>
        <ol>
          <li>Identify the CPT code or service description for the charge you are disputing. This comes from your{' '}
            <Link href="/learn/how-to-read-an-itemized-medical-bill">itemized bill</Link>.
          </li>
          <li>Search the machine-readable file for that code.</li>
          <li>Find the row corresponding to your insurance plan and plan name.</li>
          <li>Compare the negotiated rate in the file to what you were billed.</li>
        </ol>
        <p>
          If your bill charges you more than the payer-specific negotiated rate for your plan, you
          have a concrete, documented discrepancy. Your dispute letter can cite the exact rate from
          the published file, reference 45 CFR Part 180, and request correction to the contracted
          amount.
        </p>
        <p>
          This is a stronger dispute basis than most patients use. The hospital has publicly attested
          to the negotiated rate. A charge that exceeds it is inconsistent with the published contract
          data.
        </p>

        <h2>Common gotchas</h2>
        <p>
          Not every hospital publishes a complete or accurate file. CMS enforcement data shows
          ongoing non-compliance across hundreds of hospitals. If the file you find is outdated,
          missing your insurer, or does not contain payer-specific rates, document that absence and
          escalate through your insurer&rsquo;s appeals process instead.
        </p>
        <p>
          Some hospitals publish files that technically comply but are structured to be difficult
          to use: inconsistent column names, nested JSON without documentation, or plan names that
          do not match what appears on your insurance card. If you cannot match your plan, call the
          hospital&rsquo;s billing department and ask them to identify which row in the file corresponds
          to your specific plan. Their answer creates a record.
        </p>
        <p>
          The negotiated rate in the file is also not necessarily the &ldquo;allowed amount&rdquo; on your
          Explanation of Benefits. Allowed amounts reflect the negotiated rate applied to a specific
          claim after claim processing. The MRF rate is a contract floor. In practice the two numbers
          should be consistent, but discrepancies occur. When they do, the EOB and the MRF together
          are your evidence.
        </p>

        <h2>What to do if you cannot open the file</h2>
        <p>
          Large JSON files require a tool to parse. If you are comfortable with spreadsheet software,
          many JSON-to-CSV converters are freely available online. If not, calling the hospital&rsquo;s
          price transparency line and asking them to look up the negotiated rate for your CPT code
          and plan in writing is a legitimate alternative. The hospital is required to provide this
          information; the machine-readable file is one mechanism, not the only one.
        </p>
        <p>
          For the context behind why the gap between gross charges, negotiated rates, and what patients
          actually owe is so large, see our guide to{' '}
          <Link href="/learn/why-bill-exceeds-insurer-negotiated-rate">
            why your bill exceeds your insurer&rsquo;s negotiated rate
          </Link>.
        </p>
      </div>

      <Citations
        sources={[
          { label: 'CMS: Hospital Price Transparency Rule (45 CFR Part 180)', url: 'https://www.cms.gov/hospital-price-transparency' },
          { label: 'CMS: Hospital Price Transparency Final Rule (CMS-1717-F)', url: 'https://www.federalregister.gov/documents/2019/11/27/2019-24931/medicare-and-medicaid-programs-cy-2020-hospital-outpatient-pps-policy-changes-and-payment-rates-and' },
          { label: 'CMS: Hospital Price Transparency Enforcement Actions', url: 'https://www.cms.gov/hospital-price-transparency/enforcement' },
          { label: 'CMS: No Surprises Act Overview', url: 'https://www.cms.gov/nosurprises' },
        ]}
      />
      <Cta />
      <RelatedArticles current="hospital-machine-readable-files-explained" />
    </article>
  );
}

function Cta(): JSX.Element {
  return (
    <div className={s.ctaBox}>
      <p className={s.ctaTitle}>Let us find the discrepancy in your bill</p>
      <p className={s.ctaNote}>
        ClaroBill cross-references your charges against the rates hospitals are required to publish,
        flags overcharges, and writes your dispute letter with a citation for every finding.
      </p>
      <Link href="/auth/sign-in" className={s.ctaBtn}>Check my bill for free</Link>
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
            <span style={{ marginRight: '.4rem', opacity: 0.5 }}>{i + 1}.</span>
            <a href={src.url} target="_blank" rel="noopener noreferrer" className={s.sourceLink}>
              {src.label}
            </a>
          </li>
        ))}
      </ol>
    </div>
  );
}

function RelatedArticles({ current }: { current: string }): JSX.Element {
  const ALL_ARTICLES = [
    { slug: 'how-to-read-an-itemized-medical-bill', title: 'How to Read an Itemized Medical Bill' },
    { slug: 'common-medical-billing-errors', title: 'The Most Common Medical Billing Errors' },
    { slug: 'what-are-cpt-codes', title: "What Are CPT Codes? A Patient's Guide" },
    { slug: 'how-to-dispute-a-hospital-bill', title: 'How to Dispute a Hospital Bill: A Step-by-Step Guide' },
    { slug: 'medical-billing-advocates', title: 'Medical Billing Advocates: What They Do and What They Charge' },
    { slug: 'why-bill-exceeds-insurer-negotiated-rate', title: 'Why Your Bill Is Higher Than What Your Insurer Pays' },
    { slug: 'hospital-machine-readable-files-explained', title: 'Hospital Machine-Readable Files Explained' },
    { slug: 'ncci-edits-explained-for-patients', title: 'NCCI Edits: The Federal Rules That Prevent Billing Abuse' },
  ];
  const related = ALL_ARTICLES.filter((a) => a.slug !== current).slice(0, 3);
  return (
    <div className={s.relatedSection}>
      <p className={s.relatedLabel}>More guides</p>
      <div>
        {related.map((a) => (
          <Link key={a.slug} href={`/learn/${a.slug}`} className={s.relatedLink}>
            {a.title} &rarr;
          </Link>
        ))}
      </div>
    </div>
  );
}
