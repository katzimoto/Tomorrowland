from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from services.pipeline.slow_worker import EnrichmentSubtaskError, SlowWorker, run_enrich_once
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


def _make_mock_doc(doc_id: object = None) -> MagicMock:
    doc = MagicMock()
    doc.id = doc_id or uuid4()
    doc.source_id = uuid4()
    doc.source_language = "en"
    doc.target_language = "en"
    doc.title = "Test Doc"
    doc.source = "folder"
    doc.mime_type = "text/plain"
    doc.path = "/tmp/test.txt"
    return doc


class TestEnrichmentSubtaskErrors:
    """Enrichment subtask (alert/intelligence) failures surface as dead-letter jobs."""

    def _make_worker(
        self,
        *,
        alert_raises: Exception | None = None,
        intelligence_raises: Exception | None = None,
        doc: MagicMock | None = None,
    ) -> SlowWorker:
        mock_doc = doc or _make_mock_doc()

        doc_repo = MagicMock()
        doc_repo.get_by_id.return_value = mock_doc
        doc_repo.source_group_ids.return_value = []

        translator = MagicMock()
        translator.translate.return_value = "translated"

        encoder = MagicMock()
        encoder.encode_batch.return_value = []

        qdrant = MagicMock()

        alert_matcher: MagicMock | None = None
        if alert_raises is not None:
            alert_matcher = MagicMock()
            alert_matcher.match_document.side_effect = alert_raises

        intelligence: MagicMock | None = None
        if intelligence_raises is not None:
            intelligence = MagicMock()
            intelligence.process_document.side_effect = intelligence_raises

        with patch("services.pipeline.slow_worker.chunk_text", return_value=iter([])):
            worker = SlowWorker(
                document_repository=doc_repo,
                translator=translator,
                encoder=encoder,
                qdrant_client=qdrant,
                version_repository=None,
                alert_matcher=alert_matcher,
                intelligence_worker=intelligence,
            )
        worker._doc_repo = doc_repo
        worker._translator = translator
        worker._encoder = encoder
        worker._qdrant = qdrant
        worker._alert_matcher = alert_matcher
        worker._intelligence = intelligence
        return worker

    def test_alert_failure_raises_enrichment_subtask_error(self) -> None:
        worker = self._make_worker(alert_raises=RuntimeError("alert boom"))
        doc_id = uuid4()
        worker._doc_repo.get_by_id.return_value = _make_mock_doc(doc_id)

        with (
            pytest.raises(EnrichmentSubtaskError),
            patch("services.pipeline.slow_worker.chunk_text", return_value=iter([])),
        ):
            worker.process_document(doc_id)

    def test_intelligence_failure_raises_enrichment_subtask_error(self) -> None:
        worker = self._make_worker(intelligence_raises=RuntimeError("llm down"))
        doc_id = uuid4()
        worker._doc_repo.get_by_id.return_value = _make_mock_doc(doc_id)

        with (
            pytest.raises(EnrichmentSubtaskError),
            patch("services.pipeline.slow_worker.chunk_text", return_value=iter([])),
        ):
            worker.process_document(doc_id)

    def test_alert_failure_does_not_mark_document_status_failed(self) -> None:
        worker = self._make_worker(alert_raises=RuntimeError("alert boom"))
        doc_id = uuid4()
        worker._doc_repo.get_by_id.return_value = _make_mock_doc(doc_id)

        with (
            pytest.raises(EnrichmentSubtaskError),
            patch("services.pipeline.slow_worker.chunk_text", return_value=iter([])),
        ):
            worker.process_document(doc_id)

        worker._doc_repo.update_status.assert_not_called()

    def test_alert_failure_dead_letters_job_at_max_attempts(self) -> None:
        worker = self._make_worker(alert_raises=RuntimeError("alert boom"))
        doc_id = uuid4()
        worker._doc_repo.get_by_id.return_value = _make_mock_doc(doc_id)

        job = _make_enrich_job(attempts=5, max_attempts=5)
        job["document_id"] = doc_id
        repo = _FakeEnrichRepo(claimed_job=job)

        with patch("services.pipeline.slow_worker.chunk_text", return_value=iter([])):
            run_enrich_once(repo, worker, worker_id="ew1")

        assert repo.dead_lettered is not None
        assert repo.dead_lettered[0] is job["id"]
        assert repo.succeeded is None

    def test_intelligence_failure_retries_job_below_max_attempts(self) -> None:
        worker = self._make_worker(intelligence_raises=RuntimeError("llm down"))
        doc_id = uuid4()
        worker._doc_repo.get_by_id.return_value = _make_mock_doc(doc_id)

        job = _make_enrich_job(attempts=2, max_attempts=5)
        job["document_id"] = doc_id
        repo = _FakeEnrichRepo(claimed_job=job)

        with patch("services.pipeline.slow_worker.chunk_text", return_value=iter([])):
            run_enrich_once(repo, worker, worker_id="ew1")

        assert repo.retried is not None
        assert repo.retried[0] is job["id"]
        assert repo.dead_lettered is None
        assert repo.succeeded is None

    def test_both_subtasks_run_even_when_alert_fails(self) -> None:
        """Intelligence still runs even when alert raises first."""
        worker = self._make_worker(
            alert_raises=RuntimeError("alert boom"),
            intelligence_raises=RuntimeError("llm down"),
        )
        doc_id = uuid4()
        worker._doc_repo.get_by_id.return_value = _make_mock_doc(doc_id)

        with (
            pytest.raises(EnrichmentSubtaskError),
            patch("services.pipeline.slow_worker.chunk_text", return_value=iter([])),
        ):
            worker.process_document(doc_id)

        worker._alert_matcher.match_document.assert_called_once()
        worker._intelligence.process_document.assert_called_once()
