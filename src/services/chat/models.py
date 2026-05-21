"""Pydantic models for Document Chat sessions and messages."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class ChatSession(BaseModel):
    """Row model for the chat_sessions table."""

    id: UUID
    user_id: UUID
    title: str = "New Chat"
    scope_type: str
    scope_ids: list[str] = []
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None
    metadata: dict[str, Any] = {}


class ChatSessionCreate(BaseModel):
    """Input model for creating a new chat session."""

    user_id: UUID
    scope_type: str
    scope_ids: list[str] = []
    title: str = "New Chat"


class ChatSessionUpdate(BaseModel):
    """Input model for updating a chat session."""

    title: str | None = None
    archived_at: datetime | None = None


class ChatMessage(BaseModel):
    """Row model for the chat_messages table."""

    id: UUID
    session_id: UUID
    role: str
    content: str
    rewritten_query: str | None = None
    citations: list[dict[str, Any]] = []
    retrieval_trace: dict[str, Any] | None = None
    model: str | None = None
    latency_ms: int | None = None
    created_at: datetime
    metadata: dict[str, Any] = {}


class ChatMessageCreate(BaseModel):
    """Input model for creating a new chat message."""

    session_id: UUID
    role: str
    content: str
    rewritten_query: str | None = None
    citations: list[dict[str, Any]] = []
    retrieval_trace: dict[str, Any] | None = None
    model: str | None = None
    latency_ms: int | None = None
