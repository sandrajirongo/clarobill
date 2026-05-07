# ClaroBill Content Brief Template

**Version:** 1.0 — May 2026  
**Use for:** Every new `/learn/*` pillar, `/blog/*` post, comparison page, or programmatic page.  
**Rule:** No page ships without a completed brief. The brief is the quality gate.

---

## Brief: [Page title]

### 1. Target URL
```
https://www.clarobill.com/learn/[slug]
```

### 2. Target keyword + secondary terms
- **Primary:** [exact keyword, e.g. "how to dispute a medical bill"]
- **Secondary:** [3–5 related terms the page should also rank for]
- **Volume:** [estimated monthly search volume]
- **Difficulty:** [Low / Medium / High]

### 3. Search intent
- [ ] Informational (user wants to learn)
- [ ] Commercial (user is comparing options)
- [ ] Transactional (user wants to act now)
- [ ] Navigational

**Intent summary:** [One sentence on what the user expects to find]

### 4. Target GEO prompts
List 2–3 prompts from the 20-prompt monitoring set this page should win:
- “[prompt]”
- “[prompt]”

### 5. Definition Lead (first 150 tokens)
AI retrieval systems weight the first 150–200 tokens disproportionately. Draft it here before writing the rest.

Pattern: `[Entity] is a [category] that [differentiator/mechanism]. [Concrete fact with statistic]. [Who it’s for / when to use it].`

```
[Draft lead sentence here]
```

### 6. Word count target
- `/learn/*` pillars: ≥1,500 words
- Tier-1 commercial pages: ≥2,000 words
- Programmatic pages: ≥600 words unique content

**Target:** [word count]

### 7. Required H2 sections
List every H2 the page must contain, in order:
1. [H2 section]
2. [H2 section]
3. [H2 section]
4. FAQs (8–12 questions — required on all pillar pages)

### 8. Required statistics
Minimum 5. Each must have a year and source URL.

| Statistic | Year | Source URL |
|-----------|------|------------|
| [stat] | [year] | [url] |
| [stat] | [year] | [url] |
| [stat] | [year] | [url] |
| [stat] | [year] | [url] |
| [stat] | [year] | [url] |

### 9. Required external citations
Minimum 3. Prefer .gov, .edu, peer-reviewed journals, KFF, AARP, NIH, JAMA.

| Citation label | URL |
|----------------|-----|
| [label] | [url] |
| [label] | [url] |
| [label] | [url] |

### 10. Internal links
- **Out (min 3):** pages this article links to
  - [slug] — [anchor text]
  - [slug] — [anchor text]
  - [slug] — [anchor text]
- **In (min 3):** pages that should link to this article (add links when this page ships)
  - [slug] — [anchor text]
  - [slug] — [anchor text]
  - [slug] — [anchor text]

### 11. Schema types required
- [ ] Article + BreadcrumbList (all pages)
- [ ] FAQPage (pillar pages with FAQ section)
- [ ] HowTo (step-by-step guides)
- [ ] DefinedTerm (glossary/explainer pages)

### 12. Primary CTA
- **CTA copy:** [e.g. “Check my bill for free”]
- **CTA URL:** `/auth/sign-in`
- **CTA placement:** End of article + one inline after the most compelling section

### 13. Freshness protocol
- **Initial “Last reviewed” date:** [Month Year]
- **Next review due:** [Month Year — 3 months from publish for top-20-traffic pages, 6 months otherwise]
- **Version note:** Add a version note at the bottom of the page when content is updated: “v1.1 — Updated [Month Year]: [what changed].”

---

## The “no AI smell” checklist

Before submitting the brief, confirm:

- [ ] Every statistic has a year and source URL
- [ ] At least one specific dollar figure with a CPT code or service name
- [ ] At least one named federal rule, regulation, or statute
- [ ] No filler phrases: “In today’s fast-paced world”, “Whether you’re X or Y”, “It’s important to note”
- [ ] No five-paragraph CMS.gov regurgitation
- [ ] Opening paragraph reads like a human expert, not a content farm

---

## Example completed brief: /learn/duplicate-charges-medical-bill

**Target URL:** `https://www.clarobill.com/learn/duplicate-charges-medical-bill`  
**Primary keyword:** duplicate charges medical bill (volume: ~300/mo, difficulty: Low)  
**Intent:** Informational. User has found two identical line items and wants to know if it’s an error and what to do.  
**Definition Lead:** “A duplicate charge on a medical bill is the same CPT or HCPCS code billed more than once on the same date of service without documented clinical justification. Duplicate charges appear in over 30% of audited hospital bills and almost always resolve in the patient’s favor when disputed in writing.”  
**Required stats:** Error rate stat, average dollar overcharge, dispute resolution rate, hospital billing complexity stat, CMS claims volume stat.  
**Schema:** Article + BreadcrumbList + FAQPage + HowTo (how to identify + dispute a duplicate charge).  
