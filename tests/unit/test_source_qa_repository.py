"""Unit tests for SourceQARepository."""

from __future__ import annotations

from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine, create_engine

from services.intelligence.source_qa_repository import SourceQACheck, SourceQARepository
from shared.db import db_uuid


@pytest.fixture
def engine(tmp_path) -> Engine:
    db_path = tmp_path / "test.db"
    eng = create_engine(f"sqlite:///{db_path}")
    with eng.begin() as conn:
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


def test_upsert_and_get(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = SourceQARepository(conn)
        source_id = uuid4()
        check = SourceQACheck(
            source_id=source_id,
            total_documents=10,
            indexed_documents=8,
            pending_documents=1,
            failed_documents=1,
            empty_chunks=2,
            missing_content=3,
            missing_metadata=4,
            missing_title=5,
            ocr_eligible=6,
            ocr_maybe_needed=7,
            index_lag_count=8,
            issues=["test issue 1", "test issue 2"],
        )
        repo.upsert(check)

        result = repo.get_by_source(source_id)
        assert result is not None
        assert result.source_id == source_id
        assert result.total_documents == 10
        assert result.indexed_documents == 8
        assert result.pending_documents == 1
        assert result.failed_documents == 1
        assert result.empty_chunks == 2
        assert result.missing_content == 3
        assert result.missing_metadata == 4
        assert result.missing_title == 5
        assert result.ocr_eligible == 6
        assert result.ocr_maybe_needed == 7
        assert result.index_lag_count == 8
        assert result.issues == ["test issue 1", "test issue 2"]
        assert result.checked_at is not None


def test_upsert_replaces_existing(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = SourceQARepository(conn)
        source_id = uuid4()

        check1 = SourceQACheck(source_id=source_id, total_documents=5, issues=["old"])
        repo.upsert(check1)

        check2 = SourceQACheck(source_id=source_id, total_documents=10, issues=["new"])
        repo.upsert(check2)

        result = repo.get_by_source(source_id)
        assert result is not None
        assert result.total_documents == 10
        assert result.issues == ["new"]


def test_get_by_source_returns_none_when_missing(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = SourceQARepository(conn)
        result = repo.get_by_source(uuid4())
        assert result is None


def test_source_qa_check_defaults() -> None:
    source_id = uuid4()
    check = SourceQACheck(source_id=source_id)
    assert check.source_id == source_id
    assert check.total_documents == 0
    assert check.indexed_documents == 0
    assert check.pending_documents == 0
    assert check.failed_documents == 0
    assert check.empty_chunks == 0
    assert check.missing_content == 0
    assert check.missing_metadata == 0
    assert check.missing_title == 0
    assert check.ocr_eligible == 0
    assert check.ocr_maybe_needed == 0
    assert check.index_lag_count == 0
    assert check.issues == []
    assert check.checked_at is not None


def test_source_qa_check_to_dict() -> None:
    source_id = uuid4()
    check = SourceQACheck(
        source_id=source_id,
        total_documents=5,
        issues=["something wrong"],
    )
    d = check.to_dict()
    assert d["source_id"] == str(source_id)
    assert d["total_documents"] == 5
    assert d["issues"] == ["something wrong"]
    assert d["checked_at"] is not None


def test_source_qa_check_from_row() -> None:
    source_id = uuid4()
    row = {
        "source_id": db_uuid(source_id),
        "checked_at": "2026-05-30T12:00:00+00:00",
        "total_documents": 10,
        "indexed_documents": 8,
        "pending_documents": 1,
        "failed_documents": 1,
        "empty_chunks": 2,
        "missing_content": 3,
        "missing_metadata": 4,
        "missing_title": 5,
        "ocr_eligible": 6,
        "ocr_maybe_needed": 7,
        "index_lag_count": 8,
        "issues": '["issue 1", "issue 2"]',
    }
    check = SourceQACheck.from_row(row)
    assert check.source_id == source_id
    assert check.total_documents == 10
    assert check.issues == ["issue 1", "issue 2"]


def test_source_qa_check_from_row_none_issues() -> None:
    source_id = uuid4()
    row = {
        "source_id": db_uuid(source_id),
        "checked_at": "2026-05-30T12:00:00+00:00",
        "total_documents": 0,
        "indexed_documents": 0,
        "pending_documents": 0,
        "failed_documents": 0,
        "empty_chunks": 0,
        "missing_content": 0,
        "missing_metadata": 0,
        "missing_title": 0,
        "ocr_eligible": 0,
        "ocr_maybe_needed": 0,
        "index_lag_count": 0,
        "issues": None,
    }
    check = SourceQACheck.from_row(row)
    assert check.issues == []
