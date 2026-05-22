"""Annotation models."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class Annotation(BaseModel):
    """Row model for the annotations table."""

    id: UUID
    document_id: UUID
    user_id: UUID
    text: str
    note: str | None = None
    position: dict[str, Any] | None = None
    is_private: bool = False
    created_at: datetime
    updated_at: datetime


class AnnotationCreateRequest(BaseModel):
    """Request body for creating an annotation."""

    text: str = Field(..., min_length=1, max_length=5000)
    note: str | None = Field(default=None, max_length=2000)
    position: dict[str, Any] | None = None
    is_private: bool = False


class AnnotationUpdateRequest(BaseModel):
    """Request body for updating an annotation."""

    text: str | None = Field(default=None, min_length=1, max_length=5000)
    note: str | None = Field(default=None, max_length=2000)
    position: dict[str, Any] | None = None
    is_private: bool | None = None


class AnnotationReply(BaseModel):
    """Row model for the annotation_replies table."""

    id: UUID
    annotation_id: UUID
    user_id: UUID
    body: str
    created_at: datetime
    edited_at: datetime | None = None
    deleted_at: datetime | None = None


class AnnotationReplyCreateRequest(BaseModel):
    """Request body for creating an annotation reply."""

    body: str = Field(..., min_length=1, max_length=5000)
