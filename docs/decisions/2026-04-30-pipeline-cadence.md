# Decision: MRF pipeline cadence — annual + quarterly + mid-year

**Date:** 2026-04-30
**Status:** Shipped (replaces the prior weekly + bi-annual schedules)
**Owners:** Sandra, Engineering

## Context

Through Phase 4 the scraper + parser ran weekly (Tuesday) and discovery
ran bi-annually (Feb 1 + Aug 1). That cadence was wrong for the data:

- **CMS Hospital Price Transparency rule** requires hospitals to publish
  MRFs and update them at least once a year. In practice, most hospitals
  publish or refresh in early-Q1 (after the Jan 1 deadline) and a smaller
  subset (~10%) republishes in summer. Daily/weekly polling produces no
  new data 51 weeks per year and burns Cloud Run + GCS bandwidth on
  identical files.

- **Discovery** (CMS list → NPI → website → MRF URL) only changes when
  CMS adds new hospitals to its Provider of Services file. Twice-a-year
  is enough to catch new certifications; weekly is wasted compute.

- The Phase 3 implementation found websites for 11,860 hospitals but
  never persisted MRF URLs (Stage 4 was never built). This pivot to a
  rarer-but-more-comprehensive cadence aligns with the new Stage 4 build
  and lets us gap-fill what Stage 4 misses without a full re-discovery.

## Decision

**Three jobs, six total schedules.**

### Discovery job (`clarobill-mrf-discovery`)

| Schedule | Cron | Mode | Stages |
|---|---|---|---|
| `clarobill-mrf-discovery-annual` | `0 2 15 2 *` (Feb 15) | Full | Stages 1-4 + Tier 3 paid sweep |
| `clarobill-mrf-discovery-quarterly` | `0 2 15 5,8,11 *` (May/Aug/Nov 15) | Gap-fill (`--gap-fill-only`) | Stages 1-4, **skips Tier 3 paid** |

The Feb 15 anchor is intentional: hospitals get a 6-week buffer past the
Jan 1 CMS republish deadline to fix any first-pass errors. The quarterly
anchors are 45 days into each quarter (Q2 starts Apr 1 → May 15;
Q3 starts Jul 1 → Aug 15; Q4 starts Oct 1 → Nov 15). Q1 is covered by
the annual run on Feb 15. Quarterly gap-fills only re-process hospitals
where `validated_mrf_urls IS NULL` after the previous pass + any new
CMS-listed hospitals.

### Scraper job (`clarobill-mrf-scraper`)

| Schedule | Cron | Reason |
|---|---|---|
| `clarobill-mrf-scraper-annual` | `0 2 15 2 *` (Feb 15) | Same date as annual discovery — picks up freshly-discovered URLs |
| `clarobill-mrf-scraper-midyear` | `0 2 15 8 *` (Aug 15) | Catches the ~10% of hospitals that republish in summer |

`If-Modified-Since` HTTP gating means hospitals whose MRFs haven't
changed since the previous scrape get skipped automatically — both runs
are full-fleet sweeps with conditional download.

### Parser job (`clarobill-mrf-parser`)

| Schedule | Cron | Reason |
|---|---|---|
| `clarobill-mrf-parser-annual` | `0 6 15 2 *` (Feb 15) | 4h after annual scraper |
| `clarobill-mrf-parser-midyear` | `0 6 15 8 *` (Aug 15) | 4h after mid-year scraper |

## Schedules deleted

- `clarobill-mrf-scraper-weekly` (was `0 2 * * 2`) — deleted by deploy.sh
- `clarobill-mrf-parser-weekly` (was `0 6 * * 2`) — deleted by deploy.sh
- `clarobill-mrf-discovery-feb` (was `0 2 1 2 *`) — deleted by deploy.discovery.sh
- `clarobill-mrf-discovery-aug` (was `0 2 1 8 *`) — deleted by deploy.discovery.sh

## Why "the 15th" and not "the 1st"?

Two reasons:
1. **Holiday/weekend buffer.** Jan 1, Apr 1, Jul 1, Oct 1, Aug 1 fall on
   inconvenient days some years. The 15th is uncluttered.
2. **6-week post-deadline buffer (annual).** CMS sets Jan 1 as the
   republish deadline. Most hospitals miss it by a few days; some take
   several weeks. Feb 15 catches everyone who's going to comply for that
   year.
3. **Quarterly alignment.** 45 days after each quarter start = the 15th
   of the second month. May 15, Aug 15, Nov 15.

## Why no Q1 quarterly?

Feb 15 is the annual run. It already runs every stage (1-4) for every
hospital, including those still missing URLs. Adding a separate Q1
quarterly would be redundant.

## Cost & runtime impact

- **Discovery annual** (Feb 15): ~3.5h wall-clock + ~$450 Tier 3 budget
  (capped). One run per year.
- **Discovery quarterly** (May/Aug/Nov 15): ~30-60 min each, free (no
  Tier 3 in `--gap-fill-only`). Three runs per year.
- **Scraper + Parser** (Feb 15 + Aug 15): ~4h wall-clock each at
  `--tasks=6`, free except egress. Two runs per year per job.

Total Cloud Run hours per year drops from ~52 weekly scraper runs +
52 weekly parser runs = ~416 task-hours annually to ~16 task-hours
annually. ~96% reduction in compute.

## Manual triggers

```bash
# Annual full discovery (paid)
gcloud run jobs execute clarobill-mrf-discovery --region us-central1

# Gap-fill (free)
gcloud run jobs execute clarobill-mrf-discovery --region us-central1 \
  --args=--gap-fill-only

# Re-run only Stage 4 (URL crawler) on an existing run
gcloud run jobs execute clarobill-mrf-discovery --region us-central1 \
  --args=--start-stage=stage4_mrf_urls,--run-id=<id>

# Manual scrape + parse (e.g. after a hospital tells us they updated)
gcloud run jobs execute clarobill-mrf-scraper --region us-central1
gcloud run jobs execute clarobill-mrf-parser  --region us-central1
```

## Consequences

- Bills uploaded by users between the Feb 15 and Aug 15 runs see
  data that may be up to 6 months old. For the rules engine that's
  acceptable: the `pricing_effective_year` partition keeps everything
  year-correct, and CMS rule says hospitals only have to refresh once
  per year.
- If a hospital republishes in Mar-Apr-May or Sep-Oct-Nov-Dec, our copy
  will be stale until the next scheduled run. Live-data testing on
  2026-04-29 showed `Last-Modified` headers from Dec 2024 on a
  freshly-pulled MRF, so this is consistent with industry behavior.
- Manual triggers are always available for one-off refreshes (e.g. when
  a customer reports their bill prices don't match what we have).
