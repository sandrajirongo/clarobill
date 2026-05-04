<wizard-report>
# PostHog post-wizard report

The wizard has completed a deep integration of PostHog analytics into the ClaroBill FastAPI engine service. The integration is instance-based (using the `Posthog()` class constructor), configured via environment variables, and adds zero PII to event properties. Eight business-critical events are now tracked across the bill analysis pipeline, report generation flow, and insurance card extraction endpoint.

## Files changed

| File | Change |
|------|--------|
| `apps/engine/pyproject.toml` | Added `posthog==7.14.0` to dependencies; added `posthog` to mypy ignore_missing_imports overrides |
| `apps/engine/app/core/config.py` | Added `posthog_api_key` and `posthog_host` settings (both read from env) |
| `apps/engine/app/core/posthog_client.py` | **New file.** Module-level `Posthog` singleton with `enable_exception_autocapture=True`; `atexit.register(posthog_client.shutdown)` for clean flush on exit |
| `apps/engine/app/main.py` | Added `X-PostHog-Distinct-Id` and `X-PostHog-Session-Id` to CORS `allow_headers` for frontend-backend event correlation |
| `apps/engine/app/api/v1/bills.py` | Added 6 event captures across `analyze_bill`, `_run_analysis_pipeline`, `generate_report`, and `_do_generate_report` |
| `apps/engine/app/api/insurance_card.py` | Added 2 event captures for extraction success and failure |
| `apps/engine/.env` | Added `POSTHOG_API_KEY` and `POSTHOG_HOST` |

## Events instrumented

| Event | Description | File |
|-------|-------------|------|
| `bill analysis started` | Fired when a bill is accepted for analysis. Properties: `bill_id`, `has_payer_info`, `plan_type` | `apps/engine/app/api/v1/bills.py` |
| `bill analysis completed` | Fired when the full OCR + rules engine + AI pipeline succeeds. Properties: `bill_id`, `errors_found`, `has_savings`, `line_item_count`, `has_payer_info` | `apps/engine/app/api/v1/bills.py` |
| `bill analysis failed` | Fired when the pipeline fails (OCR error or unexpected exception). Properties: `bill_id`, `failure_reason` (`ocr_failed` or `pipeline_error`) | `apps/engine/app/api/v1/bills.py` |
| `report generation requested` | Fired when a report generation job is queued (post-payment trigger). Properties: `bill_id` | `apps/engine/app/api/v1/bills.py` |
| `report generated` | Fired when the PDF + dispute letter are generated and emailed successfully. Properties: `bill_id` | `apps/engine/app/api/v1/bills.py` |
| `report generation failed` | Fired when the background report generation task fails. Properties: `bill_id` | `apps/engine/app/api/v1/bills.py` |
| `insurance card extracted` | Fired when insurance card fields are successfully extracted. Properties: `provider` (gemini or claude), `confident`, `plan_type` | `apps/engine/app/api/insurance_card.py` |
| `insurance card extraction failed` | Fired when both Gemini and Claude fail to extract card data. | `apps/engine/app/api/insurance_card.py` |

## Next steps

We've built a dashboard and insights to monitor user behavior based on the events just instrumented:

- **Dashboard — Analytics basics:** https://us.posthog.com/project/372959/dashboard/1541915
- **Bill Analysis Funnel** (started → completed → report requested → report generated): https://us.posthog.com/project/372959/insights/2fOKifH0
- **Bills Analyzed Per Day** (daily analysis volume trend): https://us.posthog.com/project/372959/insights/pHczVVcJ
- **Analysis Success vs Failure Rate** (pipeline reliability): https://us.posthog.com/project/372959/insights/tCaCj37z
- **Report Generation Success Rate** (post-payment delivery reliability): https://us.posthog.com/project/372959/insights/NsjGYba8
- **Insurance Card Extraction Success Rate** (AI vision provider reliability): https://us.posthog.com/project/372959/insights/M2vTcj19

### Agent skill

We've left an agent skill folder in your project at `.claude/skills/integration-fastapi/`. You can use this context for further agent development when using Claude Code. This will help ensure the model provides the most up-to-date approaches for integrating PostHog.

</wizard-report>
