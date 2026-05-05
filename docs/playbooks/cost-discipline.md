# Cost discipline checklist

CLAUDE.md Rule 16 mandates a verified cost breakdown for every change
that touches a billable surface. This is the checklist form.

The 2026-05-04 incident — an off-the-cuff "~$2-5" estimate for a Coldline
→ Standard storage class change cost Sandra **$226** — is the reason this
doc exists. See [../postmortems/2026-05-04-claude-damage-report.md](../postmortems/2026-05-04-claude-damage-report.md)
for the full case study.

## The non-negotiable workflow

Before proposing any change that touches GCP, BigQuery, Cloud Run,
external APIs, Stripe, SendGrid, or Vercel:

1. **WebSearch the current rate** for every line item involved. Don't
   quote from memory — pricing changes frequently. (Example: GCP changed
   multi-region→regional egress on 2026-02-01.)
2. **Cite the source URL** alongside each rate.
3. **Get the exact quantity** before multiplying — query the actual size
   via BigQuery / `gcloud storage du` / equivalent. NEVER estimate object
   counts or GB.
4. **Show the math line-by-line** in a markdown table with Rate / Quantity / Total columns.
5. **Include best-case AND worst-case columns** when storage class,
   retrieval, or early-deletion fees might apply.
6. **State assumptions explicitly** for any unknowns (e.g. "assumes all
   objects are Standard class — verifying with `gcloud storage objects describe`").
7. **Compute payback period** for any one-time cost vs. recurring savings.

## Worksheet template

Copy this when proposing a change:

```markdown
### Cost analysis: <name of proposed change>

#### Assumptions
- (1) ...
- (2) ...

#### Quantities (verified)
- Object count: <N>, source: `gcloud storage ls --recursive ... | wc -l`
- Total bytes: <N GB>, source: `gcloud storage du gs://bucket`
- ...

#### Rate table
| Line item | Rate | Source URL | Date verified |
|---|---|---|---|
| Cloud Storage Standard read | $0.020 / 10K Class B ops | https://cloud.google.com/storage/pricing | 2026-05-05 |
| ... | | | |

#### Cost math (best case / worst case)
| Line item | Quantity | Best-case rate | Worst-case rate | Best total | Worst total |
|---|---|---|---|---|---|
| Class A operations | 10,000 | $0.005/1K | $0.010/1K (early-delete) | $0.05 | $0.10 |
| ... | | | | | |
| **Total** | | | | **$X.XX** | **$Y.YY** |

#### Payback period (if applicable)
One-time cost: $X.XX
Recurring saving: $Y.YY/month
Payback: X / Y = <N> months
```

## Reference: pricing pages bookmarked

| Service | Pricing page | What to look up |
|---|---|---|
| Google Cloud Storage | https://cloud.google.com/storage/pricing | Class (Standard / Nearline / Coldline / Archive), region, retrieval fees, early-delete fees, Class A/B operations, egress |
| BigQuery | https://cloud.google.com/bigquery/pricing | On-demand bytes scanned ($6.25/TiB), storage (active vs long-term), DML pricing, slot-hours if reserved |
| Cloud Run | https://cloud.google.com/run/pricing | vCPU-seconds, memory-GB-seconds, request count, egress, free tier |
| Cloud Scheduler | https://cloud.google.com/scheduler/pricing | $0.10/job/month — 3 free per project |
| Vertex AI Gemini | https://cloud.google.com/vertex-ai/generative-ai/pricing | Per-1K input + output tokens, per model variant |
| Anthropic Claude | https://www.anthropic.com/pricing | Per-MTok input + output, per model |
| Google Cloud Vision | https://cloud.google.com/vision/pricing | Per 1K units; OCR is `DOCUMENT_TEXT_DETECTION` |
| Google Places | https://developers.google.com/maps/billing-and-pricing/pricing | Per request, $200/month free credit |
| Stripe | https://stripe.com/pricing | 2.9% + $0.30 standard; 0.5% Connect; 1% subscription |
| SendGrid | https://sendgrid.com/pricing | Free tier 100 emails/day, then per-email or per-month |
| Supabase | https://supabase.com/pricing | Pro plan includes; preview branches $0.01344/hr Micro Compute |
| Vercel | https://vercel.com/pricing | Bandwidth, Edge invocations, build minutes |
| GitHub Actions | https://github.com/pricing | Public repo: free; private: 2,000-3,000 min/month included |

## Common surprise costs

- **Coldline retrieval fee.** Reading a Coldline object isn't free even
  though storage is cheap. ~$0.02/GB to retrieve.
- **Coldline 90-day minimum.** Deleting a Coldline object before 90 days
  costs the prorated remainder of the 90 days. The 2026-05-04 incident
  was largely this fee.
- **Cross-region egress.** GCP introduced billable cross-region traffic
  on 2026-02-01. $0.02/GB. Our `mrf-archive` bucket is multi-region; if
  Cloud Run reads from it cross-region, that adds up.
- **BigQuery on-demand DML.** UPDATE/MERGE on a partitioned table can
  scan more bytes than expected if the partition column isn't in the
  WHERE clause.
- **BigQuery long-term storage.** Tables not modified in 90 days get a
  50% storage discount; partitions are scoped per-partition.
- **Class A vs Class B operations.** Writes (Class A) cost ~10× reads
  (Class B). A bulk rewrite (e.g. storage class change) is millions of
  Class A ops — not free.
- **Vertex AI safety filters.** Filtered responses still bill input tokens.
  Failures don't refund.
- **Stripe disputes.** Each dispute has a $15 fee, win or lose.
- **SendGrid send limits.** Free tier capped; bursts above the limit
  drop emails silently — pay attention.

## Forbidden phrasing

CLAUDE.md Rule 16: **"Phrases like 'should be cheap', 'minimal', 'a few
dollars', 'rounding error' without the math are forbidden."**

Either:
- Show the table sourced from a current pricing page, OR
- Refuse to quote a number until you've done the research.

"I don't know yet, let me research" is the correct answer when the
research hasn't been done. "It should be small" is not.

## When to STOP and ask Sandra

Even with the math done, ask before:
- Any one-time spend > $50
- Any recurring monthly increase > $20/month
- Any data transfer between buckets > 100 GB
- Any GCS storage class change on a bucket > 50 GB
- Any BigQuery query estimated to scan > 1 TB
- Any Cloud Run config change that lifts the max-instances ceiling
- Adding a new external API dependency (Stripe + SendGrid + GCP + Anthropic
  + Vertex are the current set; new ones need a buy-in)

## Cost-related decisions on file

| Decision | Source URL | Date verified |
|---|---|---|
| Supabase Pro database compute included | Sandra's plan baseline | 2026-05-04 |
| Supabase preview branches: $0.01344/hr Micro Compute, ~$0.60/month at beta volume | https://supabase.com/pricing | 2026-05-04 |
| GitHub Actions: public repo free; private 2000-3000 min/month included | https://github.com/pricing | 2026-05-04 |
| BQ table rename free (metadata operation) | https://cloud.google.com/bigquery/docs/managing-tables#renametable | 2026-05-04 |
| Places API: only charges requests reaching Google's LB; ConnectionError refundable | https://developers.google.com/maps/documentation/places/web-service/usage-and-billing | 2026-05-04 |

## Cross-references

- CLAUDE.md Rule 16 — the engineering rule
- [../postmortems/2026-05-04-claude-damage-report.md](../postmortems/2026-05-04-claude-damage-report.md) — the $226 incident
- [../decisions/2026-04-28-google-places-cost-design.md](../decisions/2026-04-28-google-places-cost-design.md) — Places API tiering
- [../decisions/2026-04-30-pipeline-cadence.md](../decisions/2026-04-30-pipeline-cadence.md) — twice-yearly vs weekly cost trade-off

---

_Last reviewed: 2026-05-05_
