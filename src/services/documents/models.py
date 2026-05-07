"""Document persistence models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

DocumentStatus = Literal["pending", "indexed", "deleted", "failed"]
DocumentSource = Literal["folder", "nifi", "confluence", "jira"]


class DocumentRow(BaseModel):
    """Row model for the documents table."""

    id: UUID
    source_id: UUID
    external_id: str
    source: DocumentSource
    path: str | None = None
    mime_type: str
    title: str | None = None
    source_language: str | None = None
    target_language: str = "en"
    translation_quality: str | None = None
    status: DocumentStatus = "pending"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
