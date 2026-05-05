"""Tests for the public route handlers on /api/v1/bills.

Covers:
  - POST /{bill_id}/analyze — synchronous handler that schedules the pipeline
    background task. The pipeline itself is mocked; this file asserts the
    handler's contract (status update, posthog start event, 202 response).
  - POST /{bill_id}/report — the post-payment report-generation handler.
    Asserts the 404/403 paths, idempotency probe, and the background task
    schedule.
  - _do_generate_report background task — exercises the storage-upload,
    analysis_results-update, and email-send sequence end-to-end with mocks.

Mounts the router on a bare FastAPI app so the engine API key dependency
isn't required.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.bills import _do_generate_report, router
from app.core.dependencies import (
    get_ai_analysis_service,
    get_email_service,
    get_supabase_client,
)
from app.models.bill import BillStatus, ReportRequest


# ── App + dependency override fixtures ────────────────────────────────────────


@pytest.fixture()
def supabase_mock() -> MagicMock:
    """Build a chainable Supabase mock — query results default to None/[]."""
    captured: dict[str, list[Any]] = {
        "bills_updates": [],
        "analysis_results_updates": [],
        "uploads": [],
    }

    def _build_query(table_name: str) -> MagicMock:
        response = MagicMock()
        response.data = None
        query = MagicMock()
        for chain_method in (
            "select", "eq", "in_", "lte", "gte", "is_", "or_",
            "order", "limit", "single", "neq",
        ):
            getattr(query, chain_method).return_value = query
        query.execute.return_value = response

        def _update(payload: dict[str, Any]) -> MagicMock:
            if table_name == "bills":
                captured["bills_updates"].append(payload)
            elif table_name == "analysis_results":
                captured["analysis_results_updates"].append(payload)
            return query

        query.update.side_effect = _update
        query.insert.side_effect = lambda payload: query
        query.delete.side_effect = lambda: query
        return query

    client = MagicMock()
    client.table.side_effect = _build_query
    client.storage.from_.return_value.download.return_value = b"%PDF-1.4 fake"
    client.storage.from_.return_value.list.return_value = []

    def _upload(path: str, body: bytes, options: dict[str, Any]) -> Any:
        captured["uploads"].append({"path": path, "size": len(body), "options": options})
        return MagicMock()

    client.storage.from_.return_value.upload.side_effect = _upload
    client._captured = captured  # type: ignore[attr-defined]
    return client


@pytest.fixture()
def ai_service_mock() -> MagicMock:
    """An AsyncMock-style stub for the AI analysis service."""
    service = MagicMock()

    async def _gen_letter(*_args: Any, **_kwargs: Any) -> str:
        return "Dear Hospital Billing,\n\nDispute letter contents."

    async def _gen_summary(*_args: Any, **_kwargs: Any) -> str:
        return "Found 1 finding worth $500."

    service.generate_dispute_letter = MagicMock(side_effect=_gen_letter)
    service.generate_bill_summary = MagicMock(side_effect=_gen_summary)
    return service


@pytest.fixture()
def email_service_mock() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def client(
    supabase_mock: MagicMock,
    ai_service_mock: MagicMock,
    email_service_mock: MagicMock,
) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_supabase_client] = lambda: supabase_mock
    app.dependency_overrides[get_ai_analysis_service] = lambda: ai_service_mock
    app.dependency_overrides[get_email_service] = lambda: email_service_mock
    # slowapi requires a Limiter on app.state for the @limiter.limit decorator.
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    app.state.limiter = Limiter(key_func=get_remote_address)
    return TestClient(app)


# ── analyze_bill route handler ────────────────────────────────────────────────


class TestAnalyzeBillRoute:
    """POST /api/v1/bills/{bill_id}/analyze synchronous handler."""

    @pytest.fixture(autouse=True)
    def _stub_pipeline(self, monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
        """Replace the background pipeline with an async no-op."""
        calls: list[tuple[Any, ...]] = []

        async def _noop(*args: Any, **kwargs: Any) -> None:
            calls.append(args)

        monkeypatch.setattr("app.api.v1.bills._run_analysis_pipeline", _noop)
        return calls

    def test_returns_202_with_accepted_payload(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/bills/bill-123/analyze",
            json={
                "bill_id": "bill-123",
                "file_path": "user-1/bill-123.pdf",
                "user_id": "user-1",
                "state": "OHIO",
                "zip_code": "44195",
                "plan_type": "commercial",
            },
        )
        assert response.status_code == 202
        assert response.json() == {"accepted": True}

    def test_marks_bill_ocr_processing_synchronously(
        self, client: TestClient, supabase_mock: MagicMock,
    ) -> None:
        """The frontend polls for status — the synchronous handler must flip
        the bill into OCR_PROCESSING before returning, otherwise the dashboard
        sits at UPLOADING for the duration of the background task."""
        client.post(
            "/api/v1/bills/bill-123/analyze",
            json={
                "bill_id": "bill-123",
                "file_path": "user-1/bill-123.pdf",
                "user_id": "user-1",
            },
        )
        statuses = [u.get("status") for u in supabase_mock._captured["bills_updates"]]
        assert BillStatus.OCR_PROCESSING in statuses

    def test_rejects_mismatched_bill_id_with_400(self, client: TestClient) -> None:
        """URL bill_id and body bill_id must match — otherwise the handler
        could analyze an unrelated bill on behalf of the URL's owner."""
        response = client.post(
            "/api/v1/bills/bill-123/analyze",
            json={
                "bill_id": "bill-456-different",
                "file_path": "user-1/bill-123.pdf",
                "user_id": "user-1",
            },
        )
        assert response.status_code == 400
        assert "mismatch" in response.json()["detail"]

    def test_rejects_invalid_zip_with_422(self, client: TestClient) -> None:
        """H10 regression net: 4-digit / non-numeric ZIPs must be rejected at
        the request boundary, not silently passed to ambulance lookup."""
        response = client.post(
            "/api/v1/bills/bill-123/analyze",
            json={
                "bill_id": "bill-123",
                "file_path": "user-1/bill.pdf",
                "user_id": "user-1",
                "zip_code": "1234",
            },
        )
        assert response.status_code == 422

    def test_rejects_unknown_plan_type_with_422(self, client: TestClient) -> None:
        """H10 regression net: only the closed set of PlanType values is
        accepted. 'gold-plus-elite' must 422, not silently route to medicare."""
        response = client.post(
            "/api/v1/bills/bill-123/analyze",
            json={
                "bill_id": "bill-123",
                "file_path": "user-1/bill.pdf",
                "user_id": "user-1",
                "plan_type": "gold-plus-elite",
            },
        )
        assert response.status_code == 422

    def test_posthog_start_event_fires(self, client: TestClient) -> None:
        with patch("app.api.v1.bills.posthog_client.capture") as posthog:
            client.post(
                "/api/v1/bills/bill-123/analyze",
                json={
                    "bill_id": "bill-123",
                    "file_path": "user-1/bill.pdf",
                    "user_id": "user-1",
                    "plan_type": "commercial",
                    "payer_name": "Anthem",
                },
            )
            events = [c.kwargs.get("event") for c in posthog.call_args_list]
            assert "bill analysis started" in events
            for call in posthog.call_args_list:
                if call.kwargs.get("event") == "bill analysis started":
                    props = call.kwargs.get("properties", {})
                    assert props["has_payer_info"] is True
                    assert props["plan_type"] == "commercial"
                    return
            pytest.fail("'bill analysis started' was not captured")


# ── generate_report route handler ─────────────────────────────────────────────


class TestGenerateReportRoute:
    """POST /api/v1/bills/{bill_id}/report synchronous handler."""

    @pytest.fixture(autouse=True)
    def _stub_background_task(self, monkeypatch: pytest.MonkeyPatch) -> list[Any]:
        """Replace `_do_generate_report` with an async no-op."""
        calls: list[Any] = []

        async def _noop(*args: Any, **kwargs: Any) -> None:
            calls.append(kwargs)

        monkeypatch.setattr("app.api.v1.bills._do_generate_report", _noop)
        return calls

    def _bill_row(self, **overrides: Any) -> dict[str, Any]:
        base = {
            "id": "bill-123",
            "file_name": "bill.pdf",
            "file_path": "user-1/bill-123.pdf",
            "user_id": "user-1",
            "hospital_name": "Cleveland Clinic",
            "hospital_city": "Cleveland",
            "hospital_state": "OH",
            "hospital_zip": "44195",
            "payer_name": "Anthem",
            "plan_name": "Choice POS I",
            "profile_member_id": None,
        }
        base.update(overrides)
        return base

    def _analysis_row(self, **overrides: Any) -> dict[str, Any]:
        base = {
            "id": "analysis-1",
            "errors": [],
            "ai_summary": "No findings.",
            "report_url": None,
        }
        base.update(overrides)
        return base

    def _wire_supabase(
        self,
        supabase: MagicMock,
        bill: dict[str, Any] | None,
        analysis: dict[str, Any] | None,
        files_in_storage: list[str] | None = None,
    ) -> None:
        """Configure the supabase mock so .single().execute() returns the rows."""
        rows_by_table = {
            "bills": bill,
            "analysis_results": analysis,
        }
        original_table = supabase.table.side_effect

        def _table(name: str) -> MagicMock:
            query = original_table(name)  # type: ignore[misc]
            response = query.execute.return_value
            response.data = rows_by_table.get(name)
            return query

        supabase.table.side_effect = _table
        supabase.storage.from_.return_value.list.return_value = [
            {"name": n} for n in (files_in_storage or [])
        ]

    def test_returns_404_when_bill_not_found(
        self, client: TestClient, supabase_mock: MagicMock,
    ) -> None:
        self._wire_supabase(supabase_mock, bill=None, analysis=None)
        response = client.post(
            "/api/v1/bills/bill-missing/report",
            json={"user_email": "test@example.com", "user_id": "user-1"},
        )
        assert response.status_code == 404
        assert "Bill not found" in response.json()["detail"]

    def test_returns_403_when_user_not_owner(
        self, client: TestClient, supabase_mock: MagicMock,
    ) -> None:
        """Cross-tenant guard: a user requesting another user's report must 403,
        even if they know the bill_id."""
        self._wire_supabase(
            supabase_mock,
            bill=self._bill_row(user_id="OTHER-USER"),
            analysis=self._analysis_row(),
        )
        response = client.post(
            "/api/v1/bills/bill-123/report",
            json={"user_email": "test@example.com", "user_id": "user-1"},
        )
        assert response.status_code == 403

    def test_returns_404_when_analysis_missing(
        self, client: TestClient, supabase_mock: MagicMock,
    ) -> None:
        self._wire_supabase(
            supabase_mock,
            bill=self._bill_row(),
            analysis=None,
        )
        response = client.post(
            "/api/v1/bills/bill-123/report",
            json={"user_email": "test@example.com", "user_id": "user-1"},
        )
        assert response.status_code == 404
        assert "Analysis not found" in response.json()["detail"]

    def test_idempotency_skips_when_report_already_in_storage(
        self,
        client: TestClient,
        supabase_mock: MagicMock,
    ) -> None:
        """When report_url is set AND the file actually exists in storage,
        the handler returns already_done without scheduling a background task."""
        self._wire_supabase(
            supabase_mock,
            bill=self._bill_row(),
            analysis=self._analysis_row(report_url="user-1/bill-123/report.pdf"),
            files_in_storage=["report.pdf", "dispute-letter.docx"],
        )
        response = client.post(
            "/api/v1/bills/bill-123/report",
            json={"user_email": "test@example.com", "user_id": "user-1"},
        )
        assert response.status_code == 202
        assert response.json() == {"status": "already_done"}

    def test_regenerates_when_report_url_set_but_file_missing(
        self,
        client: TestClient,
        supabase_mock: MagicMock,
    ) -> None:
        """Stale report_url from a crashed run: storage probe returns no
        files, so the handler clears the URL and schedules a regeneration."""
        self._wire_supabase(
            supabase_mock,
            bill=self._bill_row(),
            analysis=self._analysis_row(report_url="user-1/bill-123/report.pdf"),
            files_in_storage=[],  # No files actually present
        )
        response = client.post(
            "/api/v1/bills/bill-123/report",
            json={"user_email": "test@example.com", "user_id": "user-1"},
        )
        assert response.status_code == 202
        assert response.json() == {"status": "processing"}
        # The stale URL must have been cleared.
        cleared = [
            u for u in supabase_mock._captured["analysis_results_updates"]
            if u.get("report_url") is None and u.get("dispute_letter_url") is None
        ]
        assert len(cleared) == 1

    def test_happy_path_returns_processing(
        self,
        client: TestClient,
        supabase_mock: MagicMock,
    ) -> None:
        self._wire_supabase(
            supabase_mock,
            bill=self._bill_row(),
            analysis=self._analysis_row(),
        )
        response = client.post(
            "/api/v1/bills/bill-123/report",
            json={"user_email": "test@example.com", "user_id": "user-1"},
        )
        assert response.status_code == 202
        assert response.json() == {"status": "processing"}


# ── _do_generate_report background task ───────────────────────────────────────


class TestDoGenerateReportTask:
    """Background task that produces PDF + DOCX, uploads, and emails."""

    @pytest.fixture()
    def line_item_rows(self) -> list[dict[str, Any]]:
        return [{
            "cpt_code": "99214", "description": "Office Visit",
            "service_date": "2026-03-15", "quantity": 1,
            "unit_charge": 350.0, "total_charge": 350.0,
            "modifier": None, "diagnosis_pointers": [],
        }]

    def _wire(
        self, supabase: MagicMock, line_items: list[dict[str, Any]],
    ) -> None:
        original_table = supabase.table.side_effect

        def _table(name: str) -> MagicMock:
            query = original_table(name)  # type: ignore[misc]
            if name == "line_items":
                query.execute.return_value.data = line_items
            return query

        supabase.table.side_effect = _table

    def test_uploads_pdf_and_docx_to_reports_bucket(
        self,
        supabase_mock: MagicMock,
        ai_service_mock: MagicMock,
        email_service_mock: MagicMock,
        line_item_rows: list[dict[str, Any]],
    ) -> None:
        self._wire(supabase_mock, line_item_rows)
        with patch("app.api.v1.bills.ReportGenerator") as gen_cls:
            gen = gen_cls.return_value
            gen.generate_report_pdf.return_value = b"%PDF-1.4 report"
            gen.generate_dispute_letter_docx.return_value = b"PK fake-docx"

            asyncio.run(_do_generate_report(
                bill_id="bill-123",
                body=ReportRequest(user_email="test@example.com", user_id="user-1"),
                bill_data={
                    "user_id": "user-1", "file_name": "bill.pdf",
                    "hospital_name": "Cleveland Clinic", "hospital_city": "Cleveland",
                    "hospital_state": "OH", "hospital_zip": "44195",
                    "payer_name": "Anthem", "plan_name": "Choice POS I",
                    "profile_member_id": None,
                },
                analysis_data={
                    "errors": [{
                        "code": "NCCI_UNBUNDLING", "severity": "warning",
                        "affectedLineItemIds": ["line-1"],
                        "description": "Test", "estimatedOvercharge": 500.0,
                        "benchmarkRate": None,
                    }],
                    "ai_summary": "Found 1 finding.",
                },
                supabase=supabase_mock,
                ai_service=ai_service_mock,
                email_service=email_service_mock,
            ))

        uploads = supabase_mock._captured["uploads"]
        paths = sorted(u["path"] for u in uploads)
        assert paths == [
            "user-1/bill-123/dispute-letter.docx",
            "user-1/bill-123/report.pdf",
        ]
        # Content-types are correct on each upload.
        types = {u["path"]: u["options"]["content-type"] for u in uploads}
        assert types["user-1/bill-123/report.pdf"] == "application/pdf"
        assert "wordprocessingml" in types["user-1/bill-123/dispute-letter.docx"]

    def test_updates_analysis_results_with_storage_paths(
        self,
        supabase_mock: MagicMock,
        ai_service_mock: MagicMock,
        email_service_mock: MagicMock,
        line_item_rows: list[dict[str, Any]],
    ) -> None:
        self._wire(supabase_mock, line_item_rows)
        with patch("app.api.v1.bills.ReportGenerator") as gen_cls:
            gen_cls.return_value.generate_report_pdf.return_value = b"pdf"
            gen_cls.return_value.generate_dispute_letter_docx.return_value = b"docx"
            asyncio.run(_do_generate_report(
                bill_id="bill-123",
                body=ReportRequest(user_email="test@example.com", user_id="user-1"),
                bill_data={
                    "user_id": "user-1", "file_name": "bill.pdf",
                    "hospital_name": None, "hospital_city": None,
                    "hospital_state": None, "hospital_zip": None,
                    "payer_name": None, "plan_name": None,
                    "profile_member_id": None,
                },
                analysis_data={"errors": [], "ai_summary": "No findings."},
                supabase=supabase_mock,
                ai_service=ai_service_mock,
                email_service=email_service_mock,
            ))

        updates = supabase_mock._captured["analysis_results_updates"]
        assert len(updates) == 1
        assert updates[0] == {
            "report_url": "user-1/bill-123/report.pdf",
            "dispute_letter_url": "user-1/bill-123/dispute-letter.docx",
        }

    def test_email_sent_with_attachments(
        self,
        supabase_mock: MagicMock,
        ai_service_mock: MagicMock,
        email_service_mock: MagicMock,
        line_item_rows: list[dict[str, Any]],
    ) -> None:
        self._wire(supabase_mock, line_item_rows)
        with patch("app.api.v1.bills.ReportGenerator") as gen_cls:
            gen_cls.return_value.generate_report_pdf.return_value = b"pdf-bytes"
            gen_cls.return_value.generate_dispute_letter_docx.return_value = b"docx-bytes"
            asyncio.run(_do_generate_report(
                bill_id="bill-123",
                body=ReportRequest(user_email="patient@example.com", user_id="user-1"),
                bill_data={
                    "user_id": "user-1", "file_name": "bill.pdf",
                    "hospital_name": None, "hospital_city": None,
                    "hospital_state": None, "hospital_zip": None,
                    "payer_name": None, "plan_name": None,
                    "profile_member_id": None,
                },
                analysis_data={"errors": [], "ai_summary": "No findings."},
                supabase=supabase_mock,
                ai_service=ai_service_mock,
                email_service=email_service_mock,
            ))

        email_service_mock.send_report_email.assert_called_once()
        kwargs = email_service_mock.send_report_email.call_args.kwargs
        assert kwargs["to_email"] == "patient@example.com"
        assert kwargs["bill_file_name"] == "bill.pdf"
        assert kwargs["report_pdf"] == b"pdf-bytes"
        assert kwargs["dispute_letter_docx"] == b"docx-bytes"

    def test_failure_in_generation_does_not_raise_to_caller(
        self,
        supabase_mock: MagicMock,
        ai_service_mock: MagicMock,
        email_service_mock: MagicMock,
        line_item_rows: list[dict[str, Any]],
    ) -> None:
        """Background task must swallow + log + telemeter exceptions —
        FastAPI's BackgroundTasks runner has no error reporting hook, so a
        bubble-up here disappears silently and the patient never knows their
        report failed. The route handler isn't waiting either."""
        self._wire(supabase_mock, line_item_rows)
        with patch("app.api.v1.bills.ReportGenerator") as gen_cls, \
                patch("app.api.v1.bills.posthog_client.capture") as posthog:
            gen_cls.return_value.generate_report_pdf.side_effect = RuntimeError(
                "fpdf2 dependency missing in this env"
            )
            # Must not raise.
            asyncio.run(_do_generate_report(
                bill_id="bill-123",
                body=ReportRequest(user_email="patient@example.com", user_id="user-1"),
                bill_data={
                    "user_id": "user-1", "file_name": "bill.pdf",
                    "hospital_name": None, "hospital_city": None,
                    "hospital_state": None, "hospital_zip": None,
                    "payer_name": None, "plan_name": None,
                    "profile_member_id": None,
                },
                analysis_data={"errors": [], "ai_summary": "No findings."},
                supabase=supabase_mock,
                ai_service=ai_service_mock,
                email_service=email_service_mock,
            ))
            # Failure event must be telemetered.
            events = [c.kwargs.get("event") for c in posthog.call_args_list]
            assert "report generation failed" in events
