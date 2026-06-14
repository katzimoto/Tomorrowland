"""Evidence pack request/response models.

Evidence packs are user-owned, durable collections of source-backed evidence
(citations, passages, claims, and notes). Every item is anchored to a document
so that pack reads and exports can be filtered by the caller's *current*
document access — a stored excerpt is never returned once the owner loses access
to its document.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

EvidencePackCreatedFrom = Literal["chat", "search", "agent", "manual"]
EvidencePackItemType = Literal["citation", "passage", "claim", "note"]


class EvidencePackCreateRequest(BaseModel):
    """Request body for creating an evidence pack."""

    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    source_scope: dict[str, Any] | None = None
    created_from: EvidencePackCreatedFrom = "manual"
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidencePackUpdateRequest(BaseModel):
    """Request body for updating an evidence pack's metadata.

    Only provided fields are changed. ``created_from`` and ownership are
    immutable after creation.
    """

    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    source_scope: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class EvidencePackItemCreateRequest(BaseModel):
    """Request body for adding an item to an evidence pack."""

    document_id: UUID
    item_type: EvidencePackItemType = "passage"
    text_excerpt: str = Field(..., min_length=1, max_length=10000)
    chunk_id: str | None = Field(default=None, max_length=255)
    citation_id: str | None = Field(default=None, max_length=255)
    page_number: int | None = Field(default=None, ge=0)
    section_heading: str | None = Field(default=None, max_length=1000)
    translated_text: str | None = Field(default=None, max_length=10000)
    claim: str | None = Field(default=None, max_length=5000)


class EvidencePackItemFromCitationRequest(BaseModel):
    """Request body for adding a pack item from a citation payload.

    Mirrors the fields of :class:`services.rag.models.Citation`. ``chunk_text``
    is stored as the item's ``text_excerpt`` snapshot — only a safe excerpt is
    persisted, never the full document.
    """

    document_id: UUID
    chunk_text: str = Field(..., min_length=1, max_length=10000)
    item_type: EvidencePackItemType = "citation"
    citation_id: str | None = Field(default=None, max_length=255)
    chunk_id: str | None = Field(default=None, max_length=255)
    page_number: int | None = Field(default=None, ge=0)
    section_heading: str | None = Field(default=None, max_length=1000)
    translated_text: str | None = Field(default=None, max_length=10000)
    claim: str | None = Field(default=None, max_length=5000)

    def to_item_request(self) -> EvidencePackItemCreateRequest:
        """Convert the citation payload into a generic item-create request."""
        return EvidencePackItemCreateRequest(
            document_id=self.document_id,
            item_type=self.item_type,
            text_excerpt=self.chunk_text,
            chunk_id=self.chunk_id,
            citation_id=self.citation_id,
            page_number=self.page_number,
            section_heading=self.section_heading,
            translated_text=self.translated_text,
            claim=self.claim,
        )


class EvidencePack(BaseModel):
    """Row model for the evidence_packs table."""

    id: UUID
    owner_user_id: UUID
    title: str
    description: str | None = None
    source_scope: dict[str, Any] | None = None
    created_from: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class EvidencePackItem(BaseModel):
    """Row model for the evidence_pack_items table."""

    id: UUID
    evidence_pack_id: UUID
    document_id: UUID
    item_type: str
    text_excerpt: str
    chunk_id: str | None = None
    citation_id: str | None = None
    page_number: int | None = None
    section_heading: str | None = None
    translated_text: str | None = None
    claim: str | None = None
    created_at: datetime
