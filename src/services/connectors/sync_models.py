"""Sync lifecycle models for canonical connector sync lifecycle (#540).

Defines the state machine, tracking record, tombstone, and source health
structures used across the scheduler, sync-now, and admin API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

# ── Enums ──────────────────────────────────────────────────────────────────

SyncRunStatus = Literal[
    "queued",
    "running",
    "completed",
    "completed_with_warnings",
    "failed",
    "cancelled",
]

SyncMode = Literal["incremental", "full_resync"]


# ── Sync run ───────────────────────────────────────────────────────────────


class SyncRun(BaseModel):
    """Tracks one sync lifecycle from queued through to a terminal state."""

    id: UUID
    source_id: UUID
    connector_type: str
    sync_mode: SyncMode = "incremental"
    status: SyncRunStatus = "queued"
    started_at: datetime
    completed_at: datetime | None = None
    checkpoint: str | None = None
    documents_discovered: int = 0
    documents_created: int = 0
    documents_updated: int = 0
    documents_unchanged: int = 0
    documents_deleted: int = 0
    documents_skipped: int = 0
    documents_failed: int = 0
    error_summary: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SyncRunCreate(BaseModel):
    """Input model for creating a new sync run."""

    source_id: UUID
    connector_type: str
    sync_mode: SyncMode = "incremental"
    checkpoint: str | None = None


class SyncRunUpdate(BaseModel):
    """Mutable fields that can be updated during a sync run's lifetime."""

    status: SyncRunStatus | None = None
    completed_at: datetime | None = None
    checkpoint: str | None = None
    documents_discovered: int | None = None
    documents_created: int | None = None
    documents_updated: int | None = None
    documents_unchanged: int | None = None
    documents_deleted: int | None = None
    documents_skipped: int | None = None
    documents_failed: int | None = None
    error_summary: str | None = None


# ── Tombstone ──────────────────────────────────────────────────────────────


class DocumentTombstone(BaseModel):
    """Records that an upstream document was deleted/tombstoned.

    The underlying documents row is kept (with ``status='deleted'``) so a
    reindex can restore a reappearing upstream item. Removing the document
    from the search/vector indexes is the responsibility of the caller that
    creates the tombstone (see ``tombstone_missing_documents``'s
    ``index_cleanup`` parameter); a tombstone on its own does not hide a
    document from search.
    """

    id: UUID
    source_id: UUID
    version_family_id: UUID | None = None
    external_id: str
    document_id: UUID | None = None
    tombstoned_at: datetime
    reason: str | None = None
    created_at: datetime | None = None


class TombstoneCreate(BaseModel):
    """Input model for creating a tombstone."""

    source_id: UUID
    version_family_id: UUID | None = None
    external_id: str
    document_id: UUID | None = None
    reason: str | None = None


# ── Source health ──────────────────────────────────────────────────────────


class SourceHealth(BaseModel):
    """Read-only source health summary exposed via the admin API."""

    last_sync_status: SyncRunStatus | None = None
    last_successful_sync_at: datetime | None = None
    last_failed_sync_at: datetime | None = None
    last_sync_error: str | None = None
    failure_count: int = 0
    warning_count: int = 0
    last_sync_id: UUID | None = None
    # Forwarded from existing ingestion_sources columns
    last_sync_indexed: int | None = None
    last_sync_skipped: int | None = None
    last_sync_failed: int | None = None
    last_sync_at: datetime | None = None
    last_validation_status: str | None = None
    last_validation_error: str | None = None
    last_validated_at: datetime | None = None


# ── Connector contract extension ───────────────────────────────────────────


class ConnectorSyncResult(BaseModel):
    """Standardised result for a single connector-returned item.

    Connectors that conform to this contract return items that carry enough
    metadata for the sync runner to make idempotent decisions before the
    document is persisted.
    """

    external_id: str
    title: str
    mime_type: str
    content_hash: str | None = Field(default=None, alias="sha256")
    source_language: str | None = None
    last_modified: datetime | None = None
    deletion_marker: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    path: str | None = None
    text_content: str | None = None
    skipped_reason: str | None = None
    error_summary: str | None = None
