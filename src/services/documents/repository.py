"""Database access for documents and ingestion deduplication."""

from __future__ import annotations

import json
from typing import Any, cast
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection, RowMapping

from services.documents.models import DocumentRow, DocumentSource, DocumentStatus
from shared.db import db_uuid, to_uuid


class DocumentRepository:
    """CRUD and queries for the documents table."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def create(
        self,
        source_id: UUID,
        external_id: str,
        source: DocumentSource,
        mime_type: str,
        path: str | None = None,
        title: str | None = None,
        source_language: str | None = None,
        sha256: str | None = None,
    ) -> DocumentRow | None:
        """Create a document row and optionally record SHA256 dedup.

        Returns *None* when *sha256* is provided and already exists in
        ``ingested_files``.
        """
        if sha256 is not None:
            existing = self._connection.execute(
                sa.text("SELECT sha256 FROM ingested_files WHERE sha256 = :sha256"),
                {"sha256": sha256},
            ).scalar_one_or_none()
            if existing is not None:
                return None

        doc_id = uuid4()
        self._connection.execute(
            sa.text(
                """
                INSERT INTO documents (
                    id, source_id, external_id, source, path,
                    mime_type, title, source_language, status
                )
                VALUES (
                    :id, :source_id, :external_id, :source, :path,
                    :mime_type, :title, :source_language, 'pending'
                )
                """
            ),
            {
                "id": db_uuid(doc_id),
                "source_id": db_uuid(source_id),
                "external_id": external_id,
                "source": source,
                "path": path,
                "mime_type": mime_type,
                "title": title,
                "source_language": source_language,
            },
        )

        if sha256 is not None:
            self._connection.execute(
                sa.text(
                    """
                    INSERT INTO ingested_files (sha256, doc_id, source_id)
                    VALUES (:sha256, :doc_id, :source_id)
                    """
                ),
                {
                    "sha256": sha256,
                    "doc_id": db_uuid(doc_id),
                    "source_id": db_uuid(source_id),
                },
            )

        row = self._get_row_by_id(doc_id)
        if row is None:
            raise RuntimeError("document insert did not persist")
        return self._row_to_model(row)

    def get_by_id(self, doc_id: UUID) -> DocumentRow | None:
        """Return a document by primary key."""
        row = self._get_row_by_id(doc_id)
        if row is None:
            return None
        return self._row_to_model(row)

    def update_status(self, doc_id: UUID, status: DocumentStatus) -> None:
        """Update the document status."""
        self._connection.execute(
            sa.text("UPDATE documents SET status = :status WHERE id = :id"),
            {"status": status, "id": db_uuid(doc_id)},
        )

    def update_indexed(
        self,
        doc_id: UUID,
        status: DocumentStatus,
        translation_quality: str | None,
    ) -> None:
        """Update document status and translation quality after indexing."""
        self._connection.execute(
            sa.text(
                """
                UPDATE documents
                SET status = :status, translation_quality = :quality
                WHERE id = :id
                """
            ),
            {"status": status, "quality": translation_quality, "id": db_uuid(doc_id)},
        )

    def list_by_source(self, source_id: UUID) -> list[DocumentRow]:
        """List all documents belonging to a source."""
        rows = self._connection.execute(
            sa.text("SELECT * FROM documents WHERE source_id = :source_id"),
            {"source_id": db_uuid(source_id)},
        ).mappings()
        return [self._row_to_model(row) for row in rows]

    def update_translation_quality(
        self,
        doc_id: UUID,
        quality: str,
    ) -> None:
        """Update the document translation quality."""
        self._connection.execute(
            sa.text(
                """
                UPDATE documents
                SET translation_quality = :quality
                WHERE id = :id
                """
            ),
            {"quality": quality, "id": db_uuid(doc_id)},
        )

    def list_pending_enrichment(self) -> list[DocumentRow]:
        """List documents queued for high-quality translation."""
        rows = self._connection.execute(
            sa.text("SELECT * FROM documents WHERE translation_quality = 'pending_high'"),
        ).mappings()
        return [self._row_to_model(row) for row in rows]

    def _get_row_by_id(self, doc_id: UUID) -> RowMapping | None:
        return (
            self._connection.execute(
                sa.text("SELECT * FROM documents WHERE id = :id"),
                {"id": db_uuid(doc_id)},
            )
            .mappings()
            .first()
        )

    @staticmethod
    def _row_to_model(row: RowMapping) -> DocumentRow:
        metadata = row["metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata) if metadata else {}
        elif metadata is None:
            metadata = {}
        return DocumentRow(
            id=to_uuid(row["id"]),
            source_id=to_uuid(row["source_id"]),
            external_id=str(row["external_id"]),
            source=cast("DocumentSource", str(row["source"])),
            path=row["path"],
            mime_type=str(row["mime_type"]),
            title=row["title"],
            source_language=row["source_language"],
            target_language=str(row["target_language"]),
            translation_quality=row["translation_quality"],
            status=cast("DocumentStatus", str(row["status"])),
            metadata=metadata,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class TranslationVersionRepository:
    """CRUD and queries for document translation versions."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def create_version(
        self,
        doc_id: UUID,
        label: str,
        quality: str,
        request_type: str,
        requested_by_id: UUID | None = None,
        target_language: str = "en",
        request_note: str | None = None,
    ) -> dict[str, Any]:
        """Create a pending translation version and return its record."""
        version_number = self._get_next_version_number(doc_id)
        version_id = uuid4()
        row = (
            self._connection.execute(
                sa.text(
                    """
                    INSERT INTO document_translation_versions (
                        id, doc_id, version_number, label, quality, request_type,
                        status, target_language, requested_by_id, request_note
                    )
                    VALUES (
                        :id, :doc_id, :version_number, :label, :quality, :request_type,
                        'pending', :target_language, :requested_by_id, :request_note
                    )
                    RETURNING id, doc_id, version_number, label, source_language,
                              target_language, quality, request_type, status,
                              requested_by_id, requested_at
                    """
                ),
                {
                    "id": db_uuid(version_id),
                    "doc_id": db_uuid(doc_id),
                    "version_number": version_number,
                    "label": label,
                    "quality": quality,
                    "request_type": request_type,
                    "target_language": target_language,
                    "requested_by_id": db_uuid(requested_by_id) if requested_by_id else None,
                    "request_note": request_note,
                },
            )
            .mappings()
            .first()
        )
        if row is None:
            raise RuntimeError("version insert did not persist")
        return dict(row)

    def list_versions(self, doc_id: UUID) -> list[dict[str, Any]]:
        """List all translation versions for a document, newest first."""
        rows = self._connection.execute(
            sa.text(
                """
                SELECT * FROM document_translation_versions
                WHERE doc_id = :doc_id
                ORDER BY version_number DESC
                """
            ),
            {"doc_id": db_uuid(doc_id)},
        ).mappings()
        return [dict(row) for row in rows]

    def get_pending_versions(self, doc_id: UUID) -> list[dict[str, Any]]:
        """Return pending translation versions for a document."""
        rows = self._connection.execute(
            sa.text(
                """
                SELECT * FROM document_translation_versions
                WHERE doc_id = :doc_id AND status = 'pending'
                ORDER BY version_number
                """
            ),
            {"doc_id": db_uuid(doc_id)},
        ).mappings()
        return [dict(row) for row in rows]

    def find_pending_or_running(
        self,
        doc_id: UUID,
        target_language: str,
    ) -> dict[str, Any] | None:
        """Return a pending or running version for the same doc + language."""
        row = (
            self._connection.execute(
                sa.text(
                    """
                    SELECT * FROM document_translation_versions
                    WHERE doc_id = :doc_id
                      AND target_language = :target_language
                      AND status IN ('pending', 'running')
                    ORDER BY requested_at DESC
                    LIMIT 1
                    """
                ),
                {
                    "doc_id": db_uuid(doc_id),
                    "target_language": target_language,
                },
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None

    def update_version_status(
        self,
        version_id: UUID,
        status: str,
        translated_text: str | None = None,
        error_summary: str | None = None,
    ) -> None:
        """Update version status and optional result fields."""
        self._connection.execute(
            sa.text(
                """
                UPDATE document_translation_versions
                SET status = :status,
                    translated_text = COALESCE(
                        :translated_text, translated_text
                    ),
                    error_summary = COALESCE(
                        :error_summary, error_summary
                    ),
                    started_at = CASE
                        WHEN :status = 'running'
                        THEN CURRENT_TIMESTAMP
                        ELSE started_at
                    END,
                    completed_at = CASE
                        WHEN :status IN ('available', 'failed', 'canceled')
                        THEN CURRENT_TIMESTAMP
                        ELSE completed_at
                    END
                WHERE id = :id
                """
            ),
            {
                "status": status,
                "translated_text": translated_text,
                "error_summary": error_summary,
                "id": db_uuid(version_id),
            },
        )

    def _get_next_version_number(self, doc_id: UUID) -> int:
        """Return the next version number for a document."""
        result = self._connection.execute(
            sa.text(
                """
                SELECT COALESCE(MAX(version_number), 0) + 1
                FROM document_translation_versions
                WHERE doc_id = :doc_id
                """
            ),
            {"doc_id": db_uuid(doc_id)},
        ).scalar_one()
        return int(result)
