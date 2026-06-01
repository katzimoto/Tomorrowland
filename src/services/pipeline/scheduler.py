"""Cron-based ingestion source scheduler.

Polls ingestion_sources for non-null ``schedule`` values and triggers
sync when the cron expression matches the current minute.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from services.api._helpers import _record_source_sync_state, _sanitize_source_error
from services.connectors.factory import build_connector
from services.connectors.sync_models import SyncRunCreate, SyncRunUpdate
from services.connectors.sync_repository import SyncRunRepository
from services.documents.models import DocumentSource
from services.documents.repository import DocumentRepository
from services.pipeline.jobs import PipelineJobRepository
from services.pipeline.original_store import move_to_originals
from shared.config import Settings
from shared.db import db_uuid

logger = logging.getLogger(__name__)

_FIELD_RANGES: dict[int, tuple[int, int]] = {
    0: (0, 59),
    1: (0, 23),
    2: (1, 31),
    3: (1, 12),
    4: (0, 7),
}


def _cron_matches(expression: str, now: datetime) -> bool:
    """Return True if *expression* matches *now*.

    Supports standard 5-field cron: ``minute hour day month weekday``.
    Wildcards (``*``), lists (``1,3,5``), step values (``*/6``),
    and ranges (``1-5``) are supported.
    """
    fields = expression.strip().split()
    if len(fields) != 5:
        return False

    current = [
        now.minute,
        now.hour,
        now.day,
        now.month,
        (now.weekday() + 1) % 7,
    ]

    for idx, field in enumerate(fields):
        try:
            values = _expand_field(field, *_FIELD_RANGES[idx])
        except (ValueError, IndexError):
            return False
        if current[idx] not in values:
            return False

    return True


def _expand_field(field: str, lo: int, hi: int) -> set[int]:
    """Expand a single cron field into the set of matching values."""
    if field == "*":
        return set(range(lo, hi + 1))

    values: set[int] = set()
    for part in field.split(","):
        step = 1
        if "/" in part:
            part, step_str = part.split("/", 1)
            step = int(step_str)

        if "-" in part:
            start_str, end_str = part.split("-", 1)
            start, end = int(start_str), int(end_str)
        elif part == "*":
            start, end = lo, hi
        else:
            start = end = int(part)

        for v in range(start, end + 1, step):
            if lo <= v <= hi:
                values.add(v)

    return values


def _publish_scheduled_rabbit_messages(
    engine: Engine,
    settings: Settings,
    pending: list[dict[str, Any]],
    rabbit: Any | None = None,
) -> Any | None:
    """Publish pipeline-job queue messages for a completed scheduled sync.

    Mirrors the post-commit publish in the ``sync-now`` API route.  The DB
    transaction commits before this call so workers can see the
    ``pipeline_jobs`` rows as soon as the message arrives on the queue.

    When *rabbit* is None a new connection is created; callers that process
    multiple sources in a tick should pass a shared client to avoid
    connection churn.

    Returns the RabbitClient so callers can reuse it across invocations.
    """
    from shared.rabbit import RabbitClient, RabbitConnectionError

    if rabbit is None:
        rabbit = RabbitClient(settings.rabbitmq_url, enabled=True)
    try:
        rabbit.connect()
        rabbit.declare_topology()
    except RabbitConnectionError:
        logger.warning(
            "RabbitMQ unreachable — %d scheduled sync job(s) not published to queue; "
            "poll-mode workers will still pick them up via pipeline_jobs",
            len(pending),
        )
        return rabbit

    message_ids: dict[str, str] = {}
    with engine.begin() as conn:
        pub_repo = PipelineJobRepository(conn)
        for p in pending:
            mid = str(uuid4())
            message_ids[str(p["job_id"])] = mid
            pub_repo.set_rabbit_message_id(p["job_id"], mid)

    for p in pending:
        body: dict[str, Any] = {
            "job_id": str(p["job_id"]),
            "document_id": str(p["document_id"]),
            "source_id": str(p["source_id"]),
            "attempt": 1,
            "pipeline_version": "v1",
        }
        if p.get("content_text"):
            body["content_text"] = p["content_text"]
        rabbit.publish_with_id("document.parse.requested", body, message_ids[str(p["job_id"])])

    return rabbit


def _sync_source(
    connection: sa.Connection,
    source_row: sa.RowMapping,
    source_id: UUID,
    files_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Run a single source sync, mirroring sync-now logic.

    Returns a list of pending RabbitMQ message descriptors for the caller
    to publish after the DB transaction commits.
    """
    doc_repo = DocumentRepository(connection)
    job_repo = PipelineJobRepository(connection)
    sync_repo = SyncRunRepository(connection)
    pending_rabbit: list[dict[str, Any]] = []

    # Guard against concurrent syncs for scheduled sources
    if sync_repo.has_active_sync(source_id):
        logger.warning(
            "scheduled sync skipped source_id=%s — active sync already in progress",
            source_id,
        )
        return pending_rabbit

    # Create and start a sync run
    connector_type = str(source_row["type"])
    sync_run = sync_repo.create(
        SyncRunCreate(
            source_id=source_id,
            connector_type=connector_type,
            sync_mode="incremental",
        )
    )
    sync_run_id = sync_run.id
    sync_repo.start(sync_run_id)

    source_language = source_row.get("source_language")

    def _fail_sync(error: str) -> None:
        if not sync_repo.complete(sync_run_id, "failed", error_summary=error):
            logger.warning(
                "sync_run %s was not in running state when failing — skipping completion",
                sync_run_id,
            )
        _record_source_sync_state(
            connection,
            source_id,
            status="failed",
            failed=1,
            error=error,
            sync_run_id=sync_run_id,
        )

    try:
        connector = build_connector(source_row)
    except ValueError as exc:
        _fail_sync(_sanitize_source_error(str(exc), source_row))
        return pending_rabbit

    try:
        connector.validate()
    except ValueError as exc:
        _fail_sync(_sanitize_source_error(str(exc), source_row))
        return pending_rabbit

    originals_root = (files_root / "originals") if files_root is not None else None
    try:
        documents = connector.fetch_documents(storage_root=originals_root)
    except NotImplementedError as exc:
        _fail_sync(_sanitize_source_error(str(exc), source_row))
        return pending_rabbit
    except Exception:
        _fail_sync(
            _sanitize_source_error(
                "Sync failed while reading source documents. "
                "Check connector settings and source availability.",
                source_row,
            )
        )
        return pending_rabbit

    discovered = 0
    created = 0
    skipped = 0
    enqueued = 0
    failed_discovery = 0
    failed_enqueue = 0

    try:
        for item in documents:
            discovered += 1
            try:
                # Move temp-file connector downloads into persistent storage
                # before creating the DB record so doc.path survives extraction.
                stored_path = item.path
                if files_root is not None:
                    moved = move_to_originals(item.path, item.mime_type, files_root)
                    if moved is not None:
                        stored_path = moved

                doc = doc_repo.create(
                    source_id=source_id,
                    external_id=item.external_id,
                    source=cast("DocumentSource", source_row["type"]),
                    mime_type=item.mime_type,
                    path=stored_path,
                    title=item.title,
                    source_language=item.source_language or source_language,
                    sha256=item.sha256,
                    metadata=item.metadata,
                )
                if doc is None:
                    skipped += 1
                    continue

                created += 1
                try:
                    job_id = job_repo.enqueue_document(
                        document_id=doc.id,
                        source_id=source_id,
                        content_text=item.text_content,
                    )
                    enqueued += 1
                    pending_rabbit.append(
                        {
                            "job_id": job_id,
                            "document_id": doc.id,
                            "source_id": source_id,
                            "content_text": item.text_content,
                        }
                    )
                except Exception:
                    failed_enqueue += 1
                    connection.execute(
                        sa.text(
                            "INSERT INTO dlq (id, document_id, error_message, status) "
                            "VALUES (:id, :document_id, :error_message, 'pending')"
                        ),
                        {
                            "id": db_uuid(uuid4()),
                            "document_id": db_uuid(doc.id),
                            "error_message": "Failed to enqueue document for processing",
                        },
                    )
            except Exception:
                failed_discovery += 1
    except Exception:
        # Generator raised mid-iteration (e.g. network failure on page 2 of a
        # Confluence sync).  Record partial state so the UI reflects the
        # interruption; the transaction still commits with the documents that
        # were created before the error.
        logger.exception(
            "sync interrupted while iterating documents source_id=%s connector_type=%s",
            source_id,
            connector_type,
        )
        sync_repo.update(
            sync_run_id,
            SyncRunUpdate(
                documents_discovered=discovered,
                documents_created=created,
                documents_skipped=skipped,
                documents_failed=failed_discovery + 1,
            ),
        )
        _fail_sync(
            _sanitize_source_error(
                "Sync interrupted: unexpected error while reading source documents.",
                source_row,
            )
        )
        return pending_rabbit

    # failed_enqueue is tracked explicitly in the inner exception handler

    # Determine outcome
    if discovered > 0 and failed_discovery == discovered:
        sync_outcome = "failed"
        sync_run_status = "failed"
    elif failed_enqueue > 0 or failed_discovery > 0:
        sync_outcome = "partial_failure"
        sync_run_status = "completed_with_warnings"
    else:
        sync_outcome = "success"
        sync_run_status = "completed"

    # Record final counts before completing — complete() sets the terminal status
    sync_repo.update(
        sync_run_id,
        SyncRunUpdate(
            documents_discovered=discovered,
            documents_created=created,
            documents_skipped=skipped,
            documents_failed=failed_discovery + failed_enqueue,
        ),
    )
    if not sync_repo.complete(sync_run_id, sync_run_status):  # type: ignore[arg-type]
        logger.warning(
            "sync_run %s was not in running state when completing (status=%s)",
            sync_run_id,
            sync_run_status,
        )

    _record_source_sync_state(
        connection,
        source_id,
        status=sync_outcome,
        indexed=enqueued,
        skipped=skipped,
        failed=failed_discovery + failed_enqueue,
        sync_run_id=sync_run_id,
    )

    logger.info(
        "scheduled sync source_id=%s outcome=%s sync_run_id=%s",
        source_id,
        sync_outcome,
        sync_run_id,
    )

    return pending_rabbit


def _run_scheduled_syncs(engine: Engine, settings: Settings | None = None) -> int:
    """Check all scheduled sources and sync those whose cron matches now.

    Each source runs in its own DB transaction so a failure in one source
    does not roll back another.  RabbitMQ messages are published after each
    transaction commits so workers see the ``pipeline_jobs`` rows before the
    message arrives.

    Returns the number of sources synced.
    """
    now = datetime.now(tz=UTC)

    with engine.connect() as conn:
        rows = (
            conn.execute(
                sa.text(
                    """
                    SELECT * FROM ingestion_sources
                    WHERE schedule IS NOT NULL
                      AND enabled = true
                    """
                )
            )
            .mappings()
            .all()
        )

    synced = 0
    _rabbit: Any | None = None
    for row in rows:
        schedule = str(row["schedule"]).strip()
        if not schedule or not _cron_matches(schedule, now):
            continue

        source_id_str = str(row["id"])
        _id = UUID(source_id_str)

        logger.info("triggering scheduled sync source_id=%s cron=%s", source_id_str, schedule)
        pending: list[dict[str, Any]] = []
        try:
            with engine.begin() as conn:
                pending = _sync_source(
                    conn,
                    row,
                    _id,
                    files_root=settings.files_root if settings is not None else None,
                )
            synced += 1
        except Exception:
            logger.exception("scheduled sync failed source_id=%s", source_id_str)
            continue

        # Publish to RabbitMQ after the DB transaction commits so consumers
        # see the pipeline_jobs rows before receiving the queue message.
        # Reuse a single RabbitClient across all syncs in this tick.
        if pending and settings is not None and getattr(settings, "rabbitmq_enabled", False):
            _rabbit = _publish_scheduled_rabbit_messages(engine, settings, pending, _rabbit)

    return synced


if __name__ == "__main__":
    settings = Settings()
    engine = sa.create_engine(settings.postgres_url)
    poll_interval = int(os.environ.get("SCHEDULER_POLL_SECONDS", "60"))

    logger.info("cron scheduler starting poll_interval=%ds", poll_interval)

    try:
        while True:
            n = _run_scheduled_syncs(engine, settings)
            if n > 0:
                logger.info("cron scheduler tick synced=%d", n)
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        logger.info("cron scheduler shutting down")
