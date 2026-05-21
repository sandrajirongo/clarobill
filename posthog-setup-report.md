<wizard-report>
# PostHog post-wizard report

The wizard has completed a deep integration of your project. ClaroBill already had a solid PostHog foundation (posthog_client singleton in the engine, captureServerEvent helper in the web app, and comprehensive events throughout the bill analysis pipeline). This session filled the remaining gaps across five server-side callsites that had no analytics coverage, completing the full user journey from referral link visit through to referral credit.

## Events added

| Event | Description | File |
|---|---|---|
| `checkout_session_created` | Fired when a Stripe checkout session is successfully created. Properties: `bill_id`, `amount_cents`, `tier_label`, `has_referral_discount`. Critical paid conversion step. | `apps/web/src/app/api/stripe/checkout/route.ts` |
| `referral_converted` | Fired when a referral is settled after a successful payment and the referrer is credited. Properties: `referral_id`, `credit_cents`. Tracks virality loop closure. | `apps/web/src/app/api/stripe/webhook/route.ts` |
| `bill_upload_initiated` | Fired when a signed upload URL is issued and the bill record is created. Properties: `bill_id`, `mime_type`, `file_size_bytes`. Marks the exact top of the analysis funnel. | `apps/web/src/app/api/bills/upload/route.ts` |
| `lead_magnet_requested` | Fired when the billing-traps guide email is successfully sent. Properties: `guide`. Anonymous — no person profile created. Top-of-funnel lead generation signal. | `apps/web/src/app/api/lead-magnet/billing-traps/route.ts` |
| `referral_link_visited` | Fired when a visitor arrives via a referral link. Anonymous — no person profile created. Measures referral reach before sign-up. | `apps/web/src/app/ref/[code]/route.ts` |

## Pre-existing events (not duplicated)

The engine already tracked: `bill analysis started`, `bill analysis skipped`, `bill analysis failed`, `bill analysis completed`, `report generation requested`, `report generated`, `report generation failed`, `insurance card extracted`, `insurance card extraction failed`.

The web layer already tracked: `user_signed_up`, `report_generation_requested`, `payment_completed`, `report_generated`, `bill_uploaded`, `analysis_started`, `analysis_completed`, `checkout_started`, `onboarding_completed`, `guide_downloaded`.

## Next steps

We've built suggested insights and a dashboard for you to keep an eye on user behavior. Create an "Analytics basics" dashboard in PostHog with these five insights:

1. **Conversion funnel** — Steps: `bill_upload_initiated` → `bill analysis completed` → `checkout_session_created` → `payment_completed`. Shows where users drop off between upload and purchase.

2. **Referral funnel** — Steps: `referral_link_visited` → `user_signed_up` → `referral_converted`. Measures how well the referral programme converts visitors into paying customers and credits.

3. **Lead magnet to signup** — Steps: `lead_magnet_requested` → `user_signed_up`. Shows how many guide downloaders eventually create accounts.

4. **Analysis success rate** — Trend of `bill analysis completed` vs `bill analysis failed` (broken down by `failure_reason`). Health metric for the OCR + AI pipeline.

5. **Revenue events over time** — Trend of `payment_completed` (with `amount_cents` as a sum aggregation). Weekly revenue signal.

Direct link to create dashboards: https://us.posthog.com/project/372959/dashboard

### Agent skill

We've left an agent skill folder in your project at `.claude/skills/integration-fastapi/`. You can use this context for further agent development when using Claude Code. This will help ensure the model provides the most up-to-date approaches for integrating PostHog.

</wizard-report>
