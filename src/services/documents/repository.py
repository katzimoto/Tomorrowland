"""Database access for documents and ingestion deduplication."""

from __future__ import annotations

from typing import cast
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection, RowMapping

from services.documents.models import DocumentRow, DocumentSource, DocumentStatus


def _db_uuid(value: UUID) -> str:
    return value.hex


def _to_uuid(value: object) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


class DocumentRepository:
    """CRUD and queries for the documents table."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def create(
        self,
        source_id: UUID,
        external_id: str,
        source: str,
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
                "id": _db_uuid(doc_id),
                "source_id": _db_uuid(source_id),
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
                    "doc_id": _db_uuid(doc_id),
                    "source_id": _db_uuid(source_id),
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

    def update_status(self, doc_id: UUID, status: str) -> None:
        """Update the document status."""
        self._connection.execute(
            sa.text("UPDATE documents SET status = :status WHERE id = :id"),
            {"status": status, "id": _db_uuid(doc_id)},
        )

    def list_by_source(self, source_id: UUID) -> list[DocumentRow]:
        """List all documents belonging to a source."""
        rows = self._connection.execute(
            sa.text("SELECT * FROM documents WHERE source_id = :source_id"),
            {"source_id": _db_uuid(source_id)},
        ).mappings()
        return [self._row_to_model(row) for row in rows]

    def _get_row_by_id(self, doc_id: UUID) -> RowMapping | None:
        return (
            self._connection.execute(
                sa.text("SELECT * FROM documents WHERE id = :id"),
                {"id": _db_uuid(doc_id)},
            )
            .mappings()
            .first()
        )

    @staticmethod
    def _row_to_model(row: RowMapping) -> DocumentRow:
        metadata = row["metadata"]
        if isinstance(metadata, str):
            import json

            metadata = json.loads(metadata) if metadata else {}
        elif metadata is None:
            metadata = {}
        return DocumentRow(
            id=_to_uuid(row["id"]),
            source_id=_to_uuid(row["source_id"]),
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
