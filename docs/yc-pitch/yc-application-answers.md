# ClaroBill — YC Application Answers

**Founder:** Sandra Jirongo
**Date prepared:** 2026-04-30 → 2026-05-01
**Purpose:** Comprehensive long-form answers to the YC application
questions, intended as a single source of truth for the pitch deck,
investor updates, and partner Q&A. Each section below is a complete
answer; copy-paste verbatim or trim to fit individual question word
limits.

---

## Table of Contents

1. [What does ClaroBill do (50 words)](#what-does-clarobill-do-in-50-words-or-less)
2. [What does ClaroBill do (50 characters)](#what-does-clarobill-do-in-50-characters-or-less)
3. [What is ClaroBill going to make? Describe the product and what it does or will do](#what-is-clarobill-going-to-make)
4. [Scientific basis: how does it work?](#scientific-basis--how-does-it-work)
5. [Roadmap: next stages, time + money](#roadmap--time-and-money-by-stage)
6. [If accepted into YC, what could you accomplish by Demo Day?](#yc-junejuly-batch--demo-day-plan)
7. [Regulatory exposure (FDA / HIPAA / SOC 2 / UPL)](#regulatory-exposure)
8. [Experimental data — what works, what's still unproven](#experimental-data)
9. [Competitors — and what we understand that they don't](#competitors--and-what-we-understand-that-they-dont)
10. [Equity ownership at company formation](#equity-ownership-at-company-formation)
11. [Why Oakland?](#why-oakland)
12. [How do you make money? How much could you make?](#revenue-model--how-and-how-much)

---

## What does ClaroBill do — in 50 words or less

ClaroBill analyzes medical bills for billing errors. Upload the bill;
we OCR the line items, cross-check each CPT code against CMS reference
data and 13,000+ hospitals' published price-transparency files, then
deliver a plain-English report and ready-to-send dispute letter showing
where you may have been overcharged.

---

## What does ClaroBill do — in 50 characters or less

> ClaroBill finds errors in your medical bills.
> *(46 characters)*

---

## What is ClaroBill going to make?

A consumer-facing web app where anyone with a medical bill can upload a
photo or PDF, get it analyzed for billing errors and overcharges within
a few minutes, and receive a plain-English report plus a ready-to-send
dispute letter they can mail to their hospital or insurer.

### Live in production today

**Bill capture and parsing.** Users upload a medical bill (PDF, JPG,
PNG) up to 20 MB. Google Cloud Vision OCRs the bill into text. A custom
parser extracts line items, where each item is a typed tuple:

`(CPT_or_HCPCS_code, description, service_date, quantity, unit_charge, total_charge, modifier, diagnosis_pointer)`

The parser handles row-major bills (proximity heuristic with ±3 line
tolerance) and column-interleaved bills (sequence-based fallback that
maps the *n*th unmatched CPT code to the *n*th unmatched dollar amount).

**Identity confirmation.** The app asks the user to confirm hospital,
insurer, plan, service dates, and patient name before running the
analysis. This catches OCR mismatches and lets us tag the bill with the
correct payer/plan for negotiated-rate lookups.

**Rules engine — 13 independent error checks.** Each CPT line is run
through every rule. Findings are deduplicated so total potential savings
can never exceed total charges:

| Rule | What it catches |
|---|---|
| `DUPLICATE_CHARGE` | Same CPT billed twice on the same date |
| `NCCI_UNBUNDLING` | Component CPT billed alongside a panel that includes it (CMS NCCI PTP edits, date-aware) |
| `REDUNDANT_CLINICAL_PAIR` | Curated payer-policy redundancies that aren't formal NCCI (OB ultrasound transabdominal+transvaginal, ABO+Rh, venipuncture+minimal E&M) |
| `MUE_EXCEEDED` | Quantity above the CMS Medically Unlikely Edit limit |
| `NON_PAYABLE_CODE` | CMS-flagged inactive (I), bundled (B), or non-covered (N) procedure codes |
| `TERMINATED_CODE_BILLED` | HCPCS Level II code billed after its CMS termination date |
| `ANESTHESIA_OUTLIER` | Implied base-units or total-units exceed clinical plausibility |
| `FACILITY_CHARGE_OUTLIER` | Hospital outpatient charge above OPPS Medicare cap × threshold |
| `AMBULANCE_CHARGE_OUTLIER` | Charge above CMS Ambulance Fee Schedule × threshold |
| `HOSPITAL_CHARGE_OUTLIER` | Charge above the hospital's own published gross charge from its MRF |
| `NEGOTIATED_RATE_EXCEEDED` | Charge above the exact negotiated rate the hospital has with the patient's specific insurer/plan |
| `NEGOTIATED_CEILING_EXCEEDED` | Charge above the highest negotiated rate any insurer pays at this hospital (fallback when exact rate isn't known) |
| `PRICE_OUTLIER` | Charge above Medicare benchmark × plan-type-aware threshold (1.05× for Medicare/Medicaid, 1.4–2.64× for commercial by service type) |

**AI-generated patient-facing content.** Gemini 2.0 Flash (primary)
writes a 2–3 sentence plain-English summary of the findings; Anthropic
Claude Sonnet is the automatic fallback if Gemini fails. A formal
dispute letter is generated with the patient's name, DOB, member ID,
today's date, and the provider's full mailing address auto-populated,
plus one numbered dispute paragraph per finding.

**Report delivery.** Letterhead-style PDF report (charges, findings,
savings totals). Editable DOCX dispute letter the patient can sign and
mail. Both delivered by email and downloadable from the dashboard.

**Pricing.** Five tiers based on potential overcharge size: Free for
clean bills, $14.99 / $79.99 / $129.99 / $199.99 for findings of
increasing magnitude. Currently in public beta — the Stripe paywall is
gated by an env var so users get full reports for free until GA.

### Being built right now

**The Phase 4 effective-dated price-transparency vault.** CMS rule
42 CFR 180 requires every U.S. hospital to publish a Machine-Readable
File (MRF) of its chargemaster + every payer's negotiated rates. There
are ~13,989 US civilian hospitals; ClaroBill is building a complete,
year-tagged copy:

- **Discovery pipeline** finds every hospital's MRF URL — Stages 1
  (CMS list) → 2 (NPI/website resolution) → 3 (Google Places paid
  lookup) → 4 (HTML crawl + depth-1 follow + curated system listings;
  60% hospital-level hit rate, 57,373 (hospital, MRF URL) pairs in
  `hospital_directory`).
- **Scraper** downloads each MRF (annual Feb 15 + mid-year Aug 15 —
  aligned with CMS's once-a-year republish rule).
- **Dual-write archiver** lands every MRF in
  `gs://mrf-archive-clarobill-prd/pricing-year={year}/{npi-or-ccn}/{sha256}.{ext}`
  with a sibling `.meta.json`, in a Coldline bucket with IAM-enforced
  no-delete (chain of custody — a patient's 2024 bill can be audited in
  2030 against the chargemaster that was actually in force).
- **Parser** loads each MRF into BigQuery `hospital_charges` with
  `pricing_effective_year` populated from JSON `last_updated_on`
  (best), HTTP `Last-Modified` (fallback), or calendar year (final
  fallback).
- **Append-only history** — old chargemasters are never deleted; the
  rules engine deduplicates at query time via `MAX(scraped_at)` per
  (hospital, code, payer, plan).

### Planned roadmap (consumer)

| Phase | Item |
|---|---|
| **5** | Cut over `rules_engine.py` from `hospital_charges_legacy_stale` (the renamed pre-Phase-4 table) to the new effective-dated `hospital_charges`. |
| 6 | Non-Medicare benchmarks — TRICARE rate integration, state-Medicaid rate scraping. |
| 6 | CSV-format MRF parser (currently we recognise + skip CSV; ~15-20% of hospitals publish in this format). |
| 6 | Headless-browser fallback for the ~10% of hospitals whose MRF link is locked behind client-side React SPAs. |
| 6 | Round-3 Stage 4 to lift the discovery hit rate from 60% toward 70%. |
| Ongoing | Sentry-monitored bug fixes; quarterly NCCI / annual CMS PFS / OPPS / Ambulance / HCPCS reference-data refreshes. |

### Future direction — B2B API

Once the consumer product is mature (post Phase 5), the same rules
engine gets exposed as a B2B API that hospital billing departments and
insurance claims-processing teams can plug into:

- **Hospital pre-bill QA** — billing departments POST a draft claim/
  bill to the API before it goes out the door; the API returns the same
  `BillingError` JSON the consumer report uses, so coders fix issues
  *before* the patient ever sees an inflated charge.
- **Insurance claim review** — payers' claims-processing systems POST
  inbound claims to the API in batch; results highlight which claims
  are worth manual review (NCCI violations, MUE overages, outlier
  charges, redundant clinical pairs the carrier's own policies deny).
- **Surface design** — REST endpoints for synchronous lookups, webhook
  callbacks for async batch processing, per-customer API keys with
  rate limits, per-call or volume-based pricing.
- **Architectural reuse** — the rules engine is already structured as
  pure functions taking parsed line items + reference data → typed
  errors. The B2B API just exposes those entry points behind
  authenticated HTTP. The consumer OCR/parser path stays consumer-
  only; B2B clients send already-parsed claim data.
- **Moat reuse** — same CMS NCCI / OPPS / MUE / HCPCS data, same
  effective-dated MRF vault, same curated REDUNDANT_CLINICAL_PAIR list.
  Build it once for consumers, monetize twice.

### Why ClaroBill matters

The U.S. medical-billing system has documented error rates of 7-50%
depending on the study. The data and tools to verify a bill exist (CMS
NCCI, OPPS, HCPCS, MRFs are all public), but a normal patient has no
realistic way to use them, and a hospital coder or claims processor
has no off-the-shelf cross-source rules engine. ClaroBill packages CMS
reference data, hospital-published price-transparency files, and AI
summarization into a 3-minute consumer experience today, and a B2B API
for healthcare-organization workflows tomorrow. Same rules. Same moat.
Two surfaces.

---

## Scientific basis — how does it work?

The product rests on a single observation: **U.S. medical bills are
computationally verifiable**. Every charge on a bill must be expressible
in a small set of standardised codes (CPT, HCPCS, ICD-10), and every
code has either a published price ceiling or a published rule that
constrains how it may be combined with other codes. Both the codes and
the rules are issued by federal agencies and made public. The science
of ClaroBill is the systematic application of those rules to a single
document.

The pipeline has four stages, each with a distinct epistemic basis.

### 1. Document understanding — extracting structured line items from an image

A medical bill arrives as either a PDF or a photograph. We use **Google
Cloud Vision OCR** to convert pixels into text with bounding-box
coordinates and confidence scores. A custom parser then extracts line
items, where each item is a tuple of:

`(CPT_or_HCPCS_code, description, service_date, quantity, unit_charge, total_charge, modifier, diagnosis_pointer)`

Two things make this non-trivial. First, the same bill format varies
enormously — Hopkins prints in column-major order, Sutter in row-major,
Kaiser embeds line items in a table-with-merged-cells layout. The
parser uses a two-pass strategy: a proximity heuristic (CPT code within
±3 lines of a charge column) for row-major bills, and a sequence-based
fallback that maps the *n*th unmatched CPT code to the *n*th unmatched
dollar amount in document order, for column-interleaved tables. Second,
real bills contain noise — ZIP codes that look like CPT codes, footer
totals that look like line charges, modifier strings like "ER" that
resemble English words. The parser uses a frozenset of ~200 valid CMS
HCPCS modifiers and address-context guards to filter these out.

This is the part of the system that most resembles a traditional ML
pipeline (OCR is a deep CNN), but the post-OCR work is rule-based, not
learned. We made that choice because medical billing has a closed
vocabulary (codes are enumerated), so a rule-based parser produces
predictable, auditable output that we can defend in a customer dispute.
A learned parser would be opaque to challenge.

### 2. Reference data — the corpus of "what should be true"

Once the bill is parsed, the question becomes: *for this CPT code, this
date, this hospital, this payer, this plan — what should the charge be?*
This is the part of the product where most of the engineering effort
goes, because the answer requires synthesising data from multiple
federal sources and cross-referencing them.

Five corpora, each refreshed on its own schedule:

**(a) CMS Physician Fee Schedule (PFS).** A national fee schedule,
updated quarterly, that publishes the maximum amount Medicare will pay
for ~10,000 CPT codes. Each rate is locality-adjusted via the
Geographic Practice Cost Index (GPCI). We load the full PFS into
PostgreSQL and resolve a 7-character locality code per bill from the
patient's state + county.

**(b) National Correct Coding Initiative (NCCI) edits.** CMS publishes
~5 million procedure-to-procedure (PTP) edit pairs and ~700,000
Medically Unlikely Edit (MUE) limits per quarter. A PTP pair says "if
you bill code A, you cannot also bill code B on the same date for the
same patient — B is bundled into A." An MUE limit says "the maximum
medically plausible quantity of code A on a single claim is N." Both
are date-aware: we use the bill's service date to select the correct
ruleset.

**(c) Outpatient Prospective Payment System (OPPS) caps and the
Ambulance Fee Schedule (AFS).** Two more service-specific fee schedules
with their own locality adjustments and update cycles.

**(d) Hospital Machine-Readable Files (MRFs).** Per CMS rule
42 CFR 180 (2021), every U.S. hospital must publish a JSON or CSV file
listing — for every CPT/HCPCS code it bills — its gross chargemaster
price, its discounted-cash price, and its negotiated rate with every
individual insurer and plan. ClaroBill operates a discovery pipeline
that finds each hospital's MRF URL by combining the CMS Provider of
Services file, the NPPES NPI Registry API, Wikidata SPARQL queries,
the Google Places API, and a web crawler that follows keyword anchors
from each hospital's homepage. Currently 6,994 hospitals × ~7 URLs each
= 57,373 (hospital, MRF URL) pairs. The MRFs are downloaded twice a
year (Feb 15 and Aug 15, after CMS's annual republish deadline),
parsed into BigQuery, and tagged with `pricing_effective_year` so that
a 2024 bill is always evaluated against the 2024 chargemaster.

**(e) Curated payer-policy redundancies.** A small (~10-pair)
hand-maintained allowlist of CPT pairs that commercial payers commonly
deny but that don't appear in CMS NCCI — e.g. transabdominal +
transvaginal OB ultrasound on the same day, ABO blood typing + Rh
typing as separate line items.

The discovery pipeline is intentionally redundant — multiple sources
converge on the same fact (a hospital's NPI, a hospital's website, an
MRF URL) so that one source's gap doesn't propagate. Year-partitioning
+ immutable Coldline storage of every MRF byte we've ever downloaded
means an audit performed in 2030 against a 2024 bill is reproducible
against the 2024 data — important for legal defensibility.

### 3. Rule evaluation — 13 independent error classes

The rules engine takes the parsed line items + the loaded reference
data and runs 13 detection rules. Each rule is a pure function that
takes the input and returns zero or more `BillingError` records. Rules
are independent — none depends on another's output — so the system can
be reasoned about and tested per-rule.

The pricing rules form a hierarchy of evidence strength. The strongest
is `NEGOTIATED_RATE_EXCEEDED` because it's the actual contracted dollar
amount for that exact patient's exact insurance plan — there is no
ambiguity. Next is `HOSPITAL_CHARGE_OUTLIER` because it's the
hospital's own published list price; charging above a hospital's own
published price is indefensible by them. Then `NEGOTIATED_CEILING_EXCEEDED`
(the highest negotiated rate any insurer pays at the hospital — a strong
signal but not patient-specific). Then the Medicare-relative rules,
which are population proxies, used with hedged language in the
patient-facing report.

A waterfall deduplication step ensures that potential savings reported
to the patient never exceed total charges: if a line item is fully
removed by a duplicate or NCCI finding, pricing rules on that line item
are suppressed.

### 4. Reporting — translating findings into actionable language

The 13-error output is summarised by Gemini 2.0 Flash (primary) with
Anthropic Claude Sonnet (fallback). Both write a 2-3-sentence
patient-facing summary and a formal dispute letter with one numbered
dispute paragraph per finding. The LLM is constrained: it receives the
structured `BillingError` records, never the raw bill, and is
instructed to write only what the deterministic rules already
established. This keeps the LLM in the narrow role of language
generation — never inference — and means a dispute letter never makes
a claim the rules engine didn't first compute.

### What this is and isn't, scientifically

ClaroBill is a **deterministic rules engine over public reference
data**, not a predictive model. The input is a bill; the output is a
set of formally-defined assertions ("CPT 99214 was billed at $X but the
hospital's published gross charge for this code is $Y, which is N%
lower"). Each finding cites its authority — CMS rule, hospital MRF,
CMS PFS — and is reproducible. The LLM is downstream and decorative.
The OCR is the only learned component; everything that affects a
finding's *truth value* is rule-based.

The validity of a finding rests on three claims:

1. The reference data is what it says it is. We trust CMS to publish
   what it publishes; we trust hospitals to publish what they publish
   (CMS rule mandates it; non-compliance is publicly enforced). The
   MRF archive's content-hash + Coldline + IAM-no-delete chain of
   custody means we can prove what data was in force on a given date
   years later.
2. The rules apply correctly. Per-rule unit tests (~155 today) and
   audit-by-comparison-to-known-flagged-bills check this.
3. The OCR captured the bill faithfully. This is the system's weakest
   scientific link — Google Vision is roughly 99% character-accurate
   on clean PDFs and ~95% on phone photos. We mitigate by asking the
   user to confirm hospital, plan, and dates before paying for a
   report (catches OCR mismatches early).

The product's scientific contribution isn't a new model. It's a
**systematic federation** of public datasets (CMS reference, hospital
MRFs, NCCI/MUE) and a **disciplined rules engine** that turns "is this
charge correct?" — a question a typical patient cannot answer — into a
deterministic computation. The hard engineering is the federation:
continuously discovering and parsing 14,000 hospitals' worth of
price-transparency files, year-tagging them so a 2024 bill is
evaluated against 2024 data, and refreshing the federal data on its
own quarterly cadence.

It is, in short, **the software that should already exist in every
patient-advocate's toolkit but doesn't**, because the data has only
been mandated public since 2021 and no consumer product has yet
stitched it together.

---

## Roadmap — time and money by stage

These are the stages between today's beta and the point where ClaroBill
is a fully launched consumer product with a B2B-ready engine. Times
assume a single full-time engineer. Money is direct cash cost (cloud
infrastructure, paid APIs, services), not opportunity cost or salary.

### Stage 1 — Phase 5 cutover: rules engine reads from new effective-dated `hospital_charges`

**Time:** 1 week
**Money:** $0

Single SQL change in `apps/engine/app/api/v1/bills.py:_load_negotiated_charges()`
and three sibling loaders, plus a fallback rule (if no row matches
`pricing_effective_year = YEAR(service_date)`, pick the nearest prior
year). Acceptance: 5 known-flagged historical bills produce identical
or improved findings against the new table.

### Stage 2 — Stripe paywall flip (beta → GA)

**Time:** 1 day
**Money:** $0 to flip; revenue starts.

Flip `BETA_MODE = false`. Set live Stripe API keys. The full 5-tier
pricing activates per the existing engine logic.

### Stage 3 — Bug-fix sweep + Sentry monitoring tuning

**Time:** 2 weeks
**Money:** ~$26/month (Sentry team plan; already paid)

Resolve every open Sentry issue; add OCR-confidence reporting; admin
metrics view. Acceptance: zero open Sentry issues with > 3 occurrences
in the trailing 14 days.

### Stage 4 — CSV-format MRF parser

**Time:** 2 weeks
**Money:** $0

15-20% of hospitals publish their MRFs in CSV. Sample 20 skipped CSVs,
cluster their headers into vendor buckets, author per-vendor column
maps. Acceptance: ≥ 80% of currently-skipped CSVs successfully populate
`hospital_charges`.

### Stage 5 — Stage 4 round 3 + headless-browser fallback

**Time:** 3 weeks
**Money:** ~$10/month additional (Playwright Cloud Run job)

Lift discovery hit rate from 60% to 75% via Playwright headless tier.
Acceptance: 70%+ hit rate, projected cost stays under $50/quarter.

### Stage 6 — TRICARE rate integration + state-Medicaid scrapers

**Time:** 4 weeks
**Money:** $0

TRICARE Maximum Allowable Charges + per-state Medicaid scrapers (top
10 states by enrollment). Acceptance: a TRICARE bill produces a
TRICARE-specific overcharge calculation.

### Stage 7 — Insurance card OCR improvements + dispute letter v2

**Time:** 2 weeks
**Money:** ~$50/month

Better card-front/back fusion; per-error legal-citation paragraphs;
Spanish-language version.

### Stage 8 — B2B API alpha (single design-partner customer)

**Time:** 6 weeks
**Money:** ~$50/month (API key management, audit logging)

REST endpoints for sync analysis, webhook callbacks for batch.
Acceptance: design partner uses the API in their pre-bill QA workflow
for ≥ 2 weeks with positive feedback.

### Stage 9 — B2B API public launch + pricing tiers

**Time:** 4 weeks
**Money:** ~$200/month additional (PagerDuty, monitoring)

Public docs, self-serve API key signup, 3-tier pricing, 99.5% uptime
SLA. Acceptance: 3 paying B2B customers using the API in production.

### Cost summary

| Stage | Time | Direct cost (one-time + recurring) |
|---|---|---|
| 1. Phase 5 cutover | 1 week | $0 |
| 2. Paywall flip | 1 day | $0 (revenue starts) |
| 3. Bug-fix + monitoring | 2 weeks | $0 (existing) |
| 4. CSV MRF parser | 2 weeks | $0 |
| 5. Stage 4 round 3 + headless | 3 weeks | $10/mo |
| 6. TRICARE + Medicaid | 4 weeks | $0 |
| 7. Insurance card + letter v2 | 2 weeks | $50/mo |
| 8. B2B API alpha | 6 weeks | $50/mo |
| 9. B2B API GA | 4 weeks | $200/mo |
| **Total to B2B GA** | **~24 weeks (≈ 6 months)** | **+~$310/mo recurring at end state** |

**Annual recurring infrastructure** at end-state: roughly $5,000-7,000/
year total. Mostly variable with bill volume; fixed floor ~$200/month.

The bottleneck is engineering hours, not capital. The reference data
is free. The compute is cheap and on-demand.

---

## YC June–July batch — Demo Day plan

Demo Day is roughly the third week of August. From batch start (early
June) that's ~12 weeks. With YC's gravity — focused engineering, peer
accountability, partner intros, and the implicit pressure to show
*traction*, not just a product — here's what I'd commit to ship.

### Week 1–2 — Phase 5 + flip paywall + start charging

- Phase 5 cutover (1 week compressed)
- Bug-fix sweep on Sentry, OCR-confidence reporting, admin metrics
- Flip Stripe out of beta. **First real revenue from real strangers.**

**Demo metric:** *N* paying customers since paywall flip, *$X* revenue,
*Y* dispute letters mailed.

### Week 3–4 — CSV MRF parser + Stage 4 round 3 + headless fallback

CSV unlocks ~15-20% of MRFs we currently skip. Stage 4 round 3 +
Playwright pushes hit rate from 60% to ~75%.

**Demo metric:** "ClaroBill has the largest year-tagged corpus of U.S.
hospital chargemasters outside of CMS itself: 75% of all 13,989
hospitals, fully searchable, immutably archived." Defensible moat in
one sentence.

### Week 5–6 — Marketing site + organic growth substrate

- Land a *Wall Street Journal* / *NYT* / *ProPublica* / *Slate* /
  *The Atlantic* health-policy reporter who's covered medical billing.
  Pitch: "We've made every U.S. hospital's chargemaster searchable;
  here are the most overcharged CPT codes by state."
- Reddit r/medicine, r/personalfinance posts authored by paid users.
- TikTok / IG creators in the medical-bill horror niche. Affiliate at
  30% rev share.
- SEO: 3 pillar articles on "is my medical bill correct," "how to
  dispute a hospital bill," "what is CPT 99214."

**Demo metric:** WAU, 7-day retention, organic vs paid acquisition split,
CAC:LTV ratio.

### Week 7–8 — TRICARE + state Medicaid for top 10 states

Widens audience from "people with commercial insurance" (~165M Americans)
to "people with any insurance" (~290M).

**Demo metric:** TAM expanded from 165M commercial-insured to 290M
total insured. Bill conversion rates by plan type.

### Week 9–11 — B2B API alpha with one design partner

YC partners introduce me to a friendly billing-department head, a
claims-processing engineer, anyone in the Cohere / Devoted Health /
Hims-style "healthcare-but-tech" ecosystem.

**Commit:** 1 signed B2B design-partner LOI by Demo Day for the API
alpha. Deliverable doesn't have to be GA-ready — just a 10-line POST
endpoint they're hitting against a sandbox, returning real
`BillingError` JSON.

**Demo metric:** "Design-partner LOI signed. Daily API calls: ___.
Errors flagged that the partner agrees are real: ___ %."

### Week 12 — Demo Day prep

Polish, rehearse the pitch, finalize the deck, line up follow-on
conversations.

### Demo Day pitch shape

> "Most U.S. medical bills have errors. CMS made the data needed to
> verify them public in 2021, but no one has assembled that data into
> a usable product. We have. We've built a federated corpus of ~14,000
> hospitals' published price-transparency files, the CMS coding rules,
> and a 13-rule engine that turns any bill into a deterministic dispute
> letter in 3 minutes.
>
> Today we have **[N] paying consumers**, **$X MRR**, and **growing
> W/W at Y%**. Our biggest realization in batch: the same rules engine
> pre-validates claims for hospital billing departments and insurance
> claims processors. We just signed our first design partner: **[hospital
> or payer name]**. They're flagging **[Z]% of their pre-submission
> claims** with errors our engine catches that their internal systems
> miss.
>
> The consumer business has a $0–$200 per-bill price point, ~$XX-billion
> TAM, and clean unit economics. The B2B API has $50k/customer/year
> minimum to $1M/customer/year enterprise, ~$YY-billion TAM, and 90%
> gross margins.
>
> We're raising **$X.X M** to: hire two engineers, expand the MRF
> corpus to all 14,000 hospitals at 90%+ coverage, and convert the
> design partner's LOI into a paid contract before YC ends."

### Realistic numerical targets at Demo Day

| Metric | Realistic | Stretch |
|---|---|---|
| Paying consumers | 200 | 800 |
| Consumer MRR | $4k | $25k |
| Bills processed lifetime | 1,500 | 5,000 |
| Hospital coverage (Stage 4 hit rate) | 75% | 80% |
| Hospitals fully scraped | 8,000 | 12,000 |
| B2B design partners | 1 LOI | 1 paid + 2 LOI |
| Press hits | 1 article | 3 articles + 1 podcast |

### What I would NOT commit to

- **Building the B2B API to GA.** Stage 9's 4 weeks is real; ramping
  to multiple paying customers means hiring, sales work, contracts,
  SOC 2 (3-6 month project). Demo Day is alpha-with-LOI, not GA.
- **A second engineer hired by Demo Day.** Hiring takes ~6-10 weeks of
  interviewing + closing. Realistic to *start* hiring during batch
  (week 4-6) and have an offer accepted with a September start.
- **Profitability.** Demo Day shows the unit economics, not absolute
  profit.

### Why this is feasible inside YC

The product is already 70% built. Phase 4 — the hardest single thing —
is shipping today. The 30% remaining is monetization, marketing, B2B
sales surface area, and last-mile reliability. None requires inventing
new technology; it requires execution and access. YC supplies access
better than any other accelerator.

The capital costs are tiny. YC's $500k SAFE plus standard $25k partner
fund is more than enough to cover 12 weeks at sane burn, hire #2, and
have 12 months of runway after Demo Day.

The market is forced into us by regulation. CMS's Hospital Price
Transparency rule (2021) is the law that makes the moat possible. CMS
keeps tightening enforcement. Every quarter that passes makes our
reference corpus more complete.

---

## Regulatory exposure

**Short answer: no FDA approval required**, but several adjacent
regulatory regimes apply and need active compliance work.

ClaroBill is software that analyzes already-issued medical *bills* and
detects coding/pricing errors. It does not diagnose, prevent, monitor,
or treat any medical condition. It does not influence the clinical
care a patient receives. It is therefore explicitly outside FDA's
medical-device jurisdiction.

### 1. FDA — does not apply

Medical-device regulation under 21 U.S.C. §§ 351, 360 applies to
products *"intended for use in the diagnosis of disease or other
conditions, or in the cure, mitigation, treatment, or prevention of
disease."* ClaroBill matches none of those.

The closest FDA category that *could* apply to a healthcare-adjacent
SaaS is **Software as a Medical Device (SaMD)** under FDA's 2017
guidance. But SaMD requires the software to make medical decisions or
provide clinical recommendations. ClaroBill does neither. Even the
**Clinical Decision Support (CDS) software** carve-out under the 21st
Century Cures Act (§3060) doesn't apply because we're not in the
clinical-decision space at all.

**Bottom line:** zero FDA pathway, zero FDA cost, zero FDA timeline.
Same regulatory category as Mint or Credit Karma — financial software
analyzing financial documents. We will publish this analysis explicitly
on our marketing site and in user-facing copy ("ClaroBill is a
billing-analysis tool, not medical advice").

### 2. HIPAA — applies in our specific role

In the **consumer use case**, patients voluntarily upload their own
bills as private individuals; HIPAA doesn't follow the data once a
patient handles it themselves. We are neither a covered entity nor a
business associate.

In the **B2B API path**, hospital billing departments and insurance
claims teams are covered entities. When they send us claims data, we
*become* their business associate. We must:
- Sign a **Business Associate Agreement (BAA)** with each B2B
  customer before transmitting any PHI.
- Implement HIPAA Security Rule administrative, physical, and
  technical safeguards.
- Have a written breach-notification process (60-day window).
- Maintain audit logs of all PHI access for 6 years.

**What we already have / need:**
- BAA template — already drafted (~$1,500 in attorney time remaining).
- All PHI-bearing data encrypted at rest (Supabase) and in transit
  (TLS 1.3).
- All GCP services we use sign HIPAA-eligible BAAs by default.
- Audit logging for `bills` table reads/writes — partially done.
- No PHI in logs (CLAUDE.md Rule 9 enforces this).
- HIPAA Security Risk Assessment — first one ~$5,000 with a
  healthcare-compliance consultant; subsequent annuals ~$2,500.

**Time and money:** ~3 weeks of engineering + ~$10,000 over the next
12 months in legal + assessment fees. Required before the first B2B
API customer signs.

### 3. SOC 2 — required by enterprise B2B customers

Not regulatory — market-driven. Every enterprise hospital or insurance
customer requires SOC 2 before signing.

**Process:**
- **Type I** audit (snapshot in time): ~3 months prep + 1 month audit.
  ~$8,000–$15,000.
- **Type II** audit (6-12 month operational evidence): ~$25,000–$35,000.

**Realistic plan:** Use Vanta or Drata ($10,000–$15,000/year) to
automate evidence collection. Standard practice for modern startups.
- **Year 1 cost:** ~$20,000 ($10k Vanta + $8k auditor)
- **Year 2 cost:** ~$15,000

Start SOC 2 work in parallel with Stage 8 (B2B API alpha).

### 4. State unauthorized practice of law (UPL) — flagged, mitigated, low risk

Our position: the dispute letter is a **template-filled document with
deterministic fields**, not custom legal counsel. Same regulatory
category as LegalZoom's templates — repeatedly upheld since *Janson v.
LegalZoom* (W.D. Mo. 2011). Our user-facing copy explicitly states:
"ClaroBill is not a law firm and does not provide legal advice."

**Risk:** low. **Cost:** ~$2,000 attorney time to review the dispute
letter template once before GA.

### 5. State consumer-protection / debt-collection / credit-reporting laws

We are NOT a debt collector under FDCPA, NOT a credit-repair
organization under CROA. We honor truth-in-billing in marketing copy
and CCPA + state privacy laws. Ongoing cost ~$5,000/year for
privacy-policy refresh.

### 6. Insurance — recommended

- **General commercial liability + Errors & Omissions (E&O)**:
  ~$3,000–$6,000/year for a $1M/$2M policy.
- **Cyber liability**: ~$5,000–$10,000/year for $1M coverage with
  HIPAA endorsements.

Required by most enterprise B2B contracts. Bought the day the first
B2B contract goes paid.

### Total regulatory cost summary

| Domain | Approval needed? | Time | Cost (Year 1) | When |
|---|---|---|---|---|
| FDA | **No** | — | $0 | Never |
| HIPAA Privacy/Security | Self-attestation; per-customer BAA | 3 weeks eng + 1 week legal | $10,000 | Stage 8 |
| SOC 2 Type I | Audit (not regulator) | 3 months automated + 1 month audit | $20,000 | Start Stage 8 |
| State UPL | Mitigated by template framing | 0 weeks dedicated | $2,000 attorney | Pre-Stage 2 |
| Consumer privacy | CCPA + state laws | Annual refresh | $5,000 | Ongoing |
| Insurance (E&O + cyber) | Market-driven | 1 week to bind | $10,000–$16,000 | First B2B contract |
| **Total Year 1** | | **~6 weeks of engineering, mostly parallel** | **~$50,000** | All before B2B GA |

**For YC Demo Day specifically:** none blocks consumer launch. The
consumer product ships and charges before any of these are complete —
only HIPAA + SOC 2 prep needs to be *underway* before a B2B
design-partner LOI signs in Week 9-11.

**Honest summary:** *"We're regulation-light by design. The hardest
single regulatory thing in our first year is achieving SOC 2 Type I,
which gates B2B sales but not consumer revenue. Total cost ~$50k,
mostly parallel to engineering, entirely compatible with shipping
consumer revenue from Week 2 of the batch."*

---

## Experimental data

Honest framing: ClaroBill isn't a research-stage product where the
central question is "does the underlying mechanism work?" — it's an
engineering product over public reference data, where the mechanism
(CMS rules, hospital MRFs) is established. The relevant experimental
questions are downstream:

1. Can the system extract structured data from a real bill reliably?
2. When the rules engine fires, are the findings actually correct?
3. When real consumers use the product, do their bills produce
   findings whose dollar values are credible to a billing professional?
4. Will real consumers pay for the output?

### Evidence that *the mechanism* works (ambient)

The peer-reviewed literature on U.S. medical billing error rates is
substantial:

- **Medical Billing Advocates of America (2014, 2016, 2019):** ~80%
  of all hospital bills contain at least one error.
- **Becker's Hospital Review (2017):** studies cite 7–80% error rates
  depending on definition; Hopkins-led claims-data audit found ~30%
  of claims contained billable errors.
- **HHS-OIG reports (2018, 2021, 2023):** tens of billions of dollars
  per year in improper Medicare payments, of which ~30% are coding/
  billing errors (CMS CERT program).
- **CMS NCCI enforcement statistics:** hundreds of millions of dollars
  in NCCI-related claim adjustments per year — the rules catch real,
  large-scale errors.

This establishes that the *problem space* is large and well-
characterized. We're not testing whether NCCI rules find errors — CMS
already proved that. We're testing whether our implementation produces
correct findings on a consumer bill.

### Component-level test evidence (extensive)

**195 unit and integration tests pass** against the engine and pipeline:

- **NCCI tests** validate that bundled CPT pairs are flagged and that
  all five override modifiers (59, XE, XS, XP, XU) correctly suppress
  flags. Run against real fixture pairs from actual CMS NCCI quarterly
  files.
- **Pricing-rule tests** verify threshold math, plan-type-aware
  multipliers, locality-adjusted Medicare lookups, waterfall
  deduplication.
- **Parser tests** include realistic OCR fixtures with known-correct
  line-item extractions, covering Hopkins-style column-major and
  Kaiser-style row-major bill layouts.
- **REDUNDANT_CLINICAL_PAIR rule tests** validate against curated
  pairs with known clinical-policy citations.

These demonstrate the *implementation* matches the rules. Necessary
but not sufficient.

### Real-data validation (limited but pointed)

- **Saint Michaels Medical Center (NPI 1568825545)** end-to-end smoke
  test: a single hospital's MRF was scraped, parsed, and loaded into
  `hospital_charges` with `pricing_effective_year=2024`. **214,613
  charge rows landed correctly** — every row tagged with the right
  year, NPI, hospital, with provenance preserved. Proves the
  data-pipeline architecture is sound at full hospital scale.
- **Pre-launch beta cohort:** ~30 real medical bills uploaded by
  consenting beta users.
  - ~80% produced at least one detected error.
  - Findings included the full rule mix — duplicates, NCCI unbundling,
    price outliers, MUE violations, terminated codes.
  - **Total dollars flagged across 30 bills: ~$11,000 in potential
    overcharges**, individual bills $0 (clean) to $1,800.
  - Too small for statistical claims and self-selected, but confirms
    real bills produce findings reviewable by a billing professional.

### Bug-discovery feedback as evidence

The bugs we found and fixed in the last 30 days were all empirical:

- UTF-8 BOM bug — would have lost 100% of Saint Michaels' data.
- Streaming-buffer DML bug in `mrf_archive_index`.
- Schema-drift bug between parser and BigQuery table.
- Dispute-letter token-truncation bug.
- NCCI misattribution issue with 76817+76801.

Each surfaced from real bills against real rules and was fixed +
validated. The testing apparatus works.

### What we don't yet have

1. **No professionally-reviewed adjudication.** Need a board-certified
   medical coder to score 50 bills' findings as correct/incorrect/
   ambiguous, producing precision/recall numbers. ~$5,000 for ~50
   hours at $100/hr. **First experiment in YC Week 1.**
2. **No randomized A/B evidence** that ClaroBill users recover more
   money than non-users. 60-90 days per cohort because dispute cycles
   are slow.
3. **No third-party comparison study** vs LemonAid / Goodbill /
   Resolve / Optum / Cotiviti.
4. **No live B2B validation.** First design-partner LOI in YC Week
   9-11 is the experiment that validates the B2B value prop.

### Sufficient for / not sufficient for

**Sufficient for:**
- Shipping the consumer product to GA with confidence.
- Charging real consumers.
- Defensible technical pitch for YC.

**Not yet sufficient for:**
- Quantitative claims like "ClaroBill recovers $X on average per bill."
- Quantitative precision/recall claims.
- Closing a sale to a sophisticated B2B customer demanding validation
  against their own claims data.

### Experiments planned during YC

| Experiment | Method | Cost | Time | What it proves |
|---|---|---|---|---|
| **Coder adjudication of 50 bills** | Hire a board-certified coder; double-blind; per-finding score | $5,000 | 3 weeks | Precision/recall numbers |
| **Beta-cohort dispute outcomes** | Track 50 beta users' resolutions for 60 days | $0 | 60 days, background | Median dollars actually recovered |
| **Sutter-style cross-validation** | Audit our rule outputs against 5 large hospitals' published pages by hand | $0 | 1 week | Data we ingested matches what hospitals published |
| **Design-partner pre-bill QA validation** | B2B alpha customer compares our findings on N pre-bill claims against their internal scrub | $0 (their effort) | 4 weeks during alpha | B2B value proposition |

Three of four cost ~$0 — labor experiments, not infrastructure spend.

### Honest summary for an investor

> "We have proven the system can extract data from a real bill, apply
> the rule library, and generate findings whose dollar values are
> credible to a billing professional. We have not yet quantitatively
> measured precision against an expert-coded ground truth — that's a
> $5,000 experiment we'll run in Week 1 of YC. We have not yet
> measured downstream dispute-recovery outcomes — that's a 60-day
> experiment running in the background of the batch. We have not yet
> validated B2B value — that's the design-partner LOI in Week 9-11."

Engineering evidence: extensive. Real-data validation: pointed but
limited. Quantitative ground-truth evidence: planned, budgeted, not
yet collected. The path from "system works on test cases" to "system
produces measurable consumer or B2B value" is an engineering path,
not a research one.

---

## Competitors — and what we understand that they don't

ClaroBill sits at an unusual intersection: medical-bill review (a
30-year-old service industry), price-transparency data (a 4-year-old
regulatory moat), and AI-driven document analysis (a 2-year-old
technical moat). Most competitors specialize in one of these three.

### 1. Direct consumer competitors — bill-review SaaS / apps

- **Goodbill** (~2020). Photo-uploads, contingency-fee model (50% of
  recovered overcharges). Backed by GV. Manual coder review with
  software assist; no public-facing rules engine; no MRF data
  ingestion that we can see.
- **Resolve Medical Debt** (~2019, YC W19). Charges flat or
  contingency for negotiation. Positioned more as debt-relief than
  error-finding.
- **Compose.ly / Bill Advocate / Health Bill Advocates.** Older,
  services-led. Human medical billing advocates ($35-100/hr). High
  cost per bill, slow turnaround, excellent at high end but
  unscalable.
- **Medical Cost Advocate / ClearHealth Costs / Castlight /
  Healthcare Bluebook.** Focused on *prospective* shopping, not
  *retrospective* error detection. Adjacent space.

**What they're missing:**
- **MRF data at scale.** None ingest the CMS price-transparency files
  systematically. Goodbill and Resolve appear to use generic Medicare
  benchmarks — the weakest of our 13 rules. We have eight stronger
  benchmarks (NEGOTIATED_RATE, HOSPITAL_CHARGE, NEGOTIATED_CEILING).
  The MRF data didn't exist as a queryable corpus until ~2022; all
  competitors were architected before this data was real.
- **Effective-dating.** None track which chargemaster was in force on
  the bill's actual service date. Our `pricing_effective_year`
  partition exists specifically for this.
- **Coverage breadth.** Existing services skip radiology, lab,
  ambulance, anesthesia bills. Our 13 rules cover the full CMS
  taxonomy.
- **Determinism + auditability.** Goodbill produces opaque human
  assertions. Ours come with a cited authority and SQL trace — which
  CMS rule, which row of which hospital's MRF, which version of NCCI.
  The patient with a deterministic citation wins more disputes.

### 2. Hospital-side / payer-side enterprise software (B2B competitors)

- **Optum / Change Healthcare / Cotiviti / Conduent / Multiplan.**
  Multi-billion-dollar revenue. Pre-bill QA for hospitals or post-pay
  claim review for insurers. The market we'd enter via Phase 5+ B2B
  API.
- **Apixio / Komodo Health / Datavant.** Adjacent, mostly clinical-
  data analytics — not billing-error detection.
- **Internal hospital revenue-cycle teams** with home-grown tools.
  Old, brittle, focused on getting claims paid quickly (not
  correctly), no real-time MRF cross-referencing.

**What they're missing:**
- **The patient as a customer.** Every B2B competitor sells to the
  institution that issued the bill. They have no incentive to surface
  errors that *help the patient* and *hurt the hospital's revenue*.
  ClaroBill's consumer business creates a wedge — patient-side
  findings establish the rule precision and dollar-recovery numbers
  we'll pitch to B2B customers as "your internal scrubbers don't
  catch X% of errors that our system catches."
- **Real-time MRF cross-referencing.** Internal scrubbers validate
  against contracted rates and CMS NCCI. They don't cross-reference
  against the hospital's own published gross-charge MRF — that data
  didn't exist when scrubbers were built. A hospital is currently in
  the awkward position of (a) publishing an MRF saying gross charge
  for CPT 99214 is $350, while (b) sometimes billing $500, because
  (c) its internal scrubber doesn't know about (a). We catch that
  gap.
- **AI-native document handling.** Optum and Cotiviti's products
  were built before LLMs. Their ingestion paths assume structured EDI
  837 inputs, not photographed bills or PDF EOBs. We can ingest
  *anything* — phone photo, scanned PDF, CSV exported from MyChart —
  and produce structured line items.

### 3. Adjacent-space — CarePricer, GoodRx, RxSaver

Prospective shopping tools. They're solving "how do I save before I
get care?" — we're solving "how do I find errors in care I already
received." Same TAM in spirit, different problem.

### 4. Lay-press / nonprofits — Patient Advocate Foundation, RIP Medical Debt

Not competitors; potential partners. Inbound population overlaps with
ours.

### 5. The "do nothing" competitor

The largest competitor by far. **The default behavior of >95% of
patients with a billing error is to do nothing.** Pricing, copy, and
positioning have to acknowledge this — the user's mental comparison
isn't ClaroBill vs Goodbill, it's ClaroBill vs "writing a check and
moving on."

### What we understand that they don't

#### 1. The MRF rule changed the game in 2021, and nobody's fully picked it up

CMS rule 42 CFR 180 went into effect Jan 1 2021. By 2025 the data is
there for ~85% of hospitals. **This is a $0-cost public dataset that
nobody systematically aggregates.** Competitors before 2021 are
architected around a world without this data. Pivoting requires
non-trivial engineering (we have ~57,000 hospital-URL pairs after
months of discovery work). Competitors after 2021 are venture-backed
marketing engines that haven't done the underlying data engineering.
**We have, and the moat compounds quarterly as CMS tightens
enforcement.**

#### 2. The right unit of analysis is the (CPT, payer, year) triple, not just the CPT code

Every existing competitor reasons about CPTs in isolation —
"is CPT 99214 priced reasonably?" — using Medicare benchmarks or
generic regional averages. **The actual right question:** "for this
CPT, this hospital, this insurer, this plan, this service year, what
is the contracted price, and is the bill above that price?" Our
schema is built around exactly this: `hospital_charges` keys are
`(hospital_npi, code, payer_name, plan_name, pricing_effective_year)`.
Goodbill's public materials suggest they index on `(hospital_name,
code)` — two dimensions, not five.

#### 3. The consumer business is a wedge for the B2B business, not the endgame

Existing consumer-facing bill-review startups treat the consumer as
the customer and stop there. **We see the consumer business as a way
to generate ground-truth precision/recall data on every CMS rule, fed
by real bills, validated by real disputes.** Once we have N=10,000
consumer bills with 100,000 findings of which X% were accepted by
hospitals on dispute, we have something no B2B competitor can buy: a
calibrated, real-world-validated rules engine. The consumer business
is both a revenue stream and the training data factory for B2B.

#### 4. Determinism beats AI for legal-defensibility

Every billing-error tool in the market is moving toward "AI looks at
your bill and tells you what's wrong." Wrong trade-off. **A patient
disputing a $500 charge needs a citation, not a prediction.** Saying
"our AI flagged it" is useless to a hospital billing department.
Saying "your bill of $500 for CPT 99214 exceeds your hospital's own
published gross charge of $350 from the MRF dated 2024-01-15, per
CMS rule 42 CFR 180.50" is impossible to ignore. We use AI for the
cosmetic layer (dispute-letter prose); findings are deterministic,
citable, reproducible.

#### 5. The market is bigger than "people who think to use a bill-review service"

Existing competitors market to patients who actively suspect their
bill is wrong. TAM measured in a few hundred thousand per year.
**Actual TAM is anyone who receives a medical bill** — ~290 million
Americans annually. The competitors are fighting over the suspicious
cohort; we want to convert the assuming cohort by making error-
checking a default 30-second action. That's why the pricing tiers go
down to $0.

### Distillation

> The competitors are competing for patients who already think they
> have a problem. We're competing for patients who don't yet know they
> have one — and we have the only architecture that scales to all of
> them, because we did the data-engineering work to ingest CMS's
> price-transparency mandate at scale, which is the moat that
> compounds.

---

## Equity ownership at company formation

The company is not yet incorporated. At formation we will file as a
**Delaware C-Corporation** named **ClaroBill, Inc.**, separate from
any pre-existing operating LLC.

### Founder

**Sandra Jirongo — Founder & CEO.**
Equity at founding: **100% of issued common stock.**

I am the sole founder. I conceived the product, wrote essentially all
the code, built the data pipelines, made every architectural decision,
and own all customer relationships, vendor accounts, GCP / Supabase /
Stripe / domain assets to date. Title is **CEO** because at this stage
the role spans product, engineering, sales, fundraising, and
operations.

### Founder vesting

Standard **4-year vesting with a 1-year cliff**, beginning at
incorporation. Required by YC and by every credible early-stage
investor. **100% acceleration on a "double-trigger"** (acquisition +
termination without cause). No single-trigger acceleration.

### Authorized shares + initial issuance

**10,000,000 shares of common stock** authorized at incorporation:

| Holder | Shares | Fully-diluted % |
|---|---|---|
| Sandra Jirongo (founder common, vesting) | 8,000,000 | 80% |
| Equity incentive pool (unallocated) | 2,000,000 | 20% |
| **Total authorized + issued** | **10,000,000** | **100%** |

### After YC SAFE (post next priced round, illustrative)

| Holder | Pre-seed % (post-conversion) |
|---|---|
| Sandra Jirongo | ~63% |
| Employee/advisor pool (post-refresh) | ~17% |
| YC ($500k SAFE → equity) | ~7% |
| Seed lead + follow-on investors | ~13% |

### Why these specific numbers

- **80/20 founder/pool at incorporation** matches YC pre-seed
  convention. The 20% pool gives room to hire ~3-5 senior people
  before needing to refresh.
- **4-year vesting / 1-year cliff for sole founder** is required by
  YC SAFE and protects the company.
- **83(b) election within 30 days** of issuance — the single most
  important tax decision a founder makes at incorporation. Saves
  millions over the company's lifetime.
- **Delaware C-Corp** because YC SAFEs only convert cleanly into a
  C-Corp's preferred stock. LLCs require an expensive conversion
  before any priced round.
- **Separate entity** from any pre-existing LLC. Founder IP
  Assignment Agreement at incorporation transfers all pre-
  incorporation IP (code, trademarks, domains, GCP project, customer
  list) to ClaroBill, Inc.

### Formation checklist

1. File Delaware Certificate of Incorporation ($89 + $50 expedited).
2. Adopt corporate bylaws (YC-compatible template).
3. Appoint myself as sole director and officer (CEO).
4. Issue 8,000,000 founder shares with Restricted Stock Purchase
   Agreement specifying vesting. Pay par value (~$800).
5. **File 83(b) election** within 30 days. Certified mail.
6. Adopt 2026 Equity Incentive Plan (reserves the 2M-share pool).
7. Sign Founder IP Assignment Agreement.
8. Open Mercury or Brex business bank account.
9. Apply for EIN.
10. Issue YC SAFEs once accepted.

**Total cost at formation:** ~$2,000-5,000 via Stripe Atlas (~$500),
Clerky (~$300 + IP-assignment template), or Cooley/Gunderson/Wilson
Sonsini (~$5k flat, often deferred until priced round).

**Time:** 5-10 business days, parallelizable with other YC week 1
work.

### Pitch wording

> "ClaroBill is not yet incorporated. At formation we will file as a
> Delaware C-Corp with 10 million authorized shares. Sandra Jirongo,
> sole founder and CEO, will hold 8 million shares (80% fully-
> diluted), subject to standard 4-year vesting with a 1-year cliff
> and double-trigger acceleration. The remaining 2 million shares
> (20%) will be reserved in an unallocated equity incentive pool for
> future employees and advisors, governed by a standard 2026 Equity
> Incentive Plan. The structure is designed to be YC-SAFE-compatible
> from day one."

---

## Why Oakland?

The honest framing: **the company doesn't *need* an HQ at this stage**
— it's a Delaware C-Corp by legal structure, my engineering work runs
from a laptop, and our customers are nationwide. But every company
eventually picks a "where we're based" answer. Oakland is the right
answer.

### 1. I'm already here

I live in Oakland. The product was built in Oakland. Saying the
company is "based in Oakland" names the place where the work has been
happening. Picking a SoMa coworking space to sound techie burns cash
on rent we don't need.

### 2. Bay Area without the Bay Area cost

Oakland gives all the practical benefits of being a Bay Area
healthtech startup — proximity to YC's office in Mountain View
(35 min), UCSF (30 min), Stanford Medicine (45 min), dozens of major
hospital systems, and the entire Sand Hill Road investor stack —
without paying San Francisco rent prices, San Francisco salary
expectations for hires, or the SF gross-receipts tax.

### 3. Kaiser Permanente is headquartered in Oakland

Kaiser's national HQ is at **One Kaiser Plaza** at 8th and Broadway —
a 12-minute drive from where I live. Kaiser is the **largest
non-profit integrated health system in the U.S.**, ~40 hospitals,
~12.7 million members. They publish MRFs for every hospital. They
have an enormous claims-processing operation. They are exactly the
kind of organization where a B2B API design partner could plausibly
come from.

### 4. Local hospital systems

UCSF Benioff Children's Oakland, Highland Hospital (Alameda Health),
Sutter's Alta Bates Summit Medical Center — all within a 15-minute
drive. For a product that needs hospital billing-department design
partners, having local hospitals available for in-person conversations
matters. Phone calls and Zoom intros only get you so far; a visit
closes design-partner deals.

### 5. The civic positioning is right

ClaroBill's product story has a populist, pro-consumer flavor —
helping ordinary people fight medical-billing errors. **Oakland has a
long civic identity around fighting predatory financial practices.**
Congruent with what ClaroBill does. When a journalist writes the
inevitable "scrappy Oakland startup takes on hospital billing
departments" article, the framing is more authentic than "another
SoMa SaaS."

### 6. Talent pool

Oakland's tech talent pool is real and growing. Healthcare-engineering
specifically has presence here (Kaiser, BlueShield of California,
Devoted Health, Hims, Lyra, Headway, Olive AI alumni). **East Bay
hires typically have lower comp expectations** (15-25% delta on senior
engineers at the same caliber) and lower attrition because commutes
are sane.

### 7. Practical operational

- Delaware incorporation + California operating presence is the
  standard YC-ready setup. Register as a foreign entity, pay state
  franchise tax (~$800/year minimum).
- No commute (home office today; East Bay central enough for future
  hires).
- YC's office is in Mountain View, not SF. The "be near YC" argument
  doesn't favor SF — Mountain View is closer from Oakland (35 min
  via BART + Caltrain) than from much of SF.

### Pitch wording

> "ClaroBill is based in Oakland, California. The founder lives and
> works here; the company will register as a foreign entity in
> California upon Delaware incorporation. Oakland gives us proximity
> to Kaiser Permanente's headquarters (an obvious B2B API design-
> partner target), three local hospital systems available for in-
> person outreach, the Bay Area investor stack within 45 minutes, and
> a meaningfully lower cost basis for our first hires than San
> Francisco — without sacrificing any of the operational advantages
> of being in the Bay Area healthtech ecosystem."

---

## Revenue model — how and how much

Two revenue lines: **per-bill consumer payments today**, **per-call
B2B API contracts post-Demo Day**. Both economic models are clean
(high gross margin), and the numbers below are bottom-up estimates
from real population statistics, real CMS error-rate research, and
real comparables in consumer-finance and healthtech-API spaces.

### Revenue line 1 — Consumer pay-per-bill

**Pricing tiers** (size of detected overcharge):

| Tier | User's bill total | Price |
|---|---|---|
| Clean Bill | $0 found | **Free** |
| Small Win | < $100 found | **$14.99** |
| Standard Fix | $100–$1,000 found | **$79.99** |
| Major Fix | $1,000–$5,000 found | **$129.99** |
| Heavy Hitter | > $5,000 found | **$199.99** |

User pays *after* seeing dollar value of findings — strong incentive
because they're paying for a known, tangible result. **ARPU lands
around $50–$60** based on beta distribution.

#### Unit economics per consumer bill

| Cost item | Per-bill estimate |
|---|---|
| Google Cloud Vision OCR | $0.0015 |
| Gemini 2.0 Flash (summary + letter) | $0.003 |
| BigQuery scan + Cloud Run engine compute | $0.005 |
| Stripe fees (2.9% + $0.30 on $50 ARPU) | $1.75 |
| Email delivery (SendGrid) | $0.001 |
| **Total variable cost** | **~$1.76** |
| **Gross margin per paying bill** | **$48.24 (~96.5%)** |

96.5% gross margin matches Mint, Credit Karma, GoodRx — software-
financial products with public reference data and AI-driven
processing.

#### Conversion and TAM

- ~290M Americans receive at least one medical bill annually (NHIS /
  KFF data).
- ~70% of bills have at least one billable error (CMS-CERT, Medical
  Billing Advocates). Conservatively call it 50%.
- Average detected overcharge in our beta cohort: ~$370.

| | TAM | SAM (5yr) | SOM (3yr) |
|---|---|---|---|
| Bills | 435M/yr | ~30M/yr | 300k/yr |

#### Three-year consumer projection scenarios

|  | Year 1 (post-GA) | Year 2 | Year 3 |
|---|---|---|---|
| **Low** — 1k bills/mo by mo 12, 40% paid conversion | ~5k paid bills | ~25k | ~75k |
| **Mid** — 5k bills/mo by mo 12, 50% paid conversion | ~25k paid bills | ~120k | ~400k |
| **High** — 20k bills/mo by mo 12, 55% paid conversion | ~100k paid bills | ~500k | ~1.5M |

At $50 ARPU:

| Scenario | Year 1 ARR | Year 2 ARR | Year 3 ARR |
|---|---|---|---|
| Low | $250k | $1.25M | $3.75M |
| **Mid** | **$1.25M** | **$6M** | **$20M** |
| High | $5M | $25M | $75M |

**Mid scenario** assumes a meaningful press hit in first 6 months,
3-5x word-of-mouth from beta users, TikTok / IG creator partnerships
converting at 1-2%, SEO ranking for ~30 long-tail queries.

**High** requires an additional growth lever — Mint plug-in, Credit
Karma offer, employer benefit, or insurer member benefit dropping a
one-click "check this bill" button.

### Revenue line 2 — B2B API (post-Demo-Day, year 2+)

**Pricing structures:**

- **Hospital billing departments** (pre-bill QA): $0.05–$0.10 per
  claim or $50k–$500k/year subscription.
- **Insurance claims-processing teams** (post-claim review):
  $0.05–$0.10 per claim or $100k–$1M/year enterprise.

Anchored to comparables — Optum's claim-review charges mid-five to
seven figures per customer per year. We're a smaller, faster-
onboarding alternative.

#### B2B unit economics per API call

| Cost item | Per-call estimate |
|---|---|
| BigQuery scan (small) | $0.0005 |
| Cloud Run engine compute | $0.002 |
| **Total variable cost** | **~$0.0025** |
| **Gross margin at $0.05/call** | **~95%** |

Annual subscriptions: ~98% gross margin (essentially fixed support +
SOC 2 + cloud overhead).

#### B2B TAM

- ~6,100 short-term acute-care hospitals in the US.
- ~900 health insurance companies.
- ~1.2 billion claims processed annually.

By year 5 capturing 100 hospital customers averaging $100k/year + 10
insurer customers averaging $500k/year:
- Hospital revenue: $10M ARR
- Insurer revenue: $5M ARR
- **B2B total: $15M ARR by year 5** at modest penetration (~1.6% of
  US hospitals, 1% of US insurers).

#### B2B three-year projection

|  | Year 2 | Year 3 | Year 4 |
|---|---|---|---|
| Low | 3 customers, $200k ARR | 10 customers, $1M ARR | 30 customers, $4M ARR |
| **Mid** | **5 customers, $500k ARR** | **20 customers, $3M ARR** | **60 customers, $12M ARR** |
| High | 10 customers, $1.5M ARR | 40 customers, $8M ARR | 120 customers, $30M ARR |

### Combined revenue trajectory (mid scenario)

| Year | Consumer ARR | B2B ARR | **Total ARR** |
|---|---|---|---|
| 1 (post-GA, late 2026) | $1.25M | $0 | **$1.25M** |
| 2 (2027) | $6M | $500k | **$6.5M** |
| 3 (2028) | $20M | $3M | **$23M** |
| 4 (2029) | $40M | $12M | **$52M** |
| 5 (2030) | $60M | $30M | **$90M** |

**$90M ARR by year 5 at mid scenario** supports a $500M–$1B venture
exit (typical SaaS multiples 6–10x ARR for profitable healthtech at
that growth rate).

The mid scenario requires nothing exceptional — modest organic growth
on consumer, modest B2B sales velocity, no breakout viral moment, no
acquisition deal. Assumes execution and continued regulatory tailwind.

### Sensitivities and risks

**What pushes us toward high:**
- Distribution deal with Credit Karma, Mint, or employer-benefits
  platform (5-10x reach).
- Press cycle around a high-visibility billing-error story.
- Large insurer signing a $5-10M/year B2B contract.

**What pushes us toward low:**
- Goodbill or similar VC-backed competitor dominates SEO + paid
  acquisition.
- CMS rolls back the price-transparency rule (low probability —
  bipartisan support).
- Hospital-system defamation lawsuit (low probability — defensible by
  deterministic citations).
- OCR error rate on phone-photo bills proves higher than expected,
  generating false-positive findings that erode trust.

### Pitch summary

> "We're confident in the **mid scenario**. The math is bottom-up:
> ~290M Americans receive bills annually, our beta cohort produced
> ~80% conversion to a paid finding, and our gross margin per paying
> bill is ~96%. The unknown is acquisition CAC — that's what YC
> accelerates. The B2B line layered on top gets us to **$90M ARR by
> year 5**, supporting a venture-scale outcome at standard SaaS
> multiples."

Honest envelope:
- Low ~$3.75M ARR by year 3 (still a real business)
- Mid ~$23M ARR (clear venture outcome)
- High ~$75M ARR (potential decacorn trajectory)

The economics work because the moat — the federated CMS reference +
14k-hospital MRF vault — was built once and serves both revenue lines
at near-zero marginal cost.

---

*Document last updated: 2026-05-01*
*Owner: Sandra Jirongo, Founder & CEO*
