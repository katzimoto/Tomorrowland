"""Unit tests for source QA diagnostic service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine, create_engine

from services.intelligence.source_qa_service import get_latest_qa, run_source_qa
from shared.db import db_uuid


@pytest.fixture
def engine(tmp_path) -> Engine:
    db_path = tmp_path / "test.db"
    eng = create_engine(f"sqlite:///{db_path}")
    with eng.begin() as conn:
        # Documents table (minimal columns for QA checks)
        conn.execute(
            sa.text("""
                CREATE TABLE documents (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'folder',
                    mime_type TEXT NOT NULL DEFAULT 'text/plain',
                    title TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        )
        conn.execute(
            sa.text("""
                CREATE TABLE document_payloads (
                    document_id TEXT PRIMARY KEY,
                    content_text TEXT,
                    content_path TEXT,
                    content_sha256 TEXT,
                    translated_text TEXT,
                    extraction_metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        )
        conn.execute(
            sa.text("""
                CREATE TABLE source_qa_checks (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL UNIQUE,
                    checked_at TEXT NOT NULL,
                    total_documents INTEGER NOT NULL DEFAULT 0,
                    indexed_documents INTEGER NOT NULL DEFAULT 0,
                    pending_documents INTEGER NOT NULL DEFAULT 0,
                    failed_documents INTEGER NOT NULL DEFAULT 0,
                    empty_chunks INTEGER NOT NULL DEFAULT 0,
                    missing_content INTEGER NOT NULL DEFAULT 0,
                    missing_metadata INTEGER NOT NULL DEFAULT 0,
                    missing_title INTEGER NOT NULL DEFAULT 0,
                    ocr_eligible INTEGER NOT NULL DEFAULT 0,
                    ocr_maybe_needed INTEGER NOT NULL DEFAULT 0,
                    index_lag_count INTEGER NOT NULL DEFAULT 0,
                    issues TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        )
    return eng


def _insert_doc(
    conn: sa.Connection,
    source_id: str,
    *,
    status: str = "indexed",
    mime_type: str = "text/plain",
    title: str | None = "Test Doc",
    metadata: str | None = '{"key": "value"}',
    created_at: str | None = None,
) -> str:
    doc_id = db_uuid(uuid4())
    conn.execute(
        sa.text("""
            INSERT INTO documents
                (id, source_id, external_id, source, mime_type, title,
                 status, metadata, created_at)
            VALUES
                (:id, :source_id, :external_id, :source, :mime_type, :title,
                 :status, :metadata, :created_at)
        """),
        {
            "id": doc_id,
            "source_id": source_id,
            "external_id": doc_id,
            "source": "folder",
            "mime_type": mime_type,
            "title": title,
            "status": status,
            "metadata": metadata,
            "created_at": created_at or datetime.now(UTC).isoformat(),
        },
    )
    return doc_id


def _insert_payload(
    conn: sa.Connection, doc_id: str, *, content_text: str | None = "some content"
) -> None:
    conn.execute(
        sa.text("""
            INSERT INTO document_payloads (document_id, content_text)
            VALUES (:document_id, :content_text)
        """),
        {"document_id": doc_id, "content_text": content_text},
    )


# ---------------------------------------------------------------------------
# Happy path — healthy source
# ---------------------------------------------------------------------------


def test_run_source_qa_healthy_source(engine: Engine) -> None:
    src_obj = uuid4()
    source_id = db_uuid(src_obj)
    with engine.begin() as conn:
        for _ in range(3):
            doc_id = _insert_doc(conn, source_id, status="indexed")
            _insert_payload(conn, doc_id)

    with engine.begin() as conn:
        check = run_source_qa(conn, src_obj)

    assert check.total_documents == 3
    assert check.indexed_documents == 3
    assert check.issues == []


def test_run_source_qa_all_indexed(engine: Engine) -> None:
    src_obj = uuid4()
    source_id = db_uuid(src_obj)
    with engine.begin() as conn:
        for _ in range(5):
            doc_id = _insert_doc(conn, source_id, status="indexed")
            _insert_payload(conn, doc_id)

    with engine.begin() as conn:
        check = run_source_qa(conn, src_obj)

    assert check.total_documents == 5
    assert check.indexed_documents == 5
    assert check.empty_chunks == 0
    assert check.missing_content == 0


# ---------------------------------------------------------------------------
# Individual issue detection
# ---------------------------------------------------------------------------


def test_detects_empty_chunks(engine: Engine) -> None:
    src_obj = uuid4()
    source_id = db_uuid(src_obj)
    with engine.begin() as conn:
        doc_id = _insert_doc(conn, source_id, status="indexed")
        _insert_payload(conn, doc_id, content_text="")

    with engine.begin() as conn:
        check = run_source_qa(conn, src_obj)

    assert check.empty_chunks == 1
    assert any("empty" in issue.lower() for issue in check.issues)


def test_detects_missing_content(engine: Engine) -> None:
    src_obj = uuid4()
    source_id = db_uuid(src_obj)
    with engine.begin() as conn:
        _insert_doc(conn, source_id, status="pending")

    with engine.begin() as conn:
        check = run_source_qa(conn, src_obj)

    assert check.missing_content == 1
    assert any("no content" in issue.lower() for issue in check.issues)


def test_detects_missing_metadata(engine: Engine) -> None:
    src_obj = uuid4()
    source_id = db_uuid(src_obj)
    with engine.begin() as conn:
        _insert_doc(conn, source_id, metadata=None)

    with engine.begin() as conn:
        check = run_source_qa(conn, src_obj)

    assert check.missing_metadata == 1
    assert any("metadata" in issue.lower() for issue in check.issues)


def test_detects_empty_metadata(engine: Engine) -> None:
    src_obj = uuid4()
    source_id = db_uuid(src_obj)
    with engine.begin() as conn:
        _insert_doc(conn, source_id, metadata="{}")

    with engine.begin() as conn:
        check = run_source_qa(conn, src_obj)

    assert check.missing_metadata == 1


def test_detects_missing_title(engine: Engine) -> None:
    src_obj = uuid4()
    source_id = db_uuid(src_obj)
    with engine.begin() as conn:
        _insert_doc(conn, source_id, title=None)

    with engine.begin() as conn:
        check = run_source_qa(conn, src_obj)

    assert check.missing_title == 1
    assert any("title" in issue.lower() for issue in check.issues)


def test_detects_empty_title(engine: Engine) -> None:
    src_obj = uuid4()
    source_id = db_uuid(src_obj)
    with engine.begin() as conn:
        _insert_doc(conn, source_id, title="")

    with engine.begin() as conn:
        check = run_source_qa(conn, src_obj)

    assert check.missing_title == 1


def test_detects_ocr_eligible(engine: Engine) -> None:
    src_obj = uuid4()
    source_id = db_uuid(src_obj)
    with engine.begin() as conn:
        for mime in ["application/pdf", "image/tiff", "image/png", "image/jpeg", "image/bmp"]:
            _insert_doc(conn, source_id, mime_type=mime, status="indexed")

    with engine.begin() as conn:
        check = run_source_qa(conn, src_obj)

    assert check.ocr_eligible == 5


def test_detects_ocr_maybe_needed(engine: Engine) -> None:
    src_obj = uuid4()
    source_id = db_uuid(src_obj)
    with engine.begin() as conn:
        doc_id = _insert_doc(conn, source_id, mime_type="application/pdf", status="indexed")
        _insert_payload(conn, doc_id, content_text=None)

    with engine.begin() as conn:
        check = run_source_qa(conn, src_obj)

    assert check.ocr_maybe_needed == 1
    assert any("OCR" in issue for issue in check.issues)


def test_detects_index_lag(engine: Engine) -> None:
    src_obj = uuid4()
    source_id = db_uuid(src_obj)
    old_time = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    with engine.begin() as conn:
        _insert_doc(conn, source_id, status="pending", created_at=old_time)

    with engine.begin() as conn:
        check = run_source_qa(conn, src_obj, index_lag_threshold_minutes=60)

    assert check.index_lag_count == 1
    assert any("lag" in issue.lower() for issue in check.issues)


def test_no_index_lag_for_recent_pending(engine: Engine) -> None:
    src_obj = uuid4()
    source_id = db_uuid(src_obj)
    with engine.begin() as conn:
        _insert_doc(conn, source_id, status="pending")

    with engine.begin() as conn:
        check = run_source_qa(conn, src_obj, index_lag_threshold_minutes=60)

    assert check.index_lag_count == 0


def test_get_latest_qa(engine: Engine) -> None:
    source_id_obj = uuid4()
    source_id = db_uuid(source_id_obj)
    with engine.begin() as conn:
        _insert_doc(conn, source_id, status="indexed")

    with engine.begin() as conn:
        check = run_source_qa(conn, source_id_obj)
        assert check.total_documents == 1

        cached = get_latest_qa(conn, source_id_obj)
        assert cached is not None
        assert cached.total_documents == 1
        assert cached.indexed_documents == 1


def test_get_latest_qa_returns_none_when_no_check(engine: Engine) -> None:
    with engine.begin() as conn:
        result = get_latest_qa(conn, uuid4())
        assert result is None
