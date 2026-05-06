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

from hospital_mrf_utils import (
    ACCEPTED_MRF_FORMATS,
    ChargeRow,
    _strip_bom,
    extract_npi_from_url,
    sniff_mrf_format,
    stream_charges_v2,
)


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
        source_gcs_uri="gs://clarobill-mrf-archive-uscentral/pricing-year=2026/1234567890/abc.json",
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


class TestExtractNpiFromUrl:
    """Phase 4 follow-up (2026-05-04): the parser previously fell back to an
    empty NPI when MRF JSON internals didn't carry one, silently writing
    rows with no joinable hospital identifier. ~60% of hospital_charges and
    2,111 of the 'parsed' archive blobs ended up with NULL NPI as a result.
    Real-world URLs almost always embed the NPI in the filename, so URL
    extraction is the cheapest and highest-coverage fix.

    Each test URL here is a real example pulled from
    `mrf_archive_index` rows whose `hospital_npi` was NULL.
    """

    def test_dignity_health_real_url_returns_none(self) -> None:
        # Real Dignity Health URL: filename starts with `941196203_` —
        # nine digits, which is the parent system's EIN/CMS Provider ID,
        # NOT an NPI. We deliberately do not promote 9-digit IDs to NPI.
        # This is the exact pattern that produced 2,111 NULL-NPI archive
        # rows on 2026-05-01/02. Surfaces as a separate "EIN-only" cohort
        # for backfill via hospital_directory.ccn → npi mapping.
        url = (
            "https://www.dignityhealth.org/content/dam/dignity-health/documents/"
            "mrf-json/southern-california/json/941196203_marian-regional-medical-center_standardcharges.json"
        )
        assert extract_npi_from_url(url) is None

    def test_filename_prefix_10_digit_npi(self) -> None:
        url = (
            "https://www.dignityhealth.org/content/dam/dignity-health/documents/"
            "mrf-json/socal/json/9411962030_marian-regional-medical-center_standardcharges.json"
        )
        assert extract_npi_from_url(url) == "9411962030"

    def test_aultman_real_pattern(self) -> None:
        url = "https://aultman.org/pricing-transparency/2026/1356366991_aultman-hospital_standardcharges.json"
        assert extract_npi_from_url(url) == "1356366991"

    def test_kettering_multi_id_prefers_10_digit(self) -> None:
        # Real URL: 9-digit health-system EIN (310536662) followed by 10-digit facility NPI (1104867167).
        # Filename basename has the EIN first; the 10-digit NPI must still be selected.
        url = "https://cdn.ketteringhealth.org/wp-content/uploads/2026/03/310536662_1104867167_fort-hamilton-hospital_standardcharges.json"
        assert extract_npi_from_url(url) == "1104867167"

    def test_uppercase_json_extension(self) -> None:
        url = "https://montclair-hospital.org/wp-content/uploads/2026/04/2028987710_MontclairHospitalMedicalCenter_standardcharges.JSON"
        assert extract_npi_from_url(url) == "2028987710"

    def test_no_separator_concatenated_filename(self) -> None:
        url = "http://www.bayhealth.org/-/media/files/patients-and-visitors/billing-financial-aid/price-transparency/2026/5100643180bayhealthhospitalsussexcampusstandardcharges.json"
        assert extract_npi_from_url(url) == "5100643180"

    def test_query_string_is_ignored(self) -> None:
        # Real URL with SAS token whose digit runs must NOT be mistaken for an NPI.
        url = (
            "https://pricetransparency.blob.core.windows.net/newmanregionalhospital/"
            "4860268351_Newman-Regional-Health_standardcharges.json"
            "?sv=2022-11-02&se=2099-04-26T22:40:35Z&sig=V53UDZpYxrVMzk1BKj4Dvm45q%2FAztzKKQCADbpBONqo%3D"
        )
        assert extract_npi_from_url(url) == "4860268351"

    def test_url_encoded_path_segments(self) -> None:
        url = (
            "https://ernesthealth.com/wp-content/uploads/2025/01/pricing/"
            "Bloomington%20Regional%20Rehabilitation%20Hospital/"
            "8537968410_Bloomington-Regional-Rehabilitation-Hospital_Standard-Charges.json"
        )
        assert extract_npi_from_url(url) == "8537968410"

    def test_path_based_layout_no_filename_npi(self) -> None:
        # Hypothetical: directory carries the NPI, basename does not.
        url = "https://example.org/mrf/1234567890/charges.json"
        assert extract_npi_from_url(url) == "1234567890"

    def test_ein_only_returns_none(self) -> None:
        # Real URL: Beartooth Billings Clinic has EIN 81-0224734 in filename
        # (renders as 9 contiguous digits without the dash). 9 digits ≠ NPI.
        # Returning None forces the parser to mark this 'failed' rather than
        # writing rows with corrupt EIN-as-NPI data.
        url = (
            "https://pricetransparency.blob.core.windows.net/beartooth/"
            "81-0224734_Beartooth-Billings-Clinic_standardcharges.json"
        )
        assert extract_npi_from_url(url) is None

    def test_ein_with_dash_collapsed_returns_none(self) -> None:
        # 9 contiguous digits collapsed from XX-XXXXXXX format must NOT match.
        url = "https://example.org/files/810224734_Some-Clinic_standardcharges.json"
        assert extract_npi_from_url(url) is None

    def test_no_digit_run_returns_none(self) -> None:
        url = "https://example.org/mrf/SomeHospital_charges.json"
        assert extract_npi_from_url(url) is None

    def test_empty_url_returns_none(self) -> None:
        assert extract_npi_from_url("") is None

    def test_eleven_digit_run_does_not_match(self) -> None:
        # Bare 11-digit number is not an NPI; we must not pick the trailing 10.
        url = "https://example.org/mrf/12345678901_Hospital_standardcharges.json"
        assert extract_npi_from_url(url) is None


class TestSniffMrfFormat:
    """Scrape-time content validation — postmortem #1 root fix.

    The 5/3 postmortem traced 16K+ garbage blobs in mrf-archive to the
    scraper writing whatever HTTP response body it got, regardless of
    Content-Type. This sniff is the gate that rejects HTML landing pages,
    PDFs, wrong-domain redirects (one ended at facebook.com) and similar
    garbage *before* it lands in staging or the immutable archive.

    Each test case is anchored to a real-world artifact we observed in
    the existing archive.
    """

    # --- Magic-byte detection ---

    def test_zip_archive(self) -> None:
        # Real example: massgeneralbrigham.org/.../222617175_Cooley-Dickinson_StandardCharges.zip
        assert sniff_mrf_format(b"PK\x03\x04..." + b"\x00" * 100) == "zip"

    def test_xlsx_via_url_extension(self) -> None:
        # XLSX is also a PK ZIP container — disambiguate by URL extension.
        assert sniff_mrf_format(b"PK\x03\x04..." + b"\x00" * 100,
                                url="https://hosp.org/charges.xlsx") == "xlsx"

    def test_pdf_rejected(self) -> None:
        assert sniff_mrf_format(b"%PDF-1.7\n...") == "pdf"

    def test_gzip_of_json(self) -> None:
        import gzip as _gz
        payload = _gz.compress(b'{"hospital_npi":"1234567890"}')
        assert sniff_mrf_format(payload) == "json"

    def test_gzip_of_html_classified_as_html(self) -> None:
        # Pre-fix scraper saved gzipped HTML 404 pages as `.json.gz`.
        # The sniffer must recognise the inner content is HTML, not JSON.
        import gzip as _gz
        payload = _gz.compress(b"<!doctype html><html><body>404</body></html>")
        assert sniff_mrf_format(payload) == "html"

    # --- Plain JSON / XML / HTML ---

    def test_json_object(self) -> None:
        assert sniff_mrf_format(b'{"hospital_name":"X"}') == "json"

    def test_json_array(self) -> None:
        assert sniff_mrf_format(b"[1,2,3]") == "json"

    def test_json_with_bom(self) -> None:
        assert sniff_mrf_format(b"\xef\xbb\xbf{\"a\":1}") == "json"

    def test_xml(self) -> None:
        assert sniff_mrf_format(b'<?xml version="1.0"?><root/>') == "xml"

    def test_html_landing_page(self) -> None:
        # Real example: dignityhealth.org/.../insurance-information page
        # was scraped + stored as JSON. 4 KB of HTML markup.
        assert sniff_mrf_format(b"<!DOCTYPE html><html><head><title>")  == "html"

    # --- Edge cases ---

    def test_empty_response(self) -> None:
        assert sniff_mrf_format(b"") == "empty"

    def test_csv_via_url_extension(self) -> None:
        # CSV has no magic bytes; URL extension is the only reliable signal.
        assert sniff_mrf_format(b"code,description,charge\n99214,Office,350.00\n",
                                url="https://hosp.org/charges.csv") == "csv"

    def test_csv_via_content_type(self) -> None:
        assert sniff_mrf_format(b"code,description,charge\n",
                                content_type="text/csv") == "csv"

    def test_unknown_falls_through(self) -> None:
        assert sniff_mrf_format(b"\x00\x00\x00\x00random binary") == "unknown"

    # --- Acceptance set ---

    def test_accepted_formats_set(self) -> None:
        assert ACCEPTED_MRF_FORMATS == {"json", "csv", "zip", "xlsx", "xml", "tsv"}

    def test_pdf_not_in_accepted(self) -> None:
        # Every real archive PDF observed was a landing page or notice,
        # never a chargemaster. Explicit rejection.
        assert "pdf" not in ACCEPTED_MRF_FORMATS

    def test_html_not_in_accepted(self) -> None:
        assert "html" not in ACCEPTED_MRF_FORMATS


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
