"""Document persistence models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

DocumentStatus = Literal["pending", "indexed", "deleted", "failed"]
DocumentSource = Literal["folder", "nifi", "confluence", "jira", "smb"]


class DocumentVersionFamily(BaseModel):
    """Row model for the document_version_families table."""

    id: UUID
    source_id: UUID
    external_id: str
    current_document_id: UUID
    created_at: datetime
    updated_at: datetime


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
    content_sha256: str | None = None
    version_family_id: UUID | None = None
    version_number: int = 1
    is_latest: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


TranslationVersionStatus = Literal["available", "pending", "running", "failed", "canceled"]
TranslationVersionQuality = Literal["fast", "high"]
TranslationVersionRequestType = Literal["ingestion", "manual", "auto_enrich"]


class DocumentTranslationVersion(BaseModel):
    """Row model for the document_translation_versions table."""

    id: UUID
    doc_id: UUID
    version_number: int
    label: str
    source_language: str | None = None
    target_language: str = "en"
    quality: TranslationVersionQuality
    request_type: TranslationVersionRequestType
    status: TranslationVersionStatus
    provider: str | None = None
    requested_by_id: UUID | None = None
    requested_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_summary: str | None = None
    request_note: str | None = None
    source_content_hash: str | None = None
    translated_text: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
