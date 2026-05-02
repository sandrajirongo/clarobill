import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Privacy Policy: Clarobill',
  description: 'Clarobill Privacy Policy. Learn how we collect, use, and protect your data, including medical bill information.',
};

export default function PrivacyPolicyPage(): JSX.Element {
  return (
    <article>
      <h1 className="text-3xl font-bold text-gray-900 mb-2">Privacy Policy</h1>
      <p className="text-sm text-gray-500 mb-8">Effective date: April 7, 2026. Last updated: April 7, 2026.</p>

      <p className="text-gray-700 mb-6">
        ClaroBill (&ldquo;we,&rdquo; &ldquo;our,&rdquo; or &ldquo;us&rdquo;) is committed to protecting your privacy.
        This policy explains what data we collect when you use ClaroBill, how we use it, and your rights regarding
        that data. Because ClaroBill processes medical bills, we treat all uploaded content as sensitive and apply
        strict handling controls throughout our systems.
      </p>

      <Section title="1. Data We Collect">
        <Subsection title="Account data">
          When you create an account: your email address and an encrypted password (managed by Supabase Auth).
          If you sign in with a third-party provider (e.g., Google), we receive only your email and display name.
        </Subsection>
        <Subsection title="Medical bill files">
          Files you upload (PDFs, images) are stored encrypted at rest in private cloud storage. Only you and
          our processing systems can access them. We do not share uploaded files with any third party other than
          as described in Section 3.
        </Subsection>
        <Subsection title="Extracted bill data">
          Text and line items extracted from your bill during OCR processing (such as procedure codes, charge
          amounts, and dates of service) are stored in our database and used to generate your report. We do not
          store patient names or date-of-birth beyond what you include in the uploaded file itself.
        </Subsection>
        <Subsection title="Payment data">
          We do not store credit card numbers. Payment processing is handled by Stripe. We retain a Stripe
          customer ID and transaction ID to support refunds and order history.
        </Subsection>
        <Subsection title="Usage data">
          Anonymized page views and feature interactions, collected via PostHog analytics. Bill IDs and other
          identifiers are stripped from URLs before any analytics event is recorded. We do not use session
          recording or keystroke logging.
        </Subsection>
        <Subsection title="Error and performance data">
          Anonymized error reports and stack traces via Sentry. Request body contents are redacted before
          transmission to Sentry to prevent PHI leakage.
        </Subsection>
      </Section>

      <Section title="2. How We Use Your Data">
        <ul className="list-disc pl-6 space-y-2 text-gray-700">
          <li>To perform OCR on your uploaded bill and extract line items</li>
          <li>To run automated billing rules checks (duplicate detection, price outliers, NCCI edits)</li>
          <li>To generate an AI-assisted analysis report</li>
          <li>To generate a dispute letter template personalized to your bill&rsquo;s findings</li>
          <li>To deliver your report and dispute letter via email (SendGrid)</li>
          <li>To process your payment and support refund requests (Stripe)</li>
          <li>To monitor service reliability and fix errors (Sentry)</li>
          <li>To understand aggregate usage patterns and improve the product (PostHog)</li>
        </ul>
        <p className="mt-3">
          We do not use your medical bill data to train AI models. That includes our own models and those of our AI
          providers. All AI services we use are contractually prohibited from using submitted content for model
          training.
        </p>
      </Section>

      <Section title="3. Third-Party Processors">
        <p>We share your data with the following sub-processors, solely to provide the Service:</p>
        <div className="mt-4 space-y-3">
          <Processor name="Supabase" purpose="Database and encrypted file storage" location="United States" />
          <Processor name="Cloud OCR provider" purpose="Text extraction from bill images" location="United States" />
          <Processor name="Generative AI services" purpose="AI-assisted bill summarization and dispute letter drafting. All providers are contractually prohibited from using submitted content for model training." location="United States" />
          <Processor name="Stripe" purpose="Payment processing" location="United States" />
          <Processor name="SendGrid (Twilio)" purpose="Transactional email delivery" location="United States" />
          <Processor name="Sentry" purpose="Error monitoring (redacted payloads)" location="United States" />
          <Processor name="PostHog" purpose="Anonymized product analytics" location="United States" />
        </div>
        <p className="mt-4">
          We do not sell your data to advertisers, data brokers, or any other third party.
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
          organizational controls (encryption at rest and in transit, strict access controls, and data minimization)
          consistent with the spirit of HIPAA and industry best practices.
        </p>
      </Section>

      <Section title="6. Your Rights">
        <p>You have the right to:</p>
        <ul className="list-disc pl-6 mt-2 space-y-1 text-gray-700">
          <li><strong>Access</strong> the data we hold about you</li>
          <li><strong>Correct</strong> inaccurate data</li>
          <li><strong>Delete</strong> your account and associated data (within 30 days of request)</li>
          <li><strong>Export</strong> your data in a machine-readable format</li>
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
          We use localStorage (not cookies) to store your PostHog analytics session identifier. This identifier
          is randomly generated and not linked to your account or personal information. We do not use
          third-party advertising cookies.
        </p>
        <p className="mt-3">
          Your Supabase authentication session is stored in a secure, httpOnly cookie.
        </p>
      </Section>

      <Section title="8. Security">
        <p>
          All data is encrypted in transit (TLS 1.2+) and at rest (AES-256). Uploaded files are stored in
          private cloud storage buckets with no public access. Access to production systems is restricted to
          authorized personnel via multi-factor authentication.
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

function Processor({ name, purpose, location }: { name: string; purpose: string; location: string }): JSX.Element {
  return (
    <div className="flex flex-col sm:flex-row sm:gap-4 text-sm border-l-2 border-gray-200 pl-3">
      <span className="font-medium text-gray-900 sm:w-36 shrink-0">{name}</span>
      <span className="text-gray-600 flex-1">{purpose}</span>
      <span className="text-gray-400 sm:w-32 shrink-0">{location}</span>
    </div>
  );
}
