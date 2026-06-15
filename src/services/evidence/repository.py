"""Database access for evidence packs and their items.

Pure CRUD: this layer performs no permission checks. Ownership and document
access are enforced by :class:`services.evidence.service.EvidencePackService`.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from services.evidence.models import EvidencePack, EvidencePackItem
from shared.db import db_uuid, to_uuid


def _json_load(value: Any) -> Any:
    """Decode a JSON column that may arrive as text (SQLite) or parsed (PG)."""
    if value is None:
        return None
    if isinstance(value, str):
        return json.loads(value) if value else None
    return value


class EvidencePackRepository:
    """CRUD and queries for evidence packs and items."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    # ------------------------------------------------------------------
    # Packs
    # ------------------------------------------------------------------

    def create_pack(
        self,
        *,
        owner_user_id: UUID,
        title: str,
        created_from: str,
        description: str | None = None,
        source_scope: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EvidencePack:
        """Insert an evidence pack and return the persisted row."""
        pack_id = uuid4()
        row = (
            self._connection.execute(
                sa.text("""
                    INSERT INTO evidence_packs (
                        id, owner_user_id, title, description, source_scope,
                        created_from, metadata, created_at, updated_at
                    )
                    VALUES (
                        :id, :owner_user_id, :title, :description, :source_scope,
                        :created_from, :metadata, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    RETURNING id, owner_user_id, title, description, source_scope,
                              created_from, metadata, created_at, updated_at
                    """),
                {
                    "id": db_uuid(pack_id),
                    "owner_user_id": db_uuid(owner_user_id),
                    "title": title,
                    "description": description,
                    "source_scope": json.dumps(source_scope) if source_scope is not None else None,
                    "created_from": created_from,
                    "metadata": json.dumps(metadata or {}),
                },
            )
            .mappings()
            .first()
        )
        if row is None:
            raise RuntimeError("evidence pack insert did not persist")
        return self._row_to_pack(row)

    def get_pack(self, pack_id: UUID) -> EvidencePack | None:
        """Return a pack by id, or None when it does not exist."""
        row = (
            self._connection.execute(
                sa.text("""
                    SELECT id, owner_user_id, title, description, source_scope,
                           created_from, metadata, created_at, updated_at
                    FROM evidence_packs
                    WHERE id = :id
                    """),
                {"id": db_uuid(pack_id)},
            )
            .mappings()
            .first()
        )
        return self._row_to_pack(row) if row else None

    def list_packs(self, owner_user_id: UUID) -> list[EvidencePack]:
        """List packs owned by *owner_user_id*, newest first."""
        rows = (
            self._connection.execute(
                sa.text("""
                    SELECT id, owner_user_id, title, description, source_scope,
                           created_from, metadata, created_at, updated_at
                    FROM evidence_packs
                    WHERE owner_user_id = :owner_user_id
                    ORDER BY created_at DESC
                    """),
                {"owner_user_id": db_uuid(owner_user_id)},
            )
            .mappings()
            .all()
        )
        return [self._row_to_pack(r) for r in rows]

    def update_pack(
        self,
        pack_id: UUID,
        *,
        title: str | None = None,
        description: str | None = None,
        source_scope: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Update the supplied (non-None) fields of a pack and bump updated_at."""
        fields: list[str] = []
        params: dict[str, Any] = {"id": db_uuid(pack_id)}

        if title is not None:
            fields.append("title = :title")
            params["title"] = title
        if description is not None:
            fields.append("description = :description")
            params["description"] = description
        if source_scope is not None:
            fields.append("source_scope = :source_scope")
            params["source_scope"] = json.dumps(source_scope)
        if metadata is not None:
            fields.append("metadata = :metadata")
            params["metadata"] = json.dumps(metadata)

        fields.append("updated_at = CURRENT_TIMESTAMP")

        # Safe: `fields` contains only hardcoded column-name fragments.
        self._connection.execute(
            sa.text(f"UPDATE evidence_packs SET {', '.join(fields)} WHERE id = :id"),
            params,
        )

    def delete_pack(self, pack_id: UUID) -> None:
        """Hard-delete a pack. Items cascade via the foreign key."""
        self._connection.execute(
            sa.text("DELETE FROM evidence_packs WHERE id = :id"),
            {"id": db_uuid(pack_id)},
        )

    def touch_pack(self, pack_id: UUID) -> None:
        """Bump a pack's updated_at — used when its items change."""
        self._connection.execute(
            sa.text("UPDATE evidence_packs SET updated_at = CURRENT_TIMESTAMP WHERE id = :id"),
            {"id": db_uuid(pack_id)},
        )

    # ------------------------------------------------------------------
    # Items
    # ------------------------------------------------------------------

    def add_item(
        self,
        *,
        evidence_pack_id: UUID,
        document_id: UUID,
        item_type: str,
        text_excerpt: str,
        chunk_id: str | None = None,
        citation_id: str | None = None,
        page_number: int | None = None,
        section_heading: str | None = None,
        translated_text: str | None = None,
        claim: str | None = None,
        text_lane: str | None = None,
        translated_from: str | None = None,
        matched_text_kind: str | None = None,
        translation_version_id: str | None = None,
        translation_quality: str | None = None,
        translation_validation_status: str | None = None,
    ) -> EvidencePackItem:
        """Insert an item into a pack and return the persisted row."""
        item_id = uuid4()
        row = (
            self._connection.execute(
                sa.text("""
                    INSERT INTO evidence_pack_items (
                        id, evidence_pack_id, document_id, chunk_id, citation_id,
                        page_number, section_heading, text_excerpt, translated_text,
                        claim, item_type,
                        text_lane, translated_from, matched_text_kind,
                        translation_version_id, translation_quality,
                        translation_validation_status,
                        created_at
                    )
                    VALUES (
                        :id, :evidence_pack_id, :document_id, :chunk_id, :citation_id,
                        :page_number, :section_heading, :text_excerpt, :translated_text,
                        :claim, :item_type,
                        :text_lane, :translated_from, :matched_text_kind,
                        :translation_version_id, :translation_quality,
                        :translation_validation_status,
                        CURRENT_TIMESTAMP
                    )
                    RETURNING id, evidence_pack_id, document_id, chunk_id, citation_id,
                              page_number, section_heading, text_excerpt, translated_text,
                              claim, item_type,
                              text_lane, translated_from, matched_text_kind,
                              translation_version_id, translation_quality,
                              translation_validation_status,
                              created_at
                    """),
                {
                    "id": db_uuid(item_id),
                    "evidence_pack_id": db_uuid(evidence_pack_id),
                    "document_id": db_uuid(document_id),
                    "chunk_id": chunk_id,
                    "citation_id": citation_id,
                    "page_number": page_number,
                    "section_heading": section_heading,
                    "text_excerpt": text_excerpt,
                    "translated_text": translated_text,
                    "claim": claim,
                    "item_type": item_type,
                    "text_lane": text_lane,
                    "translated_from": translated_from,
                    "matched_text_kind": matched_text_kind,
                    "translation_version_id": translation_version_id,
                    "translation_quality": translation_quality,
                    "translation_validation_status": translation_validation_status,
                },
            )
            .mappings()
            .first()
        )
        if row is None:
            raise RuntimeError("evidence pack item insert did not persist")
        return self._row_to_item(row)

    def get_item(self, item_id: UUID) -> EvidencePackItem | None:
        """Return an item by id, or None when it does not exist."""
        row = (
            self._connection.execute(
                sa.text("""
                    SELECT id, evidence_pack_id, document_id, chunk_id, citation_id,
                           page_number, section_heading, text_excerpt, translated_text,
                           claim, item_type,
                           text_lane, translated_from, matched_text_kind,
                           translation_version_id, translation_quality,
                           translation_validation_status,
                           created_at
                    FROM evidence_pack_items
                    WHERE id = :id
                    """),
                {"id": db_uuid(item_id)},
            )
            .mappings()
            .first()
        )
        return self._row_to_item(row) if row else None

    def list_items(self, evidence_pack_id: UUID) -> list[EvidencePackItem]:
        """List a pack's items, oldest first."""
        rows = (
            self._connection.execute(
                sa.text("""
                    SELECT id, evidence_pack_id, document_id, chunk_id, citation_id,
                           page_number, section_heading, text_excerpt, translated_text,
                           claim, item_type,
                           text_lane, translated_from, matched_text_kind,
                           translation_version_id, translation_quality,
                           translation_validation_status,
                           created_at
                    FROM evidence_pack_items
                    WHERE evidence_pack_id = :evidence_pack_id
                    ORDER BY created_at ASC
                    """),
                {"evidence_pack_id": db_uuid(evidence_pack_id)},
            )
            .mappings()
            .all()
        )
        return [self._row_to_item(r) for r in rows]

    def remove_item(self, item_id: UUID) -> None:
        """Hard-delete a single item."""
        self._connection.execute(
            sa.text("DELETE FROM evidence_pack_items WHERE id = :id"),
            {"id": db_uuid(item_id)},
        )

    # ------------------------------------------------------------------
    # Row mappers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_pack(row: Any) -> EvidencePack:
        return EvidencePack(
            id=to_uuid(row["id"]),
            owner_user_id=to_uuid(row["owner_user_id"]),
            title=row["title"],
            description=row["description"],
            source_scope=_json_load(row["source_scope"]),
            created_from=row["created_from"],
            metadata=_json_load(row["metadata"]) or {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_item(row: Any) -> EvidencePackItem:
        return EvidencePackItem(
            id=to_uuid(row["id"]),
            evidence_pack_id=to_uuid(row["evidence_pack_id"]),
            document_id=to_uuid(row["document_id"]),
            item_type=row["item_type"],
            text_excerpt=row["text_excerpt"],
            chunk_id=row.get("chunk_id"),
            citation_id=row.get("citation_id"),
            page_number=row.get("page_number"),
            section_heading=row.get("section_heading"),
            translated_text=row.get("translated_text"),
            claim=row.get("claim"),
            text_lane=row.get("text_lane"),
            translated_from=row.get("translated_from"),
            matched_text_kind=row.get("matched_text_kind"),
            translation_version_id=row.get("translation_version_id"),
            translation_quality=row.get("translation_quality"),
            translation_validation_status=row.get("translation_validation_status"),
            created_at=row["created_at"],
        )
