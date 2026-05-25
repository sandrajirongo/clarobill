# Decision: Stateless AI Vision for Insurance Card Extraction

**Date:** 2026-05-25  
**Status:** Shipped  
**Owners:** Engineering

---

## Context

Before a bill can be analyzed, the engine needs the patient's insurance details: payer name, plan name, member ID, plan type. Asking users to type these manually has high drop-off — insurance cards have arcane abbreviations and users often don't know their `plan_type` enum value.

The alternative: let users photograph their insurance card and extract the fields automatically.

---

## Decision

Build a stateless AI vision extraction endpoint (`POST /insurance-card/extract`) that:

1. Accepts an image upload (JPEG, PNG, WebP, max 10 MB)
2. Sends it to Gemini 2.5 Flash Lite (primary) or Claude Sonnet (fallback)
3. Returns structured `InsuranceCardExtraction` JSON
4. **Never stores the image** — bytes are processed in memory and discarded

---

## Why Stateless (No Storage)

Insurance cards contain PHI: member ID, payer name, and sometimes date of birth. Storing them creates regulatory obligations and breach surface area that are disproportionate to the value.

The only downstream use of the extraction result is pre-filling form fields that the user then confirms. There is no need to retrieve the card again after extraction.

---

## Why AI Vision

Insurance cards have no standard layout, font, or field labeling. Rule-based OCR (e.g. "find text after the word 'Member'") fails on the hundreds of card formats in the wild. A multimodal language model understands that "Subscriber ID", "Member #", and "ID" all mean member_id.

**Why not Google Vision API (structured OCR)?**  
Google Vision returns bounding-box text blocks — it doesn't understand that "Choice POS I" is a `plan_name` and not part of an address. A second LLM call to interpret the OCR output would have the same cost as a single multimodal call, with more failure modes.

---

## Why Dual Provider

Insurance card extraction is on the critical path to bill analysis. If the AI call fails, the user cannot proceed without manually entering their insurance details. The fallback (Claude Sonnet) ensures the endpoint remains available during:
- Vertex AI regional outages
- Gemini quota exhaustion
- Model deployment issues

The fallback adds ~200ms of overhead when triggered. Both providers use the same prompt; output format is identical.

---

## plan_type Validation

`plan_type` is a closed set (`commercial`, `medicare`, `medicaid`, `tricare`, `self_pay`). AI models sometimes return values outside this set — plan product names like `"Choice POS I"`, `"HMO Gold"`, or plan structures like `"PPO"`.

**Decision:** When the AI returns an unrecognized `plan_type`, the field is set to `null` instead of defaulting to `"commercial"`. The UI presents a dropdown; the user selects the correct type.

**Why not default to `"commercial"`?** Plan type drives the benchmark multiplier in PRICE_OUTLIER (1.40–2.64× depending on service type and plan type). A wrong plan type produces wrong benchmarks and potentially wrong overcharge estimates. A `null` that prompts the user is safer than a silent wrong assumption.

---

## Defensive JSON Parsing (H16)

The AI response is sometimes wrapped in markdown code fences (` ```json ... ``` `). `_parse_ai_response()` strips these before JSON parsing.

A prior bug (H16): a malformed response of just ` ``` ` (no newline, no closing fence) caused `IndexError` on the `split("\n", 1)[1]` access. The `except` clause only caught `JSONDecodeError + ValueError`, so the `IndexError` escaped as a raw 500 with no PostHog telemetry.

Fix: replaced string indexing with `removeprefix()` + `rstrip()` — no indexing operations that can raise on short strings. Exception handler widened to catch any exception from the parse step.

---

## Consequences

- Images are not logged, not stored, not auditable after the response is sent.
- Extraction quality depends on image legibility. Dark, blurry, or cropped cards return `confident: false` in the response — the UI surfaces this to the user.
- The `max_tokens` cap on Claude (400) is intentionally tight — the prompt asks for a small JSON object. Increase if new fields are added to `InsuranceCardExtraction`.
- Max image size is 10 MB. Insurance card photos from modern phones are typically 1–5 MB; this limit covers edge cases without creating risk of very large payloads.
