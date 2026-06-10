"""Citation feedback model and repository."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

import sqlalchemy as sa
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from shared.db import db_uuid, to_uuid

FeedbackType = Literal[
    "correct",
    "wrong_passage",
    "right_document_wrong_location",
    "missing_better_source",
    "unsupported_claim",
    "permission_concern",
    "other",
]


class CitationFeedbackCreate(BaseModel):
    citation_id: str | None = None
    message_id: UUID | None = None
    document_id: UUID
    chunk_id: str | None = None
    feedback_type: FeedbackType
    comment: str | None = None
    user_id: UUID


class CitationFeedback(BaseModel):
    id: UUID
    citation_id: str | None = None
    message_id: UUID | None = None
    document_id: UUID
    chunk_id: str | None = None
    feedback_type: str
    comment: str | None = None
    user_id: UUID
    created_at: datetime


class CitationFeedbackRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def create(self, create: CitationFeedbackCreate) -> CitationFeedback:
        row_id = uuid4()
        now = datetime.now(tz=UTC)
        self._connection.execute(
            sa.text("""
                INSERT INTO citation_feedback
                    (id, citation_id, message_id, document_id, chunk_id,
                     feedback_type, comment, user_id, created_at)
                VALUES
                    (:id, :citation_id, :message_id, :document_id, :chunk_id,
                     :feedback_type, :comment, :user_id, :created_at)
            """),
            {
                "id": db_uuid(row_id),
                "citation_id": create.citation_id,
                "message_id": db_uuid(create.message_id) if create.message_id else None,
                "document_id": db_uuid(create.document_id),
                "chunk_id": create.chunk_id,
                "feedback_type": create.feedback_type,
                "comment": create.comment,
                "user_id": db_uuid(create.user_id),
                "created_at": now,
            },
        )
        return CitationFeedback(
            id=row_id,
            citation_id=create.citation_id,
            message_id=create.message_id,
            document_id=create.document_id,
            chunk_id=create.chunk_id,
            feedback_type=create.feedback_type,
            comment=create.comment,
            user_id=create.user_id,
            created_at=now,
        )

    def list_by_document(
        self,
        document_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CitationFeedback]:
        rows = (
            self._connection.execute(
                sa.text("""
                    SELECT id, citation_id, message_id, document_id, chunk_id,
                           feedback_type, comment, user_id, created_at
                    FROM citation_feedback
                    WHERE document_id = :document_id
                    ORDER BY created_at DESC
                    LIMIT :limit OFFSET :offset
                """),
                {"document_id": db_uuid(document_id), "limit": limit, "offset": offset},
            )
            .mappings()
            .all()
        )
        return [self._row_to_feedback(r) for r in rows]

    def list_by_message(self, message_id: UUID) -> list[CitationFeedback]:
        rows = (
            self._connection.execute(
                sa.text("""
                    SELECT id, citation_id, message_id, document_id, chunk_id,
                           feedback_type, comment, user_id, created_at
                    FROM citation_feedback
                    WHERE message_id = :message_id
                    ORDER BY created_at DESC
                """),
                {"message_id": db_uuid(message_id)},
            )
            .mappings()
            .all()
        )
        return [self._row_to_feedback(r) for r in rows]

    def list_by_feedback_type(
        self,
        feedback_type: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CitationFeedback]:
        rows = (
            self._connection.execute(
                sa.text("""
                    SELECT id, citation_id, message_id, document_id, chunk_id,
                           feedback_type, comment, user_id, created_at
                    FROM citation_feedback
                    WHERE feedback_type = :feedback_type
                    ORDER BY created_at DESC
                    LIMIT :limit OFFSET :offset
                """),
                {"feedback_type": feedback_type, "limit": limit, "offset": offset},
            )
            .mappings()
            .all()
        )
        return [self._row_to_feedback(r) for r in rows]

    @staticmethod
    def _row_to_feedback(row: Any) -> CitationFeedback:
        return CitationFeedback(
            id=to_uuid(row["id"]),
            citation_id=row.get("citation_id"),
            message_id=to_uuid(row["message_id"]) if row.get("message_id") else None,
            document_id=to_uuid(row["document_id"]),
            chunk_id=row.get("chunk_id"),
            feedback_type=row["feedback_type"],
            comment=row.get("comment"),
            user_id=to_uuid(row["user_id"]),
            created_at=row["created_at"],
        )
