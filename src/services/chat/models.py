"""Pydantic models for Document Chat sessions and messages."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, model_validator

ScopeType = Literal[
    "all_accessible_documents",
    "single_document",
    "selected_documents",
    "source",
    "folder",
    "current_search_results",
]


class ChatScope(BaseModel):
    """Validated scope for a chat session's retrieval filter."""

    scope_type: ScopeType
    scope_ids: list[str] = []

    @model_validator(mode="after")
    def _validate_cardinality(self) -> ChatScope:
        st = self.scope_type
        if st == "all_accessible_documents" and self.scope_ids:
            raise ValueError("scope_ids must be empty for all_accessible_documents")
        if st == "single_document" and len(self.scope_ids) != 1:
            raise ValueError("single_document scope requires exactly one scope_id")
        multi_scope = ("selected_documents", "current_search_results", "source", "folder")
        if st in multi_scope and not self.scope_ids:
            raise ValueError(f"{st} scope requires at least one scope_id")
        return self


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
