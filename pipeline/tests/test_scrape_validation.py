"""Regression tests for scrape-time content validation (postmortem #1).

Without these the next scheduled scrape can re-pollute the archive with
the same garbage the 5/3 postmortem flagged: HTML 404s, marketing
landing pages, and one Facebook redirect, all written to GCS as
`.json.gz`. The format-sniff guard at scrape time is the root fix.

Tests focus on two pieces:
  - `_PrependedStream`: yields the sniff buffer before draining the
    underlying body (kept for backward-compat; _download_to_gcs no longer
    uses it directly but the class is public API).
  - `_download_to_gcs`: rejects HTML/PDF/unknown responses without
    writing anything to GCS, and streams accepted files via BlobWriter
    (blob.open("wb")) with zero tmpfs usage.
"""

from __future__ import annotations

import gzip
import io
import sys
from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scrape_hospital_mrfs import _PrependedStream, _download_to_gcs


# --- _PrependedStream ------------------------------------------------------

class _FakeRawSocket:
    """Stand-in for `requests.Response.raw` — read-only, non-seekable."""

    def __init__(self, payload: bytes) -> None:
        self._buf = io.BytesIO(payload)

    def read(self, n: int = -1) -> bytes:
        return self._buf.read(n)

    def readinto(self, b) -> int:  # type: ignore[no-untyped-def]
        return self._buf.readinto(b)

    @property
    def decode_content(self) -> bool:
        return False

    @decode_content.setter
    def decode_content(self, value: bool) -> None:
        pass

    def close(self) -> None:
        pass


class TestPrependedStream:
    def test_read_all_returns_prefix_plus_rest(self) -> None:
        stream = _PrependedStream(b"PREFIX-", _FakeRawSocket(b"REST-OF-BODY"))
        assert stream.read() == b"PREFIX-REST-OF-BODY"

    def test_read_chunked_preserves_order(self) -> None:
        stream = _PrependedStream(b"AAAA", _FakeRawSocket(b"BBBBCCCC"))
        assert stream.read(2) == b"AA"
        assert stream.read(4) == b"AABB"
        assert stream.read(100) == b"BBCCCC"
        assert stream.read(1) == b""

    def test_readinto_drains_correctly(self) -> None:
        stream = _PrependedStream(b"AAAA", _FakeRawSocket(b"BBBB"))
        buf = bytearray(8)
        n = stream.readinto(buf)
        assert n == 8
        assert bytes(buf) == b"AAAABBBB"

    def test_empty_prefix_is_transparent(self) -> None:
        stream = _PrependedStream(b"", _FakeRawSocket(b"BODY"))
        assert stream.read() == b"BODY"

    def test_empty_rest_yields_only_prefix(self) -> None:
        stream = _PrependedStream(b"PREFIX", _FakeRawSocket(b""))
        assert stream.read() == b"PREFIX"


# --- _download_to_gcs rejection path --------------------------------------

def _mock_response(body: bytes, content_type: str = "application/json") -> MagicMock:
    """Build a mock requests.Response that streams `body` from .raw.read()."""
    resp = MagicMock()
    resp.headers = {"Content-Type": content_type, "Content-Encoding": ""}
    resp.raw = _FakeRawSocket(body)
    resp.raise_for_status = MagicMock()
    resp.close = MagicMock()
    # After the 4096-byte sniff read from resp.raw, iter_content yields the rest.
    remaining = body[4096:]
    resp.iter_content = MagicMock(return_value=iter([remaining] if remaining else []))
    return resp


class _WriteCaptureContextManager:
    """Context manager that captures all bytes written through blob.open("wb")."""

    def __init__(self, captured: list[bytes]) -> None:
        self._buf = io.BytesIO()
        self._captured = captured

    def write(self, data: bytes) -> None:
        self._buf.write(data)

    def __enter__(self) -> "_WriteCaptureContextManager":
        return self

    def __exit__(self, *args: object) -> bool:
        self._captured.append(self._buf.getvalue())
        return False


def _mock_bucket() -> tuple[MagicMock, list[bytes]]:
    """Returns (bucket_mock, captured_chunks) where captured_chunks collects bytes written via blob.open("wb")."""
    bucket = MagicMock()
    bucket.name = "mrf-staging"
    blob = MagicMock()
    bucket.blob.return_value = blob
    captured: list[bytes] = []

    blob.open.side_effect = lambda *args, **kwargs: _WriteCaptureContextManager(captured)
    return bucket, captured


class TestDownloadToGcsValidation:
    def test_rejects_html_response(self) -> None:
        # Real example: dignityhealth.org/.../insurance-information page.
        bucket, _ = _mock_bucket()
        session = MagicMock()
        session.get.return_value = _mock_response(
            b"<!DOCTYPE html><html><head><title>404</title></head><body></body></html>",
            content_type="text/html",
        )
        result = _download_to_gcs(
            session, bucket,
            hospital={"hospital_name": "Test Hospital", "mrf_url": "https://x.org/landing"},
            scraped_at="2026-05-04T00:00:00Z",
        )
        assert result is None, "HTML response must be rejected before upload"
        bucket.blob.return_value.open.assert_not_called()

    def test_rejects_pdf_response(self) -> None:
        bucket, _ = _mock_bucket()
        session = MagicMock()
        session.get.return_value = _mock_response(
            b"%PDF-1.7\n%...content...",
            content_type="application/pdf",
        )
        result = _download_to_gcs(
            session, bucket,
            hospital={"hospital_name": "Test", "mrf_url": "https://x.org/notice.pdf"},
            scraped_at="2026-05-04T00:00:00Z",
        )
        assert result is None
        bucket.blob.return_value.open.assert_not_called()

    def test_accepts_json_and_uploads(self) -> None:
        bucket, _ = _mock_bucket()
        session = MagicMock()
        session.get.return_value = _mock_response(
            b'{"hospital_name":"X","hospital_npi":"1234567890","standard_charge_information":[]}',
            content_type="application/json",
        )
        result = _download_to_gcs(
            session, bucket,
            hospital={"hospital_name": "Test Hospital", "mrf_url": "https://x.org/charges.json",
                      "hospital_npi": "1234567890"},
            scraped_at="2026-05-04T00:00:00Z",
        )
        assert result is not None
        bucket.blob.return_value.open.assert_called_once()

    def test_accepts_gzipped_json(self) -> None:
        bucket, _ = _mock_bucket()
        session = MagicMock()
        session.get.return_value = _mock_response(
            gzip.compress(b'{"hospital_npi":"1234567890"}'),
            content_type="application/octet-stream",
        )
        result = _download_to_gcs(
            session, bucket,
            hospital={"hospital_name": "Test", "mrf_url": "https://x.org/charges.json.gz",
                      "hospital_npi": "1234567890"},
            scraped_at="2026-05-04T00:00:00Z",
        )
        assert result is not None

    def test_accepts_csv_via_url(self) -> None:
        bucket, _ = _mock_bucket()
        session = MagicMock()
        session.get.return_value = _mock_response(
            b"code,description,charge\n99214,Office,350.00\n",
            content_type="text/csv",
        )
        result = _download_to_gcs(
            session, bucket,
            hospital={"hospital_name": "Test", "mrf_url": "https://x.org/charges.csv",
                      "hospital_npi": "1234567890"},
            scraped_at="2026-05-04T00:00:00Z",
        )
        assert result is not None

    def test_uploaded_bytes_match_full_body(self) -> None:
        # The sniffer reads 4 KB; verify those bytes are not lost —
        # upload_from_file must receive the original body unchanged.
        bucket, captured = _mock_bucket()
        session = MagicMock()
        body = b'{"hospital_npi":"1234567890",' + b'"x":"y",' * 1000 + b'"end":"yes"}'
        session.get.return_value = _mock_response(body, content_type="application/json")
        result = _download_to_gcs(
            session, bucket,
            hospital={"hospital_name": "Test", "mrf_url": "https://x.org/charges.json",
                      "hospital_npi": "1234567890"},
            scraped_at="2026-05-04T00:00:00Z",
        )
        assert result is not None
        assert len(captured) == 1
        assert captured[0] == body
