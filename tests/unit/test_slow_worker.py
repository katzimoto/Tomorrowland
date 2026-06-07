from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

from services.pipeline.slow_worker import run_enrich_once
from shared.metrics import MetricsRegistry


def _make_metrics() -> MetricsRegistry:
    return MetricsRegistry(version="0.0.0", commit="test", environment="test")


def _make_enrich_job(
    *,
    attempts: int = 1,
    max_attempts: int = 5,
) -> dict:
    return {
        "id": uuid4(),
        "document_id": uuid4(),
        "source_id": uuid4(),
        "job_type": "enrich_document",
        "priority": 0,
        "attempts": attempts,
        "max_attempts": max_attempts,
        "stage": None,
        "last_error": None,
        "run_after": None,
        "locked_by": "test-enrich-worker",
    }


class _FakeEnrichRepo:
    def __init__(self, claimed_job: dict | None = None, content_text: str = "") -> None:
        self.claimed_job = claimed_job
        self.content_text = content_text
        self.succeeded: object = None
        self.retried: tuple | None = None
        self.dead_lettered: tuple | None = None

    def claim_next(self, worker_id: str, job_types: list[str] | None = None) -> dict | None:
        return self.claimed_job

    def get_payload(self, document_id: object) -> dict | None:
        return {"content_text": self.content_text} if self.content_text else {}

    def mark_running_stage(self, job_id: object, stage: str) -> None:
        pass

    def mark_succeeded(self, job_id: object) -> None:
        self.succeeded = job_id

    def mark_retry(self, job_id: object, error: object, stage: str = "enrich", **_: object) -> None:
        self.retried = (job_id, error, stage)

    def mark_dead_letter(self, job_id: object, error: object) -> None:
        self.dead_lettered = (job_id, error)

    def commit(self) -> None:
        pass


class TestRunEnrichOnce:
    def test_success_path(self) -> None:
        job = _make_enrich_job()
        repo = _FakeEnrichRepo(claimed_job=job)
        worker = MagicMock()

        result = run_enrich_once(repo, worker, worker_id="ew1")

        assert result is True
        assert repo.succeeded is job["id"]
        assert repo.retried is None
        assert repo.dead_lettered is None
        worker.process_document.assert_called_once_with(job["document_id"], content_text="")

    def test_no_job_available_returns_false(self) -> None:
        repo = _FakeEnrichRepo(claimed_job=None)
        worker = MagicMock()

        result = run_enrich_once(repo, worker, worker_id="ew1")

        assert result is False
        worker.process_document.assert_not_called()
        assert repo.succeeded is None

    def test_retry_when_below_max_attempts(self) -> None:
        job = _make_enrich_job(attempts=2, max_attempts=5)
        repo = _FakeEnrichRepo(claimed_job=job)
        worker = MagicMock()
        worker.process_document.side_effect = RuntimeError("transient")

        result = run_enrich_once(repo, worker, worker_id="ew1")

        assert result is True
        assert repo.succeeded is None
        assert repo.retried is not None
        assert repo.retried[0] is job["id"]
        assert repo.dead_lettered is None

    def test_dead_letter_when_at_max_attempts(self) -> None:
        job = _make_enrich_job(attempts=5, max_attempts=5)
        repo = _FakeEnrichRepo(claimed_job=job)
        worker = MagicMock()
        worker.process_document.side_effect = RuntimeError("permanent")

        result = run_enrich_once(repo, worker, worker_id="ew1")

        assert result is True
        assert repo.succeeded is None
        assert repo.retried is None
        assert repo.dead_lettered is not None
        assert repo.dead_lettered[0] is job["id"]

    def test_success_increments_claimed_and_succeeded_metrics(self) -> None:
        metrics = _make_metrics()
        job = _make_enrich_job()
        repo = _FakeEnrichRepo(claimed_job=job)
        worker = MagicMock()

        run_enrich_once(repo, worker, worker_id="ew1", metrics=metrics)

        claimed_val = metrics.pipeline_jobs_claimed_total.labels(
            worker_type="enrich", job_type="enrich_document"
        )._value.get()
        assert claimed_val == 1.0

        succeeded_val = metrics.pipeline_jobs_succeeded_total.labels(
            worker_type="enrich", job_type="enrich_document"
        )._value.get()
        assert succeeded_val == 1.0

    def test_retry_increments_retried_metrics(self) -> None:
        metrics = _make_metrics()
        job = _make_enrich_job(attempts=1, max_attempts=3)
        repo = _FakeEnrichRepo(claimed_job=job)
        worker = MagicMock()
        worker.process_document.side_effect = RuntimeError("boom")

        run_enrich_once(repo, worker, worker_id="ew1", metrics=metrics)

        retried_val = metrics.pipeline_jobs_retried_total.labels(
            worker_type="enrich", job_type="enrich_document"
        )._value.get()
        assert retried_val == 1.0

        dead_val = metrics.pipeline_jobs_dead_lettered_total.labels(
            worker_type="enrich", job_type="enrich_document"
        )._value.get()
        assert dead_val == 0.0

    def test_dead_letter_increments_dead_lettered_metrics(self) -> None:
        metrics = _make_metrics()
        job = _make_enrich_job(attempts=5, max_attempts=5)
        repo = _FakeEnrichRepo(claimed_job=job)
        worker = MagicMock()
        worker.process_document.side_effect = RuntimeError("final")

        run_enrich_once(repo, worker, worker_id="ew1", metrics=metrics)

        dead_val = metrics.pipeline_jobs_dead_lettered_total.labels(
            worker_type="enrich", job_type="enrich_document"
        )._value.get()
        assert dead_val == 1.0

        retried_val = metrics.pipeline_jobs_retried_total.labels(
            worker_type="enrich", job_type="enrich_document"
        )._value.get()
        assert retried_val == 0.0

    def test_none_metrics_does_not_crash(self) -> None:
        job = _make_enrich_job()
        repo = _FakeEnrichRepo(claimed_job=job)
        worker = MagicMock()

        result = run_enrich_once(repo, worker, worker_id="ew1", metrics=None)
        assert result is True
