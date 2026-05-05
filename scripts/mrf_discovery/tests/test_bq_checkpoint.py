"""Unit tests for bq_checkpoint helpers — focusing on run_dml_with_count (M13).

The full bq_checkpoint module integrates with BigQuery so most of its
functions are exercised by the live discovery run. This test covers the
M13 helper specifically because its assertion (raise on
num_dml_affected_rows is None) is the kind of code that's easy to
silently break in a refactor.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from mrf_discovery import bq_checkpoint as bq


def _mock_query_job(num_dml_affected_rows):
    """Build a stand-in for QueryJob with the given affected-row count."""
    job = MagicMock()
    job.num_dml_affected_rows = num_dml_affected_rows
    job.result.return_value = None
    return job


def _mock_client(job):
    client = MagicMock()
    client.query.return_value = job
    return client


class TestRunDmlWithCount:
    """M13: bq_checkpoint.run_dml_with_count enforces the affected-row count
    is captured. Lets us catch a silent zero-row MERGE caused by IAM
    regression / dataset typo / schema drift, and lets us catch a
    misclassified statement (CREATE TABLE accidentally routed through the
    DML helper, which would return None)."""

    def test_returns_affected_count(self):
        client = _mock_client(_mock_query_job(42))
        n = bq.run_dml_with_count(client, "MERGE ...", label="test")
        assert n == 42

    def test_logs_affected_count(self, caplog):
        client = _mock_client(_mock_query_job(7))
        with caplog.at_level(logging.INFO):
            bq.run_dml_with_count(
                client, "MERGE ...", label="my-merge",
                logger=logging.getLogger(__name__),
            )
        # The label and the count must both appear in the log line.
        assert any("my-merge" in r.message and "7" in r.message for r in caplog.records)

    def test_zero_rows_does_not_raise(self):
        """A 0-rows-affected MERGE is legal (e.g. nothing matched the
        condition). The helper returns 0 - caller decides whether to alert."""
        client = _mock_client(_mock_query_job(0))
        assert bq.run_dml_with_count(client, "MERGE ...") == 0

    def test_none_count_raises(self):
        """num_dml_affected_rows is None for non-DML statements
        (CREATE / DROP / SELECT). The helper is for DML only - using it
        on a non-DML statement is a regression we want to catch loudly."""
        client = _mock_client(_mock_query_job(None))
        with pytest.raises(RuntimeError, match="not be DML"):
            bq.run_dml_with_count(client, "CREATE TABLE foo ...")

    def test_passes_through_job_config_when_provided(self):
        client = _mock_client(_mock_query_job(1))
        cfg_sentinel = object()
        bq.run_dml_with_count(client, "MERGE ...", job_config=cfg_sentinel)  # type: ignore[arg-type]
        client.query.assert_called_once_with("MERGE ...", job_config=cfg_sentinel)

    def test_no_job_config_omits_kwarg(self):
        client = _mock_client(_mock_query_job(1))
        bq.run_dml_with_count(client, "MERGE ...")
        client.query.assert_called_once_with("MERGE ...")
