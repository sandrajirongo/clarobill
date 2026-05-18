import { NextResponse } from 'next/server';

const BASE = 'https://www.clarobill.com';

const ARTICLES = [
  {
    slug: 'no-surprises-act',
    title: 'The No Surprises Act: What It Covers, What It Does Not, and How to Use It',
    description: 'The No Surprises Act bans most surprise bills from out-of-network providers. Here is exactly what it covers, what the exceptions are, and what to do if you receive a bill it prohibits.',
    date: 'Sun, 18 May 2026 00:00:00 GMT',
  },
  {
    slug: 'what-happens-after-you-dispute-a-medical-bill',
    title: 'What Happens After You Send a Medical Bill Dispute Letter',
    description: 'You sent the letter. Here is what the hospital does next, how long it takes, what responses to expect, and exactly what to do if they deny your dispute.',
    date: 'Sat, 17 May 2026 00:00:00 GMT',
  },
  {
    slug: 'why-bill-exceeds-insurer-negotiated-rate',
    title: 'Why Your Bill Is Higher Than What Your Insurer Pays',
    description: 'Chargemaster rates, negotiated rates, and Medicare rates. Understanding the gap between what hospitals charge and what they accept is the first step to disputing it.',
    date: 'Wed, 07 May 2026 00:00:00 GMT',
  },
  {
    slug: 'hospital-machine-readable-files-explained',
    title: 'Hospital Machine-Readable Files: What They Are and How to Use Them',
    description: 'Every US hospital is required by federal law to publish its negotiated rates. Here is how to find that file, read it, and use the numbers to dispute an overcharge.',
    date: 'Wed, 07 May 2026 00:00:00 GMT',
  },
  {
    slug: 'ncci-edits-explained-for-patients',
    title: 'NCCI Edits: The Federal Rules That Prevent Billing Abuse',
    description: 'The National Correct Coding Initiative defines which CPT codes can and cannot be billed together. Here is what that means for your bill and how to use it in a dispute.',
    date: 'Wed, 07 May 2026 00:00:00 GMT',
  },
  {
    slug: 'how-to-dispute-a-hospital-bill',
    title: 'How to Dispute a Hospital Bill: A Step-by-Step Guide',
    description: 'A practical guide to disputing hospital billing errors. From requesting your itemized bill to writing a dispute letter that actually gets results.',
    date: 'Thu, 17 Apr 2026 00:00:00 GMT',
  },
  {
    slug: 'medical-billing-advocates',
    title: 'Medical Billing Advocates: What They Do, What They Charge, and Whether You Need One',
    description: 'Advocates can recover real money from billing errors. But they typically keep 25-35% of what they save you. Here is when hiring one makes sense.',
    date: 'Thu, 17 Apr 2026 00:00:00 GMT',
  },
  {
    slug: 'how-to-read-an-itemized-medical-bill',
    title: 'How to Read an Itemized Medical Bill',
    description: 'What the columns, codes, and dollar amounts actually mean. Plus how to spot the line items that should not be there.',
    date: 'Tue, 07 Apr 2026 00:00:00 GMT',
  },
  {
    slug: 'common-medical-billing-errors',
    title: 'The Most Common Medical Billing Errors (And How to Dispute Them)',
    description: 'Duplicate charges, upcoded visits, unbundled procedures. Here is what each one looks like on a real bill and what to say when you dispute it.',
    date: 'Tue, 07 Apr 2026 00:00:00 GMT',
  },
  {
    slug: 'what-are-cpt-codes',
    title: "What Are CPT Codes? A Patient's Guide",
    description: 'The five-digit numbers on your bill determine what you pay. Here is how they work, why they get abused, and how to check whether yours are right.',
    date: 'Tue, 07 Apr 2026 00:00:00 GMT',
  },
];

function escape(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

export function GET(): NextResponse {
  const items = ARTICLES.map(
    ({ slug, title, description, date }) => `
    <item>
      <title>${escape(title)}</title>
      <link>${BASE}/learn/${slug}</link>
      <guid isPermaLink="true">${BASE}/learn/${slug}</guid>
      <description>${escape(description)}</description>
      <pubDate>${date}</pubDate>
    </item>`,
  ).join('');

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>ClaroBill Medical Billing Guides</title>
    <link>${BASE}/learn</link>
    <description>Plain-English guides on reading medical bills, understanding your rights, disputing charges, and finding billing errors.</description>
    <language>en-us</language>
    <atom:link href="${BASE}/learn/feed.xml" rel="self" type="application/rss+xml"/>
    <lastBuildDate>${ARTICLES[0]?.date ?? ''}</lastBuildDate>${items}
  </channel>
</rss>`;

  return new NextResponse(xml, {
    headers: {
      'Content-Type': 'application/rss+xml; charset=utf-8',
      'Cache-Control': 'public, max-age=3600, s-maxage=3600',
    },
  });
}
