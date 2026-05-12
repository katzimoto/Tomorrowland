"""Database access for document comments."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from shared.db import db_uuid


class CommentRepository:
    """CRUD and queries for document comments."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def list_comments(
        self,
        doc_id: UUID,
        skip: int = 0,
        limit: int = 50,
        sort: str = "newest",
    ) -> list[dict[str, Any]]:
        """List visible comments for a document.

        Excludes soft-deleted comments. Sorts by *sort* (newest or oldest).
        """
        order = "DESC" if sort == "newest" else "ASC"
        rows = self._connection.execute(
            sa.text(
                f"""
                SELECT
                    c.id,
                    c.doc_id,
                    c.author_id,
                    u.display_name AS author_display_name,
                    c.body,
                    c.created_at,
                    c.updated_at,
                    c.edited_at,
                    c.edited_by_id,
                    c.deleted_at,
                    c.deleted_by_id
                FROM document_comments c
                JOIN users u ON u.id = c.author_id
                WHERE c.doc_id = :doc_id
                  AND c.deleted_at IS NULL
                ORDER BY c.created_at {order}, c.updated_at {order}, c.id {order}
                LIMIT :limit
                OFFSET :skip
                """
            ),
            {
                "doc_id": db_uuid(doc_id),
                "limit": limit,
                "skip": skip,
            },
        ).mappings()
        return [dict(row) for row in rows]

    def count_comments(self, doc_id: UUID) -> int:
        """Return the number of visible comments for a document."""
        result = self._connection.execute(
            sa.text(
                """
                SELECT COUNT(*) FROM document_comments
                WHERE doc_id = :doc_id AND deleted_at IS NULL
                """
            ),
            {"doc_id": db_uuid(doc_id)},
        ).scalar_one()
        return int(result)

    def create(
        self,
        doc_id: UUID,
        author_id: UUID,
        body: str,
    ) -> dict[str, Any]:
        """Create a new comment and return its record."""
        comment_id = uuid4()
        now = datetime.now(UTC)
        row = (
            self._connection.execute(
                sa.text(
                    """
                    INSERT INTO document_comments (
                        id, doc_id, author_id, body,
                        created_at, updated_at
                    )
                    VALUES (
                        :id, :doc_id, :author_id, :body,
                        :created_at, :updated_at
                    )
                    RETURNING id, doc_id, author_id, body,
                              created_at, updated_at
                    """
                ),
                {
                    "id": db_uuid(comment_id),
                    "doc_id": db_uuid(doc_id),
                    "author_id": db_uuid(author_id),
                    "body": body,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            .mappings()
            .first()
        )
        if row is None:
            raise RuntimeError("comment insert did not persist")
        return dict(row)

    def get_by_id(self, comment_id: UUID) -> dict[str, Any] | None:
        """Return a comment by id, including soft-deleted."""
        row = (
            self._connection.execute(
                sa.text(
                    """
                    SELECT
                        c.id,
                        c.doc_id,
                        c.author_id,
                        u.display_name AS author_display_name,
                        c.body,
                        c.created_at,
                        c.updated_at,
                        c.edited_at,
                        c.edited_by_id,
                        c.deleted_at,
                        c.deleted_by_id
                    FROM document_comments c
                    JOIN users u ON u.id = c.author_id
                    WHERE c.id = :id
                    """
                ),
                {"id": db_uuid(comment_id)},
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None

    def update(
        self,
        comment_id: UUID,
        body: str,
        edited_by_id: UUID,
    ) -> None:
        """Update a comment body and set edited metadata."""
        self._connection.execute(
            sa.text(
                """
                UPDATE document_comments
                SET body = :body,
                    edited_at = CURRENT_TIMESTAMP,
                    edited_by_id = :edited_by_id,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """
            ),
            {
                "body": body,
                "edited_by_id": db_uuid(edited_by_id),
                "id": db_uuid(comment_id),
            },
        )

    def soft_delete(
        self,
        comment_id: UUID,
        deleted_by_id: UUID,
    ) -> None:
        """Soft-delete a comment."""
        self._connection.execute(
            sa.text(
                """
                UPDATE document_comments
                SET deleted_at = CURRENT_TIMESTAMP,
                    deleted_by_id = :deleted_by_id,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """
            ),
            {
                "deleted_by_id": db_uuid(deleted_by_id),
                "id": db_uuid(comment_id),
            },
        )

    def can_edit(
        self,
        comment_id: UUID,
        user_id: UUID,
        is_admin: bool,
    ) -> bool:
        """Return whether *user_id* can edit the comment."""
        if is_admin:
            return True
        row = (
            self._connection.execute(
                sa.text(
                    """
                    SELECT author_id FROM document_comments
                    WHERE id = :id AND deleted_at IS NULL
                    """
                ),
                {"id": db_uuid(comment_id)},
            )
            .mappings()
            .first()
        )
        if row is None:
            return False
        return UUID(str(row["author_id"])) == user_id

    def can_delete(
        self,
        comment_id: UUID,
        user_id: UUID,
        is_admin: bool,
    ) -> bool:
        """Return whether *user_id* can delete the comment."""
        return self.can_edit(comment_id, user_id, is_admin)
