"""Unit tests for Stage 3 Tier 1 URL validation logic.

Exercises validate_url against a mocked HTTP layer using `responses`. No real
network calls. The real-network behavior is implicitly covered by the dev-time
sanity check Sandra runs.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from mrf_discovery.stage3_tier1_validate_urls import (  # noqa: E402
    ACCEPTABLE_CONTENT_TYPES,
    ValidationResult,
    validate_url,
)


def _mock_response(status=200, content_type="text/html", final_url=None):
    """Build a stub requests.Response-like object.

    Sets `_content_consumed=True` so tests that call .close() on the response
    (the GET fallback path) don't try to close a non-existent raw stream.
    """
    r = requests.Response()
    r.status_code = status
    r.headers["Content-Type"] = content_type
    r.url = final_url or "https://example.com"
    r._content_consumed = True  # prevents .close() from touching .raw
    return r


class TestValidateUrl:
    def test_200_html_is_valid(self):
        with patch("mrf_discovery.stage3_tier1_validate_urls.requests.head") as mock_head:
            mock_head.return_value = _mock_response(200, "text/html; charset=utf-8")
            r = validate_url("https://hospital.example.com", "010001")
            assert r.valid is True
            assert r.reason == "ok"
            assert r.status_code == 200

    def test_404_is_invalid(self):
        with patch("mrf_discovery.stage3_tier1_validate_urls.requests.head") as mock_head:
            mock_head.return_value = _mock_response(404)
            r = validate_url("https://broken.example.com", "010001")
            assert r.valid is False
            assert r.reason == "http_404"

    def test_500_is_invalid(self):
        with patch("mrf_discovery.stage3_tier1_validate_urls.requests.head") as mock_head:
            mock_head.return_value = _mock_response(500)
            r = validate_url("https://broken.example.com", "010001")
            assert r.valid is False
            assert "500" in r.reason

    def test_pdf_content_type_rejected(self):
        with patch("mrf_discovery.stage3_tier1_validate_urls.requests.head") as mock_head:
            mock_head.return_value = _mock_response(200, "application/pdf")
            r = validate_url("https://hospital.example.com/info.pdf", "010001")
            assert r.valid is False
            assert "non_html" in r.reason

    def test_xhtml_content_type_accepted(self):
        with patch("mrf_discovery.stage3_tier1_validate_urls.requests.head") as mock_head:
            mock_head.return_value = _mock_response(200, "application/xhtml+xml")
            r = validate_url("https://hospital.example.com", "010001")
            assert r.valid is True

    def test_empty_content_type_accepted(self):
        # Some servers omit Content-Type on HEAD; we accept this rather than
        # double-charge with a GET fallback.
        with patch("mrf_discovery.stage3_tier1_validate_urls.requests.head") as mock_head:
            mock_head.return_value = _mock_response(200, "")
            r = validate_url("https://hospital.example.com", "010001")
            assert r.valid is True

    def test_timeout_invalid(self):
        with patch("mrf_discovery.stage3_tier1_validate_urls.requests.head") as mock_head:
            mock_head.side_effect = requests.Timeout()
            r = validate_url("https://slow.example.com", "010001")
            assert r.valid is False
            assert r.reason == "timeout"

    def test_connection_error_invalid(self):
        with patch("mrf_discovery.stage3_tier1_validate_urls.requests.head") as mock_head:
            mock_head.side_effect = requests.ConnectionError("DNS lookup failed")
            r = validate_url("https://nodns.example.com", "010001")
            assert r.valid is False
            assert r.reason == "connection_error"

    def test_ssl_error_invalid(self):
        with patch("mrf_discovery.stage3_tier1_validate_urls.requests.head") as mock_head:
            mock_head.side_effect = requests.ConnectionError("SSL certificate verify failed")
            r = validate_url("https://badcert.example.com", "010001")
            assert r.valid is False
            assert r.reason == "ssl_error"

    def test_redirect_loop_invalid(self):
        with patch("mrf_discovery.stage3_tier1_validate_urls.requests.head") as mock_head:
            mock_head.side_effect = requests.TooManyRedirects()
            r = validate_url("https://loop.example.com", "010001")
            assert r.valid is False
            assert r.reason == "redirect_loop"

    def test_405_falls_back_to_get(self):
        # Some servers reject HEAD with 405; we try GET as a fallback
        with patch("mrf_discovery.stage3_tier1_validate_urls.requests.head") as mock_head, \
             patch("mrf_discovery.stage3_tier1_validate_urls.requests.get") as mock_get:
            mock_head.return_value = _mock_response(405)
            mock_get.return_value = _mock_response(200, "text/html")
            r = validate_url("https://strict-server.example.com", "010001")
            assert r.valid is True
            assert mock_get.called

    def test_403_falls_back_to_get(self):
        with patch("mrf_discovery.stage3_tier1_validate_urls.requests.head") as mock_head, \
             patch("mrf_discovery.stage3_tier1_validate_urls.requests.get") as mock_get:
            mock_head.return_value = _mock_response(403)
            mock_get.return_value = _mock_response(200, "text/html")
            r = validate_url("https://blocks-head.example.com", "010001")
            assert r.valid is True

    def test_redirect_final_url_recorded(self):
        with patch("mrf_discovery.stage3_tier1_validate_urls.requests.head") as mock_head:
            mock_head.return_value = _mock_response(
                200, "text/html",
                final_url="https://www.canonical-hospital.org/",
            )
            r = validate_url("https://hospital.example.com", "010001")
            assert r.valid is True
            assert r.final_url == "https://www.canonical-hospital.org/"


class TestValidationResult:
    def test_namedtuple_fields(self):
        r = ValidationResult("010001", "https://x.com", True, "https://x.com", 200, "ok")
        assert r.ccn == "010001"
        assert r.valid is True
        assert r.status_code == 200


class TestAcceptableContentTypes:
    def test_includes_html(self):
        assert any("html" in t for t in ACCEPTABLE_CONTENT_TYPES)

    def test_excludes_pdf(self):
        assert "application/pdf" not in ACCEPTABLE_CONTENT_TYPES
