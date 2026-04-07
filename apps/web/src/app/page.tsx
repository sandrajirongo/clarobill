import Link from 'next/link';
import type { Metadata } from 'next';
import { Logo } from '@/components/logo';

export const metadata: Metadata = {
  title: 'Clarobill — Find Errors in Your Medical Bill',
  description: 'AI-powered medical bill analysis. Clarobill finds overcharges, duplicate charges, and billing errors in minutes — then writes your dispute letter.',
};

export default function LandingPage(): JSX.Element {
  return (
    <div className="min-h-screen bg-white font-[family-name:var(--font-geist-sans)]">
      <Nav />
      <Hero />
      <StatsBar />
      <HowItWorks />
      <WhatWeFind />
      <Pricing />
      <Faq />
      <Footer />
    </div>
  );
}

function Nav(): JSX.Element {
  return (
    <header className="border-b border-gray-100 bg-white sticky top-0 z-10">
      <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
        <Logo size="sm" />
        <Link
          href="/auth/sign-in"
          className="text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors"
        >
          Sign in
        </Link>
      </div>
    </header>
  );
}

function Hero(): JSX.Element {
  return (
    <section className="max-w-5xl mx-auto px-6 pt-20 pb-16 text-center">
      <div className="inline-block bg-blue-50 text-blue-700 text-sm font-medium px-3 py-1 rounded-full mb-6">
        Up to 80% of medical bills contain errors
      </div>
      <h1 className="text-5xl font-bold text-gray-900 leading-tight mb-6 text-balance">
        Your medical bill<br />probably has errors.
      </h1>
      <p className="text-xl text-gray-500 max-w-2xl mx-auto mb-10 text-balance">
        Clarobill checks every line item against Medicare rates, flags duplicate
        charges and billing code violations, and writes your dispute letter —
        in minutes.
      </p>
      <Link
        href="/auth/sign-in"
        className="inline-block bg-gray-900 text-white text-base font-medium px-8 py-4 rounded-xl hover:bg-gray-700 transition-colors"
      >
        Analyze my bill →
      </Link>
      <p className="mt-4 text-sm text-gray-400">One-time $9.99. No subscription.</p>
    </section>
  );
}

function StatsBar(): JSX.Element {
  const stats = [
    { value: '80%', label: 'of bills have at least one error' },
    { value: '$1,300', label: 'avg. error on bills over $10,000' },
    { value: '3 min', label: 'average time to get your report' },
    { value: '30+', label: 'billing rules checked automatically' },
  ];

  return (
    <section className="bg-gray-50 border-y border-gray-100">
      <div className="max-w-5xl mx-auto px-6 py-10 grid grid-cols-2 md:grid-cols-4 gap-8 text-center">
        {stats.map((stat) => (
          <div key={stat.value}>
            <div className="text-3xl font-bold text-gray-900">{stat.value}</div>
            <div className="text-sm text-gray-500 mt-1">{stat.label}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

function HowItWorks(): JSX.Element {
  const steps = [
    {
      number: '1',
      title: 'Upload your bill',
      description: 'Upload a PDF or photo of your medical bill. We accept EOBs, itemized bills, and hospital statements.',
    },
    {
      number: '2',
      title: 'AI analyzes every line',
      description: 'We extract every procedure code, check it against Medicare fee schedules, and run 30+ billing rules automatically.',
    },
    {
      number: '3',
      title: 'Get your report',
      description: 'Receive a plain-English report of every error found, plus a ready-to-send dispute letter personalized to your bill.',
    },
  ];

  return (
    <section className="max-w-5xl mx-auto px-6 py-20">
      <h2 className="text-3xl font-bold text-gray-900 text-center mb-4">How it works</h2>
      <p className="text-gray-500 text-center mb-14 max-w-xl mx-auto">
        No medical billing knowledge required. Upload your bill and we handle the rest.
      </p>
      <div className="grid md:grid-cols-3 gap-10">
        {steps.map((step) => (
          <div key={step.number} className="flex flex-col items-start">
            <div className="w-10 h-10 rounded-full bg-gray-900 text-white flex items-center justify-center font-bold text-sm mb-4">
              {step.number}
            </div>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">{step.title}</h3>
            <p className="text-gray-500 leading-relaxed">{step.description}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function WhatWeFind(): JSX.Element {
  const findings = [
    {
      title: 'Duplicate charges',
      description: 'The same procedure billed twice on the same or consecutive dates.',
    },
    {
      title: 'Inflated prices',
      description: 'Line items priced significantly above the Medicare benchmark for your region.',
    },
    {
      title: 'Unbundled procedures',
      description: 'Separate billing for procedures that should be billed together under NCCI rules.',
    },
    {
      title: 'Upcoded services',
      description: 'A routine visit coded as a complex case to justify a higher charge.',
    },
    {
      title: 'Phantom charges',
      description: 'Charges for services, supplies, or medications not reflected in your records.',
    },
    {
      title: 'Invalid code combinations',
      description: 'Procedure or diagnosis codes that are clinically incompatible when billed together.',
    },
  ];

  return (
    <section className="bg-gray-50 border-y border-gray-100">
      <div className="max-w-5xl mx-auto px-6 py-20">
        <h2 className="text-3xl font-bold text-gray-900 text-center mb-4">What we find</h2>
        <p className="text-gray-500 text-center mb-14 max-w-xl mx-auto">
          Medical billing is complex. Errors happen — and most patients never catch them.
        </p>
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {findings.map((finding) => (
            <div key={finding.title} className="bg-white rounded-xl p-6 border border-gray-100">
              <div className="flex items-start gap-3">
                <span className="text-green-500 mt-0.5 text-lg">✓</span>
                <div>
                  <h3 className="font-semibold text-gray-900 mb-1">{finding.title}</h3>
                  <p className="text-sm text-gray-500 leading-relaxed">{finding.description}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Pricing(): JSX.Element {
  return (
    <section className="max-w-5xl mx-auto px-6 py-20 text-center">
      <h2 className="text-3xl font-bold text-gray-900 mb-4">Simple pricing</h2>
      <p className="text-gray-500 mb-12 max-w-md mx-auto">
        Pay once per bill. No subscription, no hidden fees.
      </p>
      <div className="max-w-sm mx-auto bg-gray-900 rounded-2xl p-8 text-white">
        <div className="text-5xl font-bold mb-1">$9.99</div>
        <div className="text-gray-400 text-sm mb-8">per bill analysis</div>
        <ul className="text-left space-y-3 mb-8 text-sm">
          {[
            'Full itemized error report',
            'Ready-to-send dispute letter',
            'Price comparison vs. Medicare rates',
            'NCCI unbundling check',
            'Delivered to your email',
            '48-hour refund if unsatisfied',
          ].map((item) => (
            <li key={item} className="flex items-center gap-3">
              <span className="text-green-400">✓</span>
              <span className="text-gray-300">{item}</span>
            </li>
          ))}
        </ul>
        <Link
          href="/auth/sign-in"
          className="block w-full bg-white text-gray-900 font-semibold py-3 rounded-xl hover:bg-gray-100 transition-colors text-center"
        >
          Analyze my bill
        </Link>
      </div>
    </section>
  );
}

function Faq(): JSX.Element {
  const questions = [
    {
      q: 'Is my medical bill data safe?',
      a: 'Yes. Your bill is stored encrypted and is only accessible to you. We never sell your data or use it to train AI models. Files are automatically deleted after 90 days. See our Privacy Policy for full details.',
    },
    {
      q: 'What if my bill has no errors?',
      a: "We'll still send you the full analysis showing what we checked and why each line item passed. If you're unsatisfied, we offer a full refund within 48 hours.",
    },
    {
      q: 'Will the dispute letter actually work?',
      a: 'Dispute letters are not a guarantee — billing departments decide whether to accept corrections. However, a specific, well-documented letter citing the exact codes and rules is far more effective than a general complaint. Many patients recover hundreds or thousands of dollars this way.',
    },
    {
      q: 'What types of bills can I upload?',
      a: 'Hospital itemized bills, Explanations of Benefits (EOBs), physician office bills, and outpatient facility bills. PDFs and clear photos or scans are supported. Maximum file size is 20MB.',
    },
    {
      q: 'Is this medical or legal advice?',
      a: 'No. Clarobill provides billing code analysis only. Nothing in your report or dispute letter constitutes medical or legal advice. See our Medical and Legal Disclaimer.',
    },
    {
      q: 'Who is Clarobill?',
      a: 'Clarobill is a product of Flow Financial Group, a company focused on educating and empowering consumers to navigate the financial landscape.',
    },
  ];

  return (
    <section className="bg-gray-50 border-t border-gray-100">
      <div className="max-w-3xl mx-auto px-6 py-20">
        <h2 className="text-3xl font-bold text-gray-900 text-center mb-12">
          Frequently asked questions
        </h2>
        <div className="space-y-8">
          {questions.map((item) => (
            <div key={item.q} className="border-b border-gray-200 pb-8 last:border-0 last:pb-0">
              <h3 className="font-semibold text-gray-900 mb-2">{item.q}</h3>
              <p className="text-gray-500 leading-relaxed text-sm">{item.a}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Footer(): JSX.Element {
  return (
    <footer className="border-t border-gray-100">
      <div className="max-w-5xl mx-auto px-6 py-8 flex flex-col sm:flex-row items-center justify-between gap-4 text-sm text-gray-400">
        <span>© {new Date().getFullYear()} Flow Financial Group. All rights reserved.</span>
        <nav className="flex gap-6">
          <Link href="/legal/terms" className="hover:text-gray-700 transition-colors">Terms</Link>
          <Link href="/legal/privacy" className="hover:text-gray-700 transition-colors">Privacy</Link>
          <Link href="/legal/disclaimer" className="hover:text-gray-700 transition-colors">Disclaimer</Link>
          <a href="mailto:support@clarobill.com" className="hover:text-gray-700 transition-colors">Support</a>
        </nav>
      </div>
    </footer>
  );
}
