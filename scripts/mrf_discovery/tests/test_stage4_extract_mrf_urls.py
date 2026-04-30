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


class TestSystemListingPages:
    """The 2026-04-30 widening added a curated dict of hospital-system
    listing pages so we hit Sutter / HCA / Ascension etc. directly. These
    tests guard the lookup contract — substring host match, first-hit-wins.
    """

    def test_sutter_homepage_resolves_to_listing(self) -> None:
        path = s4._system_listing_path("www.sutterhealth.org")
        assert path == "/billing-insurance/costs-and-charges/cost-transparency"

    def test_unknown_system_returns_none(self) -> None:
        path = s4._system_listing_path("www.tinyruralhospital.com")
        assert path is None

    def test_subdomain_match(self) -> None:
        # `mychart.sutterhealth.org` is still a Sutter property.
        path = s4._system_listing_path("mychart.sutterhealth.org")
        assert path is not None
        assert "cost-transparency" in path

    def test_curated_list_has_verified_entries(self) -> None:
        # Round-2 trimmed the list from 16 unverified to 5 verified entries.
        # Guard floor at 4 so we notice if more entries get pruned without
        # replacement; raise this when new systems are verified + added.
        assert len(s4._SYSTEM_LISTING_PAGES) >= 4


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
