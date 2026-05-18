"""Database access for intelligence outputs (summaries, entities, tags, key points)."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from shared.db import db_uuid


class IntelligenceRepository:
    """Upsert and query intelligence outputs for documents."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def upsert_summary(self, document_id: UUID, summary: str, model: str) -> None:
        """Insert or update the summary for a document."""
        self._connection.execute(
            sa.text("""
                INSERT INTO document_summaries (document_id, summary, model)
                VALUES (:document_id, :summary, :model)
                ON CONFLICT (document_id)
                DO UPDATE SET
                    summary = EXCLUDED.summary,
                    model = EXCLUDED.model,
                    updated_at = CURRENT_TIMESTAMP
                """),
            {
                "document_id": db_uuid(document_id),
                "summary": summary,
                "model": model,
            },
        )

    def get_summary(self, document_id: UUID) -> dict[str, Any] | None:
        """Return the summary for a document, or None."""
        row = (
            self._connection.execute(
                sa.text("""
                    SELECT document_id, summary, model, created_at, updated_at
                    FROM document_summaries
                    WHERE document_id = :document_id
                    """),
                {"document_id": db_uuid(document_id)},
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None

    def upsert_entity(self, name: str, entity_type: str) -> UUID:
        """Upsert an entity by (name, type) and return its id.

        Uses INSERT ... ON CONFLICT to deduplicate.
        """
        entity_id = uuid4()
        self._connection.execute(
            sa.text("""
                INSERT INTO entities (id, name, type)
                VALUES (:id, :name, :type)
                ON CONFLICT (name, type)
                DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """),
            {
                "id": db_uuid(entity_id),
                "name": name,
                "type": entity_type,
            },
        )
        # Re-fetch to get the actual id (whether inserted or existing)
        row = (
            self._connection.execute(
                sa.text("""
                    SELECT id FROM entities
                    WHERE name = :name AND type = :type
                    """),
                {"name": name, "type": entity_type},
            )
            .mappings()
            .first()
        )
        if row is None:
            raise RuntimeError("entity upsert did not persist")
        return UUID(str(row["id"]))

    def link_document_entity(
        self,
        document_id: UUID,
        entity_id: UUID,
        frequency: int = 1,
    ) -> None:
        """Link a document to an entity, incrementing frequency on conflict."""
        self._connection.execute(
            sa.text("""
                INSERT INTO document_entities (document_id, entity_id, frequency)
                VALUES (:document_id, :entity_id, :frequency)
                ON CONFLICT (document_id, entity_id)
                DO UPDATE SET
                    frequency = document_entities.frequency + EXCLUDED.frequency
                """),
            {
                "document_id": db_uuid(document_id),
                "entity_id": db_uuid(entity_id),
                "frequency": frequency,
            },
        )

    def get_entities(self, document_id: UUID) -> list[dict[str, Any]]:
        """Return all entities linked to a document."""
        rows = self._connection.execute(
            sa.text("""
                SELECT e.id, e.name, e.type, de.frequency
                FROM document_entities de
                JOIN entities e ON e.id = de.entity_id
                WHERE de.document_id = :document_id
                ORDER BY de.frequency DESC, e.name
                """),
            {"document_id": db_uuid(document_id)},
        ).mappings()
        return [dict(row) for row in rows]

    def replace_tags(self, document_id: UUID, tags: list[str]) -> None:
        """Replace all tags for a document with the given list."""
        self._connection.execute(
            sa.text("DELETE FROM document_tags WHERE document_id = :document_id"),
            {"document_id": db_uuid(document_id)},
        )
        if not tags:
            return
        self._connection.execute(
            sa.text("""
                INSERT INTO document_tags (document_id, tag)
                VALUES (:document_id, :tag)
                """),
            [{"document_id": db_uuid(document_id), "tag": tag} for tag in tags],
        )

    def get_tags(self, document_id: UUID) -> list[str]:
        """Return all tags for a document."""
        rows = self._connection.execute(
            sa.text("""
                SELECT tag FROM document_tags
                WHERE document_id = :document_id
                ORDER BY tag
                """),
            {"document_id": db_uuid(document_id)},
        ).scalars()
        return list(rows)

    def upsert_key_points(self, document_id: UUID, points: list[str]) -> None:
        """Replace all key points for a document with the given ordered list.

        Position is assigned by list index (0-based).  Empty/whitespace-only
        points are skipped.
        """
        self._connection.execute(
            sa.text("DELETE FROM document_key_points WHERE document_id = :document_id"),
            {"document_id": db_uuid(document_id)},
        )
        rows = [
            {
                "id": db_uuid(uuid4()),
                "document_id": db_uuid(document_id),
                "key_point": point.strip(),
                "position": position,
            }
            for position, point in enumerate(points)
            if isinstance(point, str) and point.strip()
        ]
        if not rows:
            return
        self._connection.execute(
            sa.text("""
                INSERT INTO document_key_points (id, document_id, key_point, position)
                VALUES (:id, :document_id, :key_point, :position)
                """),
            rows,
        )

    def get_key_points(self, document_id: UUID) -> list[str]:
        """Return all key points for a document, ordered by position."""
        rows = self._connection.execute(
            sa.text("""
                SELECT key_point FROM document_key_points
                WHERE document_id = :document_id
                ORDER BY position
                """),
            {"document_id": db_uuid(document_id)},
        ).scalars()
        return list(rows)
