# ClaroBill — a16z Speedrun Application Answers

**Founder:** Sandra Jirongo
**Date prepared:** 2026-05-03
**Purpose:** Form-ready answers + tactical rationale for the a16z Speedrun
application. Mirrors the structure of `yc.md`. Keep
both updated as positioning evolves; the YC and Speedrun decks share
moat language but diverge on framing (YC favours operating discipline
and milestones; Speedrun favours velocity and ambition).

---

## Table of Contents

1. [Relevant experience](#1-relevant-experience)
2. [Team](#2-team)
3. [What problem are you solving? What are you building?](#3-problem--what-were-building)
4. [Traction commentary](#4-traction-commentary)
5. [Anything else we should know?](#5-anything-else)
6. [Tactical notes that informed the answers](#6-tactical-notes)

---

## 1. Relevant experience

> Form prompt: "In a few sentences, highlight your most relevant
> professional, startup, or industry experience. Focus on track record,
> domain expertise, and past wins."
> Word cap: <100 words.

**Answer (~95 words):**

> Data engineer and ML ops practitioner — built training pipelines and
> feature stores for production categorization models, plus the ops
> backbone (monitoring, retraining, deployment) keeping them live. That
> data-pipeline-first instinct is why ClaroBill's moat is the
> 13,800-hospital pricing index I built from CMS-direct sources, not
> the AI layer. End-to-end: scraped, parsed, year-partitioned, and
> queryable in seconds. The rules engine cites every finding back to a
> specific dollar in real published data. Live in public beta at
> clarobill.com. Minerva University alumna, building from Oakland — adjacent
> to Kaiser HQ and a deep healthcare-tech talent pool.

**Why this works:**
- Speedrun rewards builders. Lead with what you've shipped (pipeline,
  rules engine, live beta), not credentials.
- The "data-engineering → moat" connection is doing real work. It
  explains why your past work matters for *this* company.
- "Live in public beta" is the highest-signal phrase: past pitch-deck
  stage.
- "adjacent to Kaiser HQ" is a deliberate dog-whistle for Oakland-based
  healthcare-distribution.

**Optional add-ons** (if word budget allows, swap in one):
- A specific former-employer name (most credible signal Speedrun reads).
- A dollar value of beta savings found so far (concrete proof point).

---

## 2. Team

> Form prompt: "How does the team know each other? Is there anyone else
> on the team? Why is this the best team to win? Do you have any key
> advisors? Etc."

**Answer (~165 words):**

> Currently solo. I built every layer of ClaroBill — data pipeline
> (13,800 hospitals indexed), OCR, rules engine, frontend, payment
> flow, AI-assisted dispute letter generation — myself in the last
> three months. The full product is live in public beta at
> clarobill.com today. That breadth is my best evidence that execution
> risk is low.
>
> I'm solo by choice for the build phase, not by accident. ML and
> data-engineering depth (the moat is a data problem, not a frontend
> problem) plus full-stack consumer execution covers what this stage
> needs technically. Solo speed of decision-making is a real edge when
> the field is uncrowded and the race is for distribution.
>
> Hiring plan post-Speedrun: full-stack engineer for the B2B API
> buildout (month 2), growth/SEO operator (month 3-4).
>
> Advisors: in active conversation with Hubert Thieblot (Founders Inc)
> following his open-DM invite this week; tapping the Minerva University
> alumni network for product feedback and warm intros.

**Why this works:**
- Lead with execution, not solo. "Built every layer in three months"
  is the headline. Solo-as-question gets answered by what you've
  already shipped.
- "Solo by choice, not by accident" is the line that disarms a16z's
  main concern about solo founders.
- Specific hiring plan with months signals you've thought past the
  Speedrun checkbox into actual operating reality.
- Naming Hubert is fine as "in conversation" since he opened DMs.
  Don't elevate to "advised by" until there's a formal relationship.
- "Race for distribution" is a16z-native framing. Speedrun partners
  use that language.

**Tighter ~120-word variant** (if form is more compact): cut the
hiring-plan paragraph; Speedrun's prompt is light on team-scale
specifics.

---

## 3. Problem + what we're building

> Form prompt: "What problem are you solving? What are you building?"
> Word cap: <100 words.

**Answer (~95 words):**

> 80% of US medical bills contain errors. Patients have no way to spot
> them; the human advocates who can charge 25-35% and take six weeks.
> ClaroBill audits any bill against the rates hospitals are legally
> required to publish (13,800 indexed) plus CMS rules, returns a
> dispute letter in three minutes, charges a flat fee.
>
> Today: consumer wedge. Next: B2B API for hospital billing teams,
> insurers, and self-funded employers running the same checks at scale.
> End state: medical billing departments are software, not floors of
> people.

**Why this works:**
- The kicker ("medical billing departments are software, not floors of
  people") is doing 90% of the work. It's the line a16z partners
  screenshot. Specific, ambitious, contrarian-feeling, easy to
  remember.
- "13,800 indexed" is the data-moat number — flexed once.
- "Charges a flat fee" vs "25-35%" is the unit-economics flex.
- Three-tier arc (consumer → B2B → replace billing departments) maps
  to a16z's preferred narrative shape: small wedge, scaling lever,
  fund-returner outcome.

**Sharper kicker variant** (more aggressive): *"End state: hospital
billing departments don't exist."* Three words shorter; only use if you
trust the form-reader to read it as ambition rather than antagonism
toward an industry.

---

## 4. Traction commentary

> Form prompt: "Any general commentary on your traction?"
> Word cap: <100 words.
> Reference: PostHog dashboard screenshots (DAU/WAU + referring
> domain + funnel) from 2026-05-03.

**Answer (~95 words):**

> Public beta is live with zero marketing spend; all distribution
> organic. First week of public visibility:
>
> 60+ unique users, DAU peak of 42 on May 2 (the day I launched on X).
> Twitter (t.co) drove ~33% of traffic; the @clarobillai handle is
> doing the work.
>
> Funnel reads engagement, not bounce: 30% of landing visitors read
> past page one, 17% complete a full first session, avg 2h 41m to
> third pageview.
>
> Beta volume is <100 bills processed so far, but every cohort I've
> talked to converts from "interested" to "I want the dispute letter."

**Why this works:**
- "2h 41m to third pageview" is the strongest signal — people who get
  into the product are reading, not skimming. a16z partners read
  funnel times and know what bounces look like.
- "Zero marketing spend" + "all organic" tells the partner the metric
  ceiling is much higher once you do invest. Speedrun's $1M check is
  for exactly that ramp.
- DAU peak of 42 on launch day signals you can push traffic when you
  decide to. The drop afterward is normal post-launch attrition; don't
  apologize for it.

**Visuals to attach:**
- DAU spike chart (solid line shows real user activity).
- Funnel conversion chart (the 30%/17%/avg-time-to-convert breakdown).
- *Avoid* the WAU dashed-line chart — the dashed forecast reads bad at
  a glance even though it's not historical decline.

**Strongest single add** (if we have it): one paid-tier conversion
from beta would be more powerful than 60 free signups. One $79 paid
bill proves willingness-to-pay independent of distribution. Don't
fabricate; only swap if real.

---

## 5. Anything else

> Form prompt: "If there's something that doesn't fit elsewhere, drop
> it here." (optional)
> Word cap: <100 words.

**Answer (~75 words):**

> My own medical bill is what kicked this off. The product I wished
> existed didn't, so I built it. The federal Hospital Price
> Transparency Rule made every hospital's negotiated rates legally
> scrapeable in 2021; almost no one has built on it. ClaroBill's full
> stack (data pipeline with 13,800 hospitals indexed, rules engine,
> OCR, payment flow, dispute letters) shipped solo in three months.
> Whatever Speedrun gives us, we'll move ten times faster with it.

**Why this works:**
- Founders' real why-now stories are what Speedrun partners remember.
  A specific personal detail (e.g. *"I got a $10K ED bill at Alta
  Bates last year and three weeks of chasing billing for answers
  ended in nothing — then I built this"*) beats a generic line. **Edit
  the opener to your actual personal story before submitting.**
- The 2021 regulatory hook is a quietly powerful frame: it tells the
  partner this opportunity didn't exist five years ago and the window
  is wide open. Most a16z partners don't know about the Hospital Price
  Transparency Rule; surfacing it positions ClaroBill as first-mover.
- "Almost no one has built on it" is defensible — existing players
  (Resolve, Goodbill, etc.) use human advocates plus commercial
  benchmarks, not direct MRF ingestion at scale.
- "Move ten times faster" is a specific velocity claim that pairs with
  "built in three months."

**Personal-story-free fallback** (if no founder origin to share):

> The data moat got built quietly. The federal Hospital Price
> Transparency Rule made every hospital's negotiated rates legally
> scrapeable in 2021; almost no one has built on it. ClaroBill's full
> stack (data pipeline with 13,800 hospitals indexed, rules engine,
> OCR, payment flow, dispute letters) shipped solo in three months.
> Whatever Speedrun gives us, we'll move ten times faster with it.

---

## 6. Tactical notes

### Style rules locked across all answers

- **No em-dashes.** Speedrun reads them as AI-generated copy.
- **No emojis.** Brand rule + same AI-tell concern.
- **No vendor names.** "Generative language model" not "Gemini." "Cloud
  data warehouse" not "BigQuery." See
  `feedback_no_vendor_names_in_public_copy.md` in operator memory.
- **Voice:** Direct, founder-energetic, confident-not-cocky. No filler
  words. One headline per answer; everything else supports it.

### Numbers to keep consistent across all five answers

| Stat | Value | Source |
|---|---|---|
| Hospitals indexed | 13,800 | Internal pipeline checkpoint |
| Bills with errors | 80% | Medical Billing Advocates of America |
| Average overcharge on $10K+ bills | $1,300 | GAO |
| US medical bills issued/year | ~1.2 billion | Industry estimate |
| Existing human-advocate market | $5B/year | Industry estimate |
| Unrecovered patient overcharges | ~$30B/year | Derived from GAO + AMA |
| Human advocate fees | 25-35% of recovered savings | Industry standard |
| Avg revenue per paid bill | ~$70 weighted | Internal model |
| LTV / CAC | $140 / $25 = 5.6x | Internal model |
| Beta users (week 1) | 60+ | PostHog dashboard, 2026-05-03 |
| Beta DAU peak | 42 | PostHog, 2026-05-02 |
| Funnel conversion (page 1 → 2) | 30% | PostHog |
| Funnel conversion (full session) | 17% | PostHog |
| Bills processed in beta | <100 | Internal |

### YC vs Speedrun framing diff

| Theme | YC favours | Speedrun favours |
|---|---|---|
| Solo founder narrative | "operating discipline" | "speed of decision" |
| Stage signal | "shipped + iterating" | "shipped fast" |
| Moat framing | "deterministic over public reference data" | "13,800 hospitals scraped, year-partitioned" |
| Close ambition | "consumer wedge → B2B → outcome" | "hospital billing departments are software" |
| Distribution | "SEO + organic share + referral credit" | "race for distribution" |

Both decks share the same numbers and the same product story; the
voice and sequencing differ.

### Submission checklist

- [ ] Edit Section 5 opener to a true personal-bill story (or use the
      personal-story-free fallback).
- [ ] Verify every number against latest PostHog + BigQuery snapshots
      the morning of submission.
- [ ] Run `grep "—" docs/applications/speedrun.md`
      and confirm zero results.
- [ ] Run `grep -E "Gemini|Claude|Anthropic|Vertex|Supabase|Stripe|
      SendGrid|Sentry|PostHog|Vercel"` on the answers and confirm zero
      results in any answer text (PostHog can be in the source-of-data
      context but not in the form answer itself).
- [ ] Attach the DAU spike chart and the funnel conversion chart;
      *not* the WAU dashed-line chart.
- [ ] Cross-check against `yc.md` for number
      consistency.

       H13 deferred with a note in the campaign tracker — mechanical refactor of ~30 supabase call sites; warrants a focused
  review session.  