"""DB repository for sync runs, document tombstones, and source health.

Every public method accepts an ``sa.Connection`` as first argument so it can be
used inside any existing transaction without coupling to a session or engine.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from services.connectors.sync_models import (
    DocumentTombstone,
    SourceHealth,
    SyncMode,
    SyncRun,
    SyncRunCreate,
    SyncRunStatus,
    SyncRunUpdate,
    TombstoneCreate,
)
from shared.db import db_uuid, to_uuid

# ── Status transition validation ─────────────────────────────────────────

VALID_FINAL_STATES: frozenset[SyncRunStatus] = frozenset(
    {
        "completed",
        "completed_with_warnings",
        "failed",
        "cancelled",
    }
)

# Valid transitions: (current_status, new_status) → allowed
_VALID_TRANSITIONS: dict[SyncRunStatus, frozenset[SyncRunStatus]] = {
    "queued": frozenset({"running", "cancelled"}),
    "running": frozenset({"completed", "completed_with_warnings", "failed", "cancelled"}),
    "completed": frozenset(),
    "completed_with_warnings": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}


# ── Sync runs ──────────────────────────────────────────────────────────────


class SyncRunRepository:
    """CRUD for the ``sync_runs`` table."""

    @staticmethod
    def validate_transition(
        current: SyncRunStatus,
        new: SyncRunStatus,
    ) -> None:
        """Raise ValueError if the status transition is not allowed."""
        allowed = _VALID_TRANSITIONS.get(current, frozenset())
        if new not in allowed:
            raise ValueError(
                f"Invalid sync run status transition: {current!r} -> {new!r}. "
                f"Allowed transitions from {current!r}: {sorted(allowed)}"
            )

    @staticmethod
    def is_terminal(status: SyncRunStatus) -> bool:
        """Return True if *status* is a terminal state."""
        return status in VALID_FINAL_STATES

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def create(self, run: SyncRunCreate) -> SyncRun:
        """Insert a queued sync run and return the full record."""
        run_id = uuid4()
        now = datetime.now(UTC)
        self._connection.execute(
            sa.text("""
                INSERT INTO sync_runs
                    (id, source_id, connector_type, sync_mode, status, started_at,
                     checkpoint)
                VALUES
                    (:id, :source_id, :connector_type, :sync_mode, 'queued', :started_at,
                     :checkpoint)
            """),
            {
                "id": db_uuid(run_id),
                "source_id": db_uuid(run.source_id),
                "connector_type": run.connector_type,
                "sync_mode": run.sync_mode,
                "started_at": now,
                "checkpoint": run.checkpoint,
            },
        )
        row = self._get_row_by_id(run_id)
        if row is None:
            raise RuntimeError("sync_run insert did not persist")
        return self._row_to_model(row)

    def start(self, run_id: UUID) -> bool:
        """Transition a queued sync run to running. Returns False if already done."""
        now = datetime.now(UTC)
        result = self._connection.execute(
            sa.text("""
                UPDATE sync_runs
                SET status = 'running', updated_at = :now
                WHERE id = :id AND status = 'queued'
            """),
            {"id": db_uuid(run_id), "now": now},
        )
        return result.rowcount is not None and result.rowcount > 0

    def update(self, run_id: UUID, updates: SyncRunUpdate) -> None:
        """Apply partial updates to a sync run.

        Validates status transitions when the status field is provided.
        """
        # Validate status transition if changing status
        if updates.status is not None:
            current = self.get_by_id(run_id)
            if current is None:
                raise RuntimeError(f"sync_run {run_id} not found for status update")
            self.validate_transition(current.status, updates.status)

        now = datetime.now(UTC)
        fields: list[str] = ["updated_at = :now"]
        params: dict[str, Any] = {"id": db_uuid(run_id), "now": now}

        if updates.status is not None:
            fields.append("status = :status")
            params["status"] = updates.status
        if updates.completed_at is not None:
            fields.append("completed_at = :completed_at")
            params["completed_at"] = updates.completed_at
        if updates.checkpoint is not None:
            fields.append("checkpoint = :checkpoint")
            params["checkpoint"] = updates.checkpoint
        if updates.documents_discovered is not None:
            fields.append("documents_discovered = :documents_discovered")
            params["documents_discovered"] = updates.documents_discovered
        if updates.documents_created is not None:
            fields.append("documents_created = :documents_created")
            params["documents_created"] = updates.documents_created
        if updates.documents_updated is not None:
            fields.append("documents_updated = :documents_updated")
            params["documents_updated"] = updates.documents_updated
        if updates.documents_unchanged is not None:
            fields.append("documents_unchanged = :documents_unchanged")
            params["documents_unchanged"] = updates.documents_unchanged
        if updates.documents_deleted is not None:
            fields.append("documents_deleted = :documents_deleted")
            params["documents_deleted"] = updates.documents_deleted
        if updates.documents_skipped is not None:
            fields.append("documents_skipped = :documents_skipped")
            params["documents_skipped"] = updates.documents_skipped
        if updates.documents_failed is not None:
            fields.append("documents_failed = :documents_failed")
            params["documents_failed"] = updates.documents_failed
        if updates.error_summary is not None:
            fields.append("error_summary = :error_summary")
            params["error_summary"] = updates.error_summary

        set_clause = ", ".join(fields)
        self._connection.execute(
            sa.text(f"UPDATE sync_runs SET {set_clause} WHERE id = :id"),
            params,
        )

    def complete(
        self,
        run_id: UUID,
        status: SyncRunStatus,
        *,
        error_summary: str | None = None,
    ) -> bool:
        """Mark a sync run as finished with a terminal status.

        Only transitions from ``running`` status are accepted.
        Returns False if the sync run was not in a running state.
        """
        if status not in VALID_FINAL_STATES:
            raise ValueError(
                f"{status!r} is not a valid terminal sync run status. "
                f"Expected one of: {sorted(VALID_FINAL_STATES)}"
            )

        now = datetime.now(UTC)
        result = self._connection.execute(
            sa.text("""
                UPDATE sync_runs
                SET status = :status,
                    completed_at = :completed_at,
                    error_summary = COALESCE(:error_summary, error_summary),
                    updated_at = :updated_at
                WHERE id = :id AND status = 'running'
            """),
            {
                "id": db_uuid(run_id),
                "status": status,
                "completed_at": now,
                "error_summary": error_summary,
                "updated_at": now,
            },
        )
        return result.rowcount is not None and result.rowcount > 0

    def get_by_id(self, run_id: UUID) -> SyncRun | None:
        """Return a sync run by primary key."""
        row = self._get_row_by_id(run_id)
        if row is None:
            return None
        return self._row_to_model(row)

    def get_latest_for_source(self, source_id: UUID) -> SyncRun | None:
        """Return the most recent sync run for a source."""
        row = (
            self._connection.execute(
                sa.text("""
                    SELECT * FROM sync_runs
                    WHERE source_id = :source_id
                    ORDER BY started_at DESC
                    LIMIT 1
                """),
                {"source_id": db_uuid(source_id)},
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        return self._row_to_model(row)

    def list_for_source(
        self,
        source_id: UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> list[SyncRun]:
        """List sync runs for a source, most recent first."""
        rows = (
            self._connection.execute(
                sa.text("""
                    SELECT * FROM sync_runs
                    WHERE source_id = :source_id
                    ORDER BY started_at DESC
                    LIMIT :limit OFFSET :offset
                """),
                {
                    "source_id": db_uuid(source_id),
                    "limit": limit,
                    "offset": offset,
                },
            )
            .mappings()
            .all()
        )
        return [self._row_to_model(r) for r in rows]

    def has_active_sync(self, source_id: UUID) -> bool:
        """Return True if the source has a non-terminal (queued/running) sync."""
        row = self._connection.execute(
            sa.text("""
                    SELECT 1 FROM sync_runs
                    WHERE source_id = :source_id
                      AND status NOT IN ('completed', 'completed_with_warnings',
                                         'failed', 'cancelled')
                    LIMIT 1
                """),
            {"source_id": db_uuid(source_id)},
        ).scalar_one_or_none()
        return row is not None

    def list_by_status(self, status: SyncRunStatus, limit: int = 50) -> list[SyncRun]:
        """Return sync runs with a given status."""
        rows = (
            self._connection.execute(
                sa.text("""
                    SELECT * FROM sync_runs
                    WHERE status = :status
                    ORDER BY started_at DESC
                    LIMIT :limit
                """),
                {"status": status, "limit": limit},
            )
            .mappings()
            .all()
        )
        return [self._row_to_model(r) for r in rows]

    def _get_row_by_id(self, run_id: UUID) -> sa.RowMapping | None:
        return (
            self._connection.execute(
                sa.text("SELECT * FROM sync_runs WHERE id = :id"),
                {"id": db_uuid(run_id)},
            )
            .mappings()
            .first()
        )

    @staticmethod
    def _row_to_model(row: sa.RowMapping) -> SyncRun:
        return SyncRun(
            id=to_uuid(row["id"]),
            source_id=to_uuid(row["source_id"]),
            connector_type=str(row["connector_type"]),
            sync_mode=cast("SyncMode", str(row["sync_mode"])),
            status=cast("SyncRunStatus", str(row["status"])),
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            checkpoint=row["checkpoint"],
            documents_discovered=int(row.get("documents_discovered") or 0),
            documents_created=int(row.get("documents_created") or 0),
            documents_updated=int(row.get("documents_updated") or 0),
            documents_unchanged=int(row.get("documents_unchanged") or 0),
            documents_deleted=int(row.get("documents_deleted") or 0),
            documents_skipped=int(row.get("documents_skipped") or 0),
            documents_failed=int(row.get("documents_failed") or 0),
            error_summary=row.get("error_summary"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )


# ── Tombstones ─────────────────────────────────────────────────────────────


class TombstoneRepository:
    """CRUD for the ``document_tombstones`` table."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def create(self, tombstone: TombstoneCreate) -> DocumentTombstone:
        """Insert a tombstone and return the full record."""
        ts_id = uuid4()
        now = datetime.now(UTC)
        self._connection.execute(
            sa.text("""
                INSERT INTO document_tombstones
                    (id, source_id, version_family_id, external_id, document_id,
                     tombstoned_at, reason)
                VALUES
                    (:id, :source_id, :version_family_id, :external_id, :document_id,
                     :tombstoned_at, :reason)
            """),
            {
                "id": db_uuid(ts_id),
                "source_id": db_uuid(tombstone.source_id),
                "version_family_id": (
                    db_uuid(tombstone.version_family_id)
                    if tombstone.version_family_id is not None
                    else None
                ),
                "external_id": tombstone.external_id,
                "document_id": (
                    db_uuid(tombstone.document_id) if tombstone.document_id is not None else None
                ),
                "tombstoned_at": now,
                "reason": tombstone.reason,
            },
        )
        row = self._get_row_by_id(ts_id)
        if row is None:
            raise RuntimeError("tombstone insert did not persist")
        return self._row_to_model(row)

    def is_tombstoned(self, source_id: UUID, external_id: str) -> bool:
        """Return True if an external_id has been tombstoned for this source."""
        row = self._connection.execute(
            sa.text("""
                    SELECT 1 FROM document_tombstones
                    WHERE source_id = :source_id AND external_id = :external_id
                    LIMIT 1
                """),
            {"source_id": db_uuid(source_id), "external_id": external_id},
        ).scalar_one_or_none()
        return row is not None

    def get_by_external_id(self, source_id: UUID, external_id: str) -> DocumentTombstone | None:
        """Return the tombstone for an external_id, if any."""
        row = (
            self._connection.execute(
                sa.text("""
                    SELECT * FROM document_tombstones
                    WHERE source_id = :source_id AND external_id = :external_id
                    LIMIT 1
                """),
                {"source_id": db_uuid(source_id), "external_id": external_id},
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        return self._row_to_model(row)

    def list_for_source(self, source_id: UUID) -> list[DocumentTombstone]:
        """List all tombstones for a source."""
        rows = (
            self._connection.execute(
                sa.text("""
                    SELECT * FROM document_tombstones
                    WHERE source_id = :source_id
                    ORDER BY tombstoned_at DESC
                """),
                {"source_id": db_uuid(source_id)},
            )
            .mappings()
            .all()
        )
        return [self._row_to_model(r) for r in rows]

    def remove(self, source_id: UUID, external_id: str) -> bool:
        """Remove a tombstone by source + external_id. Returns True if deleted."""
        result = self._connection.execute(
            sa.text("""
                DELETE FROM document_tombstones
                WHERE source_id = :source_id AND external_id = :external_id
            """),
            {"source_id": db_uuid(source_id), "external_id": external_id},
        )
        return result.rowcount is not None and result.rowcount > 0

    def remove_by_source(self, source_id: UUID) -> int:
        """Remove all tombstones for a source. Returns count removed."""
        result = self._connection.execute(
            sa.text("""
                DELETE FROM document_tombstones
                WHERE source_id = :source_id
            """),
            {"source_id": db_uuid(source_id)},
        )
        return result.rowcount if result.rowcount is not None else 0

    def _get_row_by_id(self, ts_id: UUID) -> sa.RowMapping | None:
        return (
            self._connection.execute(
                sa.text("SELECT * FROM document_tombstones WHERE id = :id"),
                {"id": db_uuid(ts_id)},
            )
            .mappings()
            .first()
        )

    @staticmethod
    def _row_to_model(row: sa.RowMapping) -> DocumentTombstone:
        return DocumentTombstone(
            id=to_uuid(row["id"]),
            source_id=to_uuid(row["source_id"]),
            version_family_id=(
                to_uuid(row["version_family_id"]) if row["version_family_id"] else None
            ),
            external_id=str(row["external_id"]),
            document_id=to_uuid(row["document_id"]) if row["document_id"] else None,
            tombstoned_at=row["tombstoned_at"],
            reason=row.get("reason"),
            created_at=row.get("created_at"),
        )


# ── Source health helpers ──────────────────────────────────────────────────


def update_source_health(
    connection: Connection,
    source_id: UUID,
    *,
    sync_run_id: UUID | None = None,
    status: SyncRunStatus | None = None,
    error_summary: str | None = None,
) -> None:
    """Update the inlined health columns on ``ingestion_sources``.

    Should be called each time a sync run reaches a terminal state so the
    admin API can read fast health data without a JOIN on sync_runs.
    """
    updates: list[str] = []
    params: dict[str, Any] = {"id": db_uuid(source_id)}

    if sync_run_id is not None:
        updates.append("last_sync_id = :last_sync_id")
        params["last_sync_id"] = db_uuid(sync_run_id)

    if status is not None:
        updates.append("last_sync_status = :last_sync_status")
        params["last_sync_status"] = status

        now = datetime.now(UTC)
        if status == "completed":
            updates.append("last_successful_sync_at = :success_at")
            params["success_at"] = now
        elif status in ("failed", "completed_with_warnings"):
            updates.append("last_failed_sync_at = :fail_at")
            params["fail_at"] = now

        if status == "failed":
            updates.append("failure_count = failure_count + 1")
        elif status == "completed_with_warnings":
            updates.append("warning_count = warning_count + 1")

    if error_summary is not None:
        updates.append("last_sync_error = :last_sync_error")
        params["last_sync_error"] = error_summary

    if updates:
        set_clause = ", ".join(updates)
        connection.execute(
            sa.text(f"UPDATE ingestion_sources SET {set_clause} WHERE id = :id"),
            params,
        )


def get_source_health(connection: Connection, source_id: UUID) -> SourceHealth:
    """Read the current source health from ingestion_sources."""
    row = (
        connection.execute(
            sa.text("""
                SELECT last_sync_status, last_successful_sync_at, last_failed_sync_at,
                       last_sync_error, failure_count, warning_count, last_sync_id,
                       last_sync_indexed, last_sync_skipped, last_sync_failed,
                       last_sync_at, last_validation_status, last_validation_error,
                       last_validated_at
                FROM ingestion_sources
                WHERE id = :id
            """),
            {"id": db_uuid(source_id)},
        )
        .mappings()
        .first()
    )
    if row is None:
        return SourceHealth()
    return SourceHealth(
        last_sync_status=cast("SyncRunStatus | None", row.get("last_sync_status")),
        last_successful_sync_at=row.get("last_successful_sync_at"),
        last_failed_sync_at=row.get("last_failed_sync_at"),
        last_sync_error=row.get("last_sync_error"),
        failure_count=int(row.get("failure_count") or 0),
        warning_count=int(row.get("warning_count") or 0),
        last_sync_id=to_uuid(row["last_sync_id"]) if row.get("last_sync_id") else None,
        last_sync_indexed=row.get("last_sync_indexed"),
        last_sync_skipped=row.get("last_sync_skipped"),
        last_sync_failed=row.get("last_sync_failed"),
        last_sync_at=row.get("last_sync_at"),
        last_validation_status=row.get("last_validation_status"),
        last_validation_error=row.get("last_validation_error"),
        last_validated_at=row.get("last_validated_at"),
    )


# ── Tombstone-aware index cleanup ──────────────────────────────────────────


def _documents_for_source(
    connection: Connection,
    source_id: UUID,
) -> list[dict[str, Any]]:
    """Return (id, external_id, version_family_id) for all docs of a source."""
    rows = (
        connection.execute(
            sa.text("""
                SELECT id, external_id, version_family_id
                FROM documents
                WHERE source_id = :source_id
            """),
            {"source_id": db_uuid(source_id)},
        )
        .mappings()
        .all()
    )
    return [
        {
            "id": to_uuid(r["id"]),
            "external_id": str(r["external_id"]),
            "version_family_id": (
                to_uuid(r["version_family_id"]) if r["version_family_id"] else None
            ),
        }
        for r in rows
    ]


def tombstone_missing_documents(
    connection: Connection,
    source_id: UUID,
    seen_external_ids: set[str],
    *,
    reason: str = "not_found_in_sync",
    index_cleanup: Callable[[UUID], None] | None = None,
) -> list[DocumentTombstone]:
    """Tombstone documents belonging to a source that were NOT seen during sync.

    For full_resync syncs, call this after iterating all connector documents.
    Any document whose ``external_id`` is not in *seen_external_ids* gets a
    tombstone record and its status is set to ``'deleted'``.

    .. important::
        Setting ``status = 'deleted'`` only flags the document in the database;
        keyword (Meilisearch) and vector (Qdrant) search read from their own
        indexes and do **not** filter on document status. To actually hide a
        tombstoned document from search/RAG/researcher/MCP, the caller MUST
        pass *index_cleanup* — a callback invoked with each tombstoned
        ``document_id`` (e.g. wired to ``QdrantSearchClient.delete_by_doc_id``
        and ``MeiliSearchProvider.delete_documents_by_filter``). Without it the
        document remains searchable. Deletion detection is not yet wired into
        the live sync loop; see the #540 follow-up.

    Returns the list of created tombstones.
    """
    repo = TombstoneRepository(connection)
    existing = _documents_for_source(connection, source_id)
    created: list[DocumentTombstone] = []

    for doc in existing:
        if doc["external_id"] not in seen_external_ids:
            # Clear tombstone if one already existed (reappearing doc case is
            # handled by the caller before calling this method)
            if repo.is_tombstoned(source_id, doc["external_id"]):
                # Already tombstoned — skip
                continue

            ts = repo.create(
                TombstoneCreate(
                    source_id=source_id,
                    version_family_id=doc["version_family_id"],
                    external_id=doc["external_id"],
                    document_id=doc["id"],
                    reason=reason,
                )
            )

            # Flag the document as deleted in the DB. NOTE: this alone does not
            # remove it from search — index_cleanup must be supplied for that.
            connection.execute(
                sa.text("UPDATE documents SET status = 'deleted' WHERE id = :id"),
                {"id": db_uuid(doc["id"])},
            )

            # Remove the document from the search indexes so it cannot appear in
            # keyword/vector/RAG/researcher/MCP results.
            if index_cleanup is not None:
                index_cleanup(doc["id"])

            created.append(ts)

    return created


def clear_tombstone_and_reactivate(
    connection: Connection,
    source_id: UUID,
    external_id: str,
) -> bool:
    """Remove a tombstone and mark the document as pending again.

    Returns True if a tombstone was cleared.
    """
    repo = TombstoneRepository(connection)
    ts = repo.get_by_external_id(source_id, external_id)
    if ts is None:
        return False

    # Restore the document from deleted to pending
    if ts.document_id is not None:
        connection.execute(
            sa.text("UPDATE documents SET status = 'pending' WHERE id = :id"),
            {"id": db_uuid(ts.document_id)},
        )

    repo.remove(source_id, external_id)
    return True
