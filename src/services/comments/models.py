"""Document comment models."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentComment(BaseModel):
    """Row model for the document_comments table."""

    id: UUID
    doc_id: UUID
    author_id: UUID
    body: str
    created_at: datetime
    updated_at: datetime
    edited_at: datetime | None = None
    edited_by_id: UUID | None = None
    deleted_at: datetime | None = None
    deleted_by_id: UUID | None = None


class CommentCreateRequest(BaseModel):
    """Request body for creating a comment."""

    body: str = Field(..., min_length=1)


class CommentUpdateRequest(BaseModel):
    """Request body for updating a comment."""

    body: str = Field(..., min_length=1)
