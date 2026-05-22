"""Database access for annotations."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from shared.db import db_uuid


class AnnotationRepository:
    """CRUD and queries for annotations."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def list_annotations(
        self,
        document_id: UUID,
        user_id: UUID,
        is_admin: bool = False,
    ) -> list[dict[str, Any]]:
        """List annotations visible to *user_id* on *document_id*.

        Returns:
        - All shared (is_private = false) annotations
        - Own private annotations (is_private = true AND user_id = user_id)
        - Includes reply_count for each annotation.
        """
        if is_admin:
            rows = self._connection.execute(
                sa.text("""
                    SELECT
                        a.id,
                        a.document_id,
                        a.user_id,
                        u.display_name AS user_display_name,
                        a.text,
                        a.note,
                        a.position,
                        a.is_private,
                        a.created_at,
                        a.updated_at,
                        COALESCE(rc.cnt, 0) AS reply_count
                    FROM annotations a
                    JOIN users u ON u.id = a.user_id
                    LEFT JOIN (
                        SELECT annotation_id, COUNT(*) AS cnt
                        FROM annotation_replies
                        WHERE deleted_at IS NULL
                        GROUP BY annotation_id
                    ) rc ON rc.annotation_id = a.id
                    WHERE a.document_id = :document_id
                    ORDER BY a.created_at DESC
                    """),
                {"document_id": db_uuid(document_id)},
            ).mappings()
        else:
            rows = self._connection.execute(
                sa.text("""
                    SELECT
                        a.id,
                        a.document_id,
                        a.user_id,
                        u.display_name AS user_display_name,
                        a.text,
                        a.note,
                        a.position,
                        a.is_private,
                        a.created_at,
                        a.updated_at,
                        COALESCE(rc.cnt, 0) AS reply_count
                    FROM annotations a
                    JOIN users u ON u.id = a.user_id
                    LEFT JOIN (
                        SELECT annotation_id, COUNT(*) AS cnt
                        FROM annotation_replies
                        WHERE deleted_at IS NULL
                        GROUP BY annotation_id
                    ) rc ON rc.annotation_id = a.id
                    WHERE a.document_id = :document_id
                      AND (
                          a.is_private = false
                          OR a.user_id = :user_id
                      )
                    ORDER BY a.created_at DESC
                    """),
                {
                    "document_id": db_uuid(document_id),
                    "user_id": db_uuid(user_id),
                },
            ).mappings()
        return [dict(row) for row in rows]

    def create(
        self,
        document_id: UUID,
        user_id: UUID,
        text: str,
        note: str | None = None,
        position: dict[str, Any] | None = None,
        is_private: bool = False,
    ) -> dict[str, Any]:
        """Create a new annotation and return its record."""
        annotation_id = uuid4()
        row = (
            self._connection.execute(
                sa.text("""
                    INSERT INTO annotations (
                        id, document_id, user_id, text, note, position,
                        is_private, created_at, updated_at
                    )
                    VALUES (
                        :id, :document_id, :user_id, :text, :note, :position,
                        :is_private, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    RETURNING id, document_id, user_id, text, note, position,
                              is_private, created_at, updated_at
                    """),
                {
                    "id": db_uuid(annotation_id),
                    "document_id": db_uuid(document_id),
                    "user_id": db_uuid(user_id),
                    "text": text,
                    "note": note,
                    "position": json.dumps(position) if position else None,
                    "is_private": is_private,
                },
            )
            .mappings()
            .first()
        )
        if row is None:
            raise RuntimeError("annotation insert did not persist")
        return dict(row)

    def get_by_id(self, annotation_id: UUID) -> dict[str, Any] | None:
        """Return an annotation by id."""
        row = (
            self._connection.execute(
                sa.text("""
                    SELECT
                        a.id,
                        a.document_id,
                        a.user_id,
                        u.display_name AS user_display_name,
                        a.text,
                        a.note,
                        a.position,
                        a.is_private,
                        a.created_at,
                        a.updated_at
                    FROM annotations a
                    JOIN users u ON u.id = a.user_id
                    WHERE a.id = :id
                    """),
                {"id": db_uuid(annotation_id)},
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None

    def update(
        self,
        annotation_id: UUID,
        text: str | None = None,
        note: str | None = None,
        position: dict[str, Any] | None = None,
        is_private: bool | None = None,
    ) -> None:
        """Update an annotation's fields."""
        fields: list[str] = []
        params: dict[str, Any] = {"id": db_uuid(annotation_id)}

        if text is not None:
            fields.append("text = :text")
            params["text"] = text
        if note is not None:
            fields.append("note = :note")
            params["note"] = note
        if position is not None:
            fields.append("position = :position")
            params["position"] = json.dumps(position)
        if is_private is not None:
            fields.append("is_private = :is_private")
            params["is_private"] = is_private

        if not fields:
            return

        fields.append("updated_at = CURRENT_TIMESTAMP")

        self._connection.execute(
            sa.text(f"""
                UPDATE annotations
                SET {", ".join(fields)}
                WHERE id = :id
                """),
            params,
        )

    def delete(self, annotation_id: UUID) -> None:
        """Hard-delete an annotation."""
        self._connection.execute(
            sa.text("DELETE FROM annotations WHERE id = :id"),
            {"id": db_uuid(annotation_id)},
        )

    def can_modify(
        self,
        annotation_id: UUID,
        user_id: UUID,
        is_admin: bool,
    ) -> bool:
        """Return whether *user_id* can modify or delete the annotation."""
        if is_admin:
            return True
        row = (
            self._connection.execute(
                sa.text("""
                    SELECT user_id FROM annotations
                    WHERE id = :id
                    """),
                {"id": db_uuid(annotation_id)},
            )
            .mappings()
            .first()
        )
        if row is None:
            return False
        return UUID(str(row["user_id"])) == user_id

    # ------------------------------------------------------------------
    # Annotation replies
    # ------------------------------------------------------------------

    def list_replies(self, annotation_id: UUID) -> list[dict[str, Any]]:
        """List non-deleted replies for *annotation_id*."""
        rows = (
            self._connection.execute(
                sa.text("""
                SELECT
                    r.id,
                    r.annotation_id,
                    r.user_id,
                    u.display_name AS user_display_name,
                    r.body,
                    r.created_at,
                    r.edited_at
                FROM annotation_replies r
                JOIN users u ON u.id = r.user_id
                WHERE r.annotation_id = :annotation_id
                  AND r.deleted_at IS NULL
                ORDER BY r.created_at ASC
                """),
                {"annotation_id": db_uuid(annotation_id)},
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    def create_reply(
        self,
        annotation_id: UUID,
        user_id: UUID,
        body: str,
    ) -> dict[str, Any]:
        """Create a reply to an annotation. Returns the reply row."""
        reply_id = uuid4()
        row = (
            self._connection.execute(
                sa.text("""
                    INSERT INTO annotation_replies (id, annotation_id, user_id, body)
                    VALUES (:id, :annotation_id, :user_id, :body)
                    RETURNING id, annotation_id, user_id, body, created_at
                    """),
                {
                    "id": db_uuid(reply_id),
                    "annotation_id": db_uuid(annotation_id),
                    "user_id": db_uuid(user_id),
                    "body": body,
                },
            )
            .mappings()
            .first()
        )
        if row is None:
            raise RuntimeError("reply insert did not persist")
        return dict(row)

    def delete_reply(self, reply_id: UUID) -> None:
        """Soft-delete a reply."""
        self._connection.execute(
            sa.text("""
                UPDATE annotation_replies
                SET deleted_at = CURRENT_TIMESTAMP
                WHERE id = :id AND deleted_at IS NULL
                """),
            {"id": db_uuid(reply_id)},
        )

    def can_modify_reply(
        self,
        reply_id: UUID,
        user_id: UUID,
        is_admin: bool,
    ) -> bool:
        """Return whether *user_id* can delete the reply."""
        if is_admin:
            return True
        row = (
            self._connection.execute(
                sa.text("""
                    SELECT user_id FROM annotation_replies
                    WHERE id = :id AND deleted_at IS NULL
                    """),
                {"id": db_uuid(reply_id)},
            )
            .mappings()
            .first()
        )
        if row is None:
            return False
        return UUID(str(row["user_id"])) == user_id
