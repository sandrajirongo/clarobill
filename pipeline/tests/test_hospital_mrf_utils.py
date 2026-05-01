"""Regression tests for pipeline/hospital_mrf_utils.py.

Lives next to the module (not under apps/engine/) because hospital_mrf_utils
ships in the pipeline image, not the engine image.

Run with:
    cd pipeline && python -m pytest tests/ -v
or from repo root:
    python -m pytest pipeline/tests/ -v
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hospital_mrf_utils import ChargeRow, _strip_bom, stream_charges_v2


# --- Fixtures ---------------------------------------------------------------

def _minimal_v2_mrf() -> dict:
    """A valid CMS v2.0.0 MRF with one charge item and one payer."""
    return {
        "hospital_name": "Test Hospital",
        "hospital_npi": "1234567890",
        "last_updated_on": "2026-01-15",
        "version": "2.0.0",
        "standard_charge_information": [
            {
                "description": "Office visit, established patient, moderate complexity",
                "code_information": [{"code": "99214", "type": "CPT"}],
                "standard_charges": [
                    {
                        "setting": "outpatient",
                        "gross_charge": 350.00,
                        "discounted_cash": 200.00,
                        "minimum": 100.00,
                        "maximum": 280.00,
                        "payers_information": [
                            {
                                "payer_name": "Aetna",
                                "plan_name": "PPO",
                                "standard_charge_dollar": 180.00,
                                "methodology": "fee schedule",
                            },
                        ],
                    },
                ],
            },
        ],
    }


def _stream(payload: bytes) -> io.BytesIO:
    return io.BytesIO(payload)


def _all_rows(stream: io.BytesIO) -> list[ChargeRow]:
    return list(stream_charges_v2(
        stream, hospital_npi="1234567890", pricing_effective_year=2026,
        scraped_at="2026-04-29T00:00:00Z",
        source_mrf_url="https://example.com/test.json",
        source_gcs_uri="gs://mrf-archive-clarobill-prd/pricing-year=2026/1234567890/abc.json",
    ))


# --- BOM-strip tests --------------------------------------------------------

class TestBomStrip:
    """Phase 4 regression: UTF-8 BOM at start of MRF must not break parsing.

    Real-world finding: Saint Michaels Medical Center exported their MRF
    from a Windows tool that prepends `\\xef\\xbb\\xbf` (UTF-8 BOM). ijson
    sees this and emits zero items — losing the entire hospital's pricing
    data. _strip_bom() detects and strips the BOM before ijson sees it.
    """

    def test_no_bom_yields_full_rows(self) -> None:
        payload = json.dumps(_minimal_v2_mrf()).encode()
        rows = _all_rows(_stream(payload))
        assert len(rows) == 1
        assert rows[0].code == "99214"
        assert rows[0].pricing_effective_year == 2026

    def test_bom_prefixed_payload_still_parses(self) -> None:
        # The real Saint Michaels file shape: BOM + JSON
        bom = b"\xef\xbb\xbf"
        payload = bom + json.dumps(_minimal_v2_mrf()).encode()
        rows = _all_rows(_stream(payload))
        assert len(rows) == 1
        assert rows[0].code == "99214"

    def test_bom_only_consumed_when_present(self) -> None:
        # Direct unit test of _strip_bom — sniffing must not consume bytes
        # from a payload that does NOT start with a BOM.
        payload = b'{"hello":"world"}'
        wrapped = _strip_bom(_stream(payload))
        assert wrapped.read() == payload

    def test_bom_stripped_when_present(self) -> None:
        bom = b"\xef\xbb\xbf"
        payload = bom + b'{"hello":"world"}'
        wrapped = _strip_bom(_stream(payload))
        assert wrapped.read() == b'{"hello":"world"}'

    def test_short_stream_no_bom(self) -> None:
        # A 1-byte stream that can't possibly contain the 3-byte BOM
        wrapped = _strip_bom(_stream(b'X'))
        assert wrapped.read() == b'X'


# --- Per-row tolerance test (Phase 4 Q5b) -----------------------------------

class TestPerRowTolerance:
    def test_skips_malformed_item_continues_with_rest(self) -> None:
        mrf = _minimal_v2_mrf()
        # Inject a malformed item between two valid items.
        mrf["standard_charge_information"] = [
            mrf["standard_charge_information"][0],
            "this string is not a dict and would crash _expand_charge_item",
            {
                "description": "X-ray",
                "code_information": [{"code": "71045", "type": "CPT"}],
                "standard_charges": [
                    {"setting": "both", "gross_charge": 90.00, "payers_information": []},
                ],
            },
        ]
        payload = json.dumps(mrf).encode()
        rows = _all_rows(_stream(payload))
        # Two valid items survive; the bad string is logged + skipped.
        codes = sorted(r.code for r in rows)
        assert codes == ["71045", "99214"]



# --- Non-seekable stream regression (2026-05-01) ---------------------------

class _NonSeekableStream(io.RawIOBase):
    """A binary stream that wraps a bytes payload but rejects seek().

    Mirrors the runtime behavior of gzip.GzipFile and other decompressing
    file objects — readable forward-only. Used to verify the parser does
    not crash when its alternate-root-key retry path tries to rewind.
    """

    def __init__(self, payload: bytes) -> None:
        self._buf = io.BytesIO(payload)

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return False

    def seek(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise io.UnsupportedOperation("seek")

    def readinto(self, b):  # type: ignore[no-untyped-def]
        chunk = self._buf.read(len(b))
        b[: len(chunk)] = chunk
        return len(chunk)

    def read(self, n: int = -1) -> bytes:
        return self._buf.read(n)


class TestNonSeekableStream:
    """Phase 4 parser bug (2026-05-01 b9lck run): when the first root-key
    probe failed on a gzip MRF, the parser called file_obj.seek(0) to
    retry the alternate key — but gzip streams aren't seekable, so the
    UnsupportedOperation crashed the whole parse for that file. Now the
    seek is best-effort; if it fails, we give up on this file cleanly
    (caller marks parse_status='failed' and moves on).
    """

    def test_alternate_key_retry_skipped_when_stream_not_seekable(self) -> None:
        # Build a minimal MRF that would only match the SECOND root-key
        # variant (`standard_charge_information_and_modifiers`), so the
        # first key probe is guaranteed to fail. Wrapped in a non-seekable
        # stream — the parser must NOT raise, just yield zero rows.
        mrf = {
            "version": "2.0.0",
            "standard_charge_information_and_modifiers": [
                {
                    "description": "Office visit",
                    "code_information": [{"code": "99214", "type": "CPT"}],
                    "standard_charges": [
                        {"setting": "outpatient", "gross_charge": 350.00, "payers_information": []},
                    ],
                },
            ],
        }
        payload = json.dumps(mrf).encode()
        stream = _NonSeekableStream(payload)
        # Zero rows is the expected outcome for a gzip MRF whose first
        # key-probe fails — we can't rewind to try the second key. The
        # critical assertion is that NO exception propagates up.
        rows = list(stream_charges_v2(
            stream, hospital_npi="1234567890", pricing_effective_year=2026,
            scraped_at="2026-05-01T00:00:00Z",
            source_mrf_url="https://example.com/test.json.gz",
            source_gcs_uri=None,
        ))
        assert rows == []  # graceful empty, not a crash

    def test_first_key_match_works_on_non_seekable(self) -> None:
        # Sanity check: when the FIRST key matches, no rewind is needed
        # and the parser produces rows correctly even from a non-seekable
        # source. Otherwise the fix would over-correct.
        mrf = {
            "version": "2.0.0",
            "standard_charge_information": [
                {
                    "description": "Office visit",
                    "code_information": [{"code": "99214", "type": "CPT"}],
                    "standard_charges": [
                        {"setting": "outpatient", "gross_charge": 350.00, "payers_information": []},
                    ],
                },
            ],
        }
        payload = json.dumps(mrf).encode()
        stream = _NonSeekableStream(payload)
        rows = list(stream_charges_v2(
            stream, hospital_npi="1234567890", pricing_effective_year=2026,
            scraped_at="2026-05-01T00:00:00Z",
            source_mrf_url="https://example.com/test.json.gz",
            source_gcs_uri=None,
        ))
        assert len(rows) == 1
        assert rows[0].code == "99214"
