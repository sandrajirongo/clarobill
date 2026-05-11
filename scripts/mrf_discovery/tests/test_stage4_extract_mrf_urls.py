"""Unit tests for stage4_extract_mrf_urls — link extraction, regex, TOC fan-out.

Live-network behavior (HEAD validation, full crawl loop) is tested by
the smoke harness and the live discovery run. These tests cover the pure
parsing logic.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from mrf_discovery import stage4_extract_mrf_urls as s4


# --- Filename regex --------------------------------------------------------


@pytest.mark.parametrize("filename,expected", [
    ("123456789_TestHospital_standardcharges.csv", True),
    ("1234567890_Some-Hospital_standardcharges.json", True),
    ("123456789_Memorial_Standard_Charges.csv", True),
    ("123456789_System_standardcharges.json.gz", True),
    ("987654321_X_standardcharges.xml", True),
    ("123456789_X_standardcharges.csv.zip", True),  # CMS allows zip-wrapped csv
    # Non-matches
    ("just_a_random.csv", False),
    ("standardcharges.csv", False),  # missing leading digits
    ("12_short_standardcharges.csv", False),  # too few digits
    ("123_about.html", False),
])
def test_cms_filename_regex(filename: str, expected: bool) -> None:
    assert bool(s4._CMS_FILENAME_RE.search(filename)) is expected


@pytest.mark.parametrize("text,expected", [
    ("View Standard Charges", True),
    ("Standard-Charges Disclosure", True),
    ("Machine readable file", True),
    ("Price transparency report", True),
    ("Chargemaster", True),
    ("About Us", False),
    ("Patient Portal", False),
])
def test_keyword_regex(text: str, expected: bool) -> None:
    assert bool(s4._KEYWORD_RE.search(text)) is expected


# --- S5 fix: response body cap ------------------------------------------------


class _FakeResponse:
    """Minimal stand-in for requests.Response covering the iter_content path."""

    def __init__(
        self,
        body: bytes,
        content_length: str | None = None,
        encoding: str = "utf-8",
        chunk_size: int | None = None,
    ) -> None:
        self.headers = {"Content-Length": content_length} if content_length else {}
        self.encoding = encoding
        self.apparent_encoding = encoding
        self._body = body
        # If chunk_size is set, fragment the body into multiple chunks so the
        # iter_content path is exercised end-to-end (not all at once).
        self._chunk_size = chunk_size or len(body) or 1

    def iter_content(self, chunk_size: int = 65536) -> object:  # noqa: ARG002 - parity with requests
        size = self._chunk_size
        for i in range(0, len(self._body), size):
            yield self._body[i : i + size]


class TestReadCapped:
    """S5 fix: _read_capped enforces MAX_BODY_BYTES even when the server
    omits Content-Length, preventing OOM from a single oversize response."""

    def test_returns_text_when_within_cap(self) -> None:
        body = b"<html>tiny page</html>"
        resp = _FakeResponse(body)
        assert s4._read_capped(resp, max_bytes=1024) == "<html>tiny page</html>"

    def test_rejects_oversize_via_content_length_header(self) -> None:
        # Content-Length declares a body larger than the cap — refuse without
        # downloading anything. Real-world: server lies about size, but if we
        # trust the header on rejection we save bandwidth.
        resp = _FakeResponse(b"unused", content_length=str(10 * 1024 * 1024))
        assert s4._read_capped(resp, max_bytes=1024) is None

    def test_rejects_oversize_when_content_length_absent(self) -> None:
        # Server omits Content-Length AND streams more than the cap — chunked
        # iter_content must abort. Pre-fix, requests.get() loaded the whole
        # body before any size check could fire.
        body = b"x" * (2048)
        resp = _FakeResponse(body, chunk_size=256)
        assert s4._read_capped(resp, max_bytes=1024) is None

    def test_accepts_exact_cap_size(self) -> None:
        body = b"y" * 1024
        resp = _FakeResponse(body, chunk_size=128)
        result = s4._read_capped(resp, max_bytes=1024)
        assert result == "y" * 1024

    def test_handles_chunked_body_within_cap(self) -> None:
        body = b"abc" * 100  # 300 bytes split into 25 chunks of 12 bytes
        resp = _FakeResponse(body, chunk_size=12)
        assert s4._read_capped(resp, max_bytes=1024) == "abc" * 100

    def test_decodes_with_response_encoding(self) -> None:
        body = "café résumé".encode("latin-1")
        resp = _FakeResponse(body, encoding="latin-1")
        assert s4._read_capped(resp, max_bytes=1024) == "café résumé"

    def test_replaces_invalid_bytes_rather_than_raising(self) -> None:
        body = b"\xff\xfe\x00invalid utf-8"
        resp = _FakeResponse(body, encoding="utf-8")
        # Should not raise — replace strategy returns a string with U+FFFD substitutions.
        result = s4._read_capped(resp, max_bytes=1024)
        assert result is not None
        assert "invalid utf-8" in result


class TestTransientCrawlExceptions:
    """S4 fix: distinguish transient (retryable) crawl errors from permanent
    (terminal) ones so the hospital's checkpoint state isn't poisoned by
    a network blip. Pre-fix, every exception was treated identically and
    the hospital was permanently marked 'no MRF found'."""

    def test_module_exposes_transient_set(self) -> None:
        """The set is module-scoped so the catch site can reference it without
        re-importing the requests/socket modules. If this test fails,
        someone removed the module-level constant."""
        import socket as stdlib_socket

        import requests as stdlib_requests

        assert stdlib_requests.Timeout in s4._TRANSIENT_CRAWL_EXCEPTIONS
        assert stdlib_requests.ConnectionError in s4._TRANSIENT_CRAWL_EXCEPTIONS
        assert stdlib_socket.timeout in s4._TRANSIENT_CRAWL_EXCEPTIONS
        assert ConnectionResetError in s4._TRANSIENT_CRAWL_EXCEPTIONS

    @pytest.mark.parametrize(
        "exc_type,is_transient",
        [
            (__import__("requests").Timeout, True),
            (__import__("requests").ConnectionError, True),
            (__import__("socket").timeout, True),
            (ConnectionResetError, True),
            # Permanent: anything outside the explicit transient set
            (ValueError, False),
            (KeyError, False),
            (AttributeError, False),
            (RuntimeError, False),
            # ParseError-like: a downstream regex.error or json.JSONDecodeError
            # is permanent — the page content itself is broken, retrying won't help.
            (json.JSONDecodeError, False),
        ],
    )
    def test_classification(self, exc_type: type[BaseException], is_transient: bool) -> None:
        """Pure classification check — does isinstance against the module's
        TRANSIENT set behave the way the catch site expects?"""
        # Construct a dummy instance and check whether
        # isinstance(e, _TRANSIENT_CRAWL_EXCEPTIONS) matches our intent.
        if exc_type is json.JSONDecodeError:
            instance: BaseException = json.JSONDecodeError("msg", "", 0)
        else:
            try:
                instance = exc_type("msg")
            except TypeError:
                instance = exc_type()
        assert isinstance(instance, s4._TRANSIENT_CRAWL_EXCEPTIONS) is is_transient


class TestStagingTableNaming:
    """H5 fix: staging table no longer starts with `_` so it appears in
    default `bq ls` listings. The constant is constructed inside
    _persist_results — verify the format string by reading the source."""

    def test_staging_table_prefix_is_visible(self) -> None:
        # Read the source to verify the format string. Using a regex to
        # capture the table-name f-string format ensures the fix isn't
        # silently reverted by someone restoring the underscore prefix.
        import inspect

        source = inspect.getsource(s4)
        assert "stage4_staging_" in source
        assert "._stage4_staging_" not in source

    def test_run_id_dashes_are_replaced(self) -> None:
        """BQ table names disallow `-` so any UUID-shaped run_id must have
        dashes converted to underscores. Pure check on the format string."""
        import inspect

        source = inspect.getsource(s4)
        # The format string lives inline as
        # `f"{project}.{dataset}.stage4_staging_{run_id.replace('-', '_')}"`
        # — assert the replace call is present near the table-name format.
        assert 'run_id.replace("-", "_")' in source or "run_id.replace('-', '_')" in source


class TestAssertFlushComplete:
    """S3 fix: end-of-run assertion that converts silent persist failures
    into a non-zero exit. Pre-fix, Stage 4 caught every BQ error and
    reported "complete" even when total_flushed was zero — Cloud Run
    alerts never fired because exit code was 0."""

    def test_clean_finish_does_not_raise(self) -> None:
        """Empty buffers, no recorded failures → success."""
        s4._assert_flush_complete(0, 0, [])

    def test_unflushed_discovered_rows_raise(self) -> None:
        with pytest.raises(RuntimeError, match="42 discovered"):
            s4._assert_flush_complete(42, 0, [("some_batch", "BadRequest")])

    def test_unflushed_failed_rows_raise(self) -> None:
        with pytest.raises(RuntimeError, match="17 failed"):
            s4._assert_flush_complete(0, 17, [])

    def test_both_buffers_pending_lists_both_counts(self) -> None:
        try:
            s4._assert_flush_complete(5, 3, [])
        except RuntimeError as exc:
            assert "5 discovered" in str(exc)
            assert "3 failed" in str(exc)
        else:
            pytest.fail("expected RuntimeError")

    def test_final_flush_failure_raises_even_with_empty_buffers(self) -> None:
        # Buffers cleared via some path but the recorded last failure was on
        # the final flush — defensive raise so the failure isn't lost.
        with pytest.raises(RuntimeError, match="final flush failed"):
            s4._assert_flush_complete(0, 0, [("intermediate", "BadRequest"), ("final", "Forbidden")])

    def test_only_intermediate_failures_recovered_does_not_raise(self) -> None:
        # An intermediate flush failed but a later flush (or the final)
        # successfully persisted everything — exit cleanly. The recorded
        # failure list is informational; what matters is the buffer state.
        s4._assert_flush_complete(0, 0, [("intermediate-1", "Timeout")])


def test_toc_filename_regex() -> None:
    assert s4._TOC_FILENAME_RE.search("standard-charges-toc.json")
    assert s4._TOC_FILENAME_RE.search("toc-standard-charges.json")
    assert s4._TOC_FILENAME_RE.search("standard_charges_toc.json.gz")
    assert not s4._TOC_FILENAME_RE.search("standardcharges.json")  # no toc keyword


# --- HTML link extraction --------------------------------------------------


def test_extract_direct_filename_link() -> None:
    """A direct CMS-shaped href is captured by Pass 1 (filename regex)."""
    html = '<a href="/files/123456789_test_standardcharges.csv">Download</a>'
    links = s4._extract_links_from_html(html, "https://hospital.example.com/page")
    assert "https://hospital.example.com/files/123456789_test_standardcharges.csv" in links


def test_extract_keyword_anchor() -> None:
    """An anchor whose text says "Standard Charges" is captured by Pass 2."""
    html = '<a href="/billing/charges-2026.csv">View Standard Charges</a>'
    links = s4._extract_links_from_html(html, "https://hospital.example.com/")
    assert "https://hospital.example.com/billing/charges-2026.csv" in links


def test_extract_skips_non_http_schemes() -> None:
    html = '<a href="mailto:billing@hospital.com">Email about Standard Charges</a>'
    links = s4._extract_links_from_html(html, "https://hospital.example.com/")
    assert not links


def test_extract_handles_relative_and_absolute() -> None:
    html = """
    <a href="https://cdn.hospital.com/123456789_x_standardcharges.csv">A</a>
    <a href="/local/123456789_y_standardcharges.json">B</a>
    """
    links = s4._extract_links_from_html(html, "https://hospital.example.com/page")
    assert any("cdn.hospital.com" in u for u in links)
    assert any("hospital.example.com/local/" in u for u in links)


def test_resolve_url_drops_fragments() -> None:
    out = s4._resolve_url("https://example.com/page", "/file.csv#section")
    assert out == "https://example.com/file.csv"


def test_resolve_url_rejects_javascript() -> None:
    assert s4._resolve_url("https://example.com/", "javascript:void(0)") is None


# --- File format inference -------------------------------------------------


@pytest.mark.parametrize("url,expected", [
    ("https://x.com/foo.csv", "csv"),
    ("https://x.com/foo.csv.gz", "csv"),
    ("https://x.com/foo.json", "json"),
    ("https://x.com/foo.json.gz", "json"),
    ("https://x.com/foo.xml", "xml"),
    ("https://x.com/foo.xlsx", "xlsx"),
    ("https://x.com/foo.zip", "zip"),
    ("https://x.com/foo", "unknown"),
])
def test_file_format_from_url(url: str, expected: str) -> None:
    assert s4._file_format_from_url(url) == expected


# --- TOC URL extraction ---------------------------------------------------


def test_find_toc_url_in_html() -> None:
    html = '<a href="/cdn/standard-charges-toc.json">Index</a>'
    toc = s4._find_toc_url(html, "https://hospital.example.com/")
    assert toc == "https://hospital.example.com/cdn/standard-charges-toc.json"


def test_find_toc_url_returns_none_when_missing() -> None:
    html = "<html><body>No TOC here</body></html>"
    assert s4._find_toc_url(html, "https://hospital.example.com/") is None


# --- TOC walker (no network) ----------------------------------------------


class TestSutterIncidentRegression:
    """Regression guards for the 2026-05-04 Sutter Stage 4 incident.

    The pre-2026-05-04 code had three bugs that conspired to classify
    Sutter's 5 landing-page URLs as "validated MRF URLs":
      1. _extract_links_from_html Pass 2 accepted URLs whose path contained
         keyword text (e.g. `/cost-transparency`) even when the URL had no
         MRF extension.
      2. _validate_mrf_url accepted text/html as a valid Content-Type.
      3. _SYSTEM_LISTING_PAGES hardcoded `sutterhealth.org` →
         `/billing-insurance/costs-and-charges/cost-transparency`, which
         was a landing page, not an MRF.

    All three are removed. These tests pin the new strict behaviour.
    """

    SUTTER_BAD_URLS = [
        "https://www.sutterhealth.org/billing-insurance/costs-and-charges/billing-hospital-anesthesia",
        "https://www.sutterhealth.org/billing-insurance/costs-and-charges/non-contracted-provider-payment-appeal-process",
        "https://www.sutterhealth.org/billing-insurance/costs-and-charges/cost-transparency",
        "https://www.sutterhealth.org/billing-insurance/costs-and-charges/no-surprises-act",
        "https://www.sutterhealth.org/billing-insurance/costs-and-charges",
    ]

    def test_link_extraction_rejects_landing_pages_with_keyword_text(self) -> None:
        # Each of these 5 anchors has keyword text ("Cost Transparency" etc.)
        # but the URL itself is a landing page. The old Pass 2 accepted them;
        # the new Pass 2 must reject them.
        html = (
            '<a href="/billing-insurance/costs-and-charges/billing-hospital-anesthesia">Billing</a>'
            '<a href="/billing-insurance/costs-and-charges/non-contracted-provider-payment-appeal-process">Provider Payment</a>'
            '<a href="/billing-insurance/costs-and-charges/cost-transparency">Cost Transparency</a>'
            '<a href="/billing-insurance/costs-and-charges/no-surprises-act">No Surprises Act</a>'
            '<a href="/billing-insurance/costs-and-charges">Costs and Charges</a>'
        )
        links = s4._extract_links_from_html(html, "https://www.sutterhealth.org/")
        assert links == set(), (
            f"Sutter landing-page URLs must NOT be classified as MRFs; got {links}"
        )

    def test_link_extraction_keeps_real_mrf_urls(self) -> None:
        # The actual Sutter MRF URL pattern contains a CMS-shaped filename.
        # That MUST still be extracted.
        html = (
            '<a href="/-/media/Project/SutterHealth/SutterHealth/files/'
            'billing-insurance/costs-and-charges/'
            '1295181477_alta-bates-summit-medical-center_standardcharges.csv">Download</a>'
        )
        links = s4._extract_links_from_html(html, "https://www.sutterhealth.org/")
        assert any("1295181477_alta-bates-summit" in u for u in links)

    def test_validate_rejects_url_without_mrf_shape(self) -> None:
        # Gate 1 of _validate_mrf_url filters out landing-page-shaped URLs
        # before any HEAD probe — saves a network call AND prevents
        # accidentally classifying them as MRFs.
        for url in self.SUTTER_BAD_URLS:
            ok, _ct, _size = s4._validate_mrf_url(session=None, url=url)  # type: ignore[arg-type]
            assert ok is False, f"Landing-page URL must be rejected pre-flight: {url}"

    def test_validate_accepts_url_with_real_mrf_shape(self, monkeypatch) -> None:
        # The real Sutter MRF URL passes Gate 1; we mock Gate 2 (HEAD) to
        # simulate a clean text/csv response so the test doesn't need network.
        url = (
            "https://www.sutterhealth.org/-/media/Project/SutterHealth/SutterHealth/files/"
            "billing-insurance/costs-and-charges/"
            "1295181477_alta-bates-summit-medical-center_standardcharges.csv"
        )
        monkeypatch.setattr(s4, "_head_with_ua_fallback", lambda *_a, **_kw: (200, "text/csv", 50_000_000))
        ok, ct, size = s4._validate_mrf_url(session=None, url=url)  # type: ignore[arg-type]
        assert ok is True
        assert ct == "text/csv"
        assert size == 50_000_000

    def test_validate_rejects_html_response_even_for_csv_url(self, monkeypatch) -> None:
        # Defence-in-depth: even if Gate 1 passes (URL ends in .csv) the HEAD
        # probe rejecting text/html stops a misconfigured server from leaking
        # a landing page in.
        url = "https://example.org/files/123456789_test_standardcharges.csv"
        monkeypatch.setattr(s4, "_head_with_ua_fallback", lambda *_a, **_kw: (200, "text/html; charset=utf-8", None))
        ok, ct, _size = s4._validate_mrf_url(session=None, url=url)  # type: ignore[arg-type]
        assert ok is False
        assert "text/html" in ct.lower()

    def test_ok_content_types_no_longer_includes_html(self) -> None:
        # The doomed line was `"text/html",  # some servers mislabel; we accept`.
        # Pin its removal so it can't accidentally come back in.
        assert not any(ct.startswith("text/html") for ct in s4._OK_CONTENT_TYPES)
        assert not any(ct.startswith("application/xhtml") for ct in s4._OK_CONTENT_TYPES)


class TestNoSystemListingDict:
    """The hardcoded _SYSTEM_LISTING_PAGES dict is removed. Pin its absence."""

    def test_no_system_listing_pages_attr(self) -> None:
        assert not hasattr(s4, "_SYSTEM_LISTING_PAGES"), (
            "Hardcoded system-listing dict must stay deleted; the depth-2 "
            "generic follow does the same job universally without curation."
        )

    def test_no_system_listing_path_function(self) -> None:
        assert not hasattr(s4, "_system_listing_path")


class TestKeywordAnchorFollow:
    """The 2026-04-30 rewrite added depth-1 follow-link from the homepage.
    Generic Sutter solution: homepage → 'Cost Transparency' anchor →
    fetch that page → CMS filename regex matches 50+ embedded MRF URLs.
    """

    def test_finds_keyword_anchor(self) -> None:
        html = (
            '<a href="/billing/cost-transparency">Cost Transparency</a>'
            '<a href="/about-us">About Us</a>'  # not a keyword anchor
        )
        # Pass session=None — _follow_keyword_anchors doesn't actually fetch
        # in this helper, only collects URLs to follow.
        out = s4._follow_keyword_anchors(None, html, "https://example.com/")  # type: ignore[arg-type]
        assert ("https://example.com/billing/cost-transparency", "Cost Transparency") in out

    def test_skips_direct_file_links(self) -> None:
        # File links aren't followed as HTML — they're handled by the
        # filename regex extractor on the parent page.
        html = (
            '<a href="/files/123_x_standardcharges.csv">Standard Charges</a>'
            '<a href="/billing/cost-transparency">Cost Transparency</a>'
        )
        out = s4._follow_keyword_anchors(None, html, "https://example.com/")  # type: ignore[arg-type]
        assert all(not u.endswith(".csv") for u, _ in out)

    def test_caps_followups(self) -> None:
        # Build a page with 20 keyword anchors — should cap at 5.
        anchors = "".join(
            f'<a href="/page{i}">Pricing Information</a>' for i in range(20)
        )
        out = s4._follow_keyword_anchors(None, anchors, "https://example.com/", max_followups=5)  # type: ignore[arg-type]
        assert len(out) == 5

    def test_dedupes_by_target_url(self) -> None:
        html = (
            '<a href="/cost-transparency">Cost Transparency</a>'
            '<a href="/cost-transparency">View Standard Charges</a>'  # same target
        )
        out = s4._follow_keyword_anchors(None, html, "https://example.com/")  # type: ignore[arg-type]
        assert len(out) == 1


class TestWidenedKeywordRegex:
    """The 2026-04-30 widening added 12 new keyword variants. Tests guard
    that real-world phrases hospitals use are still recognised."""

    @pytest.mark.parametrize("text,expected", [
        ("Cost Transparency", True),       # Sutter
        ("Costs and Charges", True),       # Sutter
        ("Cost Estimator", True),          # Sutter
        ("Shoppable Services", True),      # CMS-defined
        ("Hospital Charges", True),
        ("Estimate of Charges", True),
        ("Patient Pricing", True),
        ("Pricing Information", True),
        ("View Our Charges", True),
        ("Fee Schedule", True),
        ("Financial Information", True),
        # Originals still match
        ("Standard Charges", True),
        ("Price Transparency", True),
        ("Machine Readable File", True),
        ("Chargemaster", True),
        # 2026-04-30 round 2 — bare "billing" gate
        ("Billing", True),
        ("Billing Information", True),
        ("Pay My Bill", True),
        ("Patient Services", True),
        ("Patient Financial", True),
        # Non-matches — guard against over-broad regex
        ("About Us", False),
        ("Appointments", False),
    ])
    def test_keyword_variants(self, text: str, expected: bool) -> None:
        assert bool(s4._KEYWORD_RE.search(text)) is expected


class TestPass3AnchorDataExtension:
    """Pass 3: any <a href> whose URL ends with a data file extension is
    captured, regardless of anchor text. Catches hospital-name anchor links."""

    def test_hospital_name_anchor_with_csv_href(self) -> None:
        html = '<a href="/files/kaiser-oakland-2024-charges.csv">Kaiser Oakland Medical Center</a>'
        links = s4._extract_links_from_html(html, "https://hospital.example.com/")
        assert "https://hospital.example.com/files/kaiser-oakland-2024-charges.csv" in links

    def test_hospital_name_anchor_with_json_href(self) -> None:
        html = '<a href="/downloads/hospital-2025-prices.json">St. Mary\'s Hospital</a>'
        links = s4._extract_links_from_html(html, "https://hospital.example.com/")
        assert "https://hospital.example.com/downloads/hospital-2025-prices.json" in links

    def test_strips_query_string_before_extension_check(self) -> None:
        html = '<a href="/files/charges.csv?year=2025">Pricing</a>'
        links = s4._extract_links_from_html(html, "https://hospital.example.com/")
        assert "https://hospital.example.com/files/charges.csv?year=2025" in links

    def test_ignores_anchor_pointing_to_html_page(self) -> None:
        html = '<a href="/billing/cost-transparency.html">No anchor text keyword</a>'
        links = s4._extract_links_from_html(html, "https://hospital.example.com/")
        assert not links

    def test_all_data_extensions_captured(self) -> None:
        for ext in (".csv", ".json", ".xlsx", ".xml", ".zip", ".csv.gz", ".json.gz"):
            html = f'<a href="/files/data{ext}">Hospital Name</a>'
            links = s4._extract_links_from_html(html, "https://hospital.example.com/")
            assert any(f"data{ext}" in u for u in links), f"Extension {ext} not captured"


class TestPass4HtmlBodyScan:
    """Pass 4: URL-shaped strings ending in data file extensions anywhere in
    raw HTML, including inside script blocks and data-attributes."""

    def test_url_in_script_variable(self) -> None:
        html = '<script>var downloadUrl = "/files/pricing_data.csv";</script>'
        links = s4._extract_links_from_html(html, "https://hospital.example.com/")
        assert "https://hospital.example.com/files/pricing_data.csv" in links

    def test_url_in_data_attribute(self) -> None:
        html = '<button data-download="/files/2024_charges.xlsx">Download</button>'
        links = s4._extract_links_from_html(html, "https://hospital.example.com/")
        assert "https://hospital.example.com/files/2024_charges.xlsx" in links

    def test_url_in_onclick_handler(self) -> None:
        html = '<button onclick="window.open(\'/files/standardcharges.json\')">View</button>'
        links = s4._extract_links_from_html(html, "https://hospital.example.com/")
        assert "https://hospital.example.com/files/standardcharges.json" in links

    def test_deduplication_across_passes(self) -> None:
        # The same URL appears in an <a href> (Pass 3) AND in a script (Pass 4);
        # result set must contain it only once.
        html = (
            '<a href="/charges.csv">Download</a>'
            '<script>var url = "/charges.csv";</script>'
        )
        links = s4._extract_links_from_html(html, "https://hospital.example.com/")
        assert links.count("https://hospital.example.com/charges.csv") == 1 if isinstance(links, list) else True
        matches = [u for u in links if u == "https://hospital.example.com/charges.csv"]
        assert len(matches) == 1


class TestPathHeuristicFollowSignal:
    """_PATH_HEURISTIC_RE drives a third follow condition in _follow_keyword_anchors:
    an anchor whose href matches a known price-transparency path is followed
    even if neither anchor text nor href hits _KEYWORD_RE."""

    def test_module_exposes_path_heuristic_re(self) -> None:
        assert hasattr(s4, "_PATH_HEURISTIC_RE"), (
            "_PATH_HEURISTIC_RE must be a module-level compiled regex"
        )
        import re
        assert isinstance(s4._PATH_HEURISTIC_RE, re.Pattern)

    def test_path_heuristic_re_matches_known_paths(self) -> None:
        for path in (
            "/price-transparency",
            "/standard-charges",
            "/billing/standard-charges",
            "/patients/billing/standard-charges",
            "/for-patients/price-transparency",
            "/financial-assistance/price-transparency",
        ):
            assert s4._PATH_HEURISTIC_RE.search(path), f"{path} not matched by _PATH_HEURISTIC_RE"

    def test_follow_keyword_anchors_follows_path_heuristic_href(self) -> None:
        # Anchor text is generic ("Learn More") and href has no keyword,
        # but href matches a PATH_HEURISTICS entry — must be followed.
        html = '<a href="/patients/billing/standard-charges">Learn More</a>'
        out = s4._follow_keyword_anchors(None, html, "https://example.com/")  # type: ignore[arg-type]
        assert any("/patients/billing/standard-charges" in u for u, _ in out)

    def test_follow_keyword_anchors_still_follows_keyword_text(self) -> None:
        # Existing behaviour must not regress: keyword in anchor text still works.
        html = '<a href="/some/random/path">Standard Charges</a>'
        out = s4._follow_keyword_anchors(None, html, "https://example.com/")  # type: ignore[arg-type]
        assert any("/some/random/path" in u for u, _ in out)


class TestDepthAndFollowupLimits:
    """Pin MAX_FOLLOW_DEPTH=3 and MAX_FOLLOWUPS_PER_PAGE=15."""

    def test_max_follow_depth_is_three(self) -> None:
        assert s4.MAX_FOLLOW_DEPTH == 3

    def test_max_followups_per_page_is_fifteen(self) -> None:
        assert s4.MAX_FOLLOWUPS_PER_PAGE == 15

    def test_followups_cap_at_fifteen(self) -> None:
        anchors = "".join(
            f'<a href="/page{i}">Standard Charges {i}</a>' for i in range(30)
        )
        out = s4._follow_keyword_anchors(
            None, anchors, "https://example.com/",  # type: ignore[arg-type]
            max_followups=s4.MAX_FOLLOWUPS_PER_PAGE,
        )
        assert len(out) == 15


class TestNewKeywordVariants:
    """Plan A Step 2c additions: verify the 15 new keyword patterns match."""

    @pytest.mark.parametrize("text", [
        "Negotiated Rates",
        "negotiated charges",
        "Contract Rates",
        "For Patients",
        "Patient Financial Assistance",
        "Financial Assistance",
        "Insurance and Billing",
        "Insurance Billing",
        "Healthcare Costs",
        "Cost of Care",
        "CDM",
        "Medical Costs",
        "Out of Pocket",
        "Payer Specific",
        "Health Care Pricing",
        "Understanding Your Bill",
        "Rates and Charges",
    ])
    def test_new_keyword_matches(self, text: str) -> None:
        assert bool(s4._KEYWORD_RE.search(text)), f"'{text}' should match _KEYWORD_RE"


class TestListingPageLogging:
    """A page yielding 5+ file links triggers a [listing_page] log entry."""

    def test_listing_page_log_threshold_constant(self) -> None:
        # The threshold is 5. Confirm _scan_page_for_urls logs at >= 5,
        # not > 5, by checking the source text.
        import inspect
        source = inspect.getsource(s4._scan_page_for_urls)
        assert "newly_added >= 5" in source

    def test_listing_page_log_key_string(self) -> None:
        import inspect
        source = inspect.getsource(s4._scan_page_for_urls)
        assert "[listing_page]" in source


class TestDataFileExtsConstant:
    """_DATA_FILE_EXTS is module-level and reused across Pass 2/3/4."""

    def test_constant_exists(self) -> None:
        assert hasattr(s4, "_DATA_FILE_EXTS")

    def test_contains_expected_extensions(self) -> None:
        for ext in (".csv", ".json", ".xlsx", ".xml", ".zip", ".csv.gz", ".json.gz"):
            assert ext in s4._DATA_FILE_EXTS, f"{ext} missing from _DATA_FILE_EXTS"


class TestNonMrfFilenameBlocklist:
    """Gate 1b: well-known non-MRF filenames are rejected before any HEAD probe."""

    @pytest.mark.parametrize("url", [
        "https://www.hospital.org/manifest.json",
        "https://hospital.org/browserconfig.xml",
        "https://example.com/package.json",
        "https://example.com/sitemap.xml",
        "https://example.com/robots.xml",
        "https://example.com/sw.json",
        "https://example.com/service-worker.json",
        "https://example.com/feed.xml",
    ])
    def test_blocklisted_filenames_rejected(self, url: str) -> None:
        ok, ct, size = s4._validate_mrf_url(session=None, url=url)  # type: ignore[arg-type]
        assert ok is False, f"{url} should be rejected by Gate 1b blocklist"
        assert ct is None
        assert size is None

    def test_real_mrf_json_not_blocked(self, monkeypatch) -> None:
        """A CMS-filename JSON is not affected by the blocklist."""
        url = "https://hospital.org/123456789_test-hospital_standardcharges.json"
        monkeypatch.setattr(s4, "_head_with_ua_fallback", lambda *a, **kw: (200, "application/json", 1000))
        ok, _, _ = s4._validate_mrf_url(session=None, url=url)  # type: ignore[arg-type]
        assert ok is True

    def test_generic_data_json_not_blocked(self, monkeypatch) -> None:
        """A hospital-named JSON with price keyword passes Gate 1c."""
        url = "https://hospital.org/files/2024-standardcharges.json"
        monkeypatch.setattr(s4, "_head_with_ua_fallback", lambda *a, **kw: (200, "application/json", 5000))
        ok, _, _ = s4._validate_mrf_url(session=None, url=url)  # type: ignore[arg-type]
        assert ok is True


class TestGate1cFilenameKeyword:
    """Gate 1c: non-CMS-pattern URLs must contain a price-transparency keyword
    in the filename. Rejects quality reports, annual financials, QTD files."""

    @pytest.mark.parametrize("url", [
        # QTD / quality transparency data
        "https://hospital.org/files/copy-of-6.19.19-copy-of-qtd-050189-george-l.-mee-memorial-hospital-1.xlsx",
        # generic annual report
        "https://hospital.org/docs/annual-report-2024.xlsx",
        # employee data export
        "https://hospital.org/hr/staff-roster-2024.csv",
        # financial statements
        "https://hospital.org/finance/audited-financials-2023.xlsx",
        # no keyword in filename
        "https://hospital.org/files/data.csv",
        "https://hospital.org/files/2024-export.json",
    ])
    def test_non_mrf_xlsx_csv_rejected(self, url: str) -> None:
        ok, _, _ = s4._validate_mrf_url(session=None, url=url)  # type: ignore[arg-type]
        assert ok is False, f"{url} should be rejected by Gate 1c (no price-transparency keyword in filename)"

    @pytest.mark.parametrize("url,keyword", [
        ("https://hospital.org/files/hospital-standard-charges-2024.csv", "standard-charges"),
        ("https://hospital.org/docs/price-transparency-2025.xlsx", "price-transparency"),
        ("https://hospital.org/mrf-2024.json", "mrf"),
        ("https://hospital.org/files/chargemaster-export.csv", "chargemaster"),
        ("https://hospital.org/files/negotiated-rates-payer.xlsx", "negotiated-rates"),
        ("https://hospital.org/billing-charges-2024.xlsx", "charges"),
        ("https://hospital.org/in-network-rates.json", "in-network"),
    ])
    def test_price_transparency_files_pass(self, url: str, keyword: str, monkeypatch) -> None:
        monkeypatch.setattr(s4, "_head_with_ua_fallback", lambda *a, **kw: (200, "application/json", 10000))
        ok, _, _ = s4._validate_mrf_url(session=None, url=url)  # type: ignore[arg-type]
        assert ok is True, f"{url} (keyword: {keyword}) should pass Gate 1c"


def test_toc_walker_extracts_url_keys() -> None:
    """_expand_toc walks any JSON shape and pulls out url-like keys."""
    # Inline-test the inner walker by simulating a successful response.
    sample = {
        "files": [
            {"url": "https://x.com/a_standardcharges.csv"},
            {"location": "/relative/b_standardcharges.json"},
        ],
        "in_network_files": [
            {"href": "https://x.com/c_standardcharges.json"},
        ],
        "noise": {"name": "Not a URL", "id": 12345},
    }

    # Re-implement the inner walker to test it without a network call.
    urls: list[str] = []
    _URL_KEYS = ("url", "location", "href", "file_url", "mrf_url")

    def walk(node):  # type: ignore[no-untyped-def]
        if isinstance(node, dict):
            for k, v in node.items():
                if k.lower() in _URL_KEYS and isinstance(v, str):
                    abs_url = s4._resolve_url("https://hospital.example.com/toc.json", v)
                    if abs_url:
                        urls.append(abs_url)
                else:
                    walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(sample)
    assert "https://x.com/a_standardcharges.csv" in urls
    assert "https://hospital.example.com/relative/b_standardcharges.json" in urls
    assert "https://x.com/c_standardcharges.json" in urls
    # Non-URL fields are not picked up
    assert not any("Not a URL" in u for u in urls)
    assert not any("12345" in u for u in urls)


class TestExpandTocWiderKeys:
    """_expand_toc handles camelCase and non-standard URL key names."""

    def _run_expand(self, payload: dict, monkeypatch) -> list[str]:
        """Helper: mock session.get to return `payload` as JSON, call _expand_toc."""
        import types

        body = json.dumps(payload)

        class _FakeResp:
            status_code = 200
            headers = {"Content-Length": str(len(body))}
            encoding = "utf-8"
            apparent_encoding = "utf-8"
            _body = body.encode()

            def iter_content(self, chunk_size=65536):
                yield self._body

            def close(self):
                pass

        monkeypatch.setattr(
            s4, "_get_with_ua_fallback",
            lambda session, url, timeout: (_FakeResp(), body),
        )
        return s4._expand_toc(None, "https://hospital.org/mrf-index.json")  # type: ignore[arg-type]

    def test_download_url_key(self, monkeypatch) -> None:
        urls = self._run_expand(
            {"mrfFiles": [{"downloadUrl": "https://cdn.hospital.org/charges.csv"}]},
            monkeypatch,
        )
        assert "https://cdn.hospital.org/charges.csv" in urls

    def test_file_path_key(self, monkeypatch) -> None:
        urls = self._run_expand(
            {"results": [{"file_path": "/charges/facility1.csv"}]},
            monkeypatch,
        )
        assert "https://hospital.org/charges/facility1.csv" in urls

    def test_bare_string_array(self, monkeypatch) -> None:
        """A plain list of URL strings (no wrapping dict) should be expanded."""
        urls = self._run_expand(
            ["https://cdn.hospital.org/a.csv", "https://cdn.hospital.org/b.json"],
            monkeypatch,
        )
        assert "https://cdn.hospital.org/a.csv" in urls
        assert "https://cdn.hospital.org/b.json" in urls

    def test_src_key(self, monkeypatch) -> None:
        urls = self._run_expand(
            {"files": [{"src": "https://cdn.hospital.org/charges.xlsx"}]},
            monkeypatch,
        )
        assert "https://cdn.hospital.org/charges.xlsx" in urls


class TestSniffMrfContent:
    """_sniff_mrf_content detects HPT-required fields in the first 8 KB."""

    def _make_session(self, body: bytes, status: int = 200) -> object:
        """Return a minimal mock session whose .get() returns `body`."""
        import types

        class _Resp:
            status_code = status
            headers = {}

            def __init__(self, b: bytes) -> None:
                self._b = b

            def iter_content(self, chunk_size=1024):
                yield self._b

            def close(self):
                pass

        class _Session:
            def get(self, url, **kwargs):
                return _Resp(body)

        return _Session()

    def test_valid_json_hpt_passes(self) -> None:
        body = b'{"hospital_name": "Mercy General", "last_updated_on": "2025-01-01", "version": "3.0.0", "standard_charge_information": []}'
        session = self._make_session(body)
        assert s4._sniff_mrf_content(session, "https://h.org/charges.json", "json") is True  # type: ignore[arg-type]

    def test_json_without_hospital_name_rejected(self) -> None:
        body = b'{"data": [{"id": 1, "value": "test"}], "status": 200}'
        session = self._make_session(body)
        assert s4._sniff_mrf_content(session, "https://h.org/prices.json", "json") is False  # type: ignore[arg-type]

    def test_valid_csv_hpt_passes(self) -> None:
        row1 = b"hospital_name,last_updated_on,version,hospital_address\nMercy General,2025-01-01,3.0.0,123 Main St\n"
        session = self._make_session(row1)
        assert s4._sniff_mrf_content(session, "https://h.org/charges.csv", "csv") is True  # type: ignore[arg-type]

    def test_csv_missing_last_updated_on_rejected(self) -> None:
        row1 = b"description,setting,standard_charge|gross\nService A,inpatient,500\n"
        session = self._make_session(row1)
        assert s4._sniff_mrf_content(session, "https://h.org/charges.csv", "csv") is False  # type: ignore[arg-type]

    def test_xlsx_always_passes(self) -> None:
        """XLSX and other non-json/csv formats fail open (Gate 3 skips them)."""
        session = self._make_session(b"PK\x03\x04garbage")
        assert s4._sniff_mrf_content(session, "https://h.org/charges.xlsx", "xlsx") is True  # type: ignore[arg-type]

    def test_gzipped_csv_fails_open(self) -> None:
        """A .csv.gz file has binary first bytes — Gate 3 must skip it, not reject it."""
        gzip_magic = b"\x1f\x8b\x08\x00garbage binary content"
        session = self._make_session(gzip_magic)
        assert s4._sniff_mrf_content(session, "https://h.org/123456789_mercy_standardcharges.csv.gz", "csv") is True  # type: ignore[arg-type]

    def test_gzipped_json_fails_open(self) -> None:
        """A .json.gz file has binary first bytes — Gate 3 must skip it, not reject it."""
        gzip_magic = b"\x1f\x8b\x08\x00garbage binary content"
        session = self._make_session(gzip_magic)
        assert s4._sniff_mrf_content(session, "https://h.org/123456789_mercy_standardcharges.json.gz", "json") is True  # type: ignore[arg-type]

    def test_network_error_fails_open(self) -> None:
        """Any exception during sniff returns True (fail open)."""
        import requests as _r

        class _ErrorSession:
            def get(self, url, **kwargs):
                raise _r.ConnectionError("host unreachable")

        assert s4._sniff_mrf_content(_ErrorSession(), "https://h.org/charges.json", "json") is True  # type: ignore[arg-type]

    def test_non_200_response_fails_open(self) -> None:
        session = self._make_session(b"", status=503)
        assert s4._sniff_mrf_content(session, "https://h.org/charges.json", "json") is True  # type: ignore[arg-type]

    def test_partial_response_still_detected(self) -> None:
        """hospital_name in first 4 KB is enough even if rest of file is cut off."""
        opening = b'{"hospital_name": "Mercy General", "last_updated_on": "2025-01-01"'
        session = self._make_session(opening)
        assert s4._sniff_mrf_content(session, "https://h.org/charges.json", "json") is True  # type: ignore[arg-type]


class TestGate3Integration:
    """Gate 3 wired into _validate_mrf_url: sniff rejects non-HPT files."""

    def test_json_without_hospital_name_rejected_by_gate3(self, monkeypatch) -> None:
        """A JSON file that passes Gates 1-2 but lacks hospital_name is rejected."""
        url = "https://hospital.org/files/price-transparency-index.json"
        monkeypatch.setattr(s4, "_head_with_ua_fallback", lambda *a, **kw: (200, "application/json", 5000))
        monkeypatch.setattr(s4, "_sniff_mrf_content", lambda *a, **kw: False)
        monkeypatch.setattr(s4, "_expand_toc", lambda *a, **kw: [])
        ok, _, _ = s4._validate_mrf_url(session=None, url=url)  # type: ignore[arg-type]
        assert ok is False

    def test_json_without_hospital_name_tries_toc_expansion(self, monkeypatch) -> None:
        """A JSON failing Gate 3 triggers TOC expansion and injects URLs."""
        url = "https://hospital.org/files/mrf-index.json"
        toc_out: dict[str, str] = {}
        monkeypatch.setattr(s4, "_head_with_ua_fallback", lambda *a, **kw: (200, "application/json", 500))
        monkeypatch.setattr(s4, "_sniff_mrf_content", lambda *a, **kw: False)
        monkeypatch.setattr(
            s4, "_expand_toc",
            lambda *a, **kw: [
                "https://cdn.hospital.org/facility1_standardcharges.csv",
                "https://cdn.hospital.org/facility2_standardcharges.csv",
            ],
        )
        ok, _, _ = s4._validate_mrf_url(session=None, url=url, toc_urls_out=toc_out)  # type: ignore[arg-type]
        assert ok is False
        assert "https://cdn.hospital.org/facility1_standardcharges.csv" in toc_out
        assert "https://cdn.hospital.org/facility2_standardcharges.csv" in toc_out
        assert toc_out["https://cdn.hospital.org/facility1_standardcharges.csv"] == "toc_expansion"

    def test_valid_hpt_json_passes_gate3(self, monkeypatch) -> None:
        """A JSON with hospital_name in first bytes passes Gate 3 and validates."""
        url = "https://hospital.org/files/123456789_mercy_standardcharges.json"
        monkeypatch.setattr(s4, "_head_with_ua_fallback", lambda *a, **kw: (200, "application/json", 100000))
        monkeypatch.setattr(s4, "_sniff_mrf_content", lambda *a, **kw: True)
        ok, _, _ = s4._validate_mrf_url(session=None, url=url)  # type: ignore[arg-type]
        assert ok is True

    def test_csv_missing_hpt_headers_rejected(self, monkeypatch) -> None:
        """A CSV lacking hospital_name/last_updated_on in row 1 is rejected."""
        url = "https://hospital.org/files/standard-charges-2025.csv"
        monkeypatch.setattr(s4, "_head_with_ua_fallback", lambda *a, **kw: (200, "text/csv", 2000))
        monkeypatch.setattr(s4, "_sniff_mrf_content", lambda *a, **kw: False)
        ok, _, _ = s4._validate_mrf_url(session=None, url=url)  # type: ignore[arg-type]
        assert ok is False
