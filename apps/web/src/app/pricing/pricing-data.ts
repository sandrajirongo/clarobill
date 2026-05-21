// Shared static data for the pricing page. Lives in its own module so both
// the server component (page.tsx) and the client island (pricing-faq.tsx)
// can import it without pulling 'use client' into the server component tree.

export const TIERS = [
  {
    range: '$0 – $20',
    price: 'Free',
    priceSub: null,
    tag: 'Clean Bill',
    tagline: 'Your bill is clean. Enjoy the peace of mind. No charge, ever.',
    keepNote: 'No charge. Ever.',
  },
  {
    range: '$21 – $100',
    price: '$14.99',
    priceSub: 'one-time',
    tag: 'Small Win',
    tagline: "We've discounted the fee so you keep the lion's share of every dollar saved.",
    keepNote: 'You keep ≥ $6',
  },
  {
    range: '$101 – $500',
    price: '$79.99',
    priceSub: 'one-time',
    tag: 'Standard Fix',
    tagline: 'High ROI. A fraction of what a billing advocate charges for the same result.',
    keepNote: 'You keep ≥ $21',
  },
  {
    range: '$501 – $1,500',
    price: '$129.99',
    priceSub: 'one-time',
    tag: 'Major Fix',
    tagline: 'Material savings on a four-figure error. Pays for itself many times over.',
    keepNote: 'You keep ≥ $371',
  },
  {
    range: '$1,500+',
    price: '$199.99',
    priceSub: 'one-time',
    tag: 'Heavy Hitter',
    tagline: 'Significant financial impact. Worth every cent on a four-figure correction.',
    keepNote: 'You keep ≥ $1,300',
  },
] as const;

export const HOW_STEPS = [
  {
    num: '1',
    title: 'We analyze your bill first',
    body: 'Upload your medical bill or EOB. Our AI runs a deep audit across every line item to find errors and overcharges. No payment required.',
  },
  {
    num: '2',
    title: 'We calculate potential savings',
    body: 'If errors are found, we calculate the total dollar value of what you could recover and assign your tier automatically.',
  },
  {
    num: '3',
    title: 'You pay only if we found errors',
    body: 'If savings ≥ $21, you pay the one-time tier fee and unlock your full error report + ready-to-send dispute letter. Clean bills cost nothing.',
  },
] as const;

export const FAQS = [
  {
    q: 'What if the analysis finds no errors?',
    a: "If savings found are $20 or under, you pay nothing. You'll receive a confirmation that your bill looks clean. No credit card ever charged.",
  },
  {
    q: 'How is my tier determined?',
    a: 'Your tier is set automatically based on the total dollar value of errors found in your bill. You see the tier and fee before any payment is taken. No surprise charges.',
  },
  {
    q: 'When am I charged?',
    a: "After the analysis completes and savings are found, you'll see your tier and fee. You choose to pay or walk away. No hidden auto-charges.",
  },
  {
    q: 'What do I get in a paid tier?',
    a: 'Every paid tier includes a full itemized error report, plain-English explanations of each finding, and a ready-to-send dispute letter tailored to your bill.',
  },
  {
    q: 'How does this compare to a billing advocate?',
    a: 'Medical billing advocates typically charge 25–35% of recovered savings. On a $500 correction that would cost $125–$175. We charge a flat $79.99 for the same outcome at far less cost. On a $1,500 correction (advocate fee $375–$525) we charge $199.99.',
  },
  {
    q: 'Do you use my bill to train AI models?',
    a: "No. We do not use your bill, your personal information, or any data you upload to train AI models, ours or anyone else's. We do not sell, license, or share your data with advertisers, data brokers, or third parties for marketing. Your bill is used only to produce your audit report and dispute letter.",
  },
  {
    q: 'Is my bill data kept private?',
    a: 'Yes. Uploads are encrypted in transit and at rest. We retain your bill only as long as your account is active; you can delete it at any time. We never sell or share your data, and we are HIPAA-compliant in our handling of protected health information.',
  },
] as const;
