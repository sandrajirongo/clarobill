"""Tests for the insurance card extraction endpoint.

Covers the contract surface that has zero unit tests pre-Phase 7:

- MIME validation (415 for unsupported types)
- Size cap (413 for >10MB)
- Gemini happy path
- Gemini failure → Claude fallback path
- Both providers fail → 502
- AI returns unparsable JSON → 502
- Markdown code-fence stripping
- plan_type defaults to 'commercial' when AI returns null/empty

Per the Phase 7 design call, PostHog telemetry is asserted (not mocked-and-
ignored): event names are part of the public contract with the analytics
dashboard, so a rename here forces a deliberate update on both ends.

The Vertex AI Gemini call is patched at `_extract_via_gemini`; the Claude
call is patched at `_extract_via_claude_sync`. The real anthropic client is
never constructed.
"""

from __future__ import annotations

import io
import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.insurance_card import (
    InsuranceCardExtraction,
    _parse_ai_response,
    router,
)


# ── App fixture (no auth, just the router) ────────────────────────────────────


@pytest.fixture()
def client() -> TestClient:
    """Mount the router on a bare FastAPI app — no engine API key required."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return TestClient(app)


def _png_bytes(size: int = 1024) -> bytes:
    """Return a buffer that starts with the PNG magic header."""
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * (size - 8)


def _gemini_response(**fields: Any) -> str:
    """Build a fake Gemini text response with the given JSON fields."""
    payload: dict[str, Any] = {
        "payer_name": "Anthem Blue Cross",
        "plan_name": "Choice POS I",
        "member_id": "ABC12345",
        "group_id": "GRP9999",
        "plan_type": "commercial",
        "rx_bin": "610502",
        "rx_pcn": "MEDDPRIME",
        "rx_group": "BCBSWA",
        "confident": True,
        "note": None,
    }
    payload.update(fields)
    return json.dumps(payload)


# ── _parse_ai_response (pure function) ────────────────────────────────────────


class TestParseAiResponse:
    def test_plain_json_parses(self) -> None:
        assert _parse_ai_response('{"foo": "bar"}') == {"foo": "bar"}

    def test_markdown_code_fence_stripped(self) -> None:
        text = '```json\n{"foo": "bar"}\n```'
        assert _parse_ai_response(text) == {"foo": "bar"}

    def test_bare_triple_backtick_fence_stripped(self) -> None:
        text = '```\n{"foo": "bar"}\n```'
        assert _parse_ai_response(text) == {"foo": "bar"}

    def test_leading_whitespace_tolerated(self) -> None:
        text = '   \n  {"foo": "bar"}  \n'
        assert _parse_ai_response(text) == {"foo": "bar"}

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            _parse_ai_response("not json at all")


# ── /insurance-card/extract endpoint ──────────────────────────────────────────


class TestExtractEndpoint:
    """Exercises the full request handler with provider calls patched."""

    @pytest.fixture()
    def gemini_mock(self) -> Any:
        with patch(
            "app.api.insurance_card._extract_via_gemini",
            new_callable=MagicMock,
        ) as m:
            async def _async(_bytes: bytes, _mime: str) -> str:
                return _gemini_response()
            m.side_effect = _async
            yield m

    @pytest.fixture()
    def claude_mock(self) -> Any:
        with patch("app.api.insurance_card._extract_via_claude_sync") as m:
            m.return_value = _gemini_response()
            yield m

    @pytest.fixture()
    def posthog_mock(self) -> Any:
        with patch("app.api.insurance_card.posthog_client.capture") as m:
            yield m

    # ── Validation ─────────────────────────────────────────────────────────────

    def test_rejects_unsupported_mime_with_415(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/insurance-card/extract",
            files={"image": ("card.tiff", b"fake-tiff-bytes", "image/tiff")},
        )
        assert response.status_code == 415
        assert "JPEG, PNG, or WebP" in response.json()["detail"]

    def test_rejects_pdf_with_415(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/insurance-card/extract",
            files={"image": ("card.pdf", b"%PDF-1.4", "application/pdf")},
        )
        assert response.status_code == 415

    def test_rejects_oversize_image_with_413(
        self, client: TestClient, gemini_mock: MagicMock,
    ) -> None:
        # Construct an image just over 10 MB (10 * 1024 * 1024 + 1 bytes).
        big = _png_bytes(10 * 1024 * 1024 + 1)
        response = client.post(
            "/api/v1/insurance-card/extract",
            files={"image": ("card.png", big, "image/png")},
        )
        assert response.status_code == 413
        # Gemini must NOT be called when the upload is rejected pre-extract.
        gemini_mock.assert_not_called()

    def test_accepts_jpeg_png_webp(
        self, client: TestClient, gemini_mock: MagicMock,
    ) -> None:
        for filename, mime in (
            ("card.jpg", "image/jpeg"),
            ("card.png", "image/png"),
            ("card.webp", "image/webp"),
        ):
            response = client.post(
                "/api/v1/insurance-card/extract",
                files={"image": (filename, _png_bytes(), mime)},
            )
            assert response.status_code == 200, f"Failed for {mime}: {response.text}"

    # ── Gemini happy path ──────────────────────────────────────────────────────

    def test_gemini_success_returns_parsed_fields(
        self,
        client: TestClient,
        gemini_mock: MagicMock,
        claude_mock: MagicMock,
    ) -> None:
        response = client.post(
            "/api/v1/insurance-card/extract",
            files={"image": ("card.png", _png_bytes(), "image/png")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["payer_name"] == "Anthem Blue Cross"
        assert data["member_id"] == "ABC12345"
        assert data["plan_type"] == "commercial"
        assert data["confident"] is True
        # Claude must NOT be called when Gemini succeeds.
        claude_mock.assert_not_called()

    def test_gemini_strips_markdown_fence_in_response(
        self, client: TestClient,
    ) -> None:
        async def _fenced(_bytes: bytes, _mime: str) -> str:
            return f"```json\n{_gemini_response(payer_name='UnitedHealthcare')}\n```"

        with patch(
            "app.api.insurance_card._extract_via_gemini", new=_fenced,
        ):
            response = client.post(
                "/api/v1/insurance-card/extract",
                files={"image": ("card.png", _png_bytes(), "image/png")},
            )
        assert response.status_code == 200
        assert response.json()["payer_name"] == "UnitedHealthcare"

    # ── Fallback path (Gemini fails → Claude succeeds) ─────────────────────────

    def test_gemini_failure_triggers_claude_fallback(
        self, client: TestClient, claude_mock: MagicMock,
    ) -> None:
        async def _gemini_explodes(_bytes: bytes, _mime: str) -> str:
            raise RuntimeError("Vertex quota exceeded")

        with patch(
            "app.api.insurance_card._extract_via_gemini",
            new=_gemini_explodes,
        ):
            response = client.post(
                "/api/v1/insurance-card/extract",
                files={"image": ("card.png", _png_bytes(), "image/png")},
            )
        assert response.status_code == 200
        assert claude_mock.called, "Expected Claude fallback to fire when Gemini failed"
        assert response.json()["payer_name"] == "Anthem Blue Cross"

    def test_both_providers_fail_returns_502(
        self, client: TestClient,
    ) -> None:
        async def _gemini_explodes(_bytes: bytes, _mime: str) -> str:
            raise RuntimeError("Vertex down")

        def _claude_explodes(*_args: object, **_kwargs: object) -> str:
            raise RuntimeError("Anthropic down")

        with patch(
            "app.api.insurance_card._extract_via_gemini", new=_gemini_explodes,
        ), patch(
            "app.api.insurance_card._extract_via_claude_sync", new=_claude_explodes,
        ):
            response = client.post(
                "/api/v1/insurance-card/extract",
                files={"image": ("card.png", _png_bytes(), "image/png")},
            )
        assert response.status_code == 502
        assert "Could not read the card" in response.json()["detail"]

    # ── AI returns malformed JSON ──────────────────────────────────────────────

    def test_unparsable_ai_response_returns_502(
        self, client: TestClient,
    ) -> None:
        async def _garbage(_bytes: bytes, _mime: str) -> str:
            return "I'm sorry, I can't read this image."

        with patch(
            "app.api.insurance_card._extract_via_gemini", new=_garbage,
        ):
            response = client.post(
                "/api/v1/insurance-card/extract",
                files={"image": ("card.png", _png_bytes(), "image/png")},
            )
        assert response.status_code == 502
        assert "parse" in response.json()["detail"].lower()

    # ── Field-level normalization ──────────────────────────────────────────────

    def test_plan_type_defaults_to_commercial_when_null(
        self, client: TestClient,
    ) -> None:
        """Missing/null plan_type must default to 'commercial' — the rules engine
        downstream uses plan_type to pick rate multipliers; a None here would
        crash the price-outlier rule."""
        async def _no_plan_type(_bytes: bytes, _mime: str) -> str:
            return _gemini_response(plan_type=None)

        with patch(
            "app.api.insurance_card._extract_via_gemini", new=_no_plan_type,
        ):
            response = client.post(
                "/api/v1/insurance-card/extract",
                files={"image": ("card.png", _png_bytes(), "image/png")},
            )
        assert response.status_code == 200
        assert response.json()["plan_type"] == "commercial"

    def test_empty_string_fields_normalize_to_none(
        self, client: TestClient,
    ) -> None:
        """`_str` returns None for empty strings — keeps the DB rows clean of
        empty values that would otherwise pass `if foo:` checks downstream."""
        async def _empties(_bytes: bytes, _mime: str) -> str:
            return _gemini_response(group_id="", rx_bin="", note="")

        with patch(
            "app.api.insurance_card._extract_via_gemini", new=_empties,
        ):
            response = client.post(
                "/api/v1/insurance-card/extract",
                files={"image": ("card.png", _png_bytes(), "image/png")},
            )
        data = response.json()
        assert data["group_id"] is None
        assert data["rx_bin"] is None
        assert data["note"] is None

    # ── PostHog telemetry contract ────────────────────────────────────────────

    def test_success_event_fires_with_provider_label(
        self, client: TestClient,
        gemini_mock: MagicMock,
        posthog_mock: MagicMock,
    ) -> None:
        client.post(
            "/api/v1/insurance-card/extract",
            files={"image": ("card.png", _png_bytes(), "image/png")},
        )
        events = [c.kwargs.get("event") for c in posthog_mock.call_args_list]
        assert "insurance card extracted" in events
        # Find the success call and assert its provider label.
        for call in posthog_mock.call_args_list:
            if call.kwargs.get("event") == "insurance card extracted":
                props = call.kwargs.get("properties", {})
                assert props.get("provider") == "gemini"
                assert props.get("$process_person_profile") is False
                return
        pytest.fail("'insurance card extracted' event was not captured")

    def test_fallback_provider_label_is_claude(
        self, client: TestClient,
        claude_mock: MagicMock,
        posthog_mock: MagicMock,
    ) -> None:
        async def _gemini_explodes(_bytes: bytes, _mime: str) -> str:
            raise RuntimeError("down")

        with patch(
            "app.api.insurance_card._extract_via_gemini", new=_gemini_explodes,
        ):
            client.post(
                "/api/v1/insurance-card/extract",
                files={"image": ("card.png", _png_bytes(), "image/png")},
            )

        for call in posthog_mock.call_args_list:
            if call.kwargs.get("event") == "insurance card extracted":
                assert call.kwargs["properties"]["provider"] == "claude"
                return
        pytest.fail("Expected 'insurance card extracted' event with provider=claude")

    def test_failure_event_fires_when_both_providers_fail(
        self, client: TestClient, posthog_mock: MagicMock,
    ) -> None:
        async def _gemini_explodes(_bytes: bytes, _mime: str) -> str:
            raise RuntimeError("down")

        def _claude_explodes(*_args: object, **_kwargs: object) -> str:
            raise RuntimeError("down")

        with patch(
            "app.api.insurance_card._extract_via_gemini", new=_gemini_explodes,
        ), patch(
            "app.api.insurance_card._extract_via_claude_sync",
            new=_claude_explodes,
        ):
            client.post(
                "/api/v1/insurance-card/extract",
                files={"image": ("card.png", _png_bytes(), "image/png")},
            )
        events = [c.kwargs.get("event") for c in posthog_mock.call_args_list]
        assert "insurance card extraction failed" in events
        # And the success event must NOT have fired.
        assert "insurance card extracted" not in events


# ── Pydantic model contract ───────────────────────────────────────────────────


class TestInsuranceCardExtractionModel:
    """Confirms strict-mode + nullability rules on the response schema."""

    def test_strict_mode_rejects_int_for_string_field(self) -> None:
        with pytest.raises(Exception):  # pydantic.ValidationError
            InsuranceCardExtraction(
                payer_name=12345,  # type: ignore[arg-type]
                plan_name=None, member_id=None, group_id=None,
                plan_type="commercial", rx_bin=None, rx_pcn=None,
                rx_group=None, confident=False, note=None,
            )

    def test_required_fields_can_be_none(self) -> None:
        """Every string field is Optional — confidence may be low, the AI
        can return null for any field."""
        result = InsuranceCardExtraction(
            payer_name=None, plan_name=None, member_id=None, group_id=None,
            plan_type="commercial", rx_bin=None, rx_pcn=None, rx_group=None,
            confident=False, note=None,
        )
        assert result.payer_name is None
        assert result.confident is False
