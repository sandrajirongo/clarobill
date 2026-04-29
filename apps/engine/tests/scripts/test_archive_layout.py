"""Unit tests for scripts/mrf_discovery/archive_layout.

Pure functions, no I/O — every test runs in microseconds and never touches GCS.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from mrf_discovery.archive_layout import (  # noqa: E402
    ARCHIVE_BUCKET,
    ArchiveMeta,
    VALID_EXTENSIONS,
    build_meta_object_name,
    build_meta_uri,
    build_object_name,
    build_object_uri,
    parse_object_uri,
    utcnow_iso,
)


SHA = "a1b2c3d4e5f60718a1b2c3d4e5f60718a1b2c3d4e5f60718a1b2c3d4e5f60718"


class TestBuildObjectName:
    def test_npi_key(self):
        assert (
            build_object_name(2026, "1234567890", SHA, "csv")
            == "pricing-year=2026/1234567890/a1b2c3d4e5f60718.csv"
        )

    def test_uuid_key(self):
        uuid = "078d926d-76d0-4a59-8cda-0534d3b325d2"
        name = build_object_name(2026, uuid, SHA, "json.gz")
        assert name == f"pricing-year=2026/{uuid}/a1b2c3d4e5f60718.json.gz"

    def test_extension_normalised(self):
        assert build_object_name(2026, "1234567890", SHA, ".CSV").endswith(".csv")

    @pytest.mark.parametrize("ext", sorted(VALID_EXTENSIONS))
    def test_every_valid_extension_round_trips(self, ext):
        name = build_object_name(2026, "1234567890", SHA, ext)
        assert name.endswith(f".{ext}")

    def test_rejects_unknown_extension(self):
        with pytest.raises(ValueError, match="Unsupported MRF extension"):
            build_object_name(2026, "1234567890", SHA, "pdf")

    def test_rejects_year_below_range(self):
        with pytest.raises(ValueError, match="2024..2034"):
            build_object_name(2023, "1234567890", SHA, "csv")

    def test_rejects_year_above_range(self):
        with pytest.raises(ValueError, match="2024..2034"):
            build_object_name(2035, "1234567890", SHA, "csv")

    def test_rejects_short_sha(self):
        with pytest.raises(ValueError, match="hex sha256"):
            build_object_name(2026, "1234567890", "abc", "csv")

    def test_rejects_path_traversal_key(self):
        with pytest.raises(ValueError, match="alphanumeric"):
            build_object_name(2026, "../etc/passwd", SHA, "csv")

    def test_rejects_empty_key(self):
        with pytest.raises(ValueError):
            build_object_name(2026, "", SHA, "csv")


class TestBuildUri:
    def test_default_bucket(self):
        uri = build_object_uri(2026, "1234567890", SHA, "csv")
        assert uri == f"gs://{ARCHIVE_BUCKET}/pricing-year=2026/1234567890/a1b2c3d4e5f60718.csv"

    def test_custom_bucket(self):
        uri = build_object_uri(2026, "1234567890", SHA, "csv", bucket="my-test-bucket")
        assert uri.startswith("gs://my-test-bucket/")

    def test_meta_uri_sibling(self):
        data_uri = build_object_uri(2026, "1234567890", SHA, "csv")
        meta_uri = build_meta_uri(2026, "1234567890", SHA)
        # Same prefix, different suffix
        assert data_uri.rsplit(".", 1)[0] == meta_uri.removesuffix(".meta.json")


class TestParseObjectUri:
    def test_round_trip_data_object(self):
        uri = build_object_uri(2026, "1234567890", SHA, "csv")
        parsed = parse_object_uri(uri)
        assert parsed == {
            "bucket": ARCHIVE_BUCKET,
            "pricing_effective_year": 2026,
            "key": "1234567890",
            "sha256_prefix": "a1b2c3d4e5f60718",
            "extension": "csv",
            "is_meta": False,
        }

    def test_round_trip_meta_object(self):
        uri = build_meta_uri(2026, "1234567890", SHA)
        parsed = parse_object_uri(uri)
        assert parsed["is_meta"] is True
        assert parsed["extension"] is None
        assert parsed["pricing_effective_year"] == 2026

    def test_round_trip_uuid_key(self):
        uuid = "078d926d-76d0-4a59-8cda-0534d3b325d2"
        uri = build_object_uri(2026, uuid, SHA, "json.gz")
        parsed = parse_object_uri(uri)
        assert parsed["key"] == uuid
        assert parsed["extension"] == "json.gz"

    def test_rejects_non_gcs_uri(self):
        with pytest.raises(ValueError, match="Not a gs"):
            parse_object_uri("https://example.com/foo")

    def test_rejects_unknown_layout(self):
        with pytest.raises(ValueError, match="does not match archive layout"):
            parse_object_uri("gs://mrf-archive-clarobill-prd/some/random/path.csv")


class TestArchiveMeta:
    def test_round_trip(self):
        meta = ArchiveMeta(
            source_url="https://example.com/foo_standardcharges.csv",
            pricing_effective_year=2026,
            hospital_npi="1234567890",
            pra_facility_uuid="078d926d-76d0-4a59-8cda-0534d3b325d2",
            ccn="010001",
            sha256=SHA,
            file_size_bytes=70123,
            content_type="text/csv",
            mrf_last_modified_header="Wed, 15 Apr 2026 16:11:38 GMT",
            mrf_etag_header='"5373a3fb1fa76b28dc984c47621c4465"',
            scraped_at="2026-04-27T13:00:00Z",
        )
        json_text = meta.to_json()
        recovered = ArchiveMeta.from_json(json_text)
        assert recovered == meta

    def test_optional_fields_can_be_none(self):
        meta = ArchiveMeta(
            source_url="https://example.com/foo.csv",
            pricing_effective_year=2026,
            hospital_npi=None,
            pra_facility_uuid="abc",
            ccn=None,
            sha256=SHA,
            file_size_bytes=100,
            content_type=None,
            mrf_last_modified_header=None,
            mrf_etag_header=None,
            scraped_at="2026-04-27T13:00:00Z",
        )
        assert ArchiveMeta.from_json(meta.to_json()) == meta


def test_utcnow_iso_format():
    ts = utcnow_iso()
    # Format: 2026-04-27T13:00:00Z
    assert len(ts) == 20
    assert ts.endswith("Z")
    assert ts[4] == "-" and ts[7] == "-" and ts[10] == "T"
