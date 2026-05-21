"""Database access for chat sessions and messages."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection, RowMapping

from shared.db import db_uuid, to_uuid

from .models import (
    ChatMessage,
    ChatMessageCreate,
    ChatSession,
    ChatSessionCreate,
    ChatSessionUpdate,
)

_SESSION_COLS = [
    "id",
    "user_id",
    "title",
    "scope_type",
    "scope_ids",
    "created_at",
    "updated_at",
    "archived_at",
    "metadata",
]

_MESSAGE_COLS = [
    "id",
    "session_id",
    "role",
    "content",
    "rewritten_query",
    "citations",
    "retrieval_trace",
    "model",
    "latency_ms",
    "created_at",
    "metadata",
]


class ChatRepository:
    """CRUD for chat sessions and messages."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def create_session(self, create: ChatSessionCreate) -> ChatSession:
        """Create a new chat session."""
        session_id = uuid4()
        now = datetime.now(tz=UTC)
        self._connection.execute(
            sa.text("""
                INSERT INTO chat_sessions
                    (id, user_id, title, scope_type, scope_ids,
                     created_at, updated_at, metadata)
                VALUES
                    (:id, :user_id, :title, :scope_type, :scope_ids,
                     :created_at, :updated_at, :metadata)
                """),
            {
                "id": db_uuid(session_id),
                "user_id": db_uuid(create.user_id),
                "title": create.title,
                "scope_type": create.scope_type,
                "scope_ids": json.dumps(create.scope_ids),
                "created_at": now,
                "updated_at": now,
                "metadata": json.dumps({}),
            },
        )
        return ChatSession(
            id=session_id,
            user_id=create.user_id,
            title=create.title,
            scope_type=create.scope_type,
            scope_ids=create.scope_ids,
            created_at=now,
            updated_at=now,
        )

    def list_sessions(
        self,
        user_id: UUID,
        limit: int = 20,
        offset: int = 0,
        archived: bool = False,
    ) -> tuple[list[ChatSession], int]:
        """List sessions for a user, newest first.

        Returns (sessions, total_count).
        """
        where = "user_id = :user_id"
        params: dict[str, Any] = {"user_id": db_uuid(user_id)}
        if not archived:
            where += " AND archived_at IS NULL"

        count = self._connection.execute(
            sa.text(f"SELECT COUNT(*) FROM chat_sessions WHERE {where}"),
            params,
        ).scalar_one()

        rows = (
            self._connection.execute(
                sa.text(f"""
                    SELECT {", ".join(_SESSION_COLS)}
                    FROM chat_sessions
                    WHERE {where}
                    ORDER BY updated_at DESC
                    LIMIT :limit OFFSET :offset
                    """),
                {**params, "limit": limit, "offset": offset},
            )
            .mappings()
            .all()
        )

        return [self._row_to_session(r) for r in rows], count

    def get_session(
        self,
        user_id: UUID,
        session_id: UUID,
        include_messages: bool = False,
    ) -> ChatSession | None:
        """Get a session by user + session ID."""
        row = (
            self._connection.execute(
                sa.text(f"""
                    SELECT {", ".join(_SESSION_COLS)}
                    FROM chat_sessions
                    WHERE id = :id AND user_id = :user_id
                    """),
                {"id": db_uuid(session_id), "user_id": db_uuid(user_id)},
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        session = self._row_to_session(row)
        if include_messages:
            session.metadata["_messages"] = self._list_messages(session.id)
        return session

    def update_session(
        self,
        user_id: UUID,
        session_id: UUID,
        update: ChatSessionUpdate,
    ) -> ChatSession | None:
        """Update session title and/or archived_at.

        Returns None if the session does not belong to the user.
        """
        now = datetime.now(tz=UTC)
        sets: list[str] = ["updated_at = :updated_at"]
        params: dict[str, Any] = {
            "id": db_uuid(session_id),
            "user_id": db_uuid(user_id),
            "updated_at": now,
        }
        if update.title is not None:
            sets.append("title = :title")
            params["title"] = update.title
        if update.archived_at is not None:
            sets.append("archived_at = :archived_at")
            params["archived_at"] = update.archived_at

        result = self._connection.execute(
            sa.text(f"""
                UPDATE chat_sessions
                SET {", ".join(sets)}
                WHERE id = :id AND user_id = :user_id
                """),
            params,
        )
        if result.rowcount == 0:
            return None
        return self.get_session(user_id, session_id)

    def delete_session(self, user_id: UUID, session_id: UUID) -> bool:
        """Delete a session. Messages cascade via FK.

        Returns True if a row was deleted.
        """
        result = self._connection.execute(
            sa.text("""
                DELETE FROM chat_sessions
                WHERE id = :id AND user_id = :user_id
                """),
            {"id": db_uuid(session_id), "user_id": db_uuid(user_id)},
        )
        return result.rowcount > 0

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def create_message(self, create: ChatMessageCreate) -> ChatMessage:
        """Create a new message in a session.

        Does not validate session ownership — callers should ensure the
        session belongs to the intended user before creating messages.
        """
        message_id = uuid4()
        now = datetime.now(tz=UTC)
        self._connection.execute(
            sa.text("""
                INSERT INTO chat_messages (
                    id, session_id, role, content, rewritten_query,
                    citations, retrieval_trace, model, latency_ms, created_at, metadata
                )
                VALUES (
                    :id, :session_id, :role, :content, :rewritten_query,
                    :citations, :retrieval_trace, :model, :latency_ms, :created_at, :metadata
                )
                """),
            {
                "id": db_uuid(message_id),
                "session_id": db_uuid(create.session_id),
                "role": create.role,
                "content": create.content,
                "rewritten_query": create.rewritten_query,
                "citations": json.dumps(create.citations),
                "retrieval_trace": (
                    json.dumps(create.retrieval_trace)
                    if create.retrieval_trace is not None
                    else None
                ),
                "model": create.model,
                "latency_ms": create.latency_ms,
                "created_at": now,
                "metadata": json.dumps({}),
            },
        )
        return ChatMessage(
            id=message_id,
            session_id=create.session_id,
            role=create.role,
            content=create.content,
            rewritten_query=create.rewritten_query,
            citations=create.citations,
            retrieval_trace=create.retrieval_trace,
            model=create.model,
            latency_ms=create.latency_ms,
            created_at=now,
        )

    def list_messages(self, session_id: UUID) -> list[ChatMessage]:
        """List messages in a session, oldest first."""
        return self._list_messages(session_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _list_messages(self, session_id: UUID) -> list[ChatMessage]:
        rows = (
            self._connection.execute(
                sa.text(f"""
                    SELECT {", ".join(_MESSAGE_COLS)}
                    FROM chat_messages
                    WHERE session_id = :session_id
                    ORDER BY created_at ASC
                    """),
                {"session_id": db_uuid(session_id)},
            )
            .mappings()
            .all()
        )
        return [self._row_to_message(r) for r in rows]

    # ------------------------------------------------------------------
    # Row → model helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json_str(value: object) -> dict[str, Any] | list[dict[str, Any]]:
        if isinstance(value, str) and value:
            return cast("dict[str, Any] | list[dict[str, Any]]", json.loads(value))
        if isinstance(value, dict):
            return cast("dict[str, Any]", value or {})
        if isinstance(value, list):
            return cast("list[dict[str, Any]]", value)
        return {}

    @staticmethod
    def _row_to_session(row: RowMapping) -> ChatSession:
        return ChatSession(
            id=to_uuid(row["id"]),
            user_id=to_uuid(row["user_id"]),
            title=row["title"],
            scope_type=row["scope_type"],
            scope_ids=cast("list[str]", ChatRepository._parse_json_str(row["scope_ids"])),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            archived_at=row.get("archived_at"),
            metadata=cast("dict[str, Any]", ChatRepository._parse_json_str(row["metadata"])),
        )

    @staticmethod
    def _row_to_message(row: RowMapping) -> ChatMessage:
        raw_trace = row.get("retrieval_trace")
        return ChatMessage(
            id=to_uuid(row["id"]),
            session_id=to_uuid(row["session_id"]),
            role=row["role"],
            content=row["content"],
            rewritten_query=row.get("rewritten_query"),
            citations=cast(
                "list[dict[str, Any]]", ChatRepository._parse_json_str(row["citations"])
            ),
            retrieval_trace=cast(
                "dict[str, Any] | None",
                json.loads(raw_trace) if isinstance(raw_trace, str) and raw_trace else raw_trace,
            ),
            model=row.get("model"),
            latency_ms=row.get("latency_ms"),
            created_at=row["created_at"],
            metadata=cast("dict[str, Any]", ChatRepository._parse_json_str(row["metadata"])),
        )
