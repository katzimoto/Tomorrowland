from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine, create_engine

from services.pipeline.jobs import PipelineJobRepository


@pytest.fixture
def engine() -> Engine:
    eng = create_engine("sqlite://", echo=False)
    with eng.begin() as conn:
        conn.execute(
            sa.text("""
            CREATE TABLE ingestion_sources (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                path TEXT,
                source_language TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                config TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                translated_text TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        )
    return eng


def test_creates_pending_job(engine: Engine) -> None:
    with engine.begin() as conn:
        source_id = uuid4()
        document_id = uuid4()
        conn.execute(
            sa.text("INSERT INTO ingestion_sources (id, name, type) VALUES (:id, :name, :type)"),
            {"id": source_id.hex, "name": "test", "type": "folder"},
        )
        conn.execute(
            sa.text(
                "INSERT INTO documents (id, source_id, external_id, source, mime_type) "
                "VALUES (:id, :source_id, :eid, :source, :mime)"
            ),
            {
                "id": document_id.hex,
                "source_id": source_id.hex,
                "eid": "ext1",
                "source": "folder",
                "mime": "text/plain",
            },  # noqa: E501
        )

        repo = PipelineJobRepository(conn)
        job_id = repo.enqueue_document(document_id, source_id)

        assert isinstance(job_id, UUID)

        row = conn.execute(
            sa.text("SELECT status, priority, max_attempts FROM pipeline_jobs WHERE id = :id"),
            {"id": job_id.hex},
        ).one()
        assert row.status == "pending"
        assert row.priority == 0
        assert row.max_attempts == 5


def test_duplicate_active_returns_existing(engine: Engine) -> None:
    with engine.begin() as conn:
        source_id = uuid4()
        document_id = uuid4()
        conn.execute(
            sa.text("INSERT INTO ingestion_sources (id, name, type) VALUES (:id, :name, :type)"),
            {"id": source_id.hex, "name": "test", "type": "folder"},
        )
        conn.execute(
            sa.text(
                "INSERT INTO documents (id, source_id, external_id, source, mime_type) "
                "VALUES (:id, :source_id, :eid, :source, :mime)"
            ),
            {
                "id": document_id.hex,
                "source_id": source_id.hex,
                "eid": "ext1",
                "source": "folder",
                "mime": "text/plain",
            },  # noqa: E501
        )

        repo = PipelineJobRepository(conn)
        jid1 = repo.enqueue_document(document_id, source_id)
        jid2 = repo.enqueue_document(document_id, source_id)

        assert jid1 == jid2
        count = conn.execute(sa.text("SELECT COUNT(*) FROM pipeline_jobs")).scalar()
        assert count == 1


def test_completed_job_allows_new_enqueue(engine: Engine) -> None:
    with engine.begin() as conn:
        source_id = uuid4()
        document_id = uuid4()
        conn.execute(
            sa.text("INSERT INTO ingestion_sources (id, name, type) VALUES (:id, :name, :type)"),
            {"id": source_id.hex, "name": "test", "type": "folder"},
        )
        conn.execute(
            sa.text(
                "INSERT INTO documents (id, source_id, external_id, source, mime_type) "
                "VALUES (:id, :source_id, :eid, :source, :mime)"
            ),
            {
                "id": document_id.hex,
                "source_id": source_id.hex,
                "eid": "ext1",
                "source": "folder",
                "mime": "text/plain",
            },  # noqa: E501
        )

        repo = PipelineJobRepository(conn)
        jid1 = repo.enqueue_document(document_id, source_id)
        claimed = repo.claim_next("worker1")
        assert claimed is not None
        assert claimed["id"] == jid1
        repo.mark_succeeded(jid1)

        jid2 = repo.enqueue_document(document_id, source_id)
        assert jid2 != jid1
        count = conn.execute(sa.text("SELECT COUNT(*) FROM pipeline_jobs")).scalar()
        assert count == 2


def test_claims_by_priority(engine: Engine) -> None:
    with engine.begin() as conn:
        source_id = uuid4()
        doc_low = uuid4()
        doc_high = uuid4()
        conn.execute(
            sa.text("INSERT INTO ingestion_sources (id, name, type) VALUES (:id, :name, :type)"),
            {"id": source_id.hex, "name": "test", "type": "folder"},
        )
        for d in (doc_low, doc_high):
            conn.execute(
                sa.text(
                    "INSERT INTO documents (id, source_id, external_id, source, mime_type) "
                    "VALUES (:id, :source_id, :eid, :source, :mime)"
                ),
                {
                    "id": d.hex,
                    "source_id": source_id.hex,
                    "eid": d.hex,
                    "source": "folder",
                    "mime": "text/plain",
                },  # noqa: E501
            )

        repo = PipelineJobRepository(conn)
        _ = repo.enqueue_document(doc_low, source_id, priority=0)
        high_job = repo.enqueue_document(doc_high, source_id, priority=10)

        claimed = repo.claim_next("worker1")
        assert claimed is not None
        assert claimed["id"] == high_job
        assert claimed["attempts"] == 1
        assert claimed["locked_by"] == "worker1"

        second = repo.claim_next("worker2")
        assert second is not None
        assert second["priority"] == 0


def test_retry_not_claimable_before_run_after(engine: Engine) -> None:
    with engine.begin() as conn:
        source_id = uuid4()
        document_id = uuid4()
        conn.execute(
            sa.text("INSERT INTO ingestion_sources (id, name, type) VALUES (:id, :name, :type)"),
            {"id": source_id.hex, "name": "test", "type": "folder"},
        )
        conn.execute(
            sa.text(
                "INSERT INTO documents (id, source_id, external_id, source, mime_type) "
                "VALUES (:id, :source_id, :eid, :source, :mime)"
            ),
            {
                "id": document_id.hex,
                "source_id": source_id.hex,
                "eid": "ext1",
                "source": "folder",
                "mime": "text/plain",
            },  # noqa: E501
        )

        repo = PipelineJobRepository(conn)
        job_id = repo.enqueue_document(document_id, source_id)
        claimed = repo.claim_next("worker1")
        assert claimed is not None
        assert claimed["id"] == job_id

        repo.mark_retry(job_id, ValueError("boom"), retry_delay_seconds=3600)

        again = repo.claim_next("worker2")
        assert again is None


def test_mark_succeeded_updates_status(engine: Engine) -> None:
    with engine.begin() as conn:
        source_id = uuid4()
        document_id = uuid4()
        conn.execute(
            sa.text("INSERT INTO ingestion_sources (id, name, type) VALUES (:id, :name, :type)"),
            {"id": source_id.hex, "name": "test", "type": "folder"},
        )
        conn.execute(
            sa.text(
                "INSERT INTO documents (id, source_id, external_id, source, mime_type) "
                "VALUES (:id, :source_id, :eid, :source, :mime)"
            ),
            {
                "id": document_id.hex,
                "source_id": source_id.hex,
                "eid": "ext1",
                "source": "folder",
                "mime": "text/plain",
            },  # noqa: E501
        )

        repo = PipelineJobRepository(conn)
        job_id = repo.enqueue_document(document_id, source_id)
        claimed = repo.claim_next("worker1")
        assert claimed is not None
        assert claimed["id"] == job_id

        repo.mark_succeeded(job_id)

        status = conn.execute(
            sa.text("SELECT status FROM pipeline_jobs WHERE id = :id"),
            {"id": job_id.hex},
        ).scalar()
        assert status == "succeeded"

        locked_by = conn.execute(
            sa.text("SELECT locked_by FROM pipeline_jobs WHERE id = :id"),
            {"id": job_id.hex},
        ).scalar()
        assert locked_by is None


def test_mark_retry_schedules_backoff(engine: Engine) -> None:
    with engine.begin() as conn:
        source_id = uuid4()
        document_id = uuid4()
        conn.execute(
            sa.text("INSERT INTO ingestion_sources (id, name, type) VALUES (:id, :name, :type)"),
            {"id": source_id.hex, "name": "test", "type": "folder"},
        )
        conn.execute(
            sa.text(
                "INSERT INTO documents (id, source_id, external_id, source, mime_type) "
                "VALUES (:id, :source_id, :eid, :source, :mime)"
            ),
            {
                "id": document_id.hex,
                "source_id": source_id.hex,
                "eid": "ext1",
                "source": "folder",
                "mime": "text/plain",
            },  # noqa: E501
        )

        repo = PipelineJobRepository(conn)
        job_id = repo.enqueue_document(document_id, source_id)
        claimed = repo.claim_next("worker1")
        assert claimed is not None

        repo.mark_retry(job_id, ValueError("boom"), retry_delay_seconds=60)

        row = conn.execute(
            sa.text("SELECT status, last_error, run_after FROM pipeline_jobs WHERE id = :id"),
            {"id": job_id.hex},
        ).one()
        assert row.status == "retry"
        assert row.last_error == "ValueError:process"
        run_after = (
            row.run_after
            if isinstance(row.run_after, datetime)
            else datetime.fromisoformat(row.run_after)
        )  # noqa: E501
        if run_after.tzinfo is None:
            run_after = run_after.replace(tzinfo=UTC)
        assert run_after > datetime.now(UTC)


def test_mark_dead_letter(engine: Engine) -> None:
    with engine.begin() as conn:
        source_id = uuid4()
        document_id = uuid4()
        conn.execute(
            sa.text("INSERT INTO ingestion_sources (id, name, type) VALUES (:id, :name, :type)"),
            {"id": source_id.hex, "name": "test", "type": "folder"},
        )
        conn.execute(
            sa.text(
                "INSERT INTO documents (id, source_id, external_id, source, mime_type) "
                "VALUES (:id, :source_id, :eid, :source, :mime)"
            ),
            {
                "id": document_id.hex,
                "source_id": source_id.hex,
                "eid": "ext1",
                "source": "folder",
                "mime": "text/plain",
            },  # noqa: E501
        )

        repo = PipelineJobRepository(conn)
        job_id = repo.enqueue_document(document_id, source_id)
        claimed = repo.claim_next("worker1")
        assert claimed is not None

        repo.mark_dead_letter(job_id, RuntimeError("fatal"))

        row = conn.execute(
            sa.text("SELECT status, last_error FROM pipeline_jobs WHERE id = :id"),
            {"id": job_id.hex},
        ).one()
        assert row.status == "dead_letter"
        assert row.last_error == "RuntimeError:process"


def test_payload_store_and_load(engine: Engine) -> None:
    with engine.begin() as conn:
        source_id = uuid4()
        document_id = uuid4()
        conn.execute(
            sa.text("INSERT INTO ingestion_sources (id, name, type) VALUES (:id, :name, :type)"),
            {"id": source_id.hex, "name": "test", "type": "folder"},
        )
        conn.execute(
            sa.text(
                "INSERT INTO documents (id, source_id, external_id, source, mime_type) "
                "VALUES (:id, :source_id, :eid, :source, :mime)"
            ),
            {
                "id": document_id.hex,
                "source_id": source_id.hex,
                "eid": "ext1",
                "source": "folder",
                "mime": "text/plain",
            },  # noqa: E501
        )

        repo = PipelineJobRepository(conn)
        _ = repo.enqueue_document(document_id, source_id, content_text="hello world")

        payload = repo.get_payload(document_id)
        assert payload is not None
        assert payload["content_text"] == "hello world"
        assert payload["document_id"] == document_id


def test_payload_returns_none_for_missing(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = PipelineJobRepository(conn)
        result = repo.get_payload(uuid4())
        assert result is None


def test_mark_succeeded_on_non_running_is_noop(engine: Engine) -> None:
    with engine.begin() as conn:
        source_id = uuid4()
        document_id = uuid4()
        conn.execute(
            sa.text("INSERT INTO ingestion_sources (id, name, type) VALUES (:id, :name, :type)"),
            {"id": source_id.hex, "name": "test", "type": "folder"},
        )
        conn.execute(
            sa.text(
                "INSERT INTO documents (id, source_id, external_id, source, mime_type) "
                "VALUES (:id, :source_id, :eid, :source, :mime)"
            ),
            {
                "id": document_id.hex,
                "source_id": source_id.hex,
                "eid": "ext1",
                "source": "folder",
                "mime": "text/plain",
            },  # noqa: E501
        )

        repo = PipelineJobRepository(conn)
        job_id = repo.enqueue_document(document_id, source_id)

        repo.mark_succeeded(job_id)

        status = conn.execute(
            sa.text("SELECT status FROM pipeline_jobs WHERE id = :id"),
            {"id": job_id.hex},
        ).scalar()
        assert status == "pending"


def test_get_payload_translated_text_is_none_by_default(engine: Engine) -> None:
    with engine.begin() as conn:
        source_id = uuid4()
        document_id = uuid4()
        conn.execute(
            sa.text("INSERT INTO ingestion_sources (id, name, type) VALUES (:id, :name, :type)"),
            {"id": source_id.hex, "name": "test", "type": "folder"},
        )
        conn.execute(
            sa.text(
                "INSERT INTO documents (id, source_id, external_id, source, mime_type) "
                "VALUES (:id, :source_id, :eid, :source, :mime)"
            ),
            {
                "id": document_id.hex,
                "source_id": source_id.hex,
                "eid": "ext1",
                "source": "folder",
                "mime": "text/plain",
            },
        )

        repo = PipelineJobRepository(conn)
        repo.enqueue_document(document_id, source_id, content_text="raw text")

        payload = repo.get_payload(document_id)
        assert payload is not None
        assert payload["translated_text"] is None


def test_update_content_text_persists_value(engine: Engine) -> None:
    with engine.begin() as conn:
        source_id = uuid4()
        document_id = uuid4()
        conn.execute(
            sa.text("INSERT INTO ingestion_sources (id, name, type) VALUES (:id, :name, :type)"),
            {"id": source_id.hex, "name": "test", "type": "folder"},
        )
        conn.execute(
            sa.text(
                "INSERT INTO documents (id, source_id, external_id, source, mime_type) "
                "VALUES (:id, :source_id, :eid, :source, :mime)"
            ),
            {
                "id": document_id.hex,
                "source_id": source_id.hex,
                "eid": "ext1",
                "source": "folder",
                "mime": "text/plain",
            },
        )

        repo = PipelineJobRepository(conn)
        # Enqueue with content_path only (file-based doc: content_text starts NULL)
        repo.enqueue_document(document_id, source_id, content_path="/data/file.txt")
        repo.update_content_text(document_id, "extracted file content")

        payload = repo.get_payload(document_id)
        assert payload is not None
        assert payload["content_text"] == "extracted file content"


def test_update_translated_text_persists_value(engine: Engine) -> None:
    with engine.begin() as conn:
        source_id = uuid4()
        document_id = uuid4()
        conn.execute(
            sa.text("INSERT INTO ingestion_sources (id, name, type) VALUES (:id, :name, :type)"),
            {"id": source_id.hex, "name": "test", "type": "folder"},
        )
        conn.execute(
            sa.text(
                "INSERT INTO documents (id, source_id, external_id, source, mime_type) "
                "VALUES (:id, :source_id, :eid, :source, :mime)"
            ),
            {
                "id": document_id.hex,
                "source_id": source_id.hex,
                "eid": "ext1",
                "source": "folder",
                "mime": "text/plain",
            },
        )

        repo = PipelineJobRepository(conn)
        repo.enqueue_document(document_id, source_id, content_text="raw text")
        repo.update_translated_text(document_id, "translated content")

        payload = repo.get_payload(document_id)
        assert payload is not None
        assert payload["translated_text"] == "translated content"


def test_end_to_end(engine: Engine) -> None:
    with engine.begin() as conn:
        source_id = uuid4()
        document_id = uuid4()
        conn.execute(
            sa.text("INSERT INTO ingestion_sources (id, name, type) VALUES (:id, :name, :type)"),
            {"id": source_id.hex, "name": "test", "type": "folder"},
        )
        conn.execute(
            sa.text(
                "INSERT INTO documents (id, source_id, external_id, source, mime_type) "
                "VALUES (:id, :source_id, :eid, :source, :mime)"
            ),
            {
                "id": document_id.hex,
                "source_id": source_id.hex,
                "eid": "ext1",
                "source": "folder",
                "mime": "text/plain",
            },  # noqa: E501
        )

        repo = PipelineJobRepository(conn)
        job_id = repo.enqueue_document(document_id, source_id, content_text="full lifecycle")

        claimed = repo.claim_next("worker1")
        assert claimed is not None
        assert claimed["id"] == job_id
        assert claimed["document_id"] == document_id

        repo.mark_running_stage(job_id, "extracting")

        stage = conn.execute(
            sa.text("SELECT stage FROM pipeline_jobs WHERE id = :id"),
            {"id": job_id.hex},
        ).scalar()
        assert stage == "extracting"

        payload = repo.get_payload(document_id)
        assert payload is not None
        assert payload["content_text"] == "full lifecycle"

        repo.mark_succeeded(job_id)

        status = conn.execute(
            sa.text("SELECT status FROM pipeline_jobs WHERE id = :id"),
            {"id": job_id.hex},
        ).scalar()
        assert status == "succeeded"
