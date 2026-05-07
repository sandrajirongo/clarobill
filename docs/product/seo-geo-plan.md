# ClaroBill SEO & GEO Optimization Plan

**Version:** 1.0 — May 2026  
**Owner:** Sandra  
**Target GA:** July 2, 2026  
**Primary GTM channel:** SEO + GEO (organic, search-driven)

---

## Quick reference

- Task list: see §9 (50 tasks, T-001 → T-050)
- Current phase: **Phase 0** (pre-GA, now → June 30, 2026)
- Next immediate task: **T-001** done. Next: **T-006** (llms.txt) or **T-007** (JSON-LD component).
- GEO monitoring doc: `docs/product/geo-monitoring.md` (to be created at T-003)
- Content brief template: `docs/product/content-brief-template.md` (to be created at T-016)

---

## 0. Strategic context

ClaroBill finds errors in medical bills using OCR + a 13-rule engine + Claude AI, then generates dispute letters. Pricing is value-based, one-time per bill ($0–$199.99). Pre-GA: invite-only beta (now–May), open free beta in June, paid GA July 2.

**YMYL category.** Google and AI engines apply stricter E-E-A-T scrutiny for finance, medical, and legal content. Every decision in this plan is built around that constraint.

**Two parallel tracks:**
- **SEO** — blue-link traffic from Google
- **GEO** — citations inside AI answers (ChatGPT, Perplexity, Gemini, Google AI Overviews, Claude)

Solid SEO is a precondition for GEO. They diverge in content shape, measurement, and refresh cadence but are treated as one integrated program.

### Competitive landscape

**Direct consumer SaaS:**
- Goodbill (~2020, GV-backed): photo upload, 50%-of-savings contingency, manual coder review with software assist, no public rules engine, no MRF ingestion.
- Resolve Medical Debt (YC W19): flat or contingency pricing, positioned as debt-relief/negotiation more than error-finding.
- CheckMedBill.com: free dispute letter generator, no AI scan.

**Adjacent/services-led:**
- Compose.ly, Bill Advocate, Health Bill Advocates — human advocates at $35–100/hr. Rank on "medical billing advocate" head terms.
- ClearHealth Costs, Castlight, Healthcare Bluebook — prospective price-shopping tools, not retrospective error detection.

**Reference sites that dominate head terms (don't compete, cite them):** CMS.gov, AARP, JAMA, KFF.

### ClaroBill's structural moat

1. **MRF data at scale.** ClaroBill ingests the CMS Machine-Readable File corpus and applies 8 benchmarks competitors lack (NEGOTIATED_RATE, HOSPITAL_CHARGE, NEGOTIATED_CEILING, etc.). Competitors use generic Medicare benchmarks only.
2. **Effective-dating.** Checks the chargemaster in force on the bill's service date (`pricing_effective_year` partition). Competitors compare against current-year benchmarks regardless of service date.
3. **Coverage breadth.** Radiology, lab, ambulance, anesthesia — competitors skip these. ClaroBill's 13-rule engine covers the full CMS taxonomy.
4. **Determinism + auditability.** Every finding cites: CMS rule, MRF row, NCCI version, service date. Patients with deterministic citations win more disputes. This moat drives both product outcomes and GEO/SEO content depth.

---

## 1. Goals and KPIs

### 12-month targets (GA July 2026 → July 2027)

| Metric | Month 3 | Month 6 | Month 12 |
|--------|---------|---------|----------|
| Organic sessions/mo | 5,000 | 20,000 | 75,000 |
| Bills uploaded from organic | 150 | 800 | 4,000 |
| Indexed pages (quality) | 40 | 90 | 200 |
| Referring domains | 25 | 75 | 200 |
| AI citation rate (target prompt set) | 10% | 25% | 45% |
| AI mention rate (brand visibility) | 15% | 35% | 55% |
| Branded search volume/mo | 100 | 500 | 3,000 |

### GEO target prompt set (20 prompts — monitor weekly)

1. How do I find errors in my medical bill?
2. Best app to check medical bills for mistakes
3. How can I tell if my hospital bill is wrong?
4. AI tool to review medical bills
5. How to dispute a medical bill
6. What is upcoding in medical billing?
7. What is unbundling in medical billing?
8. How to read an itemized hospital bill
9. How much do medical bill review services cost?
10. Are medical bill negotiation services worth it?
11. How to write a medical bill dispute letter
12. CPT code lookup tool for patients
13. How to spot duplicate charges on a medical bill
14. What is the No Surprises Act?
15. How long do I have to dispute a medical bill?
16. Can I negotiate my hospital bill down?
17. Medical bill review service vs patient advocate
18. CheckMedBill alternatives
19. How accurate is AI for catching medical billing errors?
20. What's the average medical bill error rate?

Monitor across: ChatGPT, Perplexity, Gemini, Google AI Overviews, Claude, Copilot.

---

## 2. Technical foundation (Phase 0 prerequisites)

### 2.1 Crawler access — robots.ts ✅ DONE (T-001)

`apps/web/src/app/robots.ts` — Next.js App Router `robots()` function. Allows all AI bots (GPTBot, ChatGPT-User, OAI-SearchBot, PerplexityBot, Perplexity-User, Google-Extended, ClaudeBot, anthropic-ai, Applebot-Extended, CCBot, Bytespider). Disallows `/dashboard/`, `/onboarding/`, `/api/`, `/auth/`. References sitemap.

Verify weekly: check server logs for ChatGPT-User, PerplexityBot, ClaudeBot, Google-Extended crawl activity.

### 2.2 llms.txt (T-006)

Create `apps/web/public/llms.txt`. Product description block + core links (homepage, pricing, methodology, /learn/ hub) + reference links + trust links. Accessible at `https://clarobill.com/llms.txt`.

### 2.3 SSR audit (T-010)

All public routes must be server components or static — full HTML without JS. Test: `curl -A "ChatGPT-User" https://clarobill.com/[route]`. `/pricing/page.tsx` is currently `'use client'` — must be refactored to move interactive state to a client island. Every locale must serve correct `<html lang="...">` and hreflang.

### 2.4 JSON-LD schema markup (T-007, T-008)

Build reusable `apps/web/src/components/json-ld.tsx`. Sitewide: Organization + WebSite+SearchAction in `layout.tsx`. Per article: Article + BreadcrumbList + FAQPage + HowTo. Per pricing: Product+Offer array. Per glossary: DefinedTerm+DefinedTermSet. Per state: Article+FAQPage+GovernmentService. Author: Person with credentials + sameAs.

**Author schema is critical for YMYL.** Every article needs a Person author block. Anonymous medical content is ignored by AI engines and Google's medical-content quality systems.

### 2.5 Core Web Vitals (T-018)

- LCP < 2.0s mobile, INP < 200ms, CLS < 0.1
- Page weight < 500KB for marketing pages
- Lighthouse CI gate: any marketing route regressing CWV >10% blocks deploy

### 2.6 Sitemap (T-009)

Dynamic `apps/web/src/app/sitemap.ts` covering all static routes, /blog/[slug], /learn/[slug], programmatic routes (/state/*, /error-type/*, /cpt/*, /hospital/*), locale variants with hreflang. Submit to Google Search Console and Bing Webmaster Tools at launch.

---

## 3. Content architecture

### Layer 1 — Conversion pages (T-022, T-023)

- `/upload` — "upload medical bill" intent, BillUploader above fold
- `/free-medical-bill-check` — captures "free" modifier; during beta this is honest; post-GA becomes "free scan, pay only if we find savings"

Every conversion page: one H1 with primary keyword, Definition Lead in first 150 tokens, CTA above fold, trust block (HIPAA, sample report, methodology), FAQ block with FAQPage schema.

### Layer 2 — Educational hub /learn/* (T-004, T-015, T-024)

30 pillars over year 1. Each: 1,500–3,000 words, statistics/citations/specific dollar figures, fully schema'd, quarterly update.

**Pillar 1 — Billing errors:**
- /learn/common-medical-billing-errors
- /learn/duplicate-charges-medical-bill
- /learn/upcoding-medical-billing
- /learn/unbundling-medical-billing
- /learn/balance-billing
- /learn/phantom-charges-services-not-rendered

**Pillar 2 — Disputing and negotiating:**
- /learn/how-to-dispute-medical-bill
- /learn/medical-bill-dispute-letter-template
- /learn/how-to-negotiate-hospital-bill
- /learn/medical-bill-collections-rights
- /learn/medical-bill-credit-report-impact

**Pillar 3 — Patient rights:**
- /learn/no-surprises-act
- /learn/hospital-price-transparency-rule
- /learn/itemized-bill-rights
- /learn/charity-care-financial-assistance

**Pillar 4 — Reading bills:**
- /learn/how-to-read-itemized-hospital-bill
- /learn/medical-billing-codes-explained
- /learn/explanation-of-benefits-eob-guide
- /learn/cpt-code-lookup
- /learn/medicare-fee-schedule-explained

**Pillar 5 — Specific scenarios:**
- /learn/emergency-room-bill-too-high
- /learn/surprise-anesthesiology-bill
- /learn/childbirth-hospital-bill-errors
- /learn/surgery-bill-review
- /learn/ambulance-bill-dispute

**Pillar 6 — MRF/auditability moat (HIGHEST PRIORITY — write first):**
- /learn/hospital-machine-readable-files-explained
- /learn/negotiated-rate-vs-chargemaster-vs-medicare
- /learn/chargemaster-effective-dating
- /learn/ncci-edits-explained-for-patients
- /learn/cms-medicare-fee-schedule-vs-actual-bill
- /learn/audit-trail-medical-bill-dispute

Pillar 6 is the content nobody else can credibly write — it requires the MRF data. Every page is dense with specific, dated, sourced facts.

### Layer 3 — Programmatic SEO (T-027, T-035, T-036, T-046)

**A) State patient billing rights** — `/learn/state/[state]/patient-billing-rights` — 50 pages via `generateStaticParams`. State law, dispute deadline, flowchart, agency links, FAQ schema.

**B) CPT code reference** — `/cpt/[code]` — top 500 codes first, scale to 5,000. Code, description, Medicare allowed, average billed, common misuse, upload CTA.

**C) Hospital chargemaster** — `/hospital/[slug]` — top 1,000 hospitals (Phase 3). NPI, location, top-25 procedures, Medicare comparison, CTA.

**D) Error type × scenario matrix** — `/error/[type]/[scenario]` — ~80 pages.

**Programmatic SEO governance:** ≥600 words unique content per page, at least one expert paragraph, 3+ internal links from hub pages, real data (null fields = noindex), deindex any zero-impression page after 90 days.

### Layer 3.5 — Comparison pages (T-025)

Ship at GA launch. Disproportionately cited by AI engines (listicle/scorecard structure).

- /compare/goodbill-vs-clarobill
- /compare/resolve-vs-clarobill
- /compare/medical-bill-app-vs-human-advocate
- /compare/price-shopping-vs-bill-review
- /compare/best-medical-bill-apps

**Editorial rules:** Honest before advocate. Acknowledge where competitors are better. Comparison scorecard table with 8–12 dimensions. Legal review before publish. Update quarterly.

### Layer 4 — Blog (T-028)

- Weeks 1–12 post-GA: 1 new post/week
- Weeks 13–52: 2 posts/week (1 new + 1 update)
- Mix: 50% deep guides, 25% original data posts, 15% news commentary, 10% case studies

### Auditability moat — §3.6

**(a) /methodology page (T-002):** 13 rules, each with what it checks, federal authority cited, data source, worked example, SQL/citation pattern. Highest-leverage single content asset — YMYL trust anchor + AI citation magnet + proof point vs. Goodbill/Resolve.

**(b) Anonymized case studies (T-038):** 8–12 walkthroughs at `/case-studies/[slug]` with explicit signed consent. Error, rule that caught it, federal/MRF citation, dispute letter, resolution.

**(c) "How we know" inline component (T-033):** Embedded in every Pillar 6 article. Shows: "Rule: NCCI PTP edit pair {code, code}. Source: CMS NCCI Policy Manual, Chapter X, version YYYY.N. Effective date: [date]."

---

## 4. Keyword strategy

### Tier 1 — Primary commercial (Months 1–6)

| Keyword cluster | Est. volume | Difficulty | Target page |
|----------------|-------------|------------|-------------|
| medical bill error checker | 1,200 | Medium | / and /free-medical-bill-check |
| how to dispute a medical bill | 8,100 | High | /learn/how-to-dispute-medical-bill |
| medical bill review service | 700 | Medium | /how-it-works |
| medical bill dispute letter | 2,400 | Medium | /learn/medical-bill-dispute-letter-template |
| check medical bill for errors | 600 | Low | /free-medical-bill-check |
| AI medical bill review | 300 | Low (rising) | / and /learn/ |
| goodbill alternatives | 200 | Low | /compare/goodbill-vs-clarobill |
| resolve medical debt alternatives | 150 | Low | /compare/resolve-vs-clarobill |
| best medical bill app | 400 | Medium | /compare/best-medical-bill-apps |

### Tier 2 — Education head terms (Months 3–9)

| Keyword | Volume | Target |
|---------|--------|--------|
| no surprises act | 22,000 | /learn/no-surprises-act |
| upcoding | 5,400 | /learn/upcoding-medical-billing |
| unbundling medical billing | 1,300 | /learn/unbundling-medical-billing |
| explanation of benefits | 49,500 | /learn/explanation-of-benefits-eob-guide |
| CPT code | 90,000 | /learn/medical-billing-codes-explained + /cpt/* |
| balance billing | 8,100 | /learn/balance-billing |

### Tier 3 — Long-tail programmatic (Months 6–12)

- "[state] medical bill dispute" × 50 states
- "CPT [code]" × 5,000 codes
- "[hospital name] charges" × 1,000 hospitals

### Free interactive tools (T-026, T-037, T-045)

1. `/tools/cpt-code-lookup` — CPT → Medicare allowed + common misuse
2. `/tools/dispute-letter-generator` — state-specific templates, free
3. `/tools/hospital-cost-compare` — chargemaster comparison across hospitals

Tools earn links from journalists and patient-advocacy sites in ways pure content cannot.

---

## 5. Content production playbook

### Brief template (for every new page — T-016)

1. Target keyword + 3–5 secondary terms
2. Search intent (transactional / commercial / informational / navigational)
3. Target AI prompts this page should win
4. Definition Lead sentence (drafted up front)
5. Word count target (≥1,500 for /learn/*; ≥2,000 for tier-1 commercial)
6. Required H2 sections
7. Required statistics with sources (5 minimum)
8. Required external citations (3–5 minimum: CMS, JAMA, KFF, AARP, NIH, peer-reviewed)
9. Author + reviewer assignment
10. Internal link targets (3 out minimum, 3 in minimum)
11. Schema types required
12. Primary CTA

### Definition Lead — first 150 tokens

Pattern: `[Entity] is a [category] that [differentiator/mechanism]. [Concrete fact with statistic]. [Who it's for / when to use it].`

AI retrieval systems weight the first 150–200 tokens disproportionately.

### GEO trifecta (per Princeton GEO study, ~30–40% visibility lift)

- **Statistics:** ≥5 specific statistics per pillar, each with year and source
- **Citations:** ≥3 inline citations to authoritative sources (.gov, .edu, peer-reviewed)
- **Quotations:** ≥1 direct expert quote per pillar, with attribution and credentials

### Answer-block structure

Every H2 opens with a 2–4 sentence direct answer in plain paragraph form (not blockquote, not callout — those are harder for AI to extract). Then supporting detail.

### FAQs — every pillar page

8–12 FAQs at the bottom, FAQPage schema, questions matching real PAA/Reddit prompts. Answers 40–80 words each.

### Freshness protocol (T-017)

- Visible "Last reviewed: [Month Year]" stamp at top of every page
- `dateModified` in Article schema must match
- HTTP `Last-Modified` header set correctly
- Quarterly review of all /learn/* pages
- Monthly pass on top-20-traffic pages
- Version history at bottom of pillars: "v1.2 — Updated April 2026: refreshed No Surprises Act enforcement statistics."

### The "no AI smell" rule

Every page reads like a human expert wrote it. Sandra is the editorial gate. Forbidden: "In today's fast-paced world", "Whether you're X or Y", "It's important to note that", bulleted lists where prose would be clearer, five-paragraph CMS.gov regurgitations. Required: specifics, dollar figures, hospital names, code numbers, real cases.

---

## 6. GEO-specific tactics

### 6.1 Wikipedia/Wikidata (T-047, T-048)

- Month 3: Create Wikidata entity (factual, neutral, sourced)
- Month 10: Wikipedia article (only after 3+ independent press sources)
- Ongoing: Edit related Wikipedia articles neutrally (medical billing errors, No Surprises Act, hospital price transparency rule)

### 6.2 Unlinked brand mentions (T-029)

HARO/Qwoted/Featured — 5+ journalist queries/week. Lead with data moat, not "we use AI." Pitch hierarchy:
1. "Only consumer tool that compares bills against the actual MRF chargemaster in force on each bill's service date."
2. "Every error flag comes with a deterministic citation — CMS rule, MRF row, NCCI version."
3. AI framing only as tertiary support.

Founder LinkedIn: weekly posts with anonymized data patterns. Podcast outreach: personal finance, FIRE, healthcare reform, consumer protection.

### 6.3 Reddit presence (T-039)

Target: r/personalfinance, r/HealthInsurance, r/medicalbill, r/povertyfinance. Build over 6+ months. No promotional posts. 1-in-30 rule: 1 link mention per 30 substantive helpful comments minimum.

### 6.4 Listicle inclusion (T-040)

Target: appear in top 10 "best medical bill review apps" listicles by Month 9. Outreach to existing listicle authors with structured pitch + free trial offer.

### 6.5 Original data (T-043, T-044)

- Monthly 9: Annual "State of Medical Billing Errors Report" — 10,000+ bills, error rates by type, dollar overcharges, hospital stats. Embargoed to KFF Health News, STAT, Modern Healthcare, Axios Health, Bloomberg two weeks before release.
- Quarterly mini-analyses between annual reports.
- HIPAA-clean: k-anonymity thresholds, full public methodology, legal review.

### 6.6 Schema stacking

Stack 2–3 schemas per page. For /learn/*: Article + BreadcrumbList + FAQPage + HowTo + DefinedTerm × N.

### 6.7 Multi-platform GEO monitoring (T-003, T-042)

Weekly automated check across 20-prompt set on ChatGPT, Perplexity, Gemini, Google AI Overviews, Claude, Copilot. Tools: Otterly.ai, Profound, GenOptima, or custom API script. Track: Mention Rate, Citation Rate, Position, Share of Model. Invisible prompts → next quarter's content priorities.

---

## 7. Internationalization

- 5 locales: en, es, tl, vi, zh
- Conversion pages (/, /pricing, /how-it-works, /free-medical-bill-check): translated by native speakers, not auto-MT
- /learn/* launches en-only. Spanish first, then Vietnamese/Chinese, then Tagalog.
- Sub-path pattern: `clarobill.com/es/learn/...` (keeps domain authority unified)
- hreflang on every URL: self-referential + all locale variants

---

## 8. Link earning

1. **Annual data report** (§6.5) — centerpiece, earns more links than 12 months of guest posts
2. **Free tool link earning** — CPT lookup, dispute letter generator, hospital cost compare
3. **HARO/Qwoted founder quotes** — contextual brand mentions on authoritative sites

Avoid: paid guest posts, link exchanges, PBNs, comment links, directory submissions beyond the obvious (G2, Capterra, Product Hunt).

---

## 9. Task list (50 tasks)

### Phase 0 — Pre-GA (now → June 30, 2026)

| ID | Title | Status | Depends on |
|----|-------|--------|------------|
| T-001 | Fix `robots.ts` with full AI bot allow-list | **DONE** | — |
| T-006 | Create `public/llms.txt` | **DONE** | — |
| T-007 | Build reusable JSON-LD schema component | **DONE** | — |
| T-016 | Create content brief template + freshness protocol | todo | — |
| T-018 | Set up Lighthouse CI gate | todo | — |
| T-008 | Add sitewide Organization + WebSite JSON-LD to layout | **DONE** | T-007 |
| T-009 | Build dynamic `sitemap.ts` | **DONE** | T-001 |
| T-010 | Audit + fix SSR on all public marketing routes | **DONE** | — |
| T-011 | Add hreflang tags to all public pages | **DONE** | T-010 |
| T-005 | Wire GA4, Search Console, Bing Webmaster Tools | **INFRA DONE** — awaiting Sandra’s GA4 measurement ID + Search Console/Bing verification codes | T-001 |
| T-012 | Create `/learn` hub layout + index page | **DONE** | T-007, T-010 |
| T-013 | Upgrade `/about` to YMYL standard | **DONE** | T-007, T-008 |
| T-014 | Upgrade `/legal/*` pages to YMYL standard | **DONE** | T-007 |
| T-016 | Create content brief template + freshness protocol | **DONE** — `docs/product/content-brief-template.md` | — |
| T-002 | Build `/methodology` page (13 rules, full citations) | **DONE** — `apps/web/src/app/methodology/` | T-007 |
| T-017 | Add `Last-Modified` headers + reviewed stamps to `/learn/*` | **DONE** — byline stamp on /learn hub; standard set for all future articles | T-012 |
| T-004 | Draft canonical MRF pillar: `/learn/why-bill-exceeds-insurer-negotiated-rate` | **DONE** | T-002, T-008, T-012 |
| T-015 | Write 8 initial `/learn/*` pillar articles | **DONE** — 8 articles live under /learn/ | T-004, T-012, T-007 |
| T-018 | Set up Lighthouse CI gate | **DONE** — `.github/workflows/lighthouse.yml` + `.lighthouserc.js` | — |
| T-003 | Set up GEO measurement infrastructure | todo | T-005 |

### Phase 1 — GA Launch (July 2 → Sept 30, 2026)

| ID | Title | Status | Depends on |
|----|-------|--------|------------|
| T-019 | Add JSON-LD to existing blog posts | todo | T-007 |
| T-020 | Create `/authors/[slug]` author bio pages | todo | T-007, T-013 |
| T-021 | Build `/pricing` JSON-LD + SSR fix | todo | T-007, T-010 |
| T-022 | Build `/free-medical-bill-check` conversion page | todo | T-007, T-010 |
| T-023 | Upgrade `/upload` page for SEO | todo | T-007, T-010 |
| T-024 | Write remaining 22 `/learn/*` pillar articles (1/week) | todo | T-015, T-016, T-017 |
| T-025 | Build 5 comparison pages | todo | T-007, T-010 |
| T-026 | Build `/tools/cpt-code-lookup` tool page | todo | T-007, T-009 |
| T-027 | Build 50 `/learn/state/[state]/patient-billing-rights` pages | todo | T-012, T-007 |
| T-028 | Write 12 initial blog posts (1/week for 12 weeks) | todo | T-019, T-020 |
| T-029 | Set up HARO/Qwoted outreach workflow | todo | T-002, T-013 |
| T-030 | Launch on Product Hunt, IndieHackers, HN | todo | T-005 |
| T-031 | Update sitemap to include all Phase 1 routes | todo | T-009, T-024, T-025, T-026, T-027 |
| T-032 | Add HowTo + DefinedTerm schema stacking to `/methodology` | todo | T-002, T-007 |
| T-033 | Build "How we know" inline component | todo | T-024 |
| T-034 | Add `/methodology` trust block to all conversion pages | todo | T-002, T-022, T-023 |

### Phase 2 — Oct → Dec 2026

| ID | Title | Status | Depends on |
|----|-------|--------|------------|
| T-035 | Build first 500 `/cpt/[code]` programmatic pages | todo | T-026, T-031 |
| T-036 | Generate 80 `/error/[type]/[scenario]` pages | todo | T-007, T-031 |
| T-037 | Build `/tools/dispute-letter-generator` | todo | T-026, T-007 |
| T-038 | Build 8–12 `/case-studies/[slug]` walkthroughs | todo | T-002, T-024 |
| T-039 | Establish Reddit presence on 4 subreddits | todo | T-029 |
| T-040 | Appear in 3+ "best medical bill apps" listicles | todo | T-029, T-030 |
| T-041 | Expand sitemap to all Phase 2 programmatic routes | todo | T-035, T-036, T-038, T-031 |
| T-042 | Begin weekly GEO monitoring cadence | todo | T-003 |
| T-043 | Publish quarterly mini-analysis data post | todo | T-028, T-029 |

### Phase 3 — Jan → June 2027

| ID | Title | Status | Depends on |
|----|-------|--------|------------|
| T-044 | Publish annual "State of Medical Billing Errors" report | todo | T-043, T-029 |
| T-045 | Build `/tools/hospital-cost-compare` | todo | T-026, T-035 |
| T-046 | Build top 1,000 `/hospital/[slug]` programmatic pages | todo | T-035, T-007 |
| T-047 | Create Wikidata entity for ClaroBill | todo | T-013, T-044 |
| T-048 | Submit Wikipedia article for ClaroBill | todo | T-044, T-047 |
| T-049 | Produce Spanish `/learn/*` translations | todo | T-024, T-027, T-011 |
| T-050 | Update sitemap to include all Phase 3 routes | todo | T-046, T-044, T-049, T-041 |

---

## 10. Key implementation files

| File | Role | Status |
|------|------|--------|
| `apps/web/src/app/robots.ts` | AI bot allow-list (T-001) | **DONE** |
| `apps/web/public/llms.txt` | AI guidance file (T-006) | **DONE** |
| `apps/web/src/components/json-ld.tsx` | Reusable JSON-LD component (T-007) | **DONE** |
| `apps/web/src/app/sitemap.ts` | Dynamic sitemap (T-009) | **DONE** |
| `apps/web/src/app/layout.tsx` | Sitewide JSON-LD injection (T-008) | **DONE** |
| `apps/web/src/middleware.ts` | Must whitelist every new public route group | needs update |
| `apps/web/src/app/pricing/page.tsx` | Currently `'use client'` — must be refactored (T-010) | needs fix |
| `apps/web/src/app/methodology/page.tsx` | /methodology page (T-002) | todo |
| `docs/product/content-brief-template.md` | Content brief template (T-016) | todo |
| `docs/product/geo-monitoring.md` | GEO monitoring spec (T-003) | todo |

---

## 11. Risks and mitigations

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Google deprioritizes YMYL content from a startup without credentials | High | Real author bios with credentials; clear /methodology with per-rule federal authority; HIPAA-clean operations; named expert authors |
| AI engines stop crawling (Cloudflare block, Vercel firewall) | Medium | Monthly bot-traffic audit; explicit allow-list in robots.ts; check Vercel firewall settings |
| Programmatic SEO triggers spam systems | Medium | Hard quality floor (≥600 unique words, expert paragraph, real internal linking); monthly index audit; deindex zero-impression pages after 90 days |
| Goodbill/Resolve start ingesting MRF data | Medium | Speed on Pillar 6 content + annual data report establishes ClaroBill as named authority before competitors enter |
| Comparison page legal risk | Low / High impact | Quarterly fact-refresh with date-stamped sources; legal review pre-publish; honest competitor acknowledgment |
| Negative PR around AI accuracy in medical context | Medium | Conservative claim language; always frame as "flag potential errors for you to dispute, with federal citation"; deterministic citation trail is the rebuttal |
| HIPAA/privacy incident | Low / High impact | 60-day file retention + Edge Function deletion; written consent for all case studies; k-anonymity on data report |

---

## 12. Phased timeline

**Phase 0 (now → June 30):** Technical foundation, /about + /methodology + /legal/* to YMYL standard, 8 /learn/* pillars, GEO measurement infrastructure, GA4 + Search Console + Bing.

**Phase 1 (July 2 → Sept 30):** Launch with 8 pillars + blog + conversion funnel + 5 comparison pages + /methodology. 1 pillar/week + 1 blog/week. CPT lookup tool (Month 1). 50 state pages by Month 3. HARO outreach from week 1. Product Hunt/IndieHackers/HN launch.

**Phase 2 (Oct → Dec):** All 50 state pages, first 500 CPT pages, dispute letter tool, case studies, Reddit presence, listicle placements, weekly GEO monitoring cadence.

**Phase 3 (Jan → June 2027):** Annual data report (Month 9), hospital cost tool, Wikipedia (Month 10), Spanish /learn/* expansion, 1,000 hospital pages.
