"""Regression tests for the archive_index-driven parser path (postmortem #2).

The bucket-walk mode can't reach blobs whose staging copy was deleted
post-parse — which describes the entire pre-2026-05-04 NULL-NPI cohort
(2,583 rows). The archive_index driver reads work from BigQuery and
opens each blob's gcs_uri directly from the immutable archive bucket,
which makes those rows retryable.

These tests focus on the small-but-load-bearing pieces:
  - `_blob_from_gcs_uri` — gs:// URI parsing
  - `reset_failed_to_pending` — SQL contract (rows reset, parse_error
    annotated)
  - `process_archive_index_pending` — does NOT delete archive blobs on
    success (immutable archive invariant)
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import parse_hospital_mrfs as parser
from parse_hospital_mrfs import _blob_from_gcs_uri


class TestBlobFromGcsUri:
    def test_parses_archive_uri(self) -> None:
        gcs = MagicMock()
        bucket = MagicMock()
        blob = MagicMock()
        gcs.bucket.return_value = bucket
        bucket.blob.return_value = blob
        result = _blob_from_gcs_uri(
            gcs, "gs://mrf-archive-clarobill-prd/pricing-year=2026/1234567890/abc.json.gz"
        )
        gcs.bucket.assert_called_once_with("mrf-archive-clarobill-prd")
        bucket.blob.assert_called_once_with("pricing-year=2026/1234567890/abc.json.gz")
        assert result is blob

    def test_parses_staging_uri(self) -> None:
        gcs = MagicMock()
        _blob_from_gcs_uri(gcs, "gs://mrf-staging/raw/some-hospital/2026-05-04T00:00:00Z.json.gz")
        gcs.bucket.assert_called_once_with("mrf-staging")

    def test_rejects_uri_without_prefix(self) -> None:
        with pytest.raises(ValueError, match="gs://"):
            _blob_from_gcs_uri(MagicMock(), "https://example.com/file.json")

    def test_rejects_malformed_uri(self) -> None:
        with pytest.raises(ValueError, match="Malformed"):
            _blob_from_gcs_uri(MagicMock(), "gs://bucket-only-no-path")


class TestResetFailedToPending:
    def test_pattern_scoped_reset_uses_parameterized_sql(self) -> None:
        bq = MagicMock()
        job = MagicMock()
        job.num_dml_affected_rows = 42
        bq.query.return_value = job

        n = parser.reset_failed_to_pending(bq, error_pattern="parsed with NULL NPI%")

        assert n == 42
        bq.query.assert_called_once()
        sql_arg = bq.query.call_args.args[0]
        assert "parse_status = 'failed'" in sql_arg
        assert "parse_error LIKE @pattern" in sql_arg
        # Verify parameter is bound — protects against SQL injection if pattern
        # ever comes from untrusted input.
        job_config = bq.query.call_args.kwargs["job_config"]
        params = list(job_config.query_parameters)
        assert len(params) == 1
        assert params[0].name == "pattern"
        assert params[0].value == "parsed with NULL NPI%"

    def test_no_pattern_resets_all_failed(self) -> None:
        bq = MagicMock()
        job = MagicMock()
        job.num_dml_affected_rows = 100
        bq.query.return_value = job

        n = parser.reset_failed_to_pending(bq, error_pattern=None)

        assert n == 100
        sql_arg = bq.query.call_args.args[0]
        assert "parse_status = 'failed'" in sql_arg
        assert "parse_error LIKE" not in sql_arg

    def test_zero_affected_rows_returns_zero_not_none(self) -> None:
        bq = MagicMock()
        job = MagicMock()
        job.num_dml_affected_rows = None  # BQ sometimes returns None
        bq.query.return_value = job
        assert parser.reset_failed_to_pending(bq, error_pattern="x%") == 0


class TestArchiveIndexDriver:
    """Verify the archive-index driver respects the immutable-archive invariant."""

    def test_archive_blob_never_deleted_on_success(self) -> None:
        # The single most important property — if this regresses, we
        # erase forensic evidence on the next parse run.
        bq = MagicMock()
        gcs = MagicMock()
        staging_bucket = MagicMock()

        # One pending row pointing at the archive bucket.
        bq.query.return_value.result.return_value = iter([
            {
                "source_mrf_url": "https://hosp.org/charges.json",
                "gcs_uri": "gs://mrf-archive-clarobill-prd/pricing-year=2026/1234567890/abc.json",
                "hospital_npi": "1234567890",
                "ccn": None,
                "mrf_last_modified_header": None,
            },
        ])

        # Stub process_blob_with_meta to return success without doing real work.
        # We just need to verify it was called with delete_source_on_success=False.
        with patch.object(parser, "process_blob_with_meta", return_value=True) as mock_proc:
            succeeded, failed = parser.process_archive_index_pending(bq, gcs, staging_bucket)

        assert succeeded == 1
        assert failed == 0
        kwargs = mock_proc.call_args.kwargs
        assert kwargs["delete_source_on_success"] is False, \
            "Archive bucket blobs MUST NOT be deleted by the parser"

    def test_failure_marks_archive_index(self) -> None:
        # When process_blob_with_meta raises (not returns False), the
        # driver must still record the failure in archive_index so the
        # row doesn't get stuck pending forever.
        bq = MagicMock()
        gcs = MagicMock()
        staging_bucket = MagicMock()

        bq.query.return_value.result.return_value = iter([
            {
                "source_mrf_url": "https://hosp.org/charges.json",
                "gcs_uri": "gs://mrf-archive-clarobill-prd/x/y.json",
                "hospital_npi": "",
                "ccn": None,
                "mrf_last_modified_header": None,
            },
        ])

        with patch.object(parser, "process_blob_with_meta",
                          side_effect=RuntimeError("boom")), \
             patch.object(parser, "update_archive_index_status") as mock_update:
            succeeded, failed = parser.process_archive_index_pending(bq, gcs, staging_bucket)

        assert succeeded == 0
        assert failed == 1
        mock_update.assert_called_once()
        url_arg = mock_update.call_args.args[1]
        status_arg = mock_update.call_args.args[2]
        assert url_arg == "https://hosp.org/charges.json"
        assert status_arg == "failed"

    def test_meta_built_from_archive_index_columns(self) -> None:
        # Archive-bucket blobs do NOT carry the scraper's custom metadata
        # (hospital_name, mrf_url, etc). The driver must build that meta
        # dict from archive_index columns instead.
        bq = MagicMock()
        gcs = MagicMock()
        staging_bucket = MagicMock()

        bq.query.return_value.result.return_value = iter([
            {
                "source_mrf_url": "https://providence.org/charges.json",
                "gcs_uri": "gs://mrf-archive-clarobill-prd/x/y.json.gz",
                "hospital_npi": "1508937947",
                "ccn": None,
                "mrf_last_modified_header": "Mon, 01 Jan 2026 00:00:00 GMT",
            },
        ])

        with patch.object(parser, "process_blob_with_meta", return_value=True) as mock_proc:
            parser.process_archive_index_pending(bq, gcs, staging_bucket)

        meta_arg = mock_proc.call_args.args[1]
        assert meta_arg["mrf_url"] == "https://providence.org/charges.json"
        assert meta_arg["hospital_npi"] == "1508937947"
        assert meta_arg["last_modified"] == "Mon, 01 Jan 2026 00:00:00 GMT"
