import type { Metadata } from 'next';
import { JsonLd } from '@/components/json-ld';

export const metadata: Metadata = {
  title: 'Medical and Legal Disclaimer: Clarobill',
  description: 'Important disclaimer: Clarobill provides billing analysis only and is not a substitute for medical or legal advice.',
  alternates: {
    canonical: 'https://www.clarobill.com/legal/disclaimer',
    languages: { 'en': 'https://www.clarobill.com/legal/disclaimer', 'x-default': 'https://www.clarobill.com/legal/disclaimer' },
  },
};

const ORG_SCHEMA = {
  '@type': 'Organization' as const,
  name: 'ClaroBill',
  url: 'https://www.clarobill.com',
  description: 'AI-powered medical bill error finder.',
};

export default function DisclaimerPage(): JSX.Element {
  return (
    <article>
      <JsonLd schema={ORG_SCHEMA} />
      <h1 className="text-3xl font-bold text-gray-900 mb-2">Medical and Legal Disclaimer</h1>
      <p className="text-sm text-gray-500 mb-8">
        Effective date: April 7, 2026. Last updated: April 7, 2026.{' '}
        <span>Last reviewed: May 2026.</span>
      </p>

      {/* High-visibility summary box */}
      <div className="bg-amber-50 border border-amber-200 rounded-lg p-5 mb-10">
        <p className="font-semibold text-amber-900 mb-2">Important. Please read before using Clarobill:</p>
        <ul className="list-disc pl-5 space-y-1 text-amber-800 text-sm">
          <li>Clarobill is a billing analysis tool, not a medical or legal services provider.</li>
          <li>Nothing in your report or dispute letter constitutes medical or legal advice.</li>
          <li>Using Clarobill does not create a doctor-patient or attorney-client relationship.</li>
          <li>Clarobill does not guarantee that any dispute will result in a billing correction or refund.</li>
        </ul>
      </div>

      <Section title="1. Not Medical Advice">
        <p>
          Clarobill analyzes the <strong>billing and coding</strong> aspects of your medical bill. This analysis
          is limited to identifying potential errors in how medical services were billed (such as duplicate
          charges, charges that exceed standard fee schedules, and procedure code combinations that may violate
          billing rules).
        </p>
        <p className="mt-3">
          Clarobill does not evaluate the medical necessity, appropriateness, or quality of any medical treatment
          you received. Nothing in any report, letter, or communication from Clarobill should be construed as
          medical advice or a recommendation regarding your health, treatment, or care.
        </p>
        <p className="mt-3">
          For questions about your diagnosis, treatment, or medical decisions, consult a licensed healthcare
          provider.
        </p>
      </Section>

      <Section title="2. Not Legal Advice">
        <p>
          Clarobill generates dispute letter templates to help you communicate with your healthcare provider or
          insurer about potential billing errors. These templates are starting points for your own correspondence.
          They are not legal documents and do not constitute legal advice.
        </p>
        <p className="mt-3">
          Clarobill is not a law firm and is not providing legal services. No attorney-client relationship is
          created by your use of the Service. The dispute letter templates have not been reviewed by an attorney
          and may not be appropriate for your specific legal situation.
        </p>
        <p className="mt-3">
          If you have a complex billing dispute, believe you have been the victim of fraud, or need advice on
          your legal rights, consult a licensed attorney, particularly one specializing in healthcare law or
          patient advocacy.
        </p>
      </Section>

      <Section title="3. Analysis Accuracy">
        <p>
          Clarobill uses automated rules and AI-assisted analysis to identify potential billing errors. While we
          strive for accuracy, our analysis:
        </p>
        <ul className="list-disc pl-6 mt-2 space-y-1 text-gray-700">
          <li>May not detect all billing errors in your bill</li>
          <li>
            May flag items as potential errors that your provider can legitimately justify (e.g., a modifier
            that overrides a standard bundling rule)
          </li>
          <li>
            Is based on publicly available fee schedules and billing rules, which may differ from the specific
            contract between your provider and your insurer
          </li>
          <li>
            May be affected by OCR errors if your bill was difficult to read or was a low-quality scan
          </li>
        </ul>
        <p className="mt-3">
          You should review the findings in your report carefully and use your own judgment before submitting a
          dispute. When in doubt, consult a professional patient advocate or healthcare billing specialist.
        </p>
      </Section>

      <Section title="4. No Guarantee of Outcome">
        <p>
          Clarobill does not guarantee that any billing dispute you initiate will result in a corrected bill,
          a refund, or any other outcome. The decision to accept or reject a dispute rests entirely with your
          healthcare provider, hospital, or insurance company.
        </p>
        <p className="mt-3">
          Clarobill is not responsible for any actions you take, or fail to take, based on your report or
          dispute letter, or for any outcome of any dispute you file.
        </p>
      </Section>

      <Section title="5. Emergency Situations">
        <p>
          If you are experiencing a medical emergency, call 911 or go to your nearest emergency room
          immediately. Clarobill is not an emergency service and cannot assist with medical emergencies.
        </p>
      </Section>

      <Section title="6. Limitations of Liability">
        <p>
          TO THE MAXIMUM EXTENT PERMITTED BY LAW, CLAROBILL SHALL NOT BE LIABLE FOR ANY DIRECT, INDIRECT,
          INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES ARISING FROM YOUR RELIANCE ON THE ANALYSIS,
          REPORTS, OR DISPUTE LETTERS PROVIDED THROUGH THE SERVICE.
        </p>
        <p className="mt-3">
          This disclaimer supplements, and does not replace, the limitations of liability set forth in our{' '}
          <a href="/legal/terms" className="text-blue-600 hover:underline">Terms of Service</a>.
        </p>
      </Section>

      <Section title="7. Consult a Professional">
        <p>
          For complex medical billing situations, we encourage you to seek help from qualified professionals:
        </p>
        <ul className="list-disc pl-6 mt-2 space-y-1 text-gray-700">
          <li>
            <strong>Patient advocates:</strong> Many hospitals have patient advocates on staff at no charge.
            Independent patient advocates can also help negotiate bills.
          </li>
          <li>
            <strong>Healthcare attorneys:</strong> For disputes involving insurance denial, balance billing,
            or potential fraud.
          </li>
          <li>
            <strong>State insurance commissioner:</strong> For disputes with your health insurer, your state&rsquo;s
            insurance commissioner can be a resource.
          </li>
          <li>
            <strong>CMS:</strong> The Centers for Medicare & Medicaid Services provides resources for Medicare
            and Medicaid beneficiaries disputing bills.
          </li>
        </ul>
      </Section>

      <Section title="8. Contact">
        <p>
          Questions about this disclaimer? Contact us at{' '}
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
