"""Unit tests for the canonical connector sync lifecycle (#540).

Covers SyncRunRepository, TombstoneRepository, source health helpers,
and tombstone-aware index cleanup.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Engine

from services.connectors.sync_models import (
    SyncRunCreate,
    SyncRunUpdate,
    TombstoneCreate,
)
from services.connectors.sync_repository import (
    SyncRunRepository,
    TombstoneRepository,
    clear_tombstone_and_reactivate,
    get_source_health,
    tombstone_missing_documents,
    update_source_health,
)
from shared.db import db_uuid

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _insert_source(engine: Engine, *, source_id: UUID | None = None) -> UUID:
    sid = source_id or uuid4()
    with engine.begin() as connection:
        connection.execute(
            sa.text("""
                INSERT INTO ingestion_sources (id, name, type, source_language)
                VALUES (:id, 'Test Source', 'folder', 'en')
            """),
            {"id": db_uuid(sid)},
        )
    return sid


def _insert_document(
    engine: Engine,
    *,
    source_id: UUID,
    external_id: str = "ext-1",
    doc_id: UUID | None = None,
    status: str = "pending",
) -> UUID:
    did = doc_id or uuid4()
    with engine.begin() as connection:
        connection.execute(
            sa.text("""
                INSERT INTO documents (id, source_id, external_id, source,
                                       mime_type, status)
                VALUES (:id, :source_id, :external_id, 'folder',
                       'text/plain', :status)
            """),
            {
                "id": db_uuid(did),
                "source_id": db_uuid(source_id),
                "external_id": external_id,
                "status": status,
            },
        )
    return did


# ═══════════════════════════════════════════════════════════════════════════════
#  SyncRunRepository
# ═══════════════════════════════════════════════════════════════════════════════


class TestSyncRunRepository:
    """CRUD and state transitions for sync_runs."""

    def test_create_inserts_row(self, migrated_engine: Engine) -> None:
        source_id = _insert_source(migrated_engine)
        with migrated_engine.begin() as connection:
            repo = SyncRunRepository(connection)
            run = repo.create(
                SyncRunCreate(
                    source_id=source_id,
                    connector_type="folder",
                    sync_mode="incremental",
                )
            )

        assert run.source_id == source_id
        assert run.connector_type == "folder"
        assert run.sync_mode == "incremental"
        assert run.status == "queued"
        assert run.started_at is not None
        assert run.completed_at is None
        assert run.id is not None

    def test_create_with_checkpoint(self, migrated_engine: Engine) -> None:
        source_id = _insert_source(migrated_engine)
        with migrated_engine.begin() as connection:
            repo = SyncRunRepository(connection)
            run = repo.create(
                SyncRunCreate(
                    source_id=source_id,
                    connector_type="folder",
                    checkpoint="cursor-42",
                )
            )

        assert run.checkpoint == "cursor-42"

    def test_start_transitions_queued_to_running(self, migrated_engine: Engine) -> None:
        source_id = _insert_source(migrated_engine)
        with migrated_engine.begin() as connection:
            repo = SyncRunRepository(connection)
            run = repo.create(SyncRunCreate(source_id=source_id, connector_type="folder"))
            started = repo.start(run.id)
            fetched = repo.get_by_id(run.id)

        assert started is True
        assert fetched is not None
        assert fetched.status == "running"

    def test_start_on_already_running_returns_false(self, migrated_engine: Engine) -> None:
        source_id = _insert_source(migrated_engine)
        with migrated_engine.begin() as connection:
            repo = SyncRunRepository(connection)
            run = repo.create(SyncRunCreate(source_id=source_id, connector_type="folder"))
            repo.start(run.id)
            second_attempt = repo.start(run.id)

        assert second_attempt is False

    def test_complete_sets_terminal_state(self, migrated_engine: Engine) -> None:
        source_id = _insert_source(migrated_engine)
        with migrated_engine.begin() as connection:
            repo = SyncRunRepository(connection)
            run = repo.create(SyncRunCreate(source_id=source_id, connector_type="folder"))
            repo.start(run.id)
            repo.complete(run.id, "completed")
            fetched = repo.get_by_id(run.id)

        assert fetched is not None
        assert fetched.status == "completed"
        assert fetched.completed_at is not None

    def test_complete_with_error(self, migrated_engine: Engine) -> None:
        source_id = _insert_source(migrated_engine)
        with migrated_engine.begin() as connection:
            repo = SyncRunRepository(connection)
            run = repo.create(SyncRunCreate(source_id=source_id, connector_type="folder"))
            repo.start(run.id)
            repo.complete(run.id, "failed", error_summary="Connection timeout")
            fetched = repo.get_by_id(run.id)

        assert fetched is not None
        assert fetched.status == "failed"
        assert fetched.error_summary == "Connection timeout"

    def test_update_partial_fields(self, migrated_engine: Engine) -> None:
        source_id = _insert_source(migrated_engine)
        with migrated_engine.begin() as connection:
            repo = SyncRunRepository(connection)
            run = repo.create(SyncRunCreate(source_id=source_id, connector_type="folder"))
            repo.start(run.id)

            repo.update(
                run.id,
                SyncRunUpdate(
                    documents_discovered=10,
                    documents_created=7,
                    documents_skipped=2,
                    documents_failed=1,
                    checkpoint="page-3",
                ),
            )
            fetched = repo.get_by_id(run.id)

        assert fetched is not None
        assert fetched.documents_discovered == 10
        assert fetched.documents_created == 7
        assert fetched.documents_skipped == 2
        assert fetched.documents_failed == 1
        assert fetched.checkpoint == "page-3"
        # Unset fields should remain at default
        assert fetched.documents_updated == 0
        assert fetched.documents_deleted == 0

    def test_complete_updates_counts(self, migrated_engine: Engine) -> None:
        """complete() sets terminal status; item counts come via update()."""
        source_id = _insert_source(migrated_engine)
        with migrated_engine.begin() as connection:
            repo = SyncRunRepository(connection)
            run = repo.create(SyncRunCreate(source_id=source_id, connector_type="folder"))
            repo.start(run.id)
            repo.update(
                run.id,
                SyncRunUpdate(documents_discovered=5, documents_created=3, documents_skipped=2),
            )
            repo.complete(run.id, "completed_with_warnings", error_summary="3/5 indexed")
            fetched = repo.get_by_id(run.id)

        assert fetched is not None
        assert fetched.status == "completed_with_warnings"
        assert fetched.documents_discovered == 5
        assert fetched.documents_created == 3
        assert fetched.error_summary == "3/5 indexed"

    def test_get_by_id_missing(self, migrated_engine: Engine) -> None:
        with migrated_engine.begin() as connection:
            repo = SyncRunRepository(connection)
            result = repo.get_by_id(uuid4())
        assert result is None

    def test_get_latest_for_source(self, migrated_engine: Engine) -> None:
        """get_latest_for_source returns the most recently created sync run."""
        source_id = _insert_source(migrated_engine)
        with migrated_engine.begin() as connection:
            repo = SyncRunRepository(connection)
            repo.create(SyncRunCreate(source_id=source_id, connector_type="folder"))
            second = repo.create(SyncRunCreate(source_id=source_id, connector_type="folder"))
            latest = repo.get_latest_for_source(source_id)

        assert latest is not None
        # Most recently created comes first with ORDER BY started_at DESC
        assert latest.id == second.id

    def test_list_for_source_pagination(self, migrated_engine: Engine) -> None:
        source_id = _insert_source(migrated_engine)
        with migrated_engine.begin() as connection:
            repo = SyncRunRepository(connection)
            # Create 3 runs (reverse order is most-recent-first)
            ids: list[UUID] = []
            for _ in range(3):
                run = repo.create(SyncRunCreate(source_id=source_id, connector_type="folder"))
                ids.append(run.id)

            page1 = repo.list_for_source(source_id, limit=2, offset=0)
            page2 = repo.list_for_source(source_id, limit=2, offset=2)

        assert len(page1) == 2
        assert len(page2) == 1
        # Most recent first — last created is top
        assert page1[0].id == ids[2]
        assert page1[1].id == ids[1]
        assert page2[0].id == ids[0]

    def test_list_by_status(self, migrated_engine: Engine) -> None:
        source_id = _insert_source(migrated_engine)
        with migrated_engine.begin() as connection:
            repo = SyncRunRepository(connection)
            # Create one completed and one failed
            run_done = repo.create(SyncRunCreate(source_id=source_id, connector_type="folder"))
            repo.start(run_done.id)
            repo.complete(run_done.id, "completed")

            run_fail = repo.create(SyncRunCreate(source_id=source_id, connector_type="folder"))
            repo.start(run_fail.id)
            repo.complete(run_fail.id, "failed")

            failed_runs = repo.list_by_status("failed")
            completed_runs = repo.list_by_status("completed")
            queued_runs = repo.list_by_status("queued")

        assert len(failed_runs) == 1
        assert failed_runs[0].id == run_fail.id
        assert len(completed_runs) == 1
        assert completed_runs[0].id == run_done.id
        assert len(queued_runs) == 0  # all were started


# ═══════════════════════════════════════════════════════════════════════════════
#  TombstoneRepository
# ═══════════════════════════════════════════════════════════════════════════════


class TestTombstoneRepository:
    """CRUD for document tombstones."""

    def test_create_and_get(self, migrated_engine: Engine) -> None:
        source_id = _insert_source(migrated_engine)
        doc_id = _insert_document(migrated_engine, source_id=source_id)

        with migrated_engine.begin() as connection:
            repo = TombstoneRepository(connection)
            ts = repo.create(
                TombstoneCreate(
                    source_id=source_id,
                    external_id="ext-1",
                    document_id=doc_id,
                    reason="not_found_in_sync",
                )
            )

        assert ts.source_id == source_id
        assert ts.external_id == "ext-1"
        assert ts.document_id == doc_id
        assert ts.reason == "not_found_in_sync"
        assert ts.id is not None
        assert ts.tombstoned_at is not None

        # Fetch back
        with migrated_engine.connect() as connection:
            repo = TombstoneRepository(connection)
            fetched = repo.get_by_external_id(source_id, "ext-1")

        assert fetched is not None
        assert fetched.id == ts.id

    def test_is_tombstoned(self, migrated_engine: Engine) -> None:
        source_id = _insert_source(migrated_engine)

        with migrated_engine.begin() as connection:
            repo = TombstoneRepository(connection)
            repo.create(TombstoneCreate(source_id=source_id, external_id="gone-1"))

        with migrated_engine.begin() as connection:
            repo = TombstoneRepository(connection)
            assert repo.is_tombstoned(source_id, "gone-1") is True
            assert repo.is_tombstoned(source_id, "still-here") is False

    def test_remove_single_tombstone(self, migrated_engine: Engine) -> None:
        source_id = _insert_source(migrated_engine)

        with migrated_engine.begin() as connection:
            repo = TombstoneRepository(connection)
            repo.create(TombstoneCreate(source_id=source_id, external_id="gone-1"))

        with migrated_engine.begin() as connection:
            repo = TombstoneRepository(connection)
            removed = repo.remove(source_id, "gone-1")
            assert removed is True
            assert repo.is_tombstoned(source_id, "gone-1") is False

    def test_remove_nonexistent_returns_false(self, migrated_engine: Engine) -> None:
        source_id = _insert_source(migrated_engine)
        with migrated_engine.begin() as connection:
            repo = TombstoneRepository(connection)
            assert repo.remove(source_id, "never-existed") is False

    def test_remove_by_source(self, migrated_engine: Engine) -> None:
        source_id = _insert_source(migrated_engine)

        with migrated_engine.begin() as connection:
            repo = TombstoneRepository(connection)
            repo.create(TombstoneCreate(source_id=source_id, external_id="a"))
            repo.create(TombstoneCreate(source_id=source_id, external_id="b"))

        with migrated_engine.begin() as connection:
            repo = TombstoneRepository(connection)
            count = repo.remove_by_source(source_id)
            assert count == 2

    def test_list_for_source(self, migrated_engine: Engine) -> None:
        source_id = _insert_source(migrated_engine)
        source_id_2 = _insert_source(migrated_engine)

        with migrated_engine.begin() as connection:
            repo = TombstoneRepository(connection)
            repo.create(TombstoneCreate(source_id=source_id, external_id="a"))
            repo.create(TombstoneCreate(source_id=source_id, external_id="b"))
            repo.create(TombstoneCreate(source_id=source_id_2, external_id="c"))

        with migrated_engine.begin() as connection:
            repo = TombstoneRepository(connection)
            tombstones = repo.list_for_source(source_id)
            assert len(tombstones) == 2
            assert {ts.external_id for ts in tombstones} == {"a", "b"}


# ═══════════════════════════════════════════════════════════════════════════════
#  Source health helpers
# ═══════════════════════════════════════════════════════════════════════════════


class TestSourceHealth:
    """update_source_health and get_source_health."""

    def test_update_completed_status(self, migrated_engine: Engine) -> None:
        source_id = _insert_source(migrated_engine)
        sync_run_id = uuid4()

        with migrated_engine.begin() as connection:
            update_source_health(
                connection,
                source_id,
                sync_run_id=sync_run_id,
                status="completed",
            )

        with migrated_engine.connect() as connection:
            health = get_source_health(connection, source_id)

        assert health.last_sync_status == "completed"
        assert health.last_successful_sync_at is not None
        assert health.last_failed_sync_at is None
        assert health.last_sync_id == sync_run_id
        assert health.failure_count == 0
        assert health.warning_count == 0

    def test_update_failed_status(self, migrated_engine: Engine) -> None:
        source_id = _insert_source(migrated_engine)

        with migrated_engine.begin() as connection:
            update_source_health(
                connection,
                source_id,
                status="failed",
                error_summary="Timeout",
            )

        with migrated_engine.begin() as connection:
            # Second failure to test increment
            update_source_health(
                connection,
                source_id,
                status="failed",
                error_summary="Timeout again",
            )

        with migrated_engine.connect() as connection:
            health = get_source_health(connection, source_id)

        assert health.last_sync_status == "failed"
        assert health.last_successful_sync_at is None
        assert health.last_failed_sync_at is not None
        assert health.last_sync_error == "Timeout again"
        assert health.failure_count == 2  # incremented twice

    def test_update_completed_with_warnings(self, migrated_engine: Engine) -> None:
        source_id = _insert_source(migrated_engine)

        with migrated_engine.begin() as connection:
            update_source_health(connection, source_id, status="completed_with_warnings")
            update_source_health(connection, source_id, status="completed_with_warnings")

        with migrated_engine.connect() as connection:
            health = get_source_health(connection, source_id)

        assert health.last_sync_status == "completed_with_warnings"
        assert health.warning_count == 2

    def test_get_health_for_missing_source(self, migrated_engine: Engine) -> None:
        with migrated_engine.connect() as connection:
            health = get_source_health(connection, uuid4())

        # Should return empty health, not throw
        assert health.last_sync_status is None
        assert health.failure_count == 0
        assert health.warning_count == 0

    def test_health_does_not_overwrite_existing_success_at(self, migrated_engine: Engine) -> None:
        """A subsequent failure must not clear last_successful_sync_at."""
        source_id = _insert_source(migrated_engine)

        with migrated_engine.begin() as connection:
            update_source_health(connection, source_id, status="completed")

        time_before = datetime.now(UTC) - timedelta(seconds=1)

        with migrated_engine.begin() as connection:
            update_source_health(connection, source_id, status="failed")

        with migrated_engine.connect() as connection:
            health = get_source_health(connection, source_id)

        assert health.last_sync_status == "failed"
        assert health.last_successful_sync_at is not None
        assert health.last_successful_sync_at > time_before  # not cleared


# ═══════════════════════════════════════════════════════════════════════════════
#  Tombstone-aware index cleanup
# ═══════════════════════════════════════════════════════════════════════════════


class TestTombstoneCleanup:
    """tombstone_missing_documents and clear_tombstone_and_reactivate."""

    def test_tombstones_unseen_documents(self, migrated_engine: Engine) -> None:
        source_id = _insert_source(migrated_engine)
        _insert_document(migrated_engine, source_id=source_id, external_id="seen")
        _insert_document(migrated_engine, source_id=source_id, external_id="gone")

        seen: set[str] = {"seen"}

        with migrated_engine.begin() as connection:
            tombstones = tombstone_missing_documents(
                connection, source_id, seen, reason="not_found_in_sync"
            )

        assert len(tombstones) == 1
        assert tombstones[0].external_id == "gone"
        assert tombstones[0].reason == "not_found_in_sync"

        # Document should be marked as deleted
        with migrated_engine.connect() as connection:
            status_row = connection.execute(
                sa.text("SELECT status FROM documents WHERE external_id = 'gone'")
            ).scalar_one()
            assert status_row == "deleted"

    def test_seen_documents_not_tombstoned(self, migrated_engine: Engine) -> None:
        source_id = _insert_source(migrated_engine)
        _insert_document(migrated_engine, source_id=source_id, external_id="a")
        _insert_document(migrated_engine, source_id=source_id, external_id="b")

        seen: set[str] = {"a", "b"}

        with migrated_engine.begin() as connection:
            tombstones = tombstone_missing_documents(connection, source_id, seen)

        assert len(tombstones) == 0

    def test_empty_source_no_tombstones(self, migrated_engine: Engine) -> None:
        source_id = _insert_source(migrated_engine)

        with migrated_engine.begin() as connection:
            tombstones = tombstone_missing_documents(connection, source_id, set())

        assert len(tombstones) == 0

    def test_already_tombstoned_document_skipped(self, migrated_engine: Engine) -> None:
        """If a doc was already tombstoned in a previous sync, skip it."""
        source_id = _insert_source(migrated_engine)
        doc_id = _insert_document(migrated_engine, source_id=source_id, external_id="gone")

        # Pre-create a tombstone
        with migrated_engine.begin() as connection:
            repo = TombstoneRepository(connection)
            repo.create(
                TombstoneCreate(
                    source_id=source_id,
                    external_id="gone",
                    document_id=doc_id,
                )
            )

        seen: set[str] = set()  # "gone" is not seen
        with migrated_engine.begin() as connection:
            tombstones = tombstone_missing_documents(connection, source_id, seen)

        # Should not create a duplicate tombstone
        assert len(tombstones) == 0

    def test_clear_and_reactivate(self, migrated_engine: Engine) -> None:
        source_id = _insert_source(migrated_engine)
        doc_id = _insert_document(
            migrated_engine, source_id=source_id, external_id="gone", status="deleted"
        )

        with migrated_engine.begin() as connection:
            repo = TombstoneRepository(connection)
            repo.create(
                TombstoneCreate(
                    source_id=source_id,
                    external_id="gone",
                    document_id=doc_id,
                )
            )

        with migrated_engine.begin() as connection:
            cleared = clear_tombstone_and_reactivate(connection, source_id, "gone")

        assert cleared is True

        # Document should be restored to pending
        with migrated_engine.connect() as connection:
            status = connection.execute(
                sa.text("SELECT status FROM documents WHERE id = :id"),
                {"id": db_uuid(doc_id)},
            ).scalar_one()
            assert status == "pending"

            repo = TombstoneRepository(connection)
            assert repo.is_tombstoned(source_id, "gone") is False

    def test_clear_nonexistent_tombstone(self, migrated_engine: Engine) -> None:
        source_id = _insert_source(migrated_engine)

        with migrated_engine.begin() as connection:
            cleared = clear_tombstone_and_reactivate(connection, source_id, "never-tombstoned")

        assert cleared is False


# ═══════════════════════════════════════════════════════════════════════════════
#  Full lifecycle integration
# ═══════════════════════════════════════════════════════════════════════════════


class TestFullSyncLifecycle:
    """End-to-end scenario that combines multiple components."""

    def test_incremental_sync_idempotency(self, migrated_engine: Engine) -> None:
        """Simulating: first sync creates, repeat sync with same docs unchanged."""
        source_id = _insert_source(migrated_engine)

        # First sync: create sync run
        with migrated_engine.begin() as connection:
            repo = SyncRunRepository(connection)
            run = repo.create(SyncRunCreate(source_id=source_id, connector_type="folder"))
            repo.start(run.id)
            repo.update(
                run.id,
                SyncRunUpdate(
                    documents_discovered=3,
                    documents_created=3,
                ),
            )
            repo.complete(run.id, "completed")

        # Verify first sync created records
        with migrated_engine.connect() as connection:
            repo = SyncRunRepository(connection)
            latest = repo.get_latest_for_source(source_id)
            assert latest is not None
            assert latest.documents_discovered == 3
            assert latest.documents_created == 3

        # Second sync: same docs unchanged
        with migrated_engine.begin() as connection:
            repo = SyncRunRepository(connection)
            run2 = repo.create(SyncRunCreate(source_id=source_id, connector_type="folder"))
            repo.start(run2.id)
            repo.update(
                run2.id,
                SyncRunUpdate(
                    documents_discovered=3,
                    documents_created=0,
                    documents_unchanged=3,
                ),
            )
            repo.complete(run2.id, "completed")

        with migrated_engine.connect() as connection:
            repo = SyncRunRepository(connection)
            runs = repo.list_for_source(source_id, limit=10)
            assert len(runs) == 2
            assert runs[0].documents_unchanged == 3
            assert runs[0].documents_created == 0

    def test_full_resync_detects_deletions(self, migrated_engine: Engine) -> None:
        """Full resync: documents not seen get tombstoned."""
        source_id = _insert_source(migrated_engine)
        _insert_document(migrated_engine, source_id=source_id, external_id="keep-me")
        _insert_document(migrated_engine, source_id=source_id, external_id="delete-me")

        with migrated_engine.begin() as connection:
            tombstones = tombstone_missing_documents(
                connection,
                source_id,
                seen_external_ids={"keep-me"},
                reason="removed_in_full_resync",
            )

        assert len(tombstones) == 1
        assert tombstones[0].external_id == "delete-me"

        # Verify tombstone persisted
        with migrated_engine.connect() as connection:
            repo = TombstoneRepository(connection)
            assert repo.is_tombstoned(source_id, "delete-me") is True

    def test_reappearing_document_clears_tombstone(self, migrated_engine: Engine) -> None:
        """Document that was missing then reappears clears its tombstone."""
        source_id = _insert_source(migrated_engine)
        doc_id = _insert_document(
            migrated_engine,
            source_id=source_id,
            external_id="comes-back",
            status="deleted",
        )

        # Pre-existing tombstone
        with migrated_engine.begin() as connection:
            repo = TombstoneRepository(connection)
            repo.create(
                TombstoneCreate(
                    source_id=source_id,
                    external_id="comes-back",
                    document_id=doc_id,
                )
            )

        # Clear it (simulating reappearance)
        with migrated_engine.begin() as connection:
            cleared = clear_tombstone_and_reactivate(connection, source_id, "comes-back")

        assert cleared is True

        with migrated_engine.connect() as connection:
            status = connection.execute(
                sa.text("SELECT status FROM documents WHERE id = :id"),
                {"id": db_uuid(doc_id)},
            ).scalar_one()
            assert status == "pending"

    def test_source_health_tracks_sync_run(self, migrated_engine: Engine) -> None:
        """Source health reflects the latest sync outcome."""
        source_id = _insert_source(migrated_engine)
        sync_run_id = uuid4()

        with migrated_engine.begin() as connection:
            update_source_health(
                connection,
                source_id,
                sync_run_id=sync_run_id,
                status="completed",
            )

        with migrated_engine.connect() as connection:
            health = get_source_health(connection, source_id)

        assert health.last_sync_status == "completed"
        assert health.last_sync_id == sync_run_id
        assert health.failure_count == 0


# ═══════════════════════════════════════════════════════════════════════════════
#  ConnectorSyncResult validation
# ═══════════════════════════════════════════════════════════════════════════════


class TestConnectorSyncResult:
    """Structural validation of the ConnectorSyncResult model."""

    def test_holds_required_fields(self) -> None:
        from services.connectors.sync_models import ConnectorSyncResult

        item = ConnectorSyncResult(
            external_id="ext-1",
            title="My Document",
            mime_type="text/plain",
        )

        assert item.external_id == "ext-1"
        assert item.title == "My Document"
        assert item.mime_type == "text/plain"
        assert item.content_hash is None
        assert item.deletion_marker is False
        assert item.metadata == {}
        assert item.skipped_reason is None

    def test_content_hash_alias(self) -> None:
        from services.connectors.sync_models import ConnectorSyncResult

        item = ConnectorSyncResult(
            external_id="ext-1",
            title="Doc",
            mime_type="text/plain",
            sha256="abc123",  # via alias
        )

        assert item.content_hash == "abc123"

    def test_deletion_marker(self) -> None:
        from services.connectors.sync_models import ConnectorSyncResult

        item = ConnectorSyncResult(
            external_id="ext-1",
            title="Deleted Doc",
            mime_type="text/plain",
            deletion_marker=True,
        )

        assert item.deletion_marker is True

    def test_metadata_dict(self) -> None:
        from services.connectors.sync_models import ConnectorSyncResult

        item = ConnectorSyncResult(
            external_id="ext-1",
            title="Doc",
            mime_type="text/plain",
            metadata={"space": "ENG", "page_id": "123"},
        )

        assert item.metadata == {"space": "ENG", "page_id": "123"}
