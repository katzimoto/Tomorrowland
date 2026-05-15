"""Tests for the pipeline job runner."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import UUID, uuid4

from services.pipeline.runner import run_once


class _FakeJobRepo:
    """Minimal fake that implements only the methods run_once needs."""

    def __init__(self) -> None:
        self.claim_next_calls: list[str] = []
        self.claimed_job: dict | None = None
        self.payload: dict | None = {"content_text": "extracted text"}
        self.for_success: bool = True

    def claim_next(self, worker_id: str) -> dict | None:
        self.claim_next_calls.append(worker_id)
        return self.claimed_job

    def get_payload(self, doc_id: UUID) -> dict | None:
        return self.payload

    def mark_running_stage(self, job_id: UUID, stage: str) -> None:
        self.marked_stage = (job_id, stage)

    def mark_succeeded(self, job_id: UUID) -> None:
        self.succeeded = job_id

    def mark_retry(self, job_id: UUID, error: str | BaseException, stage: str = "process") -> None:
        self.retried = (job_id, error, stage)

    def mark_dead_letter(self, job_id: UUID, error: str | BaseException) -> None:
        self.dead_lettered = (job_id, error)


class TestRunOnce:
    def test_returns_false_when_no_job_available(self) -> None:
        repo = _FakeJobRepo()
        worker = MagicMock()
        result = run_once(repo, worker)
        assert result is False
        worker.process_document.assert_not_called()

    def test_processes_job_and_marks_succeeded(self) -> None:
        doc_id = uuid4()
        repo = _FakeJobRepo()
        repo.claimed_job = {
            "id": uuid4(),
            "doc_id": doc_id,
            "source_id": uuid4(),
            "job_type": "process_document",
            "priority": 0,
            "attempts": 1,
            "max_attempts": 5,
            "stage": None,
            "last_error": None,
            "run_after": None,
            "locked_by": "runner",
        }
        worker = MagicMock()
        result = run_once(repo, worker)
        assert result is True
        worker.process_document.assert_called_once_with(doc_id, pre_extracted_text="extracted text")
        assert repo.succeeded == repo.claimed_job["id"]

    def test_marks_retry_when_worker_raises_and_attempts_remain(self) -> None:
        repo = _FakeJobRepo()
        repo.claimed_job = {
            "id": uuid4(),
            "doc_id": uuid4(),
            "source_id": uuid4(),
            "job_type": "process_document",
            "priority": 0,
            "attempts": 1,
            "max_attempts": 3,
            "stage": None,
            "last_error": None,
            "run_after": None,
            "locked_by": "runner",
        }
        worker = MagicMock()
        worker.process_document.side_effect = RuntimeError("processing failed")
        result = run_once(repo, worker)
        assert result is True
        assert repo.retried is not None
        assert repo.retried[0] == repo.claimed_job["id"]

    def test_marks_dead_letter_when_attempts_exhausted(self) -> None:
        repo = _FakeJobRepo()
        repo.claimed_job = {
            "id": uuid4(),
            "doc_id": uuid4(),
            "source_id": uuid4(),
            "job_type": "process_document",
            "priority": 0,
            "attempts": 5,
            "max_attempts": 5,
            "stage": None,
            "last_error": None,
            "run_after": None,
            "locked_by": "runner",
        }
        worker = MagicMock()
        worker.process_document.side_effect = RuntimeError("final failure")
        result = run_once(repo, worker)
        assert result is True
        assert repo.dead_lettered is not None
        assert repo.dead_lettered[0] == repo.claimed_job["id"]

    def test_loads_payload_and_passes_to_worker(self) -> None:
        doc_id = uuid4()
        repo = _FakeJobRepo()
        repo.payload = {"content_text": "custom extracted text"}
        repo.claimed_job = {
            "id": uuid4(),
            "doc_id": doc_id,
            "source_id": uuid4(),
            "job_type": "process_document",
            "priority": 0,
            "attempts": 1,
            "max_attempts": 5,
            "stage": None,
            "last_error": None,
            "run_after": None,
            "locked_by": "runner",
        }
        worker = MagicMock()
        run_once(repo, worker)
        assert_called_args = worker.process_document.call_args
        assert_called_args[1]["pre_extracted_text"] == "custom extracted text"

    def test_handles_missing_payload_gracefully(self) -> None:
        doc_id = uuid4()
        repo = _FakeJobRepo()
        repo.payload = None
        repo.claimed_job = {
            "id": uuid4(),
            "doc_id": doc_id,
            "source_id": uuid4(),
            "job_type": "process_document",
            "priority": 0,
            "attempts": 1,
            "max_attempts": 5,
            "stage": None,
            "last_error": None,
            "run_after": None,
            "locked_by": "runner",
        }
        worker = MagicMock()
        run_once(repo, worker)
        worker.process_document.assert_called_once_with(doc_id, pre_extracted_text=None)
