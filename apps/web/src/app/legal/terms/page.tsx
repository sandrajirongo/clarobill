import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Terms of Service: Clarobill',
  description: 'Clarobill Terms of Service. Read the terms governing your use of Clarobill medical bill analysis.',
};

export default function TermsOfServicePage(): JSX.Element {
  return (
    <article>
      <h1 className="text-3xl font-bold text-gray-900 mb-2">Terms of Service</h1>
      <p className="text-sm text-gray-500 mb-8">Effective date: April 7, 2026. Last updated: April 7, 2026.</p>

      <p className="text-gray-700 mb-6">
        These Terms of Service (&ldquo;Terms&rdquo;) govern your access to and use of ClaroBill (&ldquo;Service,&rdquo;
        &ldquo;we,&rdquo; &ldquo;our,&rdquo; or &ldquo;us&rdquo;). By creating an account or
        using the Service, you agree to be bound by these Terms. If you do not agree, do not use the Service.
      </p>

      <Section title="1. What Clarobill Does">
        <p>
          Clarobill is a software tool that analyzes medical bills you upload for potential billing errors, overcharges,
          duplicate charges, and coding irregularities. The Service generates a report and, where applicable, a draft
          dispute letter for your personal use.
        </p>
        <p className="mt-3">
          Clarobill does not provide medical advice, legal advice, or financial advice. See our{' '}
          <a href="/legal/disclaimer" className="text-blue-600 hover:underline">Medical and Legal Disclaimer</a> for
          full details.
        </p>
      </Section>

      <Section title="2. Eligibility">
        <p>
          You must be at least 18 years old to use the Service. By using Clarobill, you represent that you are 18 or
          older and that you have the legal right to upload and analyze the medical bills you submit. Either because
          they are your own bills or because you are an authorized representative of the patient.
        </p>
      </Section>

      <Section title="3. Your Account">
        <p>
          You are responsible for maintaining the confidentiality of your account credentials and for all activity
          that occurs under your account. Notify us immediately at{' '}
          <a href="mailto:support@clarobill.com" className="text-blue-600 hover:underline">support@clarobill.com</a> if
          you suspect unauthorized access.
        </p>
        <p className="mt-3">
          We reserve the right to suspend or terminate accounts that violate these Terms or that we determine, in our
          sole discretion, are being used fraudulently or abusively.
        </p>
      </Section>

      <Section title="4. Payments and Refunds">
        <p>
          The Service uses Stripe for payment processing. By purchasing a report, you authorize a one-time charge to
          your payment method. All prices are in US dollars.
        </p>
        <p className="mt-3">
          We offer a full refund within 48 hours of purchase if you are unsatisfied with your report, provided you
          have not already downloaded the report more than once. To request a refund, email{' '}
          <a href="mailto:support@clarobill.com" className="text-blue-600 hover:underline">support@clarobill.com</a> with
          your order details.
        </p>
        <p className="mt-3">
          We do not store your full payment card details. All payment data is handled by Stripe in accordance with
          PCI DSS standards.
        </p>
      </Section>

      <Section title="5. Acceptable Use">
        <p>You agree not to:</p>
        <ul className="list-disc pl-6 mt-2 space-y-1 text-gray-700">
          <li>Upload bills belonging to individuals for whom you are not an authorized representative</li>
          <li>Use the Service to process bills in bulk on behalf of third parties for commercial purposes</li>
          <li>Attempt to reverse-engineer, scrape, or otherwise extract data or models from the Service</li>
          <li>Use the Service in any way that violates applicable federal or state law</li>
          <li>Circumvent any rate limits, access controls, or security measures</li>
        </ul>
      </Section>

      <Section title="6. Your Data">
        <p>
          You retain ownership of all medical bills and personal data you upload. By uploading content, you grant us
          a limited, non-exclusive license to process that content solely to provide the Service to you.
        </p>
        <p className="mt-3">
          We do not sell your data to third parties. We do not use your medical bill data to train AI models. See our{' '}
          <a href="/legal/privacy" className="text-blue-600 hover:underline">Privacy Policy</a> for full details on
          how we handle your data.
        </p>
        <p className="mt-3">
          You may request deletion of your account and associated data at any time by emailing{' '}
          <a href="mailto:support@clarobill.com" className="text-blue-600 hover:underline">support@clarobill.com</a>. We
          will delete your data within 30 days, except where retention is required by law.
        </p>
      </Section>

      <Section title="7. Intellectual Property">
        <p>
          The Service, including its software, design, and analysis methodology, is owned by ClaroBill and protected
          by intellectual property laws. These Terms do not grant you any rights to our trademarks, logos, or
          proprietary technology.
        </p>
        <p className="mt-3">
          The reports and dispute letters generated for you are yours to use for personal purposes. You may not
          resell or redistribute them commercially.
        </p>
      </Section>

      <Section title="8. Disclaimers and Limitation of Liability">
        <p>
          THE SERVICE IS PROVIDED &ldquo;AS IS&rdquo; WITHOUT WARRANTIES OF ANY KIND. WE DO NOT WARRANT THAT THE
          SERVICE WILL BE ERROR-FREE, THAT BILL ANALYSES WILL BE COMPLETE OR ACCURATE, OR THAT USE OF THE SERVICE
          WILL RESULT IN A SUCCESSFUL BILLING DISPUTE.
        </p>
        <p className="mt-3">
          TO THE MAXIMUM EXTENT PERMITTED BY LAW, OUR TOTAL LIABILITY TO YOU FOR ANY CLAIM ARISING FROM OR RELATED
          TO THESE TERMS OR THE SERVICE SHALL NOT EXCEED THE AMOUNT YOU PAID US IN THE 12 MONTHS PRECEDING THE CLAIM.
          IN NO EVENT WILL WE BE LIABLE FOR INDIRECT, INCIDENTAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES.
        </p>
      </Section>

      <Section title="9. Changes to These Terms">
        <p>
          We may update these Terms from time to time. If we make material changes, we will notify you by email or
          by posting a notice in the Service at least 14 days before the changes take effect. Continued use of the
          Service after changes take effect constitutes acceptance of the revised Terms.
        </p>
      </Section>

      <Section title="10. Governing Law">
        <p>
          These Terms are governed by the laws of the United States. Any disputes arising under these Terms will
          be resolved through binding arbitration under the rules of the American Arbitration Association, except
          that either party may seek injunctive relief in a court of competent jurisdiction.
        </p>
      </Section>

      <Section title="11. Contact">
        <p>
          Questions about these Terms? Contact us at{' '}
          <a href="mailto:legal@clarobill.com" className="text-blue-600 hover:underline">legal@clarobill.com</a>.
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
