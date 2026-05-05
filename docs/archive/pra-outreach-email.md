# Outreach Email — Patient Rights Advocate

**Status:** ARCHIVED 2026-05-05 — outreach was sent on 2026-04-28; team pivoted to CMS-direct discovery the same day. PRA partnership not pursued. Kept as a record of the original Plan B sourcing strategy.

**Send to:** https://www.patientrightsadvocate.org/contact (web form)
**Alternate:** Reply-to email from any subscribed PRA newsletter, or LinkedIn DM to Cynthia Fisher (founder)
**From:** jirongo.sandie@gmail.com (or a ClaroBill-branded address if available)
**Subject:** Mission-aligned partnership request — ClaroBill (medical bill error detection)

---

## Email Body

Hi Patient Rights Advocate team,

I'm Sandra Jirongo, founder of ClaroBill (https://clarobill.com) — an AI tool that helps patients catch errors and overcharges in their medical bills. We generate plain-English audit reports and dispute letters for individuals who have been billed for services they didn't receive, double-billed, billed at unbundled rates, or charged above the hospital's own published rates.

That last category — billed above the hospital's published rates — is where your work is the linchpin of ours. CMS hospital price transparency rules only have teeth when someone actually compares the bill to the MRF, and patients almost never do. We do, automatically, as part of every audit.

Today we cover roughly 3,100 hospitals via a third-party directory (Payerset). I came across hospitalpricingfiles.org and your sitemap shows 7,096 hospitals — essentially the full CMS census, refreshed monthly. That coverage gap is the single biggest determinant of how often we can confidently tell a patient "your hospital is charging you more than its own published rate."

I'd like to ask whether PRA would consider a data-sharing arrangement under which we could ingest your hospital index — CCN, name, state, address, phone, website, MRF file URL — into ClaroBill on a recurring basis. In exchange, we're happy to:

1. **Attribute PRA prominently** on every audit report that uses your data ("Hospital pricing index: Patient Rights Advocate / hospitalpricingfiles.org").
2. **Share back our violation findings.** Each time we detect a hospital billing above its published rate, we can send PRA a structured record (hospital CCN, billed amount, published rate, date, redacted claim type) — useful for your advocacy and enforcement work, and something no patient-facing tool currently does at scale.
3. **Cite PRA in our public materials** as a foundational data partner. We do not redistribute your dataset to third parties; it stays inside our internal audit engine.

Our goal is the same as yours: make price transparency rules actually protect patients. Right now those rules are necessary-but-not-sufficient because no one is doing the comparison. We're trying to close that loop. Whatever form of access works on your side — a signed agreement, a download, an API key, even a one-time CSV — we'd welcome the conversation.

Happy to sign whatever data-use terms you'd want, and happy to do a 15-minute call to walk you through how we'd use the data. Thank you for the work you do — the fact that hospitalpricingfiles.org exists is the only reason this audit category is even possible at scale.

Best,
Sandra Jirongo
Founder, ClaroBill
jirongo.sandie@gmail.com
https://clarobill.com

---

## Talking points for follow-up call (if they reply)

- **Specific data fields needed:** CCN, hospital name, state, city, ZIP, address, phone, website URL, MRF file URL, MRF last-updated date, file format. Optionally: NPI, EIN, system/parent name, hospital type.
- **Update cadence we'd want:** monthly download or API pull — matches their current refresh cycle.
- **What we'd send back:** a monthly "violations digest" — count of bills audited per hospital, count of "billed > published rate" findings, total overcharge dollar amount detected. Aggregated, not patient-identifying.
- **Technical fit:** If they have an existing partner program (CSV download / SFTP / signed S3 URL / authenticated API), any of those works. We can also accommodate a Snowflake share or BigQuery share if they prefer.
- **Legal:** Open to a Data Use Agreement, BAA if needed (though their data is non-PHI), attribution clause, no-redistribution clause.
- **Timeline:** We'd integrate within 2-3 weeks of access. First "violations digest" back to PRA within ~6 weeks.

---

## If they say no

- Pivot to the original CMS-direct pipeline (`docs/future_improvements/mrf-discovery-pipeline.md`).
- Do **not** scrape `staging01.visiblecharges.com` — Turnstile-gated, rate-limited, and commercial scraping of a non-profit's curated dataset is the wrong posture for a company whose entire pitch is "we help patients catch unfair behavior."
- Use their public sitemap (`/sitemap.xml`, allowed by robots.txt) only as a coverage benchmark.

---

*Drafted: 2026-04-27*
