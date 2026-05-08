"""Annotation models."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class Annotation(BaseModel):
    """Row model for the annotations table."""

    id: UUID
    doc_id: UUID
    user_id: UUID
    text: str
    note: str | None = None
    position: dict[str, Any] | None = None
    is_private: bool = False
    created_at: datetime
    updated_at: datetime


class AnnotationCreateRequest(BaseModel):
    """Request body for creating an annotation."""

    text: str = Field(..., min_length=1)
    note: str | None = None
    position: dict[str, Any] | None = None
    is_private: bool = False


class AnnotationUpdateRequest(BaseModel):
    """Request body for updating an annotation."""

    text: str | None = None
    note: str | None = None
    position: dict[str, Any] | None = None
    is_private: bool | None = None
