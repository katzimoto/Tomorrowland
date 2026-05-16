"""Database access for documents and ingestion deduplication."""

from __future__ import annotations

import json
from typing import Any, cast
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection, RowMapping

from services.documents.models import (
    DocumentRow,
    DocumentSource,
    DocumentStatus,
)
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
        metadata: dict[str, Any] | None = None,
    ) -> DocumentRow | None:
        """Create a document row and optionally record SHA256 dedup.

        Returns *None* when *sha256* is provided and the same source item has
        already ingested that exact content hash. A changed file at the same
        ``source_id`` + ``external_id`` with a different SHA is stored as a new
        document row linked to the existing version family.
        """
        if sha256 is not None:
            existing_doc_id = self._connection.execute(
                sa.text(
                    """
                    SELECT id
                    FROM documents
                    WHERE source_id = :source_id
                      AND external_id = :external_id
                      AND content_sha256 = :sha256
                    """
                ),
                {
                    "source_id": db_uuid(source_id),
                    "external_id": external_id,
                    "sha256": sha256,
                },
            ).scalar_one_or_none()
            if existing_doc_id is not None:
                return None

        content_sha256 = sha256 or ""
        doc_id = uuid4()

        family_id_hex, version_number = self._get_or_create_version_family(
            source_id=source_id,
            external_id=external_id,
            new_doc_id=doc_id,
        )

        self._connection.execute(
            sa.text(
                """
                INSERT INTO documents (
                    id, source_id, external_id, source, path,
                    mime_type, title, source_language, status,
                    content_sha256, metadata,
                    version_family_id, version_number, is_latest
                )
                VALUES (
                    :id, :source_id, :external_id, :source, :path,
                    :mime_type, :title, :source_language, 'pending',
                    :content_sha256, :metadata,
                    :version_family_id, :version_number, 1
                )
                """
            ).bindparams(sa.bindparam("metadata", type_=sa.JSON())),
            {
                "id": db_uuid(doc_id),
                "source_id": db_uuid(source_id),
                "external_id": external_id,
                "source": source,
                "path": path,
                "mime_type": mime_type,
                "title": title,
                "source_language": source_language,
                "content_sha256": content_sha256,
                "metadata": metadata or {},
                "version_family_id": family_id_hex,
                "version_number": version_number,
            },
        )

        if sha256 is not None:
            self._connection.execute(
                sa.text(
                    """
                    INSERT INTO ingested_files (sha256, doc_id, source_id, external_id)
                    VALUES (:sha256, :doc_id, :source_id, :external_id)
                    """
                ),
                {
                    "sha256": sha256,
                    "doc_id": db_uuid(doc_id),
                    "source_id": db_uuid(source_id),
                    "external_id": external_id,
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

    def list_by_ids(self, doc_ids: list[UUID]) -> list[DocumentRow]:
        """Return documents for a list of IDs."""
        if not doc_ids:
            return []
        rows = self._connection.execute(
            sa.text("SELECT * FROM documents WHERE id IN :ids").bindparams(
                sa.bindparam("ids", expanding=True)
            ),
            {"ids": [db_uuid(d) for d in doc_ids]},
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

    def source_group_ids(self, source_id: UUID) -> list[UUID]:
        """Return group IDs granted access to an ingestion source."""
        rows = self._connection.execute(
            sa.text(
                """
                SELECT group_id
                FROM source_permissions
                WHERE source_id = :source_id
                ORDER BY group_id
                """
            ),
            {"source_id": db_uuid(source_id)},
        ).scalars()
        return [to_uuid(row) for row in rows]

    def list_versions_in_family(self, doc_id: UUID) -> list[DocumentRow]:
        """Return all document versions in the same family as *doc_id*, oldest first."""
        family_id_raw = self._connection.execute(
            sa.text("SELECT version_family_id FROM documents WHERE id = :id"),
            {"id": db_uuid(doc_id)},
        ).scalar_one_or_none()
        if family_id_raw is None:
            return []
        rows = self._connection.execute(
            sa.text(
                """
                SELECT * FROM documents
                WHERE version_family_id = :family_id
                ORDER BY version_number ASC
                """
            ),
            {"family_id": str(family_id_raw)},
        ).mappings()
        return [self._row_to_model(r) for r in rows]

    def get_latest_in_family(self, doc_id: UUID) -> DocumentRow | None:
        """Return the latest document version in the same family as *doc_id*."""
        row = (
            self._connection.execute(
                sa.text(
                    """
                SELECT * FROM documents
                WHERE version_family_id = (
                    SELECT version_family_id FROM documents WHERE id = :doc_id
                )
                AND is_latest = 1
                """
                ),
                {"doc_id": db_uuid(doc_id)},
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        return self._row_to_model(row)

    def get_family_current_doc_ids(self, family_ids: list[UUID]) -> dict[UUID, UUID]:
        """Return mapping of family_id → current_document_id for a batch of families."""
        if not family_ids:
            return {}
        rows = self._connection.execute(
            sa.text(
                "SELECT id, current_document_id FROM document_version_families WHERE id IN :ids"
            ).bindparams(sa.bindparam("ids", expanding=True)),
            {"ids": [db_uuid(f) for f in family_ids]},
        ).mappings()
        return {to_uuid(row["id"]): to_uuid(row["current_document_id"]) for row in rows}

    def _get_or_create_version_family(
        self,
        source_id: UUID,
        external_id: str,
        new_doc_id: UUID,
    ) -> tuple[str, int]:
        """Return (family_id_hex, next_version_number) for a source item.

        Creates the family when none exists. For existing families, marks the
        current latest document as non-latest and updates current_document_id.
        """
        family_id_raw = self._connection.execute(
            sa.text(
                """
                SELECT id FROM document_version_families
                WHERE source_id = :source_id AND external_id = :external_id
                """
            ),
            {"source_id": db_uuid(source_id), "external_id": external_id},
        ).scalar_one_or_none()

        if family_id_raw is None:
            family_id = uuid4()
            self._connection.execute(
                sa.text(
                    """
                    INSERT INTO document_version_families
                        (id, source_id, external_id, current_document_id)
                    VALUES (:id, :source_id, :external_id, :current_doc_id)
                    """
                ),
                {
                    "id": db_uuid(family_id),
                    "source_id": db_uuid(source_id),
                    "external_id": external_id,
                    "current_doc_id": db_uuid(new_doc_id),
                },
            )
            return db_uuid(family_id), 1

        family_id_hex = str(family_id_raw)

        next_version = self._connection.execute(
            sa.text(
                """
                SELECT COALESCE(MAX(version_number), 0) + 1
                FROM documents
                WHERE version_family_id = :family_id
                """
            ),
            {"family_id": family_id_hex},
        ).scalar_one()

        self._connection.execute(
            sa.text(
                """
                UPDATE documents SET is_latest = 0
                WHERE version_family_id = :family_id AND is_latest = 1
                """
            ),
            {"family_id": family_id_hex},
        )

        self._connection.execute(
            sa.text(
                """
                UPDATE document_version_families
                SET current_document_id = :new_doc_id,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :family_id
                """
            ),
            {"new_doc_id": db_uuid(new_doc_id), "family_id": family_id_hex},
        )

        return family_id_hex, int(next_version)

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
        version_family_id_raw = row.get("version_family_id")
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
            content_sha256=row.get("content_sha256"),
            version_family_id=to_uuid(version_family_id_raw) if version_family_id_raw else None,
            version_number=int(row.get("version_number") or 1),
            is_latest=bool(row.get("is_latest", True)),
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
