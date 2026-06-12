"""Unit tests for timeline query logic and stage ordering (#673)."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest

from services.api.routers.admin.timeline import _build_timeline_stages


def _make_job(
    stage: str,
    status: str,
    created_offset_min: int = -5,
    updated_offset_min: int | None = None,
    last_error: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    created = now + timedelta(minutes=created_offset_min)
    updated = (
        now + timedelta(minutes=updated_offset_min) if updated_offset_min is not None else created
    )
    return {
        "id": str(uuid4()),
        "job_type": "process_document",
        "status": status,
        "stage": stage,
        "last_error": last_error,
        "created_at": created,
        "updated_at": updated,
    }


class TestBuildTimelineStages:
    def test_empty_jobs_returns_empty_stages(self) -> None:
        assert _build_timeline_stages([]) == []

    def test_single_succeeded_stage(self) -> None:
        job = _make_job("parsed", "succeeded", -5, -4)
        stages = _build_timeline_stages([job])
        assert len(stages) == 1
        assert stages[0]["stage"] == "parsed"
        assert stages[0]["status"] == "completed"
        assert stages[0]["duration_ms"] is not None
        assert stages[0]["duration_ms"] > 0

    def test_failed_stage(self) -> None:
        job = _make_job("embedded", "dead_letter", -3, -2, last_error="UnexpectedResponse:process")
        stages = _build_timeline_stages([job])
        assert len(stages) == 1
        assert stages[0]["stage"] == "embedded"
        assert stages[0]["status"] == "failed"
        assert stages[0]["error"] == "UnexpectedResponse:process"

    def test_pending_stage(self) -> None:
        job = _make_job("translate", "pending", -1)
        stages = _build_timeline_stages([job])
        assert len(stages) == 1
        assert stages[0]["status"] == "pending"
        assert stages[0]["duration_ms"] is None

    def test_running_stage(self) -> None:
        job = _make_job("indexed", "running", -1)
        stages = _build_timeline_stages([job])
        assert len(stages) == 1
        assert stages[0]["status"] == "running"

    def test_stage_ordering_by_created_at(self) -> None:
        jobs = [
            _make_job("embedded", "dead_letter", -2, -1, last_error="boom"),
            _make_job("parsed", "succeeded", -10, -9),
            _make_job("translated", "succeeded", -8, -5),
        ]
        stages = _build_timeline_stages(jobs)
        assert len(stages) == 3
        assert [s["stage"] for s in stages] == ["parsed", "translated", "embedded"]

    def test_duration_milliseconds_calculation(self) -> None:
        # 60 seconds = 60,000 ms
        now = datetime.now(UTC)
        job = {
            "id": str(uuid4()),
            "job_type": "process_document",
            "status": "succeeded",
            "stage": "parsed",
            "last_error": None,
            "created_at": now - timedelta(seconds=60),
            "updated_at": now,
        }
        stages = _build_timeline_stages([job])
        assert stages[0]["duration_ms"] == pytest.approx(60_000, abs=2000)

    def test_mixed_status_stages(self) -> None:
        jobs = [
            _make_job("parsed", "succeeded", -10, -9),
            _make_job("translated", "succeeded", -8, -5),
            _make_job("embedded", "dead_letter", -3, -2, last_error="UnexpectedResponse:process"),
            _make_job("indexed", "pending", -1),
        ]
        stages = _build_timeline_stages(jobs)
        statuses = [s["status"] for s in stages]
        assert statuses == ["completed", "completed", "failed", "pending"]

    def test_job_without_stage_uses_job_type(self) -> None:
        now = datetime.now(UTC)
        job = {
            "id": str(uuid4()),
            "job_type": "vector_index_document",
            "status": "succeeded",
            "stage": None,
            "last_error": None,
            "created_at": now - timedelta(minutes=5),
            "updated_at": now - timedelta(minutes=4),
        }
        stages = _build_timeline_stages([job])
        assert stages[0]["stage"] == "vector_index_document"
