"""Deterministic source-level ingestion/indexing health diagnostics.

All checks are deterministic — no LLM calls, no Hermes runtime, no external
model inference.  Operates entirely on database state and known ingestion
artifacts.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from services.intelligence.source_qa_repository import SourceQACheck, SourceQARepository
from shared.db import db_uuid


def run_source_qa(
    connection: Connection,
    source_id: UUID,
    *,
    index_lag_threshold_minutes: int = 60,
) -> SourceQACheck:
    """Run all deterministic QA checks for a source and persist the result.

    Returns the persisted ``SourceQACheck`` value object.
    """
    issues: list[str] = []

    def _add_issue(count: int, message: str) -> None:
        if count > 0:
            issues.append(f"{count} {message}")

    # --- Document breakdown by status ---
    doc_counts = _document_status_breakdown(connection, source_id)
    total = doc_counts["total"]
    indexed = doc_counts["indexed"]
    pending = doc_counts["pending"]
    failed = doc_counts["failed"]

    # --- Empty / missing content (indexed but no payload text) ---
    empty_chunks = _count_empty_chunks(connection, source_id)
    _add_issue(empty_chunks, "indexed document(s) have empty or missing content text")

    # --- Missing content_text in document_payloads ---
    no_content = _count_missing_content(connection, source_id)
    _add_issue(no_content, "document(s) have no content payload")

    # --- Missing metadata (empty or NULL JSON blob) ---
    no_metadata = _count_missing_metadata(connection, source_id)
    _add_issue(no_metadata, "document(s) have missing or empty metadata")

    # --- Missing title ---
    no_title = _count_missing_title(connection, source_id)
    _add_issue(no_title, "document(s) have no title")

    # --- OCR eligibility ---
    ocr_eligible = _count_ocr_eligible(connection, source_id)
    ocr_maybe_needed = _count_ocr_maybe_needed(connection, source_id)
    _add_issue(ocr_maybe_needed, "PDF(s) with empty text may need OCR")

    # --- Index lag (pending documents older than threshold) ---
    lag_count = _count_index_lag(connection, source_id, index_lag_threshold_minutes)
    _add_issue(
        lag_count,
        (
            f"document(s) have been pending for over {index_lag_threshold_minutes}"
            " minutes (possible index lag)"
        ),
    )

    check = SourceQACheck(
        source_id=source_id,
        checked_at=datetime.now(UTC),
        total_documents=total,
        indexed_documents=indexed,
        pending_documents=pending,
        failed_documents=failed,
        empty_chunks=empty_chunks,
        missing_content=no_content,
        missing_metadata=no_metadata,
        missing_title=no_title,
        ocr_eligible=ocr_eligible,
        ocr_maybe_needed=ocr_maybe_needed,
        index_lag_count=lag_count,
        issues=issues,
    )

    repo = SourceQARepository(connection)
    repo.upsert(check)
    return check


def get_latest_qa(connection: Connection, source_id: UUID) -> SourceQACheck | None:
    """Return the most recent persisted QA check for a source, or None."""
    return SourceQARepository(connection).get_by_source(source_id)


# ---------------------------------------------------------------------------
# Individual check helpers
# ---------------------------------------------------------------------------


def _document_status_breakdown(connection: Connection, source_id: UUID) -> dict[str, int]:
    row = (
        connection.execute(
            sa.text("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE status = 'indexed') AS indexed,
                    COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                    COUNT(*) FILTER (WHERE status = 'failed') AS failed
                FROM documents
                WHERE source_id = :source_id
            """),
            {"source_id": db_uuid(source_id)},
        )
        .mappings()
        .first()
    )
    return dict(row) if row else {"total": 0, "indexed": 0, "pending": 0, "failed": 0}


def _count_empty_chunks(connection: Connection, source_id: UUID) -> int:
    """Documents with status=indexed but no content_text or empty content."""
    row = connection.execute(
        sa.text("""
            SELECT COUNT(*)
            FROM documents d
            LEFT JOIN document_payloads p ON p.document_id = d.id
            WHERE d.source_id = :source_id
              AND d.status = 'indexed'
              AND (p.content_text IS NULL OR p.content_text = '')
        """),
        {"source_id": db_uuid(source_id)},
    ).scalar()
    return int(row or 0)


def _count_missing_content(connection: Connection, source_id: UUID) -> int:
    """Documents (any status) without a document_payloads row at all."""
    row = connection.execute(
        sa.text("""
            SELECT COUNT(*)
            FROM documents d
            LEFT JOIN document_payloads p ON p.document_id = d.id
            WHERE d.source_id = :source_id
              AND p.document_id IS NULL
        """),
        {"source_id": db_uuid(source_id)},
    ).scalar()
    return int(row or 0)


def _count_missing_metadata(connection: Connection, source_id: UUID) -> int:
    """Documents where metadata is NULL, empty string, or empty JSON object."""
    row = connection.execute(
        sa.text("""
            SELECT COUNT(*)
            FROM documents
            WHERE source_id = :source_id
              AND (
                  metadata IS NULL
                  OR CAST(metadata AS TEXT) = ''
                  OR CAST(metadata AS TEXT) = '{}'
              )
        """),
        {"source_id": db_uuid(source_id)},
    ).scalar()
    return int(row or 0)


def _count_missing_title(connection: Connection, source_id: UUID) -> int:
    """Documents where title is NULL or empty."""
    row = connection.execute(
        sa.text("""
            SELECT COUNT(*)
            FROM documents
            WHERE source_id = :source_id
              AND (title IS NULL OR title = '')
        """),
        {"source_id": db_uuid(source_id)},
    ).scalar()
    return int(row or 0)


def _count_ocr_eligible(connection: Connection, source_id: UUID) -> int:
    """Documents with OCR-eligible MIME types (image-based PDFs, scanned images)."""
    row = connection.execute(
        sa.text("""
            SELECT COUNT(*)
            FROM documents
            WHERE source_id = :source_id
              AND mime_type IN (
                  'application/pdf',
                  'image/tiff',
                  'image/png',
                  'image/jpeg',
                  'image/bmp'
              )
        """),
        {"source_id": db_uuid(source_id)},
    ).scalar()
    return int(row or 0)


def _count_ocr_maybe_needed(connection: Connection, source_id: UUID) -> int:
    """OCR-eligible documents with empty or missing content (may need OCR)."""
    row = connection.execute(
        sa.text("""
            SELECT COUNT(*)
            FROM documents d
            LEFT JOIN document_payloads p ON p.document_id = d.id
            WHERE d.source_id = :source_id
              AND d.mime_type IN (
                  'application/pdf',
                  'image/tiff',
                  'image/png',
                  'image/jpeg',
                  'image/bmp'
              )
              AND (p.content_text IS NULL OR p.content_text = '')
        """),
        {"source_id": db_uuid(source_id)},
    ).scalar()
    return int(row or 0)


def _count_index_lag(
    connection: Connection,
    source_id: UUID,
    threshold_minutes: int = 60,
) -> int:
    """Documents stuck in pending status beyond the threshold."""
    cutoff = (datetime.now(UTC) - timedelta(minutes=threshold_minutes)).isoformat()
    row = connection.execute(
        sa.text("""
            SELECT COUNT(*)
            FROM documents
            WHERE source_id = :source_id
              AND status = 'pending'
              AND created_at < :cutoff
        """),
        {"source_id": db_uuid(source_id), "cutoff": cutoff},
    ).scalar()
    return int(row or 0)
