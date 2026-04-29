"""Regression tests for API key extraction.

Sandra's 2026-04-28 incident: a Secret Manager secret got contaminated with
gcloud bootstrap output (pip install logs interleaved with the API key on
the last line). The contaminated string was passed verbatim as a request
header, which leaked the key into the error log when requests rejected the
header value.

These tests prove the extractor:
  1. Extracts a clean key from a contaminated payload
  2. Never logs the contaminated value
  3. Preserves clean keys unchanged
  4. Raises (rather than returning a bad key) when no key is found
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from mrf_discovery.stage3_tier3_places import _extract_clean_api_key  # noqa: E402


CLEAN_KEY = "AIzaSyDA-kAjWnBpqZv0hw9eS9Ju2NkJ20Gr4C0"


class TestApiKeyExtraction:
    def test_clean_key_passes_through(self):
        assert _extract_clean_api_key(CLEAN_KEY) == CLEAN_KEY

    def test_clean_key_with_trailing_newline(self):
        assert _extract_clean_api_key(CLEAN_KEY + "\n") == CLEAN_KEY

    def test_clean_key_with_trailing_whitespace(self):
        assert _extract_clean_api_key(f"  {CLEAN_KEY}  \n") == CLEAN_KEY

    def test_extracts_from_contaminated_payload(self):
        # Reproduces Sandra's 2026-04-28 incident shape exactly: gcloud
        # bootstrap output followed by the key on the last line.
        contaminated = (
            "Collecting cryptography==42.0.7\n"
            "  Downloading https://github.com/...\n"
            "Requirement already satisfied: crcmod\n"
            "Setting up virtual environment\n"
            f"{CLEAN_KEY}"
        )
        assert _extract_clean_api_key(contaminated) == CLEAN_KEY

    def test_raises_on_empty(self):
        with pytest.raises(ValueError, match="Empty"):
            _extract_clean_api_key("")

    def test_raises_when_no_key_pattern_found(self):
        with pytest.raises(ValueError, match="No valid Google API key"):
            _extract_clean_api_key("not a key at all, just text")

    def test_error_message_does_not_leak_payload(self):
        # Critical: when extraction fails, the exception message MUST NOT
        # include the original payload (which may contain partial credentials,
        # PII, or other sensitive data).
        sensitive_payload = "wrong but contains password=hunter2 and ssn=123-45-6789"
        try:
            _extract_clean_api_key(sensitive_payload)
            pytest.fail("Should have raised ValueError")
        except ValueError as exc:
            msg = str(exc)
            assert "hunter2" not in msg
            assert "123-45-6789" not in msg
            assert "password" not in msg
            # Length signal IS allowed (helps debugging without leaking content)
            assert str(len(sensitive_payload)) in msg

    def test_extracts_first_match_only(self):
        # If somehow two keys end up in the payload (unlikely but possible
        # during rotation), we take the first.
        payload = f"{CLEAN_KEY}\nrandom text\nAIzaSyOtherKey1234567890123456789012"
        result = _extract_clean_api_key(payload)
        assert result == CLEAN_KEY

    def test_real_key_shape(self):
        # Google API keys are exactly 39 characters: "AIza" (4) + 35 alphanumeric/_/-
        # If anyone "tightens" the regex too far, this test catches it.
        assert len(CLEAN_KEY) == 39
        assert CLEAN_KEY.startswith("AIza")
        result = _extract_clean_api_key(CLEAN_KEY)
        assert len(result) == 39
