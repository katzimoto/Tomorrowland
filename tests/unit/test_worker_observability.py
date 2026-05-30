"""Tests for worker observability metrics (Issue #67)."""

from __future__ import annotations

from uuid import uuid4

from shared.metrics import MetricsRegistry


def _make_metrics() -> MetricsRegistry:
    return MetricsRegistry(version="0.0.0", commit="test", environment="test")


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
                    document_id TEXT NOT NULL REFERENCES documents(id),
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
                    document_id TEXT PRIMARY KEY REFERENCES documents(id),
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
