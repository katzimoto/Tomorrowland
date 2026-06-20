from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


def chunk_record_id(document_id: str, chunk_index: int) -> str:
    """Return the Meilisearch primary key for a chunk record.

    Format: doc_{documentId}_chunk_{chunkIndex:04d}
    The zero-padded index preserves lexicographic ordering for debugging.
    """
    return f"doc_{document_id}_chunk_{chunk_index:04d}"


def build_metadata_text(metadata: ChunkMetadata) -> str:
    """Build the full-text catch-all blob from an explicit allowlist.

    Excluded intentionally: path, url, checksum, version, mimeType,
    fileExtension (sensitive, internal, or better as exact filters).
    """
    parts: list[str] = []
    for field in ("file_name", "author", "owner", "project", "workspace", "collection"):
        value = getattr(metadata, field)
        if value:
            parts.append(value)
    for field in ("tags", "labels", "topics"):
        values = getattr(metadata, field)
        if values:
            parts.extend(values)
    return " ".join(parts)


class ChunkPosition(BaseModel):
    chunk_index: int
    page_number: int | None = None
    start_offset: int | None = None
    end_offset: int | None = None


def _iso_to_epoch_seconds(value: str) -> int | None:
    """Parse an ISO date/datetime string to integer epoch seconds (UTC).

    Naive inputs are assumed to be UTC. Returns ``None`` when *value* cannot be
    parsed, so a malformed timestamp never aborts indexing.
    """
    try:
        parsed = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp())


class ChunkMetadata(BaseModel):
    # Source provenance — loosely typed to accommodate connector expansion
    source_id: str | None = None
    source: str | None = None
    document_type: (
        Literal[
            "spec",
            "design",
            "research",
            "prd",
            "notes",
            "transcript",
            "code",
            "unknown",
        ]
        | None
    ) = None
    mime_type: str | None = None
    file_name: str | None = None
    file_extension: str | None = None
    path: str | None = None
    url: str | None = None

    language: str | None = None
    author: str | None = None
    owner: str | None = None

    tags: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)

    project: str | None = None
    workspace: str | None = None
    collection: str | None = None

    created_at: str | None = None
    updated_at: str | None = None
    imported_at: str | None = None

    # Epoch-seconds mirrors of the ISO timestamps above, derived automatically.
    # Meilisearch range filters (>=, <=, TO) operate on numbers only, so
    # date-range search and chronological sort rely on these numeric fields
    # rather than the ISO strings (which are retained for display).
    created_at_ts: int | None = None
    updated_at_ts: int | None = None
    imported_at_ts: int | None = None

    # Internal — stored for dedup/staleness; excluded from filterable and displayed attributes
    version: str | None = None
    checksum: str | None = None

    @model_validator(mode="after")
    def _derive_epoch_timestamps(self) -> ChunkMetadata:
        for iso_field, ts_field in (
            ("created_at", "created_at_ts"),
            ("updated_at", "updated_at_ts"),
            ("imported_at", "imported_at_ts"),
        ):
            if getattr(self, ts_field) is not None:
                continue
            iso = getattr(self, iso_field)
            if iso:
                epoch = _iso_to_epoch_seconds(iso)
                if epoch is not None:
                    setattr(self, ts_field, epoch)
        return self


class SearchChunkRecord(BaseModel):
    """Index record written to Meilisearch. One record per document chunk.

    Primary key: id  (use chunk_record_id() to construct it)
    """

    # --- Identity ---
    id: str  # chunk_record_id(documentId, chunkIndex)
    document_id: str  # parent document UUID as string
    chunk_index: int  # duplicates position.chunk_index for top-level sort

    # --- Content (original language) ---
    title: str
    subtitle: str | None = None
    description: str | None = None
    heading: str | None = None
    section_path: list[str] = Field(default_factory=list)
    content: str
    summary: str | None = None

    # --- Translations (flat, language-suffixed) ---
    # English
    title_en: str | None = None
    content_en: str | None = None
    summary_en: str | None = None
    heading_en: str | None = None
    # Hebrew
    title_he: str | None = None
    content_he: str | None = None
    summary_he: str | None = None
    heading_he: str | None = None

    # --- Position ---
    position: ChunkPosition

    # --- Metadata ---
    metadata: ChunkMetadata = Field(default_factory=ChunkMetadata)

    # --- Full-text catch-all (built by build_metadata_text, not caller-supplied) ---
    metadata_text: str = ""

    # --- Security (required; filtered on every query) ---
    allowed_group_ids: list[str]  # no default — must be set explicitly
    is_admin_only: bool = False

    # --- Indexing provenance ---
    content_checksum: str  # SHA-256 of content; no default — must be set explicitly
    indexed_at: str  # ISO 8601; set by from_parts(), not the caller

    @model_validator(mode="after")
    def _validate_required_security(self) -> SearchChunkRecord:
        if not self.allowed_group_ids and not self.is_admin_only:
            raise ValueError("allowed_group_ids must not be empty unless is_admin_only is True")
        return self

    @staticmethod
    def content_sha256(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    @classmethod
    def from_parts(
        cls,
        *,
        document_id: str,
        chunk_index: int,
        title: str,
        content: str,
        allowed_group_ids: list[str],
        metadata: ChunkMetadata | None = None,
        position_kwargs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> SearchChunkRecord:
        """Construct a record with auto-computed id, contentChecksum, and indexedAt."""
        meta = metadata or ChunkMetadata()
        pos = ChunkPosition(chunk_index=chunk_index, **(position_kwargs or {}))
        return cls(
            id=chunk_record_id(document_id, chunk_index),
            document_id=document_id,
            chunk_index=chunk_index,
            title=title,
            content=content,
            allowed_group_ids=allowed_group_ids,
            metadata=meta,
            metadata_text=build_metadata_text(meta),
            position=pos,
            content_checksum=cls.content_sha256(content),
            indexed_at=datetime.now(UTC).isoformat(),
            **kwargs,
        )


# ---------------------------------------------------------------------------
# Query and result types (used by SearchProvider, not by the indexing pipeline)
# ---------------------------------------------------------------------------


class DocumentSearchFilters(BaseModel):
    source: list[str] = Field(default_factory=list)
    document_type: list[str] = Field(default_factory=list)
    mime_type: list[str] = Field(default_factory=list)
    file_extension: list[str] = Field(default_factory=list)
    language: list[str] = Field(default_factory=list)
    author: list[str] = Field(default_factory=list)
    owner: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    project: list[str] = Field(default_factory=list)
    workspace: list[str] = Field(default_factory=list)
    collection: list[str] = Field(default_factory=list)
    created_after: str | None = None
    created_before: str | None = None
    updated_after: str | None = None
    imported_after: str | None = None


class DocumentSearchQuery(BaseModel):
    q: str
    language: Literal["auto", "en", "he"] = "auto"
    filters: DocumentSearchFilters = Field(default_factory=DocumentSearchFilters)
    sort: Literal["relevance", "updatedAt:desc", "createdAt:desc", "importedAt:desc"] = "relevance"
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class DocumentSearchResultMetadata(BaseModel):
    document_type: str | None = None
    file_name: str | None = None
    source: str | None = None
    language: str | None = None
    tags: list[str] = Field(default_factory=list)
    updated_at: str | None = None
    project: str | None = None
    workspace: str | None = None
    collection: str | None = None


class DocumentSearchResult(BaseModel):
    document_id: str
    chunk_id: str

    title: str
    heading: str | None = None
    section_path: list[str] = Field(default_factory=list)
    snippet: str

    metadata: DocumentSearchResultMetadata = Field(default_factory=DocumentSearchResultMetadata)
    position: ChunkPosition
    score: float | None = None
