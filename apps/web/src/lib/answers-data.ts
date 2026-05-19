export interface Section {
  h2: string;
  paragraphs: string[];
  list?: { type: 'ul' | 'ol'; items: string[] };
  paragraphsAfter?: string[];
}

export interface AnswerPage {
  slug: string;
  metaTitle: string;
  h1: string;
  description: string;
  date: string;
  readTime: string;
  lead: string;
  sections: Section[];
  faqs: { q: string; a: string }[];
  sources: { label: string; url: string }[];
  related: { label: string; href: string }[];
}

export const ANSWERS: AnswerPage[] = [
  {
    slug: 'how-do-i-find-errors-in-my-medical-bill',
    metaTitle: 'How Do I Find Errors in My Medical Bill? | ClaroBill',
    h1: 'How Do I Find Errors in My Medical Bill?',
    description:
      'Medical billing errors appear in up to 80% of hospital bills. Learn how to request an itemized bill, spot common mistakes, and correct overcharges before you pay.',
    date: '2026-05-18',
    readTime: '7 min read',
    lead:
      'Studies and audits have found billing errors in as many as 80% of hospital bills. Most errors go uncorrected because patients never request an itemized statement or do not know what to look for. You have the right to a complete, itemized bill under federal law, and correcting errors before you pay can save hundreds or thousands of dollars.',
    sections: [
      {
        h2: 'Start with an itemized bill',
        paragraphs: [
          'A summary bill shows totals by category. An itemized bill lists every individual charge: each procedure, supply, room night, and medication with its code and unit price. Always ask for the itemized version. Hospitals are required to provide it upon request.',
          'Call the billing department and ask specifically for the "itemized statement" or "itemized bill." Get it in writing, not just verbally. If the hospital charges a fee for printing, ask them to waive it or send it by email.',
        ],
      },
      {
        h2: 'Compare the bill against your Explanation of Benefits',
        paragraphs: [
          'Your insurer sends an Explanation of Benefits (EOB) after processing a claim. The EOB lists every service billed, what the insurer paid, and what you owe. Lay the EOB next to your itemized bill and compare them line by line.',
          'Look for services on the hospital bill that do not appear on your EOB. A service not covered by insurance is not necessarily something you must pay. It could be an unbundled charge, a duplicate, or a service that was never performed.',
        ],
      },
      {
        h2: 'Common billing errors to look for',
        paragraphs: [
          'Duplicate charges are the most common error: the same service billed more than once under slightly different descriptions or codes. Upcoding happens when a provider bills a more expensive code than the service actually performed. Unbundling occurs when a single procedure is split into multiple codes to increase the total charge.',
          'Other errors include charges for services never received, operating room time that does not match surgical records, and medications billed at retail price rather than the lower wholesale cost hospitals actually pay.',
        ],
        list: {
          type: 'ul',
          items: [
            'Duplicate line items for the same service or supply',
            'Upcoded procedure or room codes (e.g., intensive care when standard care was given)',
            'Unbundled charges for procedures that should be billed together at a lower rate',
            'Services marked as performed on dates you were not at the facility',
            'Medications listed at quantities higher than dispensed',
            'Operating room time that exceeds the actual procedure duration',
          ],
        },
      },
      {
        h2: 'Check CPT and diagnosis codes',
        paragraphs: [
          'Every procedure on your bill has a five-digit Current Procedural Terminology (CPT) code. You can look up any CPT code at the American Medical Association website or on the CMS fee schedule to see what it represents. Verify that each code matches the service you actually received.',
          'Diagnosis codes (ICD-10 codes) also matter. If a code is incorrectly assigned, your insurer may deny coverage for a service that should be covered, or you could be flagged for a pre-existing condition you do not have.',
        ],
      },
      {
        h2: 'What to do when you find an error',
        paragraphs: [
          'Document every error in writing. Note the line item, the code, the amount, and the reason you believe it is incorrect. Contact the hospital billing department first. Many errors are corrected at this stage without a formal dispute.',
          'If the billing department does not resolve the error within 30 days, file a dispute in writing with both the hospital and your insurer. Keep copies of everything. Under the No Surprises Act (effective January 1, 2022), you have specific rights to dispute bills from out-of-network providers for emergency services.',
        ],
      },
    ],
    faqs: [
      {
        q: 'Can I request an itemized bill even after I have already paid?',
        a: 'Yes. You can request an itemized bill at any time. If you find an error after paying, you can still file a dispute and request a refund. Hospitals are required to provide itemized bills upon request regardless of payment status.',
      },
      {
        q: 'How long does a hospital have to correct a billing error?',
        a: 'There is no federal deadline for hospitals to correct billing errors, but most billing disputes are resolved within 30 to 60 days. If you are not getting a response, escalate in writing and contact your state insurance commissioner.',
      },
      {
        q: 'What percentage of medical bills contain errors?',
        a: 'Estimates range from 49% to 80%, depending on the study and the type of bill. A 2021 audit of Medicare claims found improper payments totaling $25.1 billion in a single year, most of which were billing errors rather than fraud.',
      },
      {
        q: 'Do I need to hire a medical billing advocate to find errors?',
        a: 'No, but it helps for complex or large bills. Advocates typically charge 25% to 35% of the amount they recover. For bills under $1,000, a careful review using your EOB and itemized statement is usually sufficient.',
      },
    ],
    sources: [
      {
        label: 'CMS Improper Payment Report 2021',
        url: 'https://www.cms.gov/files/document/2021-medicare-fee-service-supplemental-improper-payment-data.pdf',
      },
      {
        label: 'No Surprises Act Overview, CMS',
        url: 'https://www.cms.gov/nosurprises',
      },
      {
        label: 'CFPB Medical Debt Report 2022',
        url: 'https://www.consumerfinance.gov/data-research/research-reports/medical-debt-burden-in-the-united-states/',
      },
    ],
    related: [
      { label: 'Common Medical Billing Errors', href: '/learn/common-medical-billing-errors' },
      { label: 'What Are CPT Codes?', href: '/learn/what-are-cpt-codes' },
      { label: 'How to Read an Itemized Medical Bill', href: '/learn/how-to-read-an-itemized-medical-bill' },
      { label: 'How to Dispute a Hospital Bill', href: '/learn/how-to-dispute-a-hospital-bill' },
    ],
  },

  {
    slug: 'how-do-i-dispute-a-medical-bill',
    metaTitle: 'How Do I Dispute a Medical Bill? | ClaroBill',
    h1: 'How Do I Dispute a Medical Bill?',
    description:
      'Learn the exact steps to dispute a medical bill, including how to write a dispute letter, what documentation to gather, and how to escalate if the hospital does not respond.',
    date: '2026-05-18',
    readTime: '8 min read',
    lead:
      'Disputing a medical bill is a formal process with defined steps. Success depends on documentation, written communication, and knowing which laws protect you. Patients who dispute bills in writing recover money far more often than those who only call to complain.',
    sections: [
      {
        h2: 'Step 1: Gather your documentation',
        paragraphs: [
          'Before contacting anyone, collect three documents: the itemized bill from the hospital, the Explanation of Benefits (EOB) from your insurer, and any medical records or discharge summary relevant to the disputed services.',
          'Compare the itemized bill to the EOB line by line. Write down every discrepancy. Note the specific charge, the amount, the date of service, and the reason you believe the charge is incorrect. This list becomes the foundation of your dispute letter.',
        ],
      },
      {
        h2: 'Step 2: Contact the hospital billing department first',
        paragraphs: [
          'Call the billing department and ask them to review the specific charges you identified. Have your account number ready. Ask for the name and direct contact information of the person handling your account.',
          'Many errors are corrected at this stage. Hospitals make data entry mistakes, and billing staff can often remove a duplicate charge or correct a code without a formal dispute. Ask for written confirmation of any correction.',
        ],
      },
      {
        h2: 'Step 3: Send a written dispute letter',
        paragraphs: [
          'If the phone call does not resolve the issue within 10 to 14 days, send a dispute letter by certified mail with return receipt. The letter should state: your account number, each disputed charge with its code and dollar amount, the reason each charge is incorrect, and the specific correction you are requesting.',
          'Do not pay the disputed amount while the dispute is active. Write "amount in dispute" on any partial payment you make. Keep a copy of the letter and the certified mail receipt.',
        ],
      },
      {
        h2: 'Step 4: Escalate to your insurer and regulators',
        paragraphs: [
          'Send a copy of your dispute letter to your health insurer at the same time. If the bill involves services that should be covered, file a claim appeal with your insurer. Under the Affordable Care Act, you have the right to an internal appeal and then an independent external review.',
          'If neither the hospital nor the insurer resolves the dispute, file a complaint with your state insurance commissioner. The CFPB also accepts complaints about medical billing. For billing from federally qualified health centers, you can escalate to the HHS Office of the Inspector General.',
        ],
      },
      {
        h2: 'Your rights during a dispute',
        paragraphs: [
          'Under the No Surprises Act, hospitals and providers must give you a good faith cost estimate before scheduled procedures. If the final bill exceeds that estimate by more than $400, you have the right to dispute it through the federal patient-provider dispute resolution process.',
          'Disputes do not automatically pause collections. If you receive a collections notice while a dispute is active, send a written debt validation request within 30 days. Under the Fair Debt Collection Practices Act, collectors must cease collection activity until they validate the debt.',
        ],
      },
    ],
    faqs: [
      {
        q: 'How long do I have to dispute a medical bill?',
        a: 'There is no single federal deadline, but most hospitals and insurers require disputes within 90 to 180 days of the bill date. Check your EOB and the bill itself for specific deadlines. For insurance appeals, the ACA requires insurers to allow at least 180 days from the denial date.',
      },
      {
        q: 'Can a hospital send my bill to collections while I am disputing it?',
        a: 'Technically yes, but under the CFPB rules that took effect in July 2022, medical debt under $500 cannot appear on credit reports. Debts over $500 that are paid cannot appear on credit reports. A written dispute letter creates a paper trail that can support your position if a collector contacts you.',
      },
      {
        q: 'What if the hospital refuses to correct a clear error?',
        a: 'Escalate to your state insurance commissioner, file a complaint with the CFPB at consumerfinance.gov/complaint, and contact your state attorney general if the hospital is not for-profit. For Medicare or Medicaid billing errors, file a complaint with CMS.',
      },
      {
        q: 'Should I hire a lawyer to dispute a medical bill?',
        a: 'For most disputes under $5,000, a lawyer is not cost-effective. A medical billing advocate can be more practical. For larger amounts or if the hospital threatens legal action, consult an attorney who specializes in consumer debt or healthcare billing.',
      },
    ],
    sources: [
      {
        label: 'Patient Rights Under the No Surprises Act, CMS',
        url: 'https://www.cms.gov/nosurprises/consumers',
      },
      {
        label: 'Filing a Health Insurance Appeal, HHS',
        url: 'https://www.hhs.gov/healthcare/about-the-aca/index.html',
      },
      {
        label: 'CFPB Medical Billing Complaint Process',
        url: 'https://www.consumerfinance.gov/complaint/',
      },
      {
        label: 'Fair Debt Collection Practices Act, FTC',
        url: 'https://www.ftc.gov/legal-library/browse/rules/fair-debt-collection-practices-act-text',
      },
    ],
    related: [
      { label: 'How to Dispute a Hospital Bill', href: '/learn/how-to-dispute-a-hospital-bill' },
      { label: 'What Happens After You Dispute a Medical Bill', href: '/learn/what-happens-after-you-dispute-a-medical-bill' },
      { label: 'Common Medical Billing Errors', href: '/learn/common-medical-billing-errors' },
      { label: 'No Surprises Act', href: '/learn/no-surprises-act' },
    ],
  },

  {
    slug: 'what-is-an-itemized-medical-bill',
    metaTitle: 'What Is an Itemized Medical Bill? | ClaroBill',
    h1: 'What Is an Itemized Medical Bill?',
    description:
      'An itemized medical bill lists every charge individually with procedure codes and prices. Learn why you should always request one and how to read it.',
    date: '2026-05-18',
    readTime: '6 min read',
    lead:
      'An itemized medical bill is a line-by-line record of every charge on your hospital or provider account. It includes the specific service performed, the date, the corresponding billing code, the quantity, and the unit price. A summary bill shows only category totals. The itemized version is what you need to identify errors, negotiate, or dispute charges.',
    sections: [
      {
        h2: 'What an itemized bill contains',
        paragraphs: [
          'Each line item on an itemized bill typically includes a revenue code (a four-digit code used by hospitals), a procedure or CPT code, a description of the service, the date of service, the quantity, and the charge. For inpatient stays, you will also see daily room-and-board charges, nursing care charges, and separate charges for each medication administered.',
          'A single emergency department visit can produce 40 to 100 line items. A surgical inpatient stay can produce 200 or more. That volume is exactly why errors slip through: no one is expected to review them, so no one does.',
        ],
      },
      {
        h2: 'How an itemized bill differs from a summary bill',
        paragraphs: [
          'A summary bill groups charges into broad categories like "pharmacy," "laboratory," and "room and board." It gives you a total but hides the individual components. Hospitals typically mail summary bills by default because they are simpler and draw less scrutiny.',
          'An itemized bill breaks every charge out individually. It is the document auditors, insurers, and billing advocates use to verify that what was billed matches what was actually provided. You are entitled to it upon request at no charge in most states.',
        ],
      },
      {
        h2: 'Your right to an itemized bill',
        paragraphs: [
          'Federal law does not explicitly require hospitals to provide itemized bills, but Medicare Conditions of Participation (42 CFR Part 482) require hospitals to have a process for resolving billing disputes, which implicitly requires access to itemized records. More than 30 states have laws that explicitly require hospitals to provide itemized bills upon patient request.',
          'In practice, virtually every hospital will provide one if you ask. If a hospital refuses, cite your state law and file a complaint with the state health department. For Medicare patients, contact your Medicare Administrative Contractor.',
        ],
      },
      {
        h2: 'How to read an itemized bill',
        paragraphs: [
          'Start with the header: confirm the patient name, admission and discharge dates, and attending physician are correct. Then scan for the date column. Any charge with a date outside your admission window is immediately suspicious.',
          'Look up unfamiliar codes. Revenue codes starting with "0" are facility fees. CPT codes in the 99200-99499 range are evaluation and management visits. CPT codes in the 10000-69999 range are surgical procedures. The CMS physician fee schedule search tool at cms.gov lets you look up any CPT code and see what Medicare pays for it as a reference point.',
        ],
      },
      {
        h2: 'What to do after reviewing your itemized bill',
        paragraphs: [
          'Mark every line you cannot verify or do not recognize. Then request your medical records from the same stay and cross-reference. If a charge appears on the bill but not in the medical records, it should not be there.',
          'Compare the itemized bill against your Explanation of Benefits from your insurer. The EOB shows what your insurer was billed for each service. Discrepancies between the two documents are a strong indicator of a billing error.',
        ],
      },
    ],
    faqs: [
      {
        q: 'Is an itemized bill the same as a UB-04?',
        a: 'The UB-04 is the standardized claim form hospitals use to submit bills to insurers. It contains much of the same information as an itemized bill but is formatted for payer processing. Patients can request a copy of the UB-04, but the itemized patient bill is often more readable.',
      },
      {
        q: 'How do I request an itemized bill?',
        a: 'Call the hospital billing department and ask for your "itemized statement" or "itemized bill." Give them your account number from any bill you have received. Follow up in writing if you do not receive it within 5 to 7 business days.',
      },
      {
        q: 'Can I request an itemized bill for outpatient or clinic visits?',
        a: 'Yes. Itemized bills are available for any healthcare encounter: inpatient, outpatient, emergency, or clinic. The format varies, but all providers bill using standard codes that can be reviewed the same way.',
      },
      {
        q: 'What if the itemized bill contains codes I cannot identify?',
        a: 'Use the CMS fee schedule at cms.gov/medicare/physician-fee-schedule/search to look up any CPT code. For supply or revenue codes, the hospital billing department is required to explain each charge upon request.',
      },
    ],
    sources: [
      {
        label: 'Medicare Conditions of Participation, CMS (42 CFR Part 482)',
        url: 'https://www.ecfr.gov/current/title-42/chapter-IV/subchapter-G/part-482',
      },
      {
        label: 'CMS Physician Fee Schedule Search',
        url: 'https://www.cms.gov/medicare/physician-fee-schedule/search',
      },
      {
        label: 'KFF: Medical Bills and Debt in the United States',
        url: 'https://www.kff.org/health-costs/poll-finding/kff-health-care-debt-survey/',
      },
    ],
    related: [
      { label: 'How to Read an Itemized Medical Bill', href: '/learn/how-to-read-an-itemized-medical-bill' },
      { label: 'Common Medical Billing Errors', href: '/learn/common-medical-billing-errors' },
      { label: 'What Are CPT Codes?', href: '/learn/what-are-cpt-codes' },
    ],
  },

  {
    slug: 'can-i-negotiate-my-hospital-bill',
    metaTitle: 'Can I Negotiate My Hospital Bill? | ClaroBill',
    h1: 'Can I Negotiate My Hospital Bill?',
    description:
      'Yes, hospital bills are negotiable. Learn proven strategies to reduce your balance, including financial assistance programs, prompt-pay discounts, and lump-sum settlement offers.',
    date: '2026-05-18',
    readTime: '7 min read',
    lead:
      'Hospital bills are almost always negotiable. Hospitals routinely accept less than their chargemaster list prices, and most nonprofit hospitals are legally required to offer financial assistance programs. Knowing the right levers to pull can reduce a bill by 20% to 60% without hiring anyone.',
    sections: [
      {
        h2: 'Why hospitals negotiate',
        paragraphs: [
          'The chargemaster price is the hospital\'s starting position, not a fixed price. Insurers negotiate steep discounts: commercial insurers typically pay 30% to 60% below chargemaster rates. Uninsured and self-pay patients who do not negotiate often get billed the full chargemaster rate, which is always the highest price.',
          'Hospitals collect only a fraction of what they bill. According to CMS data, the average hospital collects roughly 28 cents for every dollar billed on the chargemaster. This means there is always room to negotiate, and hospitals expect it from uninsured and underinsured patients.',
        ],
      },
      {
        h2: 'Financial assistance programs (charity care)',
        paragraphs: [
          'All nonprofit hospitals that accept Medicare and Medicaid must have a financial assistance policy under Section 501(r) of the Internal Revenue Code. These programs can reduce or eliminate bills entirely for patients who qualify. Income thresholds vary, but many hospitals extend assistance to patients earning up to 400% of the federal poverty level.',
          'To apply, ask the billing department for a "financial assistance application" or "charity care application." You will typically need to provide proof of income (tax returns, pay stubs) and proof of household size. Apply before the bill goes to collections.',
        ],
      },
      {
        h2: 'Prompt-pay and lump-sum discounts',
        paragraphs: [
          'Many hospitals offer a prompt-pay discount of 10% to 30% if you pay the balance in full within a short window, often 30 days. Always ask for this explicitly: "Do you have a prompt-pay discount if I pay the full balance today?"',
          'For larger bills, a lump-sum settlement below the full balance is common. Offer 40% to 60% of the total as a one-time payment. Hospitals often accept this rather than pursue collections. Get any agreed reduction in writing before you pay.',
        ],
      },
      {
        h2: 'Benchmarking against published rates',
        paragraphs: [
          'Under the Hospital Price Transparency Rule (effective January 1, 2021), all hospitals must publish a machine-readable file listing their prices for at least 300 services. You can compare what the hospital charges other payers for the same service and use that data in negotiations.',
          'If the hospital charges your insurer $800 for a service but bills you $3,200 as a self-pay patient, that gap is your negotiating leverage. Reference the hospital\'s own published rates and ask to be charged the negotiated or self-pay rate rather than the chargemaster rate.',
        ],
      },
      {
        h2: 'Payment plans and interest',
        paragraphs: [
          'If you cannot pay in a lump sum, ask for a no-interest payment plan. Most hospitals offer these, and nonprofit hospitals are generally prohibited from charging interest on financial assistance plans. A written payment agreement stops collections activity while you pay.',
          'Avoid using a credit card to pay a medical bill before negotiating. Once you pay by credit card, you lose all negotiating leverage and may pay interest on top of a bill that could have been reduced.',
        ],
      },
    ],
    faqs: [
      {
        q: 'Can I negotiate after my bill has gone to collections?',
        a: 'Yes. Debt collectors typically purchase medical debt for 3 to 7 cents on the dollar, so they have room to settle for 20% to 50% of the face value. Get any settlement agreement in writing before you pay.',
      },
      {
        q: 'What is the best way to start a negotiation?',
        a: 'Call the billing department and ask two questions: "Do you have a financial assistance program?" and "What is your self-pay or prompt-pay discount?" The answers tell you the floor you are negotiating toward.',
      },
      {
        q: 'Does negotiating a medical bill affect my credit?',
        a: 'Medical debt under $500 was removed from credit reports in 2023 under CFPB rules. Paid medical debt of any amount cannot appear on credit reports. Negotiating does not itself affect your credit score.',
      },
      {
        q: 'Can I negotiate a bill that my insurance already processed?',
        a: 'You can negotiate your portion, the amount your insurer determined you owe after applying your benefits. This includes your deductible, copay, and any amounts your insurer deemed your responsibility. Financial assistance programs can also cover these patient-responsibility amounts.',
      },
    ],
    sources: [
      {
        label: 'Hospital Price Transparency Rule, CMS',
        url: 'https://www.cms.gov/hospital-price-transparency',
      },
      {
        label: 'IRS Section 501(r) Financial Assistance Requirements',
        url: 'https://www.irs.gov/charities-non-profits/charitable-organizations/financial-assistance-policy-and-emergency-medical-care-policy',
      },
      {
        label: 'KFF: Uninsured and Self-Pay Billing Practices',
        url: 'https://www.kff.org/uninsured/issue-brief/the-uninsured-and-the-aca-a-primer/',
      },
    ],
    related: [
      { label: 'How to Dispute a Hospital Bill', href: '/learn/how-to-dispute-a-hospital-bill' },
      { label: 'Why Your Bill Exceeds the Insurer Negotiated Rate', href: '/learn/why-bill-exceeds-insurer-negotiated-rate' },
      { label: 'Common Medical Billing Errors', href: '/learn/common-medical-billing-errors' },
    ],
  },

  {
    slug: 'what-is-balance-billing',
    metaTitle: 'What Is Balance Billing? | ClaroBill',
    h1: 'What Is Balance Billing?',
    description:
      'Balance billing is when an out-of-network provider charges you the difference between their fee and what your insurer paid. Federal law now bans it in many situations.',
    date: '2026-05-18',
    readTime: '6 min read',
    lead:
      'Balance billing happens when an out-of-network provider bills you for the gap between their charge and what your insurer pays. For example, if a provider charges $2,000, your insurer pays $800, and the provider bills you the remaining $1,200, that is a balance bill. The No Surprises Act, effective January 1, 2022, bans this practice in most emergency situations and for certain non-emergency services.',
    sections: [
      {
        h2: 'How balance billing works',
        paragraphs: [
          'In-network providers have contracts with your insurer. Those contracts set a negotiated rate and require the provider to accept it as payment in full. Out-of-network providers have no such contract. They can charge any amount and then bill you for whatever your insurer does not cover.',
          'Before the No Surprises Act, balance billing was common in emergency situations where patients had no choice of provider. Patients would go to an in-network hospital but be treated by an out-of-network physician, such as an anesthesiologist or radiologist, without their knowledge.',
        ],
      },
      {
        h2: 'What the No Surprises Act prohibits',
        paragraphs: [
          'Effective January 1, 2022, the No Surprises Act (part of the Consolidated Appropriations Act, 2021) bans balance billing in three main scenarios. First, for emergency services at any hospital or free-standing emergency department, regardless of whether the facility is in-network. Second, for non-emergency services at in-network facilities when you did not receive adequate notice that a provider was out-of-network. Third, for air ambulance services from providers that are not in your insurer\'s network.',
          'Under these protections, providers can only charge you your in-network cost-sharing amount, meaning your deductible, copay, or coinsurance as calculated against your in-network benefit.',
        ],
      },
      {
        h2: 'When balance billing is still allowed',
        paragraphs: [
          'The No Surprises Act does not cover all situations. Out-of-network providers for non-emergency services can still balance bill you if they give you advance written notice and you sign a consent form at least 72 hours before the service. You must also be given a good faith cost estimate at that time.',
          'Ground ambulance services are not covered by the No Surprises Act. Congress directed an advisory committee to study ground ambulance billing, but federal protections have not yet been enacted as of 2026. Some states have their own ground ambulance balance billing protections.',
        ],
      },
      {
        h2: 'What to do if you receive a balance bill',
        paragraphs: [
          'First, determine if the service falls under No Surprises Act protections. If it does, the provider cannot legally collect the balance from you. Contact your insurer and report the balance bill. Insurers are required to handle disputes with out-of-network providers through an independent dispute resolution (IDR) process.',
          'File a complaint with the No Surprises Help Desk at 1-800-985-3059 or at cms.gov/nosurprises. CMS has authority to investigate violations and assess civil money penalties of up to $10,000 per violation.',
        ],
      },
      {
        h2: 'State balance billing protections',
        paragraphs: [
          'Many states had balance billing protections before the federal law. States like California, New York, Texas, and Illinois have comprehensive laws that may provide additional protections beyond the No Surprises Act. Some states cover ground ambulances and other services not included in the federal law.',
          'Check your state insurance commissioner\'s website for state-specific protections. When state law is more protective than federal law, the state law applies.',
        ],
      },
    ],
    faqs: [
      {
        q: 'Is balance billing the same as a surprise bill?',
        a: 'Yes, the terms are often used interchangeably. A surprise bill is a balance bill you did not expect, typically from an out-of-network provider at an in-network facility. The No Surprises Act targets exactly this scenario.',
      },
      {
        q: 'Can I be balance billed by an air ambulance?',
        a: 'No. The No Surprises Act explicitly covers air ambulance services from non-network providers. You can only be charged your in-network cost-sharing amount for air ambulance transport, and you have the right to dispute bills that exceed that.',
      },
      {
        q: 'What is the independent dispute resolution (IDR) process?',
        a: 'When providers and insurers cannot agree on an out-of-network payment amount, they can submit to a federal IDR process administered by certified arbitrators. The patient is not involved in this process and pays only the in-network cost-sharing amount regardless of the IDR outcome.',
      },
      {
        q: 'Does the No Surprises Act apply to self-pay patients?',
        a: 'Partially. Self-pay patients are protected by the good faith cost estimate requirements: providers must give written estimates for scheduled services at least one business day in advance. Patients can dispute bills that exceed the estimate by more than $400 through the patient-provider dispute resolution process.',
      },
    ],
    sources: [
      {
        label: 'No Surprises Act, CMS',
        url: 'https://www.cms.gov/nosurprises',
      },
      {
        label: 'Consolidated Appropriations Act 2021, Congress.gov',
        url: 'https://www.congress.gov/bill/116th-congress/house-bill/133/text',
      },
      {
        label: 'KFF: Balance Billing Overview',
        url: 'https://www.kff.org/private-insurance/issue-brief/surprise-medical-bills-new-protections-for-consumers-take-effect-in-2022/',
      },
    ],
    related: [
      { label: 'No Surprises Act', href: '/learn/no-surprises-act' },
      { label: 'What Is Out-of-Network Billing', href: '/learn/why-bill-exceeds-insurer-negotiated-rate' },
      { label: 'How to Dispute a Hospital Bill', href: '/learn/how-to-dispute-a-hospital-bill' },
    ],
  },

  {
    slug: 'how-long-do-i-have-to-pay-a-medical-bill',
    metaTitle: 'How Long Do I Have to Pay a Medical Bill? | ClaroBill',
    h1: 'How Long Do I Have to Pay a Medical Bill?',
    description:
      'There is no universal deadline to pay a medical bill, but providers can send unpaid bills to collections after 60 to 180 days. Learn your timeline and your rights.',
    date: '2026-05-18',
    readTime: '5 min read',
    lead:
      'There is no single federal law that sets a deadline for paying a medical bill. Providers set their own policies, but most will send an unpaid balance to a collections agency after 90 to 180 days. Understanding the timeline helps you prioritize, dispute errors, and apply for assistance before the bill escalates.',
    sections: [
      {
        h2: 'Typical billing timelines',
        paragraphs: [
          'Most hospitals send an initial bill within 30 to 45 days of your visit or discharge. They typically send a second notice after 30 days and a final notice before referring the account to collections. The total window from initial bill to collections referral is usually 90 to 180 days, but some providers act faster.',
          'Your insurer adds time to this process. A claim can take 30 to 90 days to process, especially if it requires coordination of benefits or a prior authorization review. Do not pay a hospital bill before your insurer has processed the claim.',
        ],
      },
      {
        h2: 'Collections and your credit report',
        paragraphs: [
          'In 2022 and 2023, the three major credit bureaus (Equifax, Experian, TransUnion) and the CFPB made significant changes to medical debt reporting. As of 2023, paid medical collection accounts cannot appear on credit reports. Medical debts under $500 in collections cannot appear on credit reports. Medical debts over $500 now have a one-year grace period before they can be reported, giving you more time to resolve them.',
          'In January 2025, the CFPB finalized a rule that would ban medical debt from credit reports entirely. That rule is currently in litigation as of May 2026, so its status may change.',
        ],
      },
      {
        h2: 'Statutes of limitations on medical debt',
        paragraphs: [
          'Every state has a statute of limitations on debt collection. This is the window during which a creditor can sue you to collect. For medical debt, statutes of limitations typically range from 3 to 10 years depending on the state and the type of contract.',
          'After the statute of limitations expires, the debt still exists but collectors cannot sue you to collect it. The debt can still be reported on your credit report within the FCRA\'s 7-year window, which runs from the date of first delinquency, not the statute of limitations.',
        ],
      },
      {
        h2: 'When to delay payment intentionally',
        paragraphs: [
          'Paying quickly before reviewing your bill for errors is a common and costly mistake. Take time to request the itemized bill, compare it to your EOB, and apply for financial assistance if applicable. Most hospitals will not send a bill to collections without multiple notices over at least 90 days.',
          'If you are applying for financial assistance, tell the billing department. Applications pause collections activity at most hospitals while they review your eligibility.',
        ],
      },
      {
        h2: 'How to protect yourself from collections',
        paragraphs: [
          'If you cannot pay the full balance, set up a payment plan in writing. A signed payment plan agreement typically prevents the account from being referred to collections as long as you make payments. Ask explicitly whether a payment arrangement will stop the collections referral.',
          'If the bill does go to collections, you have 30 days to request written debt validation under the Fair Debt Collection Practices Act. The collector must provide verification of the debt and pause collection efforts until they do.',
        ],
      },
    ],
    faqs: [
      {
        q: 'What happens to medical debt after 7 years?',
        a: 'Medical debt can only appear on your credit report for 7 years from the date of first delinquency under the Fair Credit Reporting Act. After 7 years, it falls off your report automatically. The underlying debt may still be legally collectible depending on your state\'s statute of limitations.',
      },
      {
        q: 'Can a hospital garnish my wages for an unpaid medical bill?',
        a: 'Yes, if the hospital sues you and wins a court judgment. However, hospitals rarely sue patients for small balances. Many states exempt certain amounts of wages or income from garnishment. Nonprofit hospitals that receive federal funding have restrictions on using aggressive collection practices against patients who qualify for financial assistance.',
      },
      {
        q: 'Does a payment plan affect my credit score?',
        a: 'A payment plan does not directly help your credit score, but it prevents the account from going to collections, which would be much worse. Some hospital payment plans are not reported to credit bureaus at all.',
      },
      {
        q: 'What if I am waiting for my insurer to process the claim?',
        a: 'Tell the billing department that the claim is pending with your insurer. Most billing departments will hold collection activity while a claim is being processed. Do not pay the hospital bill before your insurer has paid their portion.',
      },
    ],
    sources: [
      {
        label: 'CFPB Medical Debt Credit Reporting Rule 2025',
        url: 'https://www.consumerfinance.gov/rules-policy/final-rules/prohibition-on-creditors-and-consumer-reporting-agencies-concerning-medical-information/',
      },
      {
        label: 'Fair Credit Reporting Act, FTC',
        url: 'https://www.ftc.gov/legal-library/browse/statutes/fair-credit-reporting-act',
      },
      {
        label: 'KFF: Medical Debt in the United States',
        url: 'https://www.kff.org/health-costs/issue-brief/the-burden-of-medical-debt-in-the-united-states/',
      },
    ],
    related: [
      { label: 'How to Dispute a Hospital Bill', href: '/learn/how-to-dispute-a-hospital-bill' },
      { label: 'How to Get Hospital Financial Assistance', href: '/learn/how-to-dispute-a-hospital-bill' },
      { label: 'Common Medical Billing Errors', href: '/learn/common-medical-billing-errors' },
    ],
  },

  {
    slug: 'what-happens-if-i-dont-pay-a-medical-bill',
    metaTitle: "What Happens If I Don't Pay a Medical Bill? | ClaroBill",
    h1: "What Happens If I Don't Pay a Medical Bill?",
    description:
      'Unpaid medical bills can go to collections, affect your credit, and result in lawsuits. Learn the timeline, your rights, and how to protect yourself.',
    date: '2026-05-18',
    readTime: '6 min read',
    lead:
      'Not paying a medical bill sets off a predictable sequence of events: collection calls, credit reporting, potential lawsuits, and in extreme cases, wage garnishment. But your rights have grown significantly in recent years. New CFPB rules and state laws limit how medical debt can be collected and reported, giving you more time and options than you may realize.',
    sections: [
      {
        h2: 'Stage 1: Internal collections and reminder notices',
        paragraphs: [
          'Most hospitals have an internal billing team that handles overdue accounts for the first 90 to 180 days. During this period, you will receive reminder statements, phone calls, and final notices. This is the best time to negotiate, apply for financial assistance, or set up a payment plan.',
          'Nonprofit hospitals under IRS Section 501(r) are prohibited from engaging in "extraordinary collection actions" before making reasonable efforts to determine whether a patient qualifies for financial assistance. These prohibited actions include reporting to credit bureaus, filing lawsuits, and wage garnishment.',
        ],
      },
      {
        h2: 'Stage 2: Third-party collections',
        paragraphs: [
          'If the billing department cannot collect, the account is typically sold or referred to a third-party collections agency. Collectors may purchase the debt for 3 to 7 cents on the dollar. Once in collections, the debt can be harder to dispute, but your legal rights under the Fair Debt Collection Practices Act (FDCPA) become active.',
          'Under the FDCPA, collectors cannot call before 8 a.m. or after 9 p.m., cannot use abusive language, and must stop contacting you if you send a written cease-and-desist letter. You also have the right to request written debt validation within 30 days of first contact.',
        ],
      },
      {
        h2: 'Stage 3: Credit reporting',
        paragraphs: [
          'Medical debt affects credit differently than other debt. As of 2023, the three major credit bureaus removed all paid medical collections from credit reports and all medical collections under $500. Medical debts over $500 now have a one-year grace period before they can be reported.',
          'A CFPB rule finalized in January 2025 would ban all medical debt from credit reports entirely, but that rule is in litigation as of May 2026. Check the CFPB website for current status.',
        ],
      },
      {
        h2: 'Stage 4: Lawsuits and judgments',
        paragraphs: [
          'Providers and collectors can sue you for unpaid medical debt if the amount warrants it and the statute of limitations has not expired. If they win a judgment, they can garnish wages (up to 25% of disposable earnings under federal law, or less under state law), levy bank accounts, or place a lien on real property.',
          'Suing patients is costly and time-consuming. Most lawsuits are filed for balances over $1,000 to $2,000. If you have received a summons, respond to it. Ignoring a lawsuit results in a default judgment against you, which is worse than negotiating.',
        ],
      },
      {
        h2: 'Alternatives that prevent escalation',
        paragraphs: [
          'Apply for financial assistance before the bill escalates. Nonprofit hospitals must have these programs, and many for-profit systems do too. Income thresholds are often higher than people expect: many programs cover patients earning up to 400% of the federal poverty level.',
          'Set up a payment plan in writing. File a dispute if you believe any charges are incorrect. Contact your state insurance commissioner if the bill involves insurance coverage disputes. Many states have patient advocates or ombudsman offices that can intervene.',
        ],
      },
    ],
    faqs: [
      {
        q: 'Can a hospital take my house if I don\'t pay a medical bill?',
        a: 'In theory, yes, if they win a lawsuit and obtain a judgment lien on real property. In practice, this is rare. Many states protect primary residences through homestead exemptions. The risk is highest for large balances left unaddressed for years.',
      },
      {
        q: 'Can I go to jail for not paying a medical bill?',
        a: 'No. Debt in the United States is civil, not criminal. You cannot be jailed for failing to pay a medical bill. However, ignoring a court summons related to a debt lawsuit can result in a contempt finding in some jurisdictions.',
      },
      {
        q: 'Can a hospital deny me future care if I have an unpaid bill?',
        a: 'Hospitals must provide emergency care regardless of ability to pay or outstanding debts under EMTALA (Emergency Medical Treatment and Labor Act). For non-emergency care, some hospitals can decline to provide elective services to patients with outstanding balances.',
      },
      {
        q: 'What is the best thing to do if I simply cannot afford to pay?',
        a: 'Apply for financial assistance or charity care at the hospital. If you do not qualify, ask about a zero-interest payment plan. If the bill is already in collections, negotiate a settlement for less than the full balance. Many collectors will accept 20% to 50% of face value as settlement.',
      },
    ],
    sources: [
      {
        label: 'FDCPA, FTC',
        url: 'https://www.ftc.gov/legal-library/browse/rules/fair-debt-collection-practices-act-text',
      },
      {
        label: 'IRS 501(r) Limitations on Extraordinary Collection Actions',
        url: 'https://www.irs.gov/charities-non-profits/charitable-organizations/limitation-on-extraordinary-collection-actions',
      },
      {
        label: 'KFF: Medical Debt and Bankruptcy',
        url: 'https://www.kff.org/health-costs/poll-finding/kff-health-care-debt-survey/',
      },
    ],
    related: [
      { label: 'How to Get Hospital Financial Assistance', href: '/learn/how-to-dispute-a-hospital-bill' },
      { label: 'How to Dispute a Hospital Bill', href: '/learn/how-to-dispute-a-hospital-bill' },
      { label: 'Common Medical Billing Errors', href: '/learn/common-medical-billing-errors' },
    ],
  },

  {
    slug: 'what-is-an-explanation-of-benefits',
    metaTitle: 'What Is an Explanation of Benefits (EOB)? | ClaroBill',
    h1: 'What Is an Explanation of Benefits?',
    description:
      'An Explanation of Benefits (EOB) is not a bill. It is your insurer\'s record of how it processed a claim. Learn how to read it and use it to spot billing errors.',
    date: '2026-05-18',
    readTime: '5 min read',
    lead:
      'An Explanation of Benefits, or EOB, is a document your health insurer sends after processing a medical claim. It is not a bill. It explains what was billed, what the insurer paid, what was adjusted or denied, and what you owe. Reading your EOB carefully is one of the most effective ways to catch billing errors before you pay.',
    sections: [
      {
        h2: 'What an EOB contains',
        paragraphs: [
          'Every EOB includes the date of service, the name of the provider, each service that was billed with its procedure code, the amount billed by the provider, any adjustments the insurer applied (such as contractual discounts), the amount the insurer paid, and the amount the insurer says you owe.',
          'The "amount billed" column reflects what the provider submitted to the insurer. The "plan paid" column shows what your insurer actually paid. The "your responsibility" column is what you legally owe under your plan, after the insurer\'s negotiated discount and your plan benefits are applied.',
        ],
      },
      {
        h2: 'How to use an EOB to find billing errors',
        paragraphs: [
          'Compare the EOB to your itemized bill from the provider. Every service on the provider\'s bill should appear on the EOB. If a service appears on the bill but not on the EOB, the provider may not have billed the insurer for it correctly, or may be attempting to bill you directly for something the insurer was supposed to cover.',
          'If the amount billed on the EOB differs from what the hospital sent you, contact both the hospital and your insurer. Providers occasionally submit incorrect codes or amounts to the insurer that differ from what they bill the patient.',
        ],
      },
      {
        h2: 'Understanding denials on your EOB',
        paragraphs: [
          'The EOB will show a reason code for each service that was denied or not paid in full. Common reasons include "service not covered under your plan," "prior authorization required," "out-of-network provider," and "duplicate claim." Each reason code corresponds to a specific problem that may or may not be correctable.',
          'A denial is not final. You have the right to appeal any denial. The EOB must include instructions for filing an internal appeal with your insurer. Under the Affordable Care Act, if your internal appeal is denied, you have the right to an independent external review.',
        ],
      },
      {
        h2: 'EOB vs. bill: what you actually owe',
        paragraphs: [
          'You should never pay an amount that exceeds what your EOB shows as your responsibility, unless you received a corrected EOB after an appeal or dispute. If the hospital is billing you more than your EOB says you owe, that is an error. Contact your insurer first.',
          'Keep every EOB. They are essential documentation if you need to dispute a bill, appeal a denial, or prove that a service was covered. Insurers are required to make EOBs available electronically, and most provide them through your online member portal within a few weeks of processing the claim.',
        ],
      },
    ],
    faqs: [
      {
        q: 'When will I receive my EOB?',
        a: 'Insurers typically send or post an EOB within 30 to 45 days after the claim is processed. Processing time varies. If you have not received an EOB within 60 days of your visit, call your insurer or check your online portal.',
      },
      {
        q: 'What should I do if my EOB shows a service I did not receive?',
        a: 'Contact your insurer immediately and report the discrepancy. Then contact the provider\'s billing department. A charge appearing on your EOB for a service you did not receive is a billing error. In some cases it is a sign of medical identity theft.',
      },
      {
        q: 'Do I get an EOB if I am on Medicaid?',
        a: 'Medicaid programs vary by state. Most state Medicaid programs provide member statements similar to an EOB, but not all. Contact your state Medicaid office to understand what claim documentation is available to you.',
      },
      {
        q: 'What is the difference between an EOB and a Medicare Summary Notice?',
        a: 'A Medicare Summary Notice (MSN) is Medicare\'s equivalent of an EOB. Original Medicare sends an MSN every three months if you had claims during that period. Medicare Advantage plans send EOBs similar to private insurer documents.',
      },
    ],
    sources: [
      {
        label: 'How to Appeal a Health Insurance Decision, HHS',
        url: 'https://www.healthcare.gov/appeal-insurance-company-decision/appeals/',
      },
      {
        label: 'Medicare Summary Notices, CMS',
        url: 'https://www.medicare.gov/claims-appeals/medicare-claims/your-medicare-summary-notice-msn',
      },
      {
        label: 'CFPB: Understanding Your Medical Bills',
        url: 'https://www.consumerfinance.gov/consumer-tools/medical-bills/',
      },
    ],
    related: [
      { label: 'How to Read an Itemized Medical Bill', href: '/learn/how-to-read-an-itemized-medical-bill' },
      { label: 'How to Dispute a Hospital Bill', href: '/learn/how-to-dispute-a-hospital-bill' },
      { label: 'Common Medical Billing Errors', href: '/learn/common-medical-billing-errors' },
    ],
  },

  {
    slug: 'how-do-i-appeal-a-health-insurance-denial',
    metaTitle: 'How Do I Appeal a Health Insurance Denial? | ClaroBill',
    h1: 'How Do I Appeal a Health Insurance Denial?',
    description:
      'You have the legal right to appeal insurance claim denials. Learn the internal and external appeal process, deadlines, and how to write an effective appeal letter.',
    date: '2026-05-18',
    readTime: '7 min read',
    lead:
      'Health insurers deny roughly 17% of in-network claims, according to KFF analysis of marketplace plan data. Most denials are never appealed. Of those that are, a significant portion are overturned. Filing an appeal is one of the highest-value actions you can take after a denial.',
    sections: [
      {
        h2: 'Why insurers deny claims',
        paragraphs: [
          'The most common denial reasons are: prior authorization not obtained or not approved, the service was deemed not medically necessary, the provider or service was out-of-network, a claim was filed incorrectly or past the deadline, or the service is excluded from your plan.',
          'The denial reason code on your Explanation of Benefits is the starting point for your appeal. Different reasons require different responses. A prior authorization denial requires different documentation than a medical necessity denial.',
        ],
      },
      {
        h2: 'The internal appeal process',
        paragraphs: [
          'An internal appeal is a formal request for your insurer to review its own decision. Under the Affordable Care Act, all non-grandfathered health plans must allow at least one internal appeal. You must file within 180 days of receiving the denial notice, though your plan may allow more time.',
          'Your appeal must be in writing and should include: the claim number, the date of service, the specific denial reason, the medical justification for the service, a letter of medical necessity from your treating physician, and any relevant clinical guidelines or research that support the treatment.',
        ],
      },
      {
        h2: 'Urgent and expedited appeals',
        paragraphs: [
          'For ongoing or urgent care, you can request an expedited internal appeal. Insurers must respond within 72 hours for expedited reviews, versus 30 to 60 days for standard reviews. Expedited appeals apply when waiting for the standard timeline would seriously jeopardize your health.',
          'You can also request expedited external review simultaneously with an expedited internal appeal in urgent situations.',
        ],
      },
      {
        h2: 'External review',
        paragraphs: [
          'If your internal appeal is denied, you have the right to an independent external review. External reviewers are certified organizations that are not affiliated with your insurer. Their decision is binding on the insurer.',
          'You have four months from the internal denial to request external review. The external reviewer must decide within 45 days (or 72 hours for expedited reviews). Under ACA rules, this right applies to most medical necessity denials and rescissions. Grandfathered plans and some self-funded employer plans may use state or alternative processes.',
        ],
      },
      {
        h2: 'Writing an effective appeal letter',
        paragraphs: [
          'The appeal letter should be precise and clinical, not emotional. State the claim number, the date of service, the service that was denied, and the specific denial reason. Then methodically rebut each ground for denial using your physician\'s letter, clinical guidelines, and any applicable coverage provisions.',
          'Reference specific policy language from your Summary of Benefits and Coverage. If your plan covers a service for condition A but the insurer denied it for condition B, show why your diagnosis qualifies under the covered condition. Get your doctor to write a detailed letter that addresses the insurer\'s specific medical necessity criteria.',
        ],
      },
    ],
    faqs: [
      {
        q: 'What percentage of insurance appeals succeed?',
        a: 'Data varies by insurer and denial type. KFF analysis found that marketplace plan enrollees won about 39% to 59% of internal appeals and a higher percentage of external reviews, depending on the insurer. The success rate is higher when appeals include physician documentation and cite specific clinical guidelines.',
      },
      {
        q: 'Can I appeal a denial after 180 days?',
        a: 'Generally no, for internal appeals. The 180-day deadline is set by ACA rules. Some plans allow more time. If you miss the deadline, ask your insurer if a late appeal will be accepted and document any extenuating circumstances. Your state insurance commissioner may have additional options.',
      },
      {
        q: 'Do I need a lawyer to appeal?',
        a: 'No. Most internal appeals and external reviews can be handled without a lawyer. For complex or high-value denials, a patient advocate or healthcare attorney can help. Many patient advocacy organizations provide free assistance.',
      },
      {
        q: 'What happens if I lose the external review?',
        a: 'After external review, your remaining option is to file a complaint with your state insurance commissioner or bring a civil lawsuit if you are in a fully-insured state plan. Self-funded employer plans are governed by federal ERISA law, which has different remedies.',
      },
    ],
    sources: [
      {
        label: 'ACA Internal Appeals and External Review Rights, HHS',
        url: 'https://www.healthcare.gov/appeal-insurance-company-decision/appeals/',
      },
      {
        label: 'KFF: Claims Denials and Appeals in ACA Marketplace Plans',
        url: 'https://www.kff.org/private-insurance/issue-brief/claims-denials-and-appeals-in-aca-marketplace-plans/',
      },
      {
        label: 'External Appeal Information, CMS',
        url: 'https://www.cms.gov/cciio/resources/consumer-assistance-grants/external-appeal',
      },
    ],
    related: [
      { label: 'What Is an Explanation of Benefits', href: '/learn/how-to-read-an-itemized-medical-bill' },
      { label: 'How to Dispute a Hospital Bill', href: '/learn/how-to-dispute-a-hospital-bill' },
      { label: 'No Surprises Act', href: '/learn/no-surprises-act' },
    ],
  },

  {
    slug: 'can-hospitals-charge-whatever-they-want',
    metaTitle: 'Can Hospitals Charge Whatever They Want? | ClaroBill',
    h1: 'Can Hospitals Charge Whatever They Want?',
    description:
      'Hospitals set prices through a chargemaster, but price transparency rules, insurer contracts, and Medicaid limits constrain what they actually collect. Here is how it works.',
    date: '2026-05-18',
    readTime: '6 min read',
    lead:
      'Hospitals publish list prices through a "chargemaster," which can be many times higher than what they actually collect. Federal price transparency rules now require hospitals to publish their prices publicly. But for the uninsured and out-of-network patients, list prices are often the default, making it critical to know how hospital pricing works.',
    sections: [
      {
        h2: 'The chargemaster: where prices start',
        paragraphs: [
          'Every hospital maintains a chargemaster, a master list of every billable item and service with an associated price. Chargemaster prices are set by hospital administrators and have historically been opaque. They bear little relationship to the actual cost of delivering care.',
          'A study by the Johns Hopkins Bloomberg School of Public Health found that hospitals charge an average of 3.4 times what Medicare pays for the same services. Some hospitals charge 10 times or more. These markups are the starting point for negotiations with insurers, not prices that patients actually pay.',
        ],
      },
      {
        h2: 'How insurance contracts constrain prices',
        paragraphs: [
          'Insurers negotiate contracts with hospitals that set specific allowed amounts for each service. These contracted rates are typically 30% to 70% below chargemaster prices. Hospitals agree to accept the contracted rate as payment in full from in-network patients.',
          'Medicaid rates are set by state governments and are generally the lowest rates hospitals receive, often below the actual cost of providing the service. Medicare rates are set by CMS through the fee schedule and inpatient prospective payment systems. Hospitals cannot bill Medicare patients more than the Medicare rate for covered services.',
        ],
      },
      {
        h2: 'Price transparency requirements',
        paragraphs: [
          'The Hospital Price Transparency Rule, effective January 1, 2021, requires all hospitals participating in Medicare and Medicaid to publish: a machine-readable file with prices for all items and services, and a consumer-friendly display with prices for at least 300 shoppable services. The file must show the chargemaster rate, the negotiated rates with each payer, and the de-identified minimum and maximum negotiated rates.',
          'Hospitals that do not comply face civil monetary penalties. CMS has enforced the rule against non-compliant hospitals, with penalties scaled to hospital bed size, up to $2 million per year for large facilities.',
        ],
      },
      {
        h2: 'What this means for uninsured patients',
        paragraphs: [
          'Uninsured patients who do not negotiate are often billed the full chargemaster rate. This is the highest possible price. Hospitals are not legally required to give uninsured patients the same discounts they give insurers, though the ACA\'s Section 501(r) limits how much nonprofit hospitals can charge patients who qualify for financial assistance.',
          'Under 501(r), nonprofit hospitals cannot charge patients who qualify for financial assistance more than "amounts generally billed" to insured patients. This provides an implicit cap on what qualifying uninsured patients can be charged.',
        ],
      },
      {
        h2: 'Using published prices in negotiations',
        paragraphs: [
          'Hospital price transparency data is publicly available. You can use it to see what your hospital charges other payers for the service you received, and use that information to negotiate as a self-pay patient.',
          'Tools like CMS\'s Hospital Compare and third-party aggregators of transparency data make it possible to compare prices across hospitals in your area. For elective procedures, shopping across facilities can produce savings of thousands of dollars for the same procedure.',
        ],
      },
    ],
    faqs: [
      {
        q: 'Are hospitals required to tell me the price before I receive care?',
        a: 'Under the No Surprises Act, providers must give good faith cost estimates to uninsured and self-pay patients before scheduled services. For insured patients, the requirements are less specific, but hospitals must provide the publicly posted prices.',
      },
      {
        q: 'Why does the same hospital charge different amounts to different patients?',
        a: 'Because hospitals have different negotiated rates with every insurer, set a separate self-pay rate, and have a chargemaster list price. For the same procedure, a hospital might receive $800 from Medicaid, $1,400 from a commercial insurer, $2,200 from another insurer, and bill $6,000 to an uninsured patient.',
      },
      {
        q: 'How do I find a hospital\'s published prices?',
        a: 'Go directly to the hospital\'s website and search for "price transparency" or "patient estimates." CMS also provides links to hospital transparency files at cms.gov/hospital-price-transparency. Third-party tools like RAND Hospital Price Transparency Tool aggregate this data.',
      },
      {
        q: 'Can hospitals charge different rates based on where you live?',
        a: 'Hospitals set one chargemaster and negotiate different contracts with different insurers. The variation is based on the payer, not the patient\'s geography. However, different hospitals in different regions have different chargemaster rates, so where you receive care matters enormously.',
      },
    ],
    sources: [
      {
        label: 'Hospital Price Transparency Rule, CMS',
        url: 'https://www.cms.gov/hospital-price-transparency',
      },
      {
        label: 'IRS 501(r) Amounts Generally Billed Guidance',
        url: 'https://www.irs.gov/charities-non-profits/charitable-organizations/amounts-generally-billed',
      },
      {
        label: 'KFF: How Much More Than Medicare Do Private Insurers Pay?',
        url: 'https://www.kff.org/medicare/issue-brief/how-much-more-than-medicare-do-private-insurers-pay/',
      },
    ],
    related: [
      { label: 'Why Your Bill Exceeds the Insurer Negotiated Rate', href: '/learn/why-bill-exceeds-insurer-negotiated-rate' },
      { label: 'What Are CPT Codes?', href: '/learn/what-are-cpt-codes' },
      { label: 'How to Dispute a Hospital Bill', href: '/learn/how-to-dispute-a-hospital-bill' },
    ],
  },

  {
    slug: 'what-is-a-surprise-medical-bill',
    metaTitle: 'What Is a Surprise Medical Bill? | ClaroBill',
    h1: 'What Is a Surprise Medical Bill?',
    description:
      'A surprise medical bill comes from an out-of-network provider at an in-network facility. Federal law now bans most surprise bills for emergency services and many other situations.',
    date: '2026-05-18',
    readTime: '5 min read',
    lead:
      'A surprise medical bill is a charge you did not expect because you received care from an out-of-network provider without knowing it, typically in an emergency or during a procedure at an in-network facility. Before 2022, surprise bills were legal and common. The No Surprises Act now prohibits them in most circumstances.',
    sections: [
      {
        h2: 'How surprise bills happen',
        paragraphs: [
          'You go to an in-network hospital for surgery. The surgeon is in-network. But the anesthesiologist, the radiologist reading your imaging, or the assistant surgeon is out-of-network. You never chose these providers. You did not know they were out-of-network. After the procedure, you receive a bill for thousands of dollars from a provider you have never heard of.',
          'This scenario was extremely common before 2022. A 2020 KFF analysis found that 1 in 5 emergency room visits and 1 in 6 in-network hospital stays involved at least one out-of-network charge.',
        ],
      },
      {
        h2: 'What the No Surprises Act does',
        paragraphs: [
          'The No Surprises Act, effective January 1, 2022, prohibits out-of-network providers from billing you more than your in-network cost-sharing amount in three situations: emergency care at any facility, non-emergency care at an in-network facility when you did not receive sufficient advance notice, and air ambulance transport from non-network providers.',
          'Under the law, the dispute about the actual payment amount is handled between the provider and the insurer through an independent dispute resolution (IDR) process. You are not involved and pay only your in-network cost-sharing amount.',
        ],
      },
      {
        h2: 'The consent exception',
        paragraphs: [
          'For non-emergency services, an out-of-network provider can balance bill you if: they give you written notice at least 72 hours before the service, the notice explains that you have the right to choose an in-network provider, the notice gives you a good faith cost estimate, and you sign a consent form acknowledging all of this.',
          'This consent exception cannot be used for certain specialists, including anesthesiologists, pathologists, radiologists, and neonatologists when they are the only provider available at an in-network facility.',
        ],
      },
      {
        h2: 'Ground ambulance: still a gap',
        paragraphs: [
          'Ground ambulance services were explicitly excluded from the No Surprises Act. Congress directed an advisory committee to study the issue and report recommendations. As of May 2026, no federal ground ambulance balance billing protection is in effect. Some states have enacted their own protections.',
          'If you receive a large surprise bill from a ground ambulance service, check your state insurance commissioner\'s website for state-specific protections. Also check whether your insurer has any out-of-network emergency provisions that might apply.',
        ],
      },
      {
        h2: 'How to respond to a surprise bill',
        paragraphs: [
          'If you receive a bill from an out-of-network provider for a service that should be covered by the No Surprises Act, do not pay it. Contact your insurer and report the bill. Your insurer is responsible for handling the payment dispute with the provider.',
          'File a complaint with the No Surprises Help Desk at 1-800-985-3059 or at cms.gov/nosurprises. Violations of the No Surprises Act carry civil monetary penalties of up to $10,000 per violation.',
        ],
      },
    ],
    faqs: [
      {
        q: 'How do I know if my bill is a surprise bill covered by the No Surprises Act?',
        a: 'The bill is likely covered if it is from an out-of-network provider for emergency services at any facility, or from an out-of-network provider at an in-network hospital or surgery center for a service you scheduled through that facility. Contact your insurer to confirm.',
      },
      {
        q: 'Can the No Surprises Act help with bills I already paid before 2022?',
        a: 'No. The law applies to services received on or after January 1, 2022. Bills for services before that date are not covered.',
      },
      {
        q: 'What if my employer plan is self-funded? Does the No Surprises Act apply?',
        a: 'Yes. The No Surprises Act applies to both insured and self-funded employer health plans. It also applies to non-grandfathered individual and group health insurance.',
      },
      {
        q: 'Does the No Surprises Act cap what providers can charge each other?',
        a: 'It caps what they can charge you. It does not set the final payment between the provider and insurer. That is determined by negotiation or the federal IDR process. Providers and insurers dispute those amounts among themselves, not with you.',
      },
    ],
    sources: [
      {
        label: 'No Surprises Act Consumer Information, CMS',
        url: 'https://www.cms.gov/nosurprises/consumers',
      },
      {
        label: 'KFF: Surprise Medical Bills in Emergency Settings',
        url: 'https://www.kff.org/private-insurance/issue-brief/surprise-medical-bills-new-protections-for-consumers-take-effect-in-2022/',
      },
      {
        label: 'Consolidated Appropriations Act 2021 (No Surprises Act Text)',
        url: 'https://www.congress.gov/bill/116th-congress/house-bill/133/text',
      },
    ],
    related: [
      { label: 'No Surprises Act', href: '/learn/no-surprises-act' },
      { label: 'What Is Balance Billing', href: '/learn/why-bill-exceeds-insurer-negotiated-rate' },
      { label: 'How to Dispute a Hospital Bill', href: '/learn/how-to-dispute-a-hospital-bill' },
    ],
  },

  {
    slug: 'what-is-out-of-network-billing',
    metaTitle: 'What Is Out-of-Network Billing? | ClaroBill',
    h1: 'What Is Out-of-Network Billing?',
    description:
      'Out-of-network billing happens when you receive care from a provider who has no contract with your insurer. Learn what it costs, when it applies, and how to minimize your exposure.',
    date: '2026-05-18',
    readTime: '6 min read',
    lead:
      'Out-of-network billing applies when a healthcare provider does not have a contract with your health insurer. Without a contract, there is no agreed rate. The provider can charge any amount, and your insurer may pay little or nothing. The result is often a large unexpected bill for you.',
    sections: [
      {
        h2: 'How in-network and out-of-network differ',
        paragraphs: [
          'In-network providers have signed contracts with your insurer agreeing to specific rates for specific services. They accept those rates as payment in full. You pay your deductible, copay, or coinsurance based on those negotiated rates.',
          'Out-of-network providers have no such agreement. They bill at their own rates, often at or near chargemaster prices. Your insurer may pay nothing (if your plan has no out-of-network benefits) or may pay based on an "allowed amount" that is far below what the provider charged, leaving you responsible for the balance.',
        ],
      },
      {
        h2: 'How your plan handles out-of-network claims',
        paragraphs: [
          'HMO plans (Health Maintenance Organizations) generally do not cover out-of-network care except in emergencies. PPO plans (Preferred Provider Organizations) cover out-of-network care but at a higher cost-sharing rate. EPO plans (Exclusive Provider Organizations) typically do not cover out-of-network care at all.',
          'Your Summary of Benefits and Coverage document explains how your specific plan handles out-of-network care. Key numbers to find: your out-of-network deductible (often higher than the in-network deductible), your out-of-network coinsurance percentage, and your out-of-network out-of-pocket maximum (some plans have no out-of-network maximum).',
        ],
      },
      {
        h2: 'The "allowed amount" problem',
        paragraphs: [
          'When your insurer processes an out-of-network claim, it calculates an "allowed amount," the maximum it will reimburse for that service. This amount is based on internal benchmarks, historical data, or a percentage of Medicare rates. It has no relation to what the provider actually charged.',
          'If a provider charges $5,000 and your insurer\'s allowed amount is $1,200, your insurer pays its share of $1,200 (say, 60%, or $720). You owe your share of $1,200 (40%, or $480) plus the $3,800 balance that exceeds the allowed amount. That balance is the balance bill.',
        ],
      },
      {
        h2: 'When the No Surprises Act limits out-of-network billing',
        paragraphs: [
          'As of January 1, 2022, the No Surprises Act prohibits out-of-network billing for emergency services at any facility and for certain services at in-network facilities where you did not choose an out-of-network provider. In these situations, you pay only your in-network cost-sharing amount.',
          'The law does not cover all out-of-network situations. If you knowingly and voluntarily choose an out-of-network provider for a scheduled procedure, you can still be billed at out-of-network rates, provided the provider gave you adequate advance notice.',
        ],
      },
      {
        h2: 'How to avoid out-of-network charges',
        paragraphs: [
          'Before any scheduled procedure, verify that every provider involved is in-network. This includes the facility, the surgeon, the anesthesiologist, the assistant surgeon, and the facility\'s pathology and radiology groups. Hospitals frequently use employed or contracted specialists who are not on your insurer\'s panel.',
          'Call your insurer directly to verify network status. Do not rely solely on the hospital\'s claim that a provider is in-network. Get confirmation in writing or note the date, time, and representative name from your call.',
        ],
      },
    ],
    faqs: [
      {
        q: 'What does "usual, customary, and reasonable" (UCR) mean on my EOB?',
        a: 'UCR is the amount your insurer considers reasonable for a given service in your geographic area. It is often used to calculate the allowed amount for out-of-network claims. UCR rates are set by insurers and are not regulated. They are often far below actual market rates.',
      },
      {
        q: 'Can I ask a provider to waive the out-of-network balance?',
        a: 'Yes, and many will. Especially if the provider is at an in-network facility, they may agree to accept in-network rates as a courtesy or to avoid a patient complaint. Get any waiver agreement in writing.',
      },
      {
        q: 'Does going out-of-network reset my deductible?',
        a: 'Most plans have a separate, higher out-of-network deductible. Amounts paid toward your in-network deductible typically do not count toward the out-of-network deductible, and vice versa. Check your plan documents.',
      },
      {
        q: 'Can an out-of-network provider send me to collections while I dispute the balance?',
        a: 'Yes, unless the bill is protected by the No Surprises Act. If the bill falls under No Surprises Act protections, you should not be paying the balance at all. File a complaint with CMS and your insurer immediately.',
      },
    ],
    sources: [
      {
        label: 'No Surprises Act, CMS',
        url: 'https://www.cms.gov/nosurprises',
      },
      {
        label: 'KFF: Out-of-Network Billing and the No Surprises Act',
        url: 'https://www.kff.org/private-insurance/issue-brief/surprise-medical-bills-new-protections-for-consumers-take-effect-in-2022/',
      },
      {
        label: 'Understanding Your Health Insurance, CFPB',
        url: 'https://www.consumerfinance.gov/consumer-tools/medical-bills/',
      },
    ],
    related: [
      { label: 'No Surprises Act', href: '/learn/no-surprises-act' },
      { label: 'Why Your Bill Exceeds the Insurer Negotiated Rate', href: '/learn/why-bill-exceeds-insurer-negotiated-rate' },
      { label: 'How to Dispute a Hospital Bill', href: '/learn/how-to-dispute-a-hospital-bill' },
    ],
  },

  {
    slug: 'how-do-i-get-hospital-financial-assistance',
    metaTitle: 'How Do I Get Financial Assistance From a Hospital? | ClaroBill',
    h1: 'How Do I Get Financial Assistance From a Hospital?',
    description:
      'Most nonprofit hospitals are legally required to offer financial assistance programs. Learn how to apply, what income limits apply, and what documentation you need.',
    date: '2026-05-18',
    readTime: '6 min read',
    lead:
      'Every nonprofit hospital that accepts Medicare and Medicaid must have a financial assistance program under IRS Section 501(r). These programs, often called charity care, can reduce or eliminate your bill entirely. Most people who qualify never apply because they do not know the program exists or assume they make too much to qualify.',
    sections: [
      {
        h2: 'Who is required to have financial assistance programs',
        paragraphs: [
          'All nonprofit hospitals that have 501(c)(3) tax-exempt status must maintain a written financial assistance policy under IRS Section 501(r), enacted as part of the ACA. This covers most community hospitals, teaching hospitals, and health system hospitals in the United States.',
          'For-profit hospitals are not legally required to have financial assistance programs, but many do. Government-owned hospitals have their own programs governed by state or local rules. Even for-profit systems often have charity care programs that mirror nonprofit requirements.',
        ],
      },
      {
        h2: 'Income and eligibility thresholds',
        paragraphs: [
          'Income thresholds vary by hospital and state, but many programs cover patients earning up to 200% to 400% of the federal poverty level (FPL). For 2026, 200% FPL is approximately $30,120 for a single person and $61,920 for a family of four. At 400% FPL, those figures double.',
          'Some hospitals use a sliding scale: patients below 200% FPL pay nothing, patients between 200% and 300% FPL pay a reduced percentage, and so on up to the program limit. The specific scale is in the hospital\'s financial assistance policy, which they are required to make publicly available.',
        ],
      },
      {
        h2: 'What financial assistance can cover',
        paragraphs: [
          'Financial assistance programs can apply to any medically necessary service provided at the hospital, including emergency care, inpatient stays, outpatient procedures, and associated physician fees if those physicians are hospital employees.',
          'The program typically reduces or eliminates the charges before insurance is applied. If you have insurance, the program may cover amounts your insurance leaves as your responsibility: your deductible, copay, or coinsurance. The most generous programs eliminate all patient-responsibility amounts for qualifying patients.',
        ],
      },
      {
        h2: 'How to apply',
        paragraphs: [
          'Call the hospital billing department and say: "I would like to apply for your financial assistance program." By law, the hospital must give you an application and plain-language information about the program. They cannot send your bill to collections for at least 120 days after providing care and must give you at least 30 days after notifying you about the application before taking collection actions.',
          'You will typically need to provide: proof of income (recent tax returns, W-2s, or pay stubs), proof of household size (a list of dependents), and sometimes bank statements. If you do not have all documents, submit what you have and ask for an extension.',
        ],
      },
      {
        h2: 'Limits on collection while you apply',
        paragraphs: [
          'Under IRS 501(r) rules, nonprofit hospitals cannot take "extraordinary collection actions" before making a reasonable effort to screen you for financial assistance. Extraordinary collection actions include: reporting to credit bureaus, filing lawsuits, garnishing wages, and placing liens on property.',
          'If a hospital takes collection action without first notifying you of its financial assistance program, it is in violation of 501(r). File a complaint with the IRS using Form 13909 and your state attorney general\'s office.',
        ],
      },
    ],
    faqs: [
      {
        q: 'Can I apply for financial assistance after my bill has gone to collections?',
        a: 'Yes. Many hospitals will recall a bill from collections if you apply for financial assistance and qualify. Apply immediately upon receipt of any collection notice and reference the hospital\'s 501(r) obligations in your application.',
      },
      {
        q: 'What if I do not qualify for the main financial assistance program?',
        a: 'Ask about a sliding-scale discount or a reduced self-pay rate. Many hospitals have multiple tiers. Also ask whether the hospital has a separate "prompt-pay discount" or "uninsured discount" that does not require an income-based application.',
      },
      {
        q: 'Does applying for financial assistance affect my credit?',
        a: 'The application itself does not affect your credit. While an application is pending, the hospital should not be reporting the debt or taking collection actions. If it does, that is a potential 501(r) violation.',
      },
      {
        q: 'Can financial assistance cover past bills I have already paid?',
        a: 'Possibly. If you paid a bill within the past year and believe you would have qualified for assistance, ask the hospital. Some programs will retroactively apply assistance and refund your payment. This is not guaranteed but worth asking.',
      },
    ],
    sources: [
      {
        label: 'IRS Section 501(r) Requirements for Hospital Organizations',
        url: 'https://www.irs.gov/charities-non-profits/charitable-organizations/requirements-for-501c3-hospitals-under-the-affordable-care-act-section-501r',
      },
      {
        label: 'HHS Federal Poverty Level Guidelines 2026',
        url: 'https://aspe.hhs.gov/topics/poverty-economic-mobility/poverty-guidelines',
      },
      {
        label: 'KFF: Charity Care in US Hospitals',
        url: 'https://www.kff.org/health-costs/issue-brief/a-look-at-hospital-charity-care-trends-and-policy-implications/',
      },
    ],
    related: [
      { label: 'How to Dispute a Hospital Bill', href: '/learn/how-to-dispute-a-hospital-bill' },
      { label: 'Common Medical Billing Errors', href: '/learn/common-medical-billing-errors' },
      { label: 'Can I Negotiate My Hospital Bill', href: '/learn/how-to-dispute-a-hospital-bill' },
    ],
  },

  {
    slug: 'what-does-in-network-mean',
    metaTitle: 'What Does In-Network Mean? | ClaroBill',
    h1: 'What Does In-Network Mean?',
    description:
      'In-network means a provider has a contract with your insurer that sets specific rates. Using in-network providers significantly reduces your out-of-pocket costs.',
    date: '2026-05-18',
    readTime: '5 min read',
    lead:
      'A provider is "in-network" when they have a signed contract with your health insurer. That contract sets specific rates for every covered service, and the provider agrees to accept those rates as payment in full. Using in-network providers is almost always significantly cheaper than using out-of-network providers, sometimes by thousands of dollars for a single service.',
    sections: [
      {
        h2: 'What the in-network contract means for you',
        paragraphs: [
          'When you use an in-network provider, your insurer processes the claim, applies the contracted discount, pays its share, and you pay your share, which is your deductible, copay, or coinsurance percentage based on the discounted rate.',
          'For example: a procedure costs $4,000 at chargemaster rates. The insurer\'s negotiated rate is $1,800. The insurer applies the $2,200 discount. You pay a percentage of $1,800, not $4,000. For a procedure costing tens of thousands of dollars, this difference is enormous.',
        ],
      },
      {
        h2: 'How to verify if a provider is in-network',
        paragraphs: [
          'Your insurer\'s website has a "find a doctor" or "provider directory" search tool. You can search by name, specialty, or location to see which providers are in your network. Directories can be outdated, so always call both your insurer and the provider\'s office to confirm network status before a scheduled procedure.',
          'When calling your insurer, ask specifically: "Is [provider name] in-network for my specific plan?" Plans within the same insurer can have different networks. A provider in-network for your insurer\'s PPO plan may not be in-network for the same insurer\'s HMO plan.',
        ],
      },
      {
        h2: 'Network types and what they mean',
        paragraphs: [
          'HMOs (Health Maintenance Organizations) require you to choose a primary care physician who coordinates your care and provides referrals to in-network specialists. Out-of-network care is not covered except in emergencies.',
          'PPOs (Preferred Provider Organizations) allow you to see any provider, in or out of network, but charge you more for out-of-network care. EPOs (Exclusive Provider Organizations) require in-network use like HMOs but without the referral requirement. HDHPs (High Deductible Health Plans) can be paired with any network type.',
        ],
      },
      {
        h2: 'The narrow network problem',
        paragraphs: [
          'Insurers have increasingly moved to "narrow networks" that include fewer providers in exchange for lower premiums. Narrow network plans can leave you in situations where the closest specialist or the only facility that performs a specific procedure is out-of-network.',
          'Before selecting a health plan during open enrollment, check whether your current doctors, specialists, and preferred hospitals are in the network. The cheapest premium is not the best deal if your providers are out-of-network.',
        ],
      },
      {
        h2: 'When you cannot find an in-network provider',
        paragraphs: [
          'If no in-network provider is available for a medically necessary service in your geographic area, you can request a "network adequacy exception" from your insurer. This allows you to see an out-of-network provider at in-network cost-sharing rates.',
          'Under ACA rules, insurers must maintain networks that meet minimum adequacy standards. If your plan lacks sufficient in-network providers in your area for a specialty you need, file a complaint with your state insurance commissioner.',
        ],
      },
    ],
    faqs: [
      {
        q: 'Can a provider leave my insurer\'s network without notice?',
        a: 'Provider contracts can end, removing a provider from your network mid-year. Some states require insurers to give enrollees 60 to 90 days notice when a provider leaves the network. Under the No Surprises Act, continuing treatment patients have continuity of care rights for up to 90 days when a provider leaves the network.',
      },
      {
        q: 'Is an in-network facility the same as all in-network providers?',
        a: 'No. A hospital being in-network does not mean every physician who works there is in-network. Anesthesiologists, radiologists, and other specialists may be employed by separate groups with their own insurer contracts. Always verify each provider independently.',
      },
      {
        q: 'What is a tiered network?',
        a: 'Some plans have tiered networks with Tier 1 (preferred), Tier 2 (standard), and Tier 3 (out-of-network) levels. Tier 1 providers have the lowest cost-sharing for you, often because they have agreed to additional cost-control measures. Using Tier 2 providers costs more but is still covered.',
      },
      {
        q: 'Can I get a referral to an out-of-network provider covered at in-network rates?',
        a: 'In some cases, yes. If your plan has a network adequacy exception process or if your physician certifies that no in-network provider can meet your medical needs, your insurer may cover an out-of-network provider at in-network rates. This requires advance approval from the insurer.',
      },
    ],
    sources: [
      {
        label: 'Network Adequacy Standards, HHS',
        url: 'https://www.healthcare.gov/glossary/network/',
      },
      {
        label: 'Understanding Health Plan Types, HHS',
        url: 'https://www.healthcare.gov/choose-a-plan/plan-types/',
      },
      {
        label: 'KFF: Networks and Cost-Sharing in Health Plans',
        url: 'https://www.kff.org/private-insurance/issue-brief/cost-sharing-for-plans-in-the-individual-market/',
      },
    ],
    related: [
      { label: 'What Is Out-of-Network Billing', href: '/learn/why-bill-exceeds-insurer-negotiated-rate' },
      { label: 'No Surprises Act', href: '/learn/no-surprises-act' },
      { label: 'How to Dispute a Hospital Bill', href: '/learn/how-to-dispute-a-hospital-bill' },
    ],
  },

  {
    slug: 'how-do-hospitals-determine-what-to-charge',
    metaTitle: 'How Do Hospitals Determine What to Charge? | ClaroBill',
    h1: 'How Do Hospitals Determine What to Charge?',
    description:
      'Hospitals set prices through a chargemaster, negotiate different rates with each insurer, and are now required to publish those rates publicly. Here is how the system works.',
    date: '2026-05-18',
    readTime: '7 min read',
    lead:
      'Hospital pricing is a layered system with list prices, negotiated rates, government-set rates, and patient-specific rates. Understanding how each layer works helps you know which price applies to you and where you have leverage to reduce what you pay.',
    sections: [
      {
        h2: 'The chargemaster: the list price',
        paragraphs: [
          'Every hospital maintains a chargemaster, a master file of every billable item with an associated price. This is the hospital\'s list price. Chargemaster prices are set by hospital administrators and revenue cycle staff, often based on what competitors charge and what the market will bear for uninsured patients.',
          'Chargemaster prices are consistently higher than what any payer actually pays. A RAND Corporation study of hospital prices found that commercial insurers paid an average of 224% of Medicare rates in 2020. Chargemaster prices are often 300% to 1,000% of Medicare rates. The chargemaster is a ceiling, not a market price.',
        ],
      },
      {
        h2: 'How insurers negotiate different rates',
        paragraphs: [
          'Every insurer that contracts with a hospital negotiates its own rates. Larger insurers with more covered patients have more leverage and typically negotiate lower rates. The same hospital may have dozens of different contracted rates for the same procedure, one for each insurer it works with.',
          'Rates are negotiated as percentages of the chargemaster, as fixed payments per case (DRGs for inpatient care), or as percentages of Medicare rates. The final negotiated rate is confidential under most contracts, which is why price transparency regulation was necessary to surface this information.',
        ],
      },
      {
        h2: 'Government-set rates: Medicare and Medicaid',
        paragraphs: [
          'Medicare rates for inpatient hospital stays are set through the Inpatient Prospective Payment System (IPPS), which assigns each diagnosis a Diagnosis Related Group (DRG) with a fixed payment. For outpatient services, rates are set through the Outpatient Prospective Payment System (OPPS) and the Medicare Physician Fee Schedule.',
          'Medicaid rates are set by each state and are generally lower than Medicare rates, often below the actual cost of providing care. Hospitals serving large Medicaid populations receive supplemental Disproportionate Share Hospital (DSH) payments to offset these losses.',
        ],
      },
      {
        h2: 'Price transparency requirements',
        paragraphs: [
          'The Hospital Price Transparency Rule (effective January 1, 2021) requires all Medicare-participating hospitals to publish two types of pricing information: a comprehensive machine-readable file listing prices for all items and services, and a consumer-friendly display of prices for at least 300 shoppable services.',
          'The machine-readable file must include the chargemaster rate, negotiated rates with each insurer identified by plan name, and de-identified minimum and maximum rates. This data makes it possible for the first time to compare prices across hospitals and across payers.',
        ],
      },
      {
        h2: 'What self-pay patients are charged',
        paragraphs: [
          'Self-pay patients without insurance are typically billed the chargemaster rate unless they negotiate or qualify for financial assistance. Some hospitals have a separate "uninsured" or "self-pay" discount rate that is lower than the chargemaster but still higher than negotiated insurance rates.',
          'Under IRS Section 501(r), nonprofit hospitals cannot charge patients who qualify for financial assistance more than the "amounts generally billed" to insured patients. This is typically the average of what all private insurers and Medicare pay for the service, which provides an implicit ceiling for qualifying uninsured patients.',
        ],
      },
    ],
    faqs: [
      {
        q: 'Why do hospitals charge so much more than what they actually receive?',
        a: 'The chargemaster system evolved because hospitals negotiated different rates with different payers. To have room to discount, they started from a high list price. The system is self-reinforcing: as list prices rose, negotiated discounts grew, and hospitals raised list prices further to maintain revenue. The result is list prices with no relationship to actual costs.',
      },
      {
        q: 'Can I find out what my insurer pays before I receive care?',
        a: 'Yes, through the hospital\'s published price transparency file. The file must show your insurer\'s negotiated rate for specific services. Most insurers also now provide cost estimation tools that show your estimated out-of-pocket cost for planned procedures.',
      },
      {
        q: 'Do all hospitals use the same pricing structure?',
        a: 'No. Physician-owned clinics, federally qualified health centers (FQHCs), and rural health clinics use different rate structures. Ambulatory surgery centers (ASCs) have separate Medicare payment schedules than hospitals. The chargemaster-based system primarily applies to traditional hospitals.',
      },
      {
        q: 'How do DRGs affect what I pay?',
        a: 'DRGs (Diagnosis Related Groups) set the total Medicare payment for an inpatient stay regardless of actual services used. Hospitals keep the DRG payment whether the stay is short or long. You are typically responsible for the Medicare Part A deductible per benefit period ($1,676 in 2026), not a per-day amount for the first 60 days.',
      },
    ],
    sources: [
      {
        label: 'Hospital Price Transparency Rule, CMS',
        url: 'https://www.cms.gov/hospital-price-transparency',
      },
      {
        label: 'Medicare Inpatient Prospective Payment System, CMS',
        url: 'https://www.cms.gov/medicare/payment/prospective-payment-systems/acute-inpatient-pps',
      },
      {
        label: 'RAND Hospital Price Transparency Study',
        url: 'https://www.rand.org/health-care/projects/hospital-pricing.html',
      },
      {
        label: 'KFF: How Do Hospital Prices Compare to Medicare?',
        url: 'https://www.kff.org/medicare/issue-brief/how-much-more-than-medicare-do-private-insurers-pay/',
      },
    ],
    related: [
      { label: 'Why Your Bill Exceeds the Insurer Negotiated Rate', href: '/learn/why-bill-exceeds-insurer-negotiated-rate' },
      { label: 'What Are CPT Codes?', href: '/learn/what-are-cpt-codes' },
      { label: 'Hospital Machine-Readable Files Explained', href: '/learn/hospital-machine-readable-files-explained' },
    ],
  },
];
