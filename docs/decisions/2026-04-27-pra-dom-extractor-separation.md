# Separate the PRA DOM Extractor from the Playwright Renderer

**Date:** 2026-04-27
**Status:** SUPERSEDED-BY [2026-04-28-cms-direct-mrf-discovery.md](2026-04-28-cms-direct-mrf-discovery.md). PRA-based discovery was abandoned the next day; the separation rationale is moot.

---

## Context

Stage 2 of the PRA-sourced MRF discovery pipeline has to extract structured hospital fields (name, address, CCN, phone, website, price-transparency-page URL, MRF file URL, file format, file size, last-checked-on date) from each rendered `/details/{uuid}` page on hospitalpricingfiles.org.

The page is a React single-page application hydrated from a Cloudflare-Turnstile-protected JSON API. We cannot scrape the API directly without violating their anti-bot intent, and a static HTTP fetch sees only an empty `<div id="root"></div>` shell. The only viable approach is rendering the page in headless Playwright (Chromium) and reading the resulting DOM.

That gives us a natural choice point. Stage 2 has two distinct responsibilities:

1. **Render** — drive Playwright, navigate to the URL, wait for hydration, handle Turnstile if present, retrieve the rendered HTML.
2. **Parse** — find the right elements, pull the right text out, normalise it (trim whitespace, parse the file-size from "70.6KB", validate the MRF URL is well-formed), and return a typed dict.

These two responsibilities have different change drivers, different test ergonomics, and different failure modes. The decision is whether to keep them in one module or split them.

---

## Decision

**Split into two modules:**

- `scripts/mrf_discovery/stage2_pra_detail_extract.py` — owns Playwright lifecycle, rate limiting, retries, browser context management, and the BigQuery checkpoint integration. Does not know what the page looks like.
- `scripts/mrf_discovery/pra_dom_extractor.py` — pure function `extract(html: str) -> ExtractedFacility | None`. Takes rendered HTML as input, returns a typed dataclass. No I/O. No Playwright dependency. No network.

The Playwright stage calls the extractor like this:

```python
async def process_uuid(uuid: str, page: playwright.Page) -> dict:
    await page.goto(f"https://hospitalpricingfiles.org/details/{uuid}")
    await page.wait_for_selector("text=Link to Price Transparency File", timeout=30_000)
    html = await page.content()
    extracted = pra_dom_extractor.extract(html)
    if extracted is None:
        raise ExtractionFailed(f"Selectors returned no match for {uuid}")
    return extracted.to_checkpoint_dict()
```

Test fixtures live at `apps/engine/tests/scripts/fixtures/pra/{uuid}.html` — saved HTML snapshots from 5-10 representative detail pages (small hospital, big hospital, system facility, hospital with no MRF link, hospital using a vendor URL, hospital with an XLSX file, etc.). Tests assert that `pra_dom_extractor.extract(open(fixture).read())` returns the expected typed dict.

---

## Reasoning

### 1. Selector logic changes more often than browser logic

PRA can redesign their detail page tomorrow. When that happens, every selector in the extractor breaks but the Playwright loop still works. With a split module, the fix is: (a) save the new HTML as a fixture, (b) update the extractor, (c) all 27 existing tests still pass plus the new fixture. With a combined module, every fix has to navigate around Playwright setup code and we need a live PRA session to test.

### 2. Tests run in microseconds without Playwright

`pra_dom_extractor` is a pure function. Its tests load HTML strings from disk and assert on dict outputs. No browser launch, no network, no flakiness. The full test suite for the extractor will run faster than a single Playwright page.goto. This matters because we will iterate on selectors many times — every iteration is a millisecond test, not a 30-second integration test.

### 3. Failure modes are crisply separated

When a hospital extraction fails in production, the error tells us which layer broke:

- "Playwright timeout waiting for selector" → render layer; PRA is slow or down or Turnstile escalated
- "Extractor returned None for ccn field" → parse layer; a specific field's selector is broken

Combined, every error looks the same and triage takes longer.

### 4. The extractor can be reused for fixtures captured by other tooling

If we ever want to run the extractor against an HTML file saved by `curl --user-agent <real-browser>` for a debug session, or against a snapshot scraped by an entirely different framework, the extractor doesn't care. It is the same pure function.

### 5. The cost of splitting is one import line

There is no real downside. One module imports the other. Both live in the same package directory. There is no API surface to maintain across boundaries, no serialisation overhead.

---

## Consequences

### Positive

- Selector changes ship as one-file PRs with fixture diffs reviewers can read.
- Extractor tests run in milliseconds and provide a tight feedback loop during selector development.
- Playwright's quirks (browser launch, context isolation, Turnstile handling) stay quarantined to one file.
- When PRA changes their HTML, "save the broken page as a new fixture, update the extractor" is the literal repro-and-fix recipe.

### Negative

- One extra file in the package. (Cost is negligible.)
- Anyone adding a new field has to touch two places — the extractor (to populate it) and the checkpoint schema (to store it). This is the right outcome; it forces explicit dataclass updates rather than free-form dict spreading.

### Implementation notes

- The extractor's typed dataclass should be named `ExtractedFacility` and live in `pra_dom_extractor.py`. It maps 1:1 to the inflight table columns Stage 2 fills in.
- The first commit that lands the extractor must include at least 5 fixture HTML files covering: standard hospital, system facility (Ascension/HCA-style), hospital with no MRF URL listed, hospital with an XLSX/non-CSV file, hospital with a third-party vendor URL (machine-readable-files.com, Turquoise).
- HTML fixtures are committed as-is (no sanitization). They are public web pages and contain no PHI. Including them in the repo is the entire point — they are the regression suite.

---

## References

- `docs/decisions/2026-04-27-pra-mrf-discovery-architecture.md` — parent architecture decision
- `docs/future-improvements/pra-pipeline-build.md` — implementation tracking
- Stage 2 implementation target: `scripts/mrf_discovery/stage2_pra_detail_extract.py` and `scripts/mrf_discovery/pra_dom_extractor.py`
- Test target: `apps/engine/tests/scripts/test_pra_dom_extractor.py` + `fixtures/pra/*.html`
