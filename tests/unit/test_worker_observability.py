"""Tests for worker observability metrics (Issue #67)."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

from services.pipeline.runner import run_once
from services.pipeline.vector_worker import run_vector_once
from shared.metrics import MetricsRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_metrics() -> MetricsRegistry:
    return MetricsRegistry(version="0.0.0", commit="test", environment="test")


def _make_pipeline_job(
    *,
    attempts: int = 1,
    max_attempts: int = 5,
    job_type: str = "process_document",
) -> dict:
    return {
        "id": uuid4(),
        "doc_id": uuid4(),
        "source_id": uuid4(),
        "job_type": job_type,
        "priority": 0,
        "attempts": attempts,
        "max_attempts": max_attempts,
        "stage": None,
        "last_error": None,
        "run_after": None,
        "locked_by": "test-worker",
    }


class _FakePipelineRepo:
    def __init__(self, claimed_job: dict | None = None) -> None:
        self.claimed_job = claimed_job
        self.payload: dict | None = {"content_text": "text"}
        self.succeeded: object = None
        self.retried: tuple | None = None
        self.dead_lettered: tuple | None = None
        self.enqueued: list = []

    def claim_next(self, worker_id: str) -> dict | None:
        return self.claimed_job

    def get_payload(self, doc_id: object) -> dict | None:
        return self.payload

    def mark_running_stage(self, job_id: object, stage: str) -> None:
        pass

    def mark_succeeded(self, job_id: object) -> None:
        self.succeeded = job_id

    def mark_retry(
        self, job_id: object, error: object, stage: str = "process", **_: object
    ) -> None:
        self.retried = (job_id, error, stage)

    def mark_dead_letter(self, job_id: object, error: object) -> None:
        self.dead_lettered = (job_id, error)

    def enqueue_document(self, **kwargs: object) -> object:
        self.enqueued.append(kwargs)
        return uuid4()


class _FakeVectorRepo(_FakePipelineRepo):
    def claim_next(  # type: ignore[override]
        self, worker_id: str, job_types: list[str] | None = None
    ) -> dict | None:
        return self.claimed_job


# ---------------------------------------------------------------------------
# Metric registration
# ---------------------------------------------------------------------------


class TestWorkerMetricRegistration:
    def test_two_independent_registries_do_not_conflict(self) -> None:
        r1 = _make_metrics()
        r2 = _make_metrics()
        # Both instantiate without ValueError (duplicate name in same registry)
        assert r1 is not r2

    def test_all_worker_metrics_are_registered(self) -> None:
        from prometheus_client import Counter, Gauge, Histogram

        metrics = _make_metrics()
        assert isinstance(metrics.worker_heartbeat_timestamp_seconds, Gauge)
        assert isinstance(metrics.pipeline_queue_depth, Gauge)
        assert isinstance(metrics.pipeline_jobs_claimed_total, Counter)
        assert isinstance(metrics.pipeline_jobs_succeeded_total, Counter)
        assert isinstance(metrics.pipeline_jobs_retried_total, Counter)
        assert isinstance(metrics.pipeline_jobs_dead_lettered_total, Counter)
        assert isinstance(metrics.pipeline_jobs_stale_lock_reaped_total, Counter)
        assert isinstance(metrics.pipeline_job_duration_seconds, Histogram)
        assert isinstance(metrics.worker_loop_errors_total, Counter)

    def test_existing_metrics_still_registered(self) -> None:
        from prometheus_client import Counter, Gauge

        metrics = _make_metrics()
        assert isinstance(metrics.http_requests_total, Counter)
        assert isinstance(metrics.pipeline_documents_total, Counter)
        assert isinstance(metrics.dlq_records_total, Counter)
        assert isinstance(metrics.build_info, Gauge)


# ---------------------------------------------------------------------------
# Pipeline runner metrics
# ---------------------------------------------------------------------------


class TestPipelineRunnerMetrics:
    def test_success_increments_claimed_and_succeeded(self) -> None:
        metrics = _make_metrics()
        job = _make_pipeline_job()
        repo = _FakePipelineRepo(claimed_job=job)
        worker = MagicMock()

        result = run_once(repo, worker, worker_id="w1", metrics=metrics)

        assert result is True
        claimed_val = metrics.pipeline_jobs_claimed_total.labels(
            worker_type="pipeline", job_type="process_document"
        )._value.get()
        assert claimed_val == 1.0

        succeeded_val = metrics.pipeline_jobs_succeeded_total.labels(
            worker_type="pipeline", job_type="process_document"
        )._value.get()
        assert succeeded_val == 1.0

    def test_success_observes_duration(self) -> None:
        metrics = _make_metrics()
        job = _make_pipeline_job()
        repo = _FakePipelineRepo(claimed_job=job)
        worker = MagicMock()

        run_once(repo, worker, worker_id="w1", metrics=metrics)

        count = sum(
            s.value
            for m in metrics.registry.collect()
            if "pipeline_job_duration_seconds" in m.name
            for s in m.samples
            if s.name.endswith("_count")
            and s.labels.get("outcome") == "succeeded"
            and s.labels.get("worker_type") == "pipeline"
        )
        assert count == 1.0

    def test_retry_increments_retried(self) -> None:
        metrics = _make_metrics()
        job = _make_pipeline_job(attempts=1, max_attempts=3)
        repo = _FakePipelineRepo(claimed_job=job)
        worker = MagicMock()
        worker.process_document.side_effect = RuntimeError("boom")

        run_once(repo, worker, worker_id="w1", metrics=metrics)

        retried_val = metrics.pipeline_jobs_retried_total.labels(
            worker_type="pipeline", job_type="process_document"
        )._value.get()
        assert retried_val == 1.0

        dead_val = metrics.pipeline_jobs_dead_lettered_total.labels(
            worker_type="pipeline", job_type="process_document"
        )._value.get()
        assert dead_val == 0.0

    def test_dead_letter_increments_dead_lettered(self) -> None:
        metrics = _make_metrics()
        job = _make_pipeline_job(attempts=5, max_attempts=5)
        repo = _FakePipelineRepo(claimed_job=job)
        worker = MagicMock()
        worker.process_document.side_effect = RuntimeError("final")

        run_once(repo, worker, worker_id="w1", metrics=metrics)

        dead_val = metrics.pipeline_jobs_dead_lettered_total.labels(
            worker_type="pipeline", job_type="process_document"
        )._value.get()
        assert dead_val == 1.0

        retried_val = metrics.pipeline_jobs_retried_total.labels(
            worker_type="pipeline", job_type="process_document"
        )._value.get()
        assert retried_val == 0.0

    def test_no_job_available_emits_no_claimed(self) -> None:
        metrics = _make_metrics()
        repo = _FakePipelineRepo(claimed_job=None)
        worker = MagicMock()

        result = run_once(repo, worker, worker_id="w1", metrics=metrics)

        assert result is False
        # Counter should not yet exist / be zero
        claimed_val = metrics.pipeline_jobs_claimed_total.labels(
            worker_type="pipeline", job_type="process_document"
        )._value.get()
        assert claimed_val == 0.0

    def test_none_metrics_does_not_crash(self) -> None:
        job = _make_pipeline_job()
        repo = _FakePipelineRepo(claimed_job=job)
        worker = MagicMock()

        result = run_once(repo, worker, worker_id="w1", metrics=None)
        assert result is True

    def test_error_outcome_label_uses_safe_class_name_only(self) -> None:
        """Duration histogram outcome label must be a fixed keyword, not raw error text."""
        metrics = _make_metrics()
        job = _make_pipeline_job(attempts=5, max_attempts=5)
        repo = _FakePipelineRepo(claimed_job=job)
        worker = MagicMock()
        worker.process_document.side_effect = ValueError("sensitive: user query text here")

        run_once(repo, worker, worker_id="w1", metrics=metrics)

        count = sum(
            s.value
            for m in metrics.registry.collect()
            if "pipeline_job_duration_seconds" in m.name
            for s in m.samples
            if s.name.endswith("_count")
            and s.labels.get("outcome") == "dead_lettered"
            and s.labels.get("worker_type") == "pipeline"
        )
        assert count == 1.0


# ---------------------------------------------------------------------------
# Vector worker metrics
# ---------------------------------------------------------------------------


class TestVectorWorkerMetrics:
    def test_success_increments_claimed_and_succeeded(self) -> None:
        metrics = _make_metrics()
        job = _make_pipeline_job(job_type="vector_index_document")
        repo = _FakeVectorRepo(claimed_job=job)

        doc = MagicMock()
        doc.path = None
        doc_repo = MagicMock()
        doc_repo.get_by_id.return_value = doc
        doc_repo.source_group_ids.return_value = []

        encoder = MagicMock()
        encoder.encode.return_value = [0.1, 0.2]

        qdrant = MagicMock()
        extractor = MagicMock()

        # Patch chunk_text to return one chunk so encode/upsert run
        import services.pipeline.vector_worker as vw_module

        original_chunk_text = vw_module.chunk_text
        try:
            vw_module.chunk_text = lambda _: ["chunk one"]
            result = run_vector_once(
                repo, encoder, qdrant, doc_repo, extractor, worker_id="vw1", metrics=metrics
            )
        finally:
            vw_module.chunk_text = original_chunk_text

        assert result is True
        claimed_val = metrics.pipeline_jobs_claimed_total.labels(
            worker_type="vector", job_type="vector_index_document"
        )._value.get()
        assert claimed_val == 1.0

        succeeded_val = metrics.pipeline_jobs_succeeded_total.labels(
            worker_type="vector", job_type="vector_index_document"
        )._value.get()
        assert succeeded_val == 1.0

    def test_retry_increments_retried(self) -> None:
        metrics = _make_metrics()
        job = _make_pipeline_job(job_type="vector_index_document", attempts=1, max_attempts=3)
        repo = _FakeVectorRepo(claimed_job=job)

        doc_repo = MagicMock()
        doc_repo.get_by_id.side_effect = RuntimeError("encode failed")

        encoder = MagicMock()
        qdrant = MagicMock()
        extractor = MagicMock()

        run_vector_once(
            repo, encoder, qdrant, doc_repo, extractor, worker_id="vw1", metrics=metrics
        )

        retried_val = metrics.pipeline_jobs_retried_total.labels(
            worker_type="vector", job_type="vector_index_document"
        )._value.get()
        assert retried_val == 1.0

    def test_dead_letter_increments_dead_lettered(self) -> None:
        metrics = _make_metrics()
        job = _make_pipeline_job(job_type="vector_index_document", attempts=5, max_attempts=5)
        repo = _FakeVectorRepo(claimed_job=job)

        doc_repo = MagicMock()
        doc_repo.get_by_id.side_effect = RuntimeError("fatal encode error")

        encoder = MagicMock()
        qdrant = MagicMock()
        extractor = MagicMock()

        run_vector_once(
            repo, encoder, qdrant, doc_repo, extractor, worker_id="vw1", metrics=metrics
        )

        dead_val = metrics.pipeline_jobs_dead_lettered_total.labels(
            worker_type="vector", job_type="vector_index_document"
        )._value.get()
        assert dead_val == 1.0

    def test_none_metrics_does_not_crash(self) -> None:
        job = _make_pipeline_job(job_type="vector_index_document")
        repo = _FakeVectorRepo(claimed_job=job)

        doc = MagicMock()
        doc.path = None
        doc_repo = MagicMock()
        doc_repo.get_by_id.return_value = doc
        doc_repo.source_group_ids.return_value = []

        encoder = MagicMock()
        encoder.encode.return_value = [0.1]
        qdrant = MagicMock()
        extractor = MagicMock()

        import services.pipeline.vector_worker as vw_module

        original_chunk_text = vw_module.chunk_text
        try:
            vw_module.chunk_text = lambda _: ["chunk"]
            result = run_vector_once(
                repo, encoder, qdrant, doc_repo, extractor, worker_id="vw1", metrics=None
            )
        finally:
            vw_module.chunk_text = original_chunk_text

        assert result is True


# ---------------------------------------------------------------------------
# Queue depth / stale lock helpers
# ---------------------------------------------------------------------------


class TestCountByStatus:
    def test_count_by_status_via_fake(self) -> None:
        """count_by_status returns a dict keyed by (status, job_type)."""
        import sqlalchemy as sa
        from sqlalchemy import create_engine

        from services.pipeline.jobs import PipelineJobRepository

        engine = create_engine("sqlite://", echo=False)
        with engine.begin() as conn:
            conn.execute(
                sa.text("""
                CREATE TABLE ingestion_sources (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, type TEXT NOT NULL
                )
            """)
            )
            conn.execute(
                sa.text("""
                CREATE TABLE documents (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL REFERENCES ingestion_sources(id),
                    external_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    path TEXT,
                    mime_type TEXT NOT NULL,
                    title TEXT,
                    source_language TEXT,
                    target_language TEXT NOT NULL DEFAULT 'en',
                    translation_quality TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            )
            conn.execute(
                sa.text("""
                CREATE TABLE pipeline_jobs (
                    id TEXT PRIMARY KEY,
                    doc_id TEXT NOT NULL REFERENCES documents(id),
                    source_id TEXT NOT NULL REFERENCES ingestion_sources(id),
                    job_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    priority INTEGER NOT NULL DEFAULT 0,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 5,
                    stage TEXT,
                    last_error TEXT,
                    run_after TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    locked_by TEXT,
                    locked_at TIMESTAMP,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            )
            conn.execute(
                sa.text("""
                CREATE TABLE document_payloads (
                    doc_id TEXT PRIMARY KEY REFERENCES documents(id),
                    content_text TEXT,
                    content_path TEXT,
                    content_sha256 TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            )

            source_id = uuid4()
            doc_id_1 = uuid4()
            doc_id_2 = uuid4()
            conn.execute(
                sa.text("INSERT INTO ingestion_sources (id, name, type) VALUES (:id, :n, :t)"),
                {"id": source_id.hex, "n": "s", "t": "folder"},
            )
            for did in (doc_id_1, doc_id_2):
                conn.execute(
                    sa.text(
                        "INSERT INTO documents (id, source_id, external_id, source, mime_type) "
                        "VALUES (:id, :sid, :eid, :src, :mime)"
                    ),
                    {
                        "id": did.hex,
                        "sid": source_id.hex,
                        "eid": did.hex,
                        "src": "folder",
                        "mime": "text/plain",
                    },
                )

            repo = PipelineJobRepository(conn)
            repo.enqueue_document(doc_id_1, source_id, job_type="process_document")
            repo.enqueue_document(doc_id_2, source_id, job_type="vector_index_document")

            counts = repo.count_by_status()

        assert ("pending", "process_document") in counts
        assert counts[("pending", "process_document")] == 1
        assert ("pending", "vector_index_document") in counts
        assert counts[("pending", "vector_index_document")] == 1
