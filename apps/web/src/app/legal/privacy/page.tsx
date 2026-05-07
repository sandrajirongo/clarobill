import type { Metadata } from 'next';
import { JsonLd } from '@/components/json-ld';

export const metadata: Metadata = {
  title: 'Privacy Policy: Clarobill',
  description: 'Clarobill Privacy Policy. Learn how we collect, use, and protect your data, including medical bill information.',
  alternates: {
    canonical: 'https://www.clarobill.com/legal/privacy',
    languages: { 'en': 'https://www.clarobill.com/legal/privacy', 'x-default': 'https://www.clarobill.com/legal/privacy' },
  },
};

const ORG_SCHEMA = {
  '@type': 'Organization' as const,
  name: 'ClaroBill',
  url: 'https://www.clarobill.com',
  description: 'AI-powered medical bill error finder.',
};

export default function PrivacyPolicyPage(): JSX.Element {
  return (
    <article>
      <JsonLd schema={ORG_SCHEMA} />
      <h1 className="text-3xl font-bold text-gray-900 mb-2">Privacy Policy</h1>
      <p className="text-sm text-gray-500 mb-8">
        Effective date: April 7, 2026. Last updated: April 7, 2026.{' '}
        <span>Last reviewed: May 2026.</span>
      </p>

      <p className="text-gray-700 mb-6">
        ClaroBill (&ldquo;we,&rdquo; &ldquo;our,&rdquo; or &ldquo;us&rdquo;) is committed to protecting your privacy.
        This policy explains what data we collect when you use ClaroBill, how we use it, and your rights regarding
        that data. Because ClaroBill processes medical bills, we treat all uploaded content as sensitive and apply
        strict handling controls throughout our systems.
      </p>

      <Section title="1. Data We Collect">
        <Subsection title="Account data">
          When you create an account: your email address and an authentication credential. If you sign in with a
          third-party identity provider, we receive only your email and display name from that provider.
        </Subsection>
        <Subsection title="Medical bill files">
          Files you upload (PDFs, images) are stored encrypted at rest in private storage. Only you and our
          processing systems can access them. We do not share uploaded files with any third party other than as
          described in Section 3.
        </Subsection>
        <Subsection title="Extracted bill data">
          Text and line items extracted from your bill (such as procedure codes, charge amounts, and dates of
          service) are stored in our database and used to generate your report. We do not store patient names or
          dates of birth beyond what you include in the uploaded file itself.
        </Subsection>
        <Subsection title="Payment data">
          We do not store credit card numbers. Payment processing is handled by an external payment service. We
          retain a customer identifier and transaction identifier from that service to support refunds and order
          history.
        </Subsection>
        <Subsection title="Usage data">
          Anonymized page views and feature interactions. Bill identifiers and other personal identifiers are
          stripped before any analytics event is recorded. We do not use session recording or keystroke logging.
        </Subsection>
        <Subsection title="Error and performance data">
          Anonymized error reports and stack traces. Request body contents are redacted before transmission to
          prevent leakage of sensitive information.
        </Subsection>
      </Section>

      <Section title="2. How We Use Your Data">
        <ul className="list-disc pl-6 space-y-2 text-gray-700">
          <li>To extract text and line items from your uploaded bill</li>
          <li>To run automated billing checks against the line items on your bill</li>
          <li>To generate an analysis report and a personalized dispute letter draft</li>
          <li>To deliver your report and dispute letter via email</li>
          <li>To process your payment and support refund requests</li>
          <li>To monitor service reliability and fix errors</li>
          <li>To understand aggregate usage patterns and improve the product</li>
        </ul>
        <p className="mt-3">
          We do not use your medical bill data to train AI models. That includes our own models and those of any
          service provider we work with. Every service we use that processes your data is contractually prohibited
          from using submitted content for model training or any purpose other than performing the service for us.
        </p>
      </Section>

      <Section title="3. Categories of Service Providers">
        <p>
          To deliver the Service, we engage a small number of service providers to handle specific operational
          functions. We do not publish the names of these providers on this page in order to limit the value of
          the disclosure to bad actors and competitors. We share only the minimum data necessary for each provider
          to perform its function. The categories are:
        </p>
        <div className="mt-4 space-y-3">
          <Processor category="Cloud infrastructure" purpose="Database, encrypted file storage, and authentication" />
          <Processor category="Document processing" purpose="Text extraction from uploaded bill images and PDFs" />
          <Processor category="AI services" purpose="Bill summarization and dispute letter drafting. Contractually prohibited from using submitted content for model training." />
          <Processor category="Payment processing" purpose="Card processing, refund support, and transaction history" />
          <Processor category="Email delivery" purpose="Delivery of transactional emails (account, reports, receipts)" />
          <Processor category="Operational telemetry" purpose="Anonymized error reporting and aggregate usage analytics, with personal identifiers stripped before transmission" />
        </div>
        <p className="mt-4">
          All service providers operate in the United States. A current list of named sub-processors is available
          to enterprise customers and regulators on written request to{' '}
          <a href="mailto:privacy@clarobill.com" className="text-blue-600 hover:underline">privacy@clarobill.com</a>.
        </p>
        <p className="mt-3">
          We do not sell your data to advertisers, data brokers, or any other third party. We do not share your
          data for advertising or marketing purposes.
        </p>
      </Section>

      <Section title="4. Data Retention">
        <ul className="list-disc pl-6 space-y-2 text-gray-700">
          <li>Uploaded bill files: retained for 90 days after upload, then automatically deleted</li>
          <li>Extracted line item data and reports: retained for 12 months, then deleted</li>
          <li>Account data: retained until you delete your account</li>
          <li>Payment records: retained for 7 years as required by financial regulations</li>
          <li>Anonymized analytics: retained indefinitely in aggregate, with no link to your identity</li>
        </ul>
      </Section>

      <Section title="5. HIPAA Notice">
        <p>
          Clarobill is not a Covered Entity or Business Associate as defined by the Health Insurance Portability
          and Accountability Act (HIPAA). Medical bills you upload are not &ldquo;protected health information&rdquo;
          (PHI) under HIPAA in the context of this Service because Clarobill is not a healthcare provider, health
          plan, or healthcare clearinghouse.
        </p>
        <p className="mt-3">
          However, because your bill may contain sensitive health information, we apply strong technical and
          organizational controls (encryption at rest and in transit, strict access controls, and data
          minimization) consistent with the spirit of HIPAA and industry best practices.
        </p>
      </Section>

      <Section title="6. Your Rights">
        <p>You have the right to:</p>
        <ul className="list-disc pl-6 mt-2 space-y-1 text-gray-700">
          <li><strong>Access</strong> the data we hold about you</li>
          <li><strong>Correct</strong> inaccurate data</li>
          <li><strong>Delete</strong> your account and associated data (within 30 days of request)</li>
          <li><strong>Export</strong> your data in a portable format</li>
          <li><strong>Opt out</strong> of analytics by using a browser with tracking protection enabled</li>
        </ul>
        <p className="mt-3">
          To exercise any of these rights, email{' '}
          <a href="mailto:privacy@clarobill.com" className="text-blue-600 hover:underline">privacy@clarobill.com</a>.
          We will respond within 30 days.
        </p>
      </Section>

      <Section title="7. Cookies and Tracking">
        <p>
          We store a randomly generated analytics session identifier in your browser. This identifier is not
          linked to your account or personal information. We do not use third-party advertising cookies and we do
          not allow advertising networks to track you through our Service.
        </p>
        <p className="mt-3">
          Your authentication session is stored in a secure, httpOnly cookie.
        </p>
      </Section>

      <Section title="8. Security">
        <p>
          All data is encrypted in transit (TLS 1.2+) and at rest (AES-256). Uploaded files are stored in private
          storage with no public access. Access to production systems is restricted to authorized personnel via
          multi-factor authentication.
        </p>
        <p className="mt-3">
          If you discover a security vulnerability, please report it responsibly to{' '}
          <a href="mailto:security@clarobill.com" className="text-blue-600 hover:underline">security@clarobill.com</a>.
        </p>
      </Section>

      <Section title="9. Children">
        <p>
          The Service is not directed at children under 13. We do not knowingly collect data from children.
          If you believe a child has submitted data to Clarobill, contact us at{' '}
          <a href="mailto:privacy@clarobill.com" className="text-blue-600 hover:underline">privacy@clarobill.com</a> and
          we will delete it promptly.
        </p>
      </Section>

      <Section title="10. Changes to This Policy">
        <p>
          We will notify you of material changes to this policy by email at least 14 days before they take
          effect. The &ldquo;Last updated&rdquo; date at the top of this page reflects the most recent revision.
        </p>
      </Section>

      <Section title="11. Contact">
        <p>
          Privacy questions or requests:{' '}
          <a href="mailto:privacy@clarobill.com" className="text-blue-600 hover:underline">privacy@clarobill.com</a>
        </p>
      </Section>
    </article>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }): JSX.Element {
  return (
    <section className="mb-8">
      <h2 className="text-xl font-semibold text-gray-900 mb-3">{title}</h2>
      <div className="text-gray-700 leading-relaxed">{children}</div>
    </section>
  );
}

function Subsection({ title, children }: { title: string; children: React.ReactNode }): JSX.Element {
  return (
    <div className="mb-3">
      <span className="font-medium text-gray-900">{title}: </span>
      <span className="text-gray-700">{children}</span>
    </div>
  );
}

function Processor({ category, purpose }: { category: string; purpose: string }): JSX.Element {
  return (
    <div className="flex flex-col sm:flex-row sm:gap-4 text-sm border-l-2 border-gray-200 pl-3">
      <span className="font-medium text-gray-900 sm:w-44 shrink-0">{category}</span>
      <span className="text-gray-600 flex-1">{purpose}</span>
    </div>
  );
}
