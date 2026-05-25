# Vertex AI and AI Model Architecture

ClaroBill uses AI models in two distinct places: bill analysis summarization and insurance card field extraction. Both use the same provider hierarchy.

---

## Provider Hierarchy

| Priority | Provider | Model | SDK |
|---|---|---|---|
| Primary | Google Vertex AI | `gemini-2.5-flash-lite` | `vertexai` Python SDK |
| Fallback | Anthropic API | `claude-sonnet-4-6` | `anthropic` Python SDK |

The Gemini model is called first. Any exception triggers the Claude fallback. If both fail, the operation errors.

---

## Use 1: Bill Analysis Summary (`ai_analysis.py`)

Called from `bills.py::_run_analysis_pipeline` after the rules engine completes.

**Purpose:** Generate `ai_summary` — a plain-English narrative + recommendations from the rules engine output.

**Inputs:**
- Full OCR extracted text from the bill image
- Structured line items (CPT codes, charges, quantities, dates)
- All `BillingError` objects from the rules engine (error codes, descriptions, estimated overcharges)

**Output:** `ai_summary` JSONB stored in `analysis_results.ai_summary`. Contains:
- `narrative` — plain-English explanation of the errors and why they matter
- `recommendations` — ordered list of actions for the patient

**Fallback trigger:** Any exception from the Vertex AI call → Claude retry. If both fail, the pipeline continues without an AI summary (rules engine output is still saved).

**Initialization:**  
`vertexai.init(project=settings.gcp_project_id, location=settings.vertex_ai_location)` is called in `AiAnalysisService.__init__`. When `settings.gcp_project_id` is empty (local dev without ADC), Vertex AI init is skipped entirely and Claude is used for all calls.

---

## Use 2: Insurance Card Extraction (`insurance_card.py`)

Called from `POST /insurance-card/extract`.

**Purpose:** Extract structured insurance plan fields (payer name, plan name, member ID, plan type, pharmacy fields) from a card photo.

**Inputs:** Single image file — JPEG, PNG, or WebP, max 10 MB.

**Output:** `InsuranceCardExtraction` Pydantic model (camelCase JSON).

**Fallback trigger:** Any exception from Gemini → Claude retry. If both fail → HTTP 502.

**Key implementation details:**
- Image is **never stored** — this endpoint is stateless. Bytes are read into memory, passed to the model, and discarded.
- `plan_type` is validated against the `PlanType` closed enum. If the AI returns a string outside the enum (e.g. `"PPO"`, `"Choice POS I"`), `plan_type` is set to `null` so the user selects from the UI instead of getting a silently wrong benchmark.
- Response parsing is defensive via `_parse_ai_response()` — strips markdown code fences before JSON parsing.

See `docs/decisions/2026-05-25-insurance-card-extraction.md` for the design rationale.

---

## Credentials

In production (Cloud Run), the engine authenticates to Vertex AI via Application Default Credentials using the `clarobill-vision-sa` service account, which has the `roles/aiplatform.user` role on `clarobill-prd`.

In local development, set `GOOGLE_APPLICATION_CREDENTIALS` to a service account key file path, or set `GOOGLE_CREDENTIALS_JSON` to the full key JSON content. Without either, `gcp_project_id` should be left unset — the Vertex AI path is bypassed and Claude handles all calls.

---

## Configuration

| Setting | Default | Description |
|---|---|---|
| `GCP_PROJECT_ID` | `""` | GCP project ID. When empty, Vertex AI is skipped. |
| `VERTEX_AI_LOCATION` | `"us-central1"` | Vertex AI region. |
| `ANTHROPIC_API_KEY` | Required | Claude fallback — required in production so the fallback path is always available. |

---

## Why Gemini as primary

- **Cost:** Gemini 2.5 Flash Lite is significantly cheaper per token than Claude Sonnet.
- **Multimodal:** Native image input support without base64 encoding overhead for insurance card extraction.
- **Latency:** Flash Lite is optimized for fast responses on structured extraction tasks.
- **Same GCP project:** No cross-cloud auth required — Vertex AI uses the same service account as BigQuery and Cloud Run.

Claude Sonnet is retained as fallback because it provides strong structured output quality and is the most reliable alternative when Vertex AI is unavailable (quota, region outage, etc.).

---

*Last reviewed: 2026-05-25*
