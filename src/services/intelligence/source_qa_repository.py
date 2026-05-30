"""Database access for source QA check results."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection, RowMapping

from shared.db import db_uuid, to_uuid


class SourceQACheck:
    """Value object representing a source QA check result."""

    def __init__(
        self,
        source_id: UUID,
        *,
        checked_at: datetime | None = None,
        total_documents: int = 0,
        indexed_documents: int = 0,
        pending_documents: int = 0,
        failed_documents: int = 0,
        empty_chunks: int = 0,
        missing_content: int = 0,
        missing_metadata: int = 0,
        missing_title: int = 0,
        ocr_eligible: int = 0,
        ocr_maybe_needed: int = 0,
        index_lag_count: int = 0,
        issues: list[str] | None = None,
    ) -> None:
        self.source_id = source_id
        self.checked_at = checked_at or datetime.now(UTC)
        self.total_documents = total_documents
        self.indexed_documents = indexed_documents
        self.pending_documents = pending_documents
        self.failed_documents = failed_documents
        self.empty_chunks = empty_chunks
        self.missing_content = missing_content
        self.missing_metadata = missing_metadata
        self.missing_title = missing_title
        self.ocr_eligible = ocr_eligible
        self.ocr_maybe_needed = ocr_maybe_needed
        self.index_lag_count = index_lag_count
        self.issues = issues or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": str(self.source_id),
            "checked_at": self.checked_at.isoformat() if self.checked_at else None,
            "total_documents": self.total_documents,
            "indexed_documents": self.indexed_documents,
            "pending_documents": self.pending_documents,
            "failed_documents": self.failed_documents,
            "empty_chunks": self.empty_chunks,
            "missing_content": self.missing_content,
            "missing_metadata": self.missing_metadata,
            "missing_title": self.missing_title,
            "ocr_eligible": self.ocr_eligible,
            "ocr_maybe_needed": self.ocr_maybe_needed,
            "index_lag_count": self.index_lag_count,
            "issues": self.issues,
        }

    @classmethod
    def from_row(cls, row: RowMapping) -> SourceQACheck:
        raw_issues = row.get("issues")
        return cls(
            source_id=to_uuid(row["source_id"]),
            checked_at=datetime.fromisoformat(str(row["checked_at"]).replace("Z", "+00:00"))
            if isinstance(row["checked_at"], str)
            else row["checked_at"],
            total_documents=int(row["total_documents"]),
            indexed_documents=int(row["indexed_documents"]),
            pending_documents=int(row["pending_documents"]),
            failed_documents=int(row["failed_documents"]),
            empty_chunks=int(row["empty_chunks"]),
            missing_content=int(row["missing_content"]),
            missing_metadata=int(row["missing_metadata"]),
            missing_title=int(row["missing_title"]),
            ocr_eligible=int(row["ocr_eligible"]),
            ocr_maybe_needed=int(row["ocr_maybe_needed"]),
            index_lag_count=int(row["index_lag_count"]),
            issues=json.loads(raw_issues) if isinstance(raw_issues, str) else raw_issues or [],
        )


class SourceQARepository:
    """Upsert and query source QA check results."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def upsert(self, check: SourceQACheck) -> None:
        """Insert or replace the QA check for a source."""
        self._connection.execute(
            sa.text("""
                INSERT INTO source_qa_checks (
                    id, source_id, checked_at,
                    total_documents, indexed_documents, pending_documents, failed_documents,
                    empty_chunks, missing_content, missing_metadata, missing_title,
                    ocr_eligible, ocr_maybe_needed,
                    index_lag_count, issues, created_at
                ) VALUES (
                    :id, :source_id, :checked_at,
                    :total_documents, :indexed_documents, :pending_documents, :failed_documents,
                    :empty_chunks, :missing_content, :missing_metadata, :missing_title,
                    :ocr_eligible, :ocr_maybe_needed,
                    :index_lag_count, :issues, CURRENT_TIMESTAMP
                )
                ON CONFLICT (source_id) DO UPDATE SET
                    id = EXCLUDED.id,
                    checked_at = EXCLUDED.checked_at,
                    total_documents = EXCLUDED.total_documents,
                    indexed_documents = EXCLUDED.indexed_documents,
                    pending_documents = EXCLUDED.pending_documents,
                    failed_documents = EXCLUDED.failed_documents,
                    empty_chunks = EXCLUDED.empty_chunks,
                    missing_content = EXCLUDED.missing_content,
                    missing_metadata = EXCLUDED.missing_metadata,
                    missing_title = EXCLUDED.missing_title,
                    ocr_eligible = EXCLUDED.ocr_eligible,
                    ocr_maybe_needed = EXCLUDED.ocr_maybe_needed,
                    index_lag_count = EXCLUDED.index_lag_count,
                    issues = EXCLUDED.issues,
                    created_at = CURRENT_TIMESTAMP
            """),
            {
                "id": db_uuid(uuid4()),
                "source_id": db_uuid(check.source_id),
                "checked_at": (
                    check.checked_at.isoformat()
                    if check.checked_at
                    else datetime.now(UTC).isoformat()
                ),
                "total_documents": check.total_documents,
                "indexed_documents": check.indexed_documents,
                "pending_documents": check.pending_documents,
                "failed_documents": check.failed_documents,
                "empty_chunks": check.empty_chunks,
                "missing_content": check.missing_content,
                "missing_metadata": check.missing_metadata,
                "missing_title": check.missing_title,
                "ocr_eligible": check.ocr_eligible,
                "ocr_maybe_needed": check.ocr_maybe_needed,
                "index_lag_count": check.index_lag_count,
                "issues": json.dumps(check.issues),
            },
        )

    def get_by_source(self, source_id: UUID) -> SourceQACheck | None:
        """Return the latest QA check for a source, or None."""
        row = (
            self._connection.execute(
                sa.text("""
                    SELECT source_id, checked_at,
                           total_documents, indexed_documents, pending_documents, failed_documents,
                           empty_chunks, missing_content, missing_metadata, missing_title,
                           ocr_eligible, ocr_maybe_needed,
                           index_lag_count, issues
                    FROM source_qa_checks
                    WHERE source_id = :source_id
                """),
                {"source_id": db_uuid(source_id)},
            )
            .mappings()
            .first()
        )
        return SourceQACheck.from_row(dict(row)) if row else None
