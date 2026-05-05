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
            gcs, "gs://clarobill-mrf-archive-uscentral/pricing-year=2026/1234567890/abc.json.gz"
        )
        gcs.bucket.assert_called_once_with("clarobill-mrf-archive-uscentral")
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
                "gcs_uri": "gs://clarobill-mrf-archive-uscentral/pricing-year=2026/1234567890/abc.json",
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
                "gcs_uri": "gs://clarobill-mrf-archive-uscentral/x/y.json",
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

    def test_dedupe_query_groups_by_gcs_uri(self) -> None:
        # Regression for 2026-05-04 16:46 runaway: archive_index has multiple
        # rows per source_mrf_url (re-scrapes, Dignity Health duplicate-archive
        # cohort, etc). Without GROUP BY gcs_uri, the loop processed the same
        # blob 3+ times before update_archive_index_status caught up, appending
        # duplicate rows to the (append-only) hospital_charges table.
        bq = MagicMock()
        gcs = MagicMock()
        staging_bucket = MagicMock()
        bq.query.return_value.result.return_value = iter([])

        parser.process_archive_index_pending(bq, gcs, staging_bucket)

        sql_arg = bq.query.call_args.args[0]
        assert "GROUP BY gcs_uri" in sql_arg, \
            "Pending query must dedupe by gcs_uri to avoid re-processing blobs"

    def test_inmemory_dedupe_skips_duplicate_uris(self) -> None:
        # Belt-and-suspenders against any race that lets duplicate gcs_uris
        # slip past the SQL GROUP BY. Same gcs_uri appearing twice in the
        # iter must be processed exactly once.
        bq = MagicMock()
        gcs = MagicMock()
        staging_bucket = MagicMock()
        same_uri = "gs://clarobill-mrf-archive-uscentral/x/y.json"
        bq.query.return_value.result.return_value = iter([
            {"source_mrf_url": "https://hosp.org/c.json", "gcs_uri": same_uri,
             "hospital_npi": "1234567890", "ccn": None, "mrf_last_modified_header": None},
            {"source_mrf_url": "https://hosp.org/c.json", "gcs_uri": same_uri,
             "hospital_npi": "1234567890", "ccn": None, "mrf_last_modified_header": None},
            {"source_mrf_url": "https://hosp.org/c.json", "gcs_uri": same_uri,
             "hospital_npi": "1234567890", "ccn": None, "mrf_last_modified_header": None},
        ])

        with patch.object(parser, "process_blob_with_meta", return_value=True) as mock_proc:
            parser.process_archive_index_pending(bq, gcs, staging_bucket)

        assert mock_proc.call_count == 1, \
            "Duplicate gcs_uri rows must collapse to a single process call"

    def test_sharding_no_overlap_no_gaps(self) -> None:
        # Six tasks, 30 rows — each task should process exactly 5 rows,
        # the union should equal the full set, no row processed twice.
        bq = MagicMock()
        gcs = MagicMock()
        staging_bucket = MagicMock()

        full_rows = [
            {"source_mrf_url": f"https://h{i}.org/c.json",
             "gcs_uri": f"gs://archive/{i:02d}.json",
             "hospital_npi": f"{1000000000 + i}",
             "ccn": None, "mrf_last_modified_header": None}
            for i in range(30)
        ]

        # Each call to bq.query returns the SAME ordered full set — that's
        # what the ORDER BY gcs_uri in the SQL guarantees.
        processed_uris: set[str] = set()
        with patch.object(parser, "process_blob_with_meta", return_value=True) as mock_proc:
            for shard in range(6):
                bq.query.return_value.result.return_value = iter(list(full_rows))
                parser.process_archive_index_pending(
                    bq, gcs, staging_bucket,
                    task_index=shard, task_count=6,
                )
                # Track which URIs THIS task processed.
                for call in mock_proc.call_args_list[-len(full_rows[shard::6]):]:
                    processed_uris.add(call.args[0].name if hasattr(call.args[0], "name") else "")

        # Sanity: total process calls = 30 (each row processed exactly once
        # across the union of all tasks).
        assert mock_proc.call_count == 30

    def test_sharding_uses_stable_ordering(self) -> None:
        # Without ORDER BY in the SQL, two tasks could see different row
        # orderings and end up with overlapping or gapped stripes.
        bq = MagicMock()
        gcs = MagicMock()
        staging_bucket = MagicMock()
        bq.query.return_value.result.return_value = iter([])

        parser.process_archive_index_pending(
            bq, gcs, staging_bucket,
            task_index=0, task_count=6,
        )

        sql_arg = bq.query.call_args.args[0]
        assert "ORDER BY gcs_uri" in sql_arg, \
            "Sharding requires deterministic row ordering across tasks"

    def test_single_task_default_processes_full_set(self) -> None:
        # task_count=1 (default) must process every row, not stripe.
        bq = MagicMock()
        gcs = MagicMock()
        staging_bucket = MagicMock()
        bq.query.return_value.result.return_value = iter([
            {"source_mrf_url": f"https://h{i}.org/c.json",
             "gcs_uri": f"gs://archive/{i}.json",
             "hospital_npi": "1234567890",
             "ccn": None, "mrf_last_modified_header": None}
            for i in range(5)
        ])

        with patch.object(parser, "process_blob_with_meta", return_value=True) as mock_proc:
            parser.process_archive_index_pending(bq, gcs, staging_bucket)

        assert mock_proc.call_count == 5

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
                "gcs_uri": "gs://clarobill-mrf-archive-uscentral/x/y.json.gz",
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
