"""Cron-based ingestion source scheduler.

Polls ingestion_sources for non-null ``schedule`` values and triggers
sync when the cron expression matches the current minute.
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import suppress
from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

import sqlalchemy as sa

from services.api._helpers import _record_source_sync_state, _sanitize_source_error
from services.connectors.factory import build_connector
from services.documents.models import DocumentSource
from services.documents.repository import DocumentRepository
from services.pipeline.jobs import PipelineJobRepository
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


def _sync_source(
    connection: sa.Connection,
    source_row: sa.RowMapping,
    source_id: UUID,
) -> None:
    """Run a single source sync, mirroring sync-now logic."""
    doc_repo = DocumentRepository(connection)
    job_repo = PipelineJobRepository(connection)

    source_language = source_row.get("source_language")

    def _record_dlq(document_id: UUID | None, message: str) -> None:
        connection.execute(
            sa.text(
                """
                INSERT INTO dlq (id, document_id, error_message, status)
                VALUES (:id, :document_id, :error_message, 'pending')
                """
            ),
            {
                "id": db_uuid(uuid4()),
                "document_id": (db_uuid(document_id) if document_id is not None else None),
                "error_message": message,
            },
        )

    connector_type = str(source_row["type"])
    try:
        connector = build_connector(source_row)
    except ValueError as exc:
        _record_source_sync_state(
            connection,
            source_id,
            status="failed",
            failed=1,
            error=_sanitize_source_error(str(exc), source_row),
        )
        return

    try:
        connector.validate()
    except ValueError as exc:
        _record_source_sync_state(
            connection,
            source_id,
            status="failed",
            failed=1,
            error=_sanitize_source_error(str(exc), source_row),
        )
        return

    try:
        documents = connector.fetch_documents()
    except NotImplementedError as exc:
        _record_source_sync_state(
            connection,
            source_id,
            status="failed",
            failed=1,
            error=_sanitize_source_error(str(exc), source_row),
        )
        return
    except Exception:
        _record_source_sync_state(
            connection,
            source_id,
            status="failed",
            failed=1,
            error=_sanitize_source_error(
                "Sync failed while reading source documents. "
                "Check connector settings and source availability.",
                source_row,
            ),
        )
        return

    discovered = 0
    created = 0
    skipped = 0
    enqueued = 0
    failed_discovery = 0

    for item in documents:
        discovered += 1
        try:
            doc = doc_repo.create(
                source_id=source_id,
                external_id=item.external_id,
                source=cast("DocumentSource", source_row["type"]),
                mime_type=item.mime_type,
                path=item.path,
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
                job_repo.enqueue_document(
                    document_id=doc.id,
                    source_id=source_id,
                    content_text=item.text_content,
                )
                enqueued += 1
            except Exception:
                _record_dlq(doc.id, "Failed to enqueue document for processing")
        except Exception:
            failed_discovery += 1
        finally:
            if connector_type == "smb" and item.path:
                with suppress(OSError):
                    os.unlink(item.path)

    failed_enqueue = discovered - created - skipped - failed_discovery

    sync_outcome = (
        "failed"
        if failed_discovery > 0 and discovered == 0
        else ("partial_failure" if failed_enqueue > 0 or failed_discovery > 0 else "success")
    )

    _record_source_sync_state(
        connection,
        source_id,
        status=sync_outcome,
        indexed=enqueued,
        skipped=skipped,
        failed=failed_discovery + failed_enqueue,
    )

    logger.info(
        "scheduled sync source_id=%s outcomes=%s",
        source_id,
        sync_outcome,
    )


def _run_scheduled_syncs(connection: sa.Connection) -> int:
    """Check all scheduled sources and sync those whose cron matches now.

    Returns the number of sources synced.
    """
    now = datetime.now(tz=datetime.UTC)

    rows = (
        connection.execute(
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
    for row in rows:
        schedule = str(row["schedule"]).strip()
        if not schedule or not _cron_matches(schedule, now):
            continue

        source_id_str = str(row["id"])
        _id = UUID(source_id_str)

        logger.info("triggering scheduled sync source_id=%s cron=%s", source_id_str, schedule)
        try:
            _sync_source(connection, row, _id)
            synced += 1
        except Exception:
            logger.exception("scheduled sync failed source_id=%s", source_id_str)

    return synced


if __name__ == "__main__":
    settings = Settings()
    engine = sa.create_engine(settings.postgres_url)
    poll_interval = int(os.environ.get("SCHEDULER_POLL_SECONDS", "60"))

    logger.info("cron scheduler starting poll_interval=%ds", poll_interval)

    try:
        while True:
            with engine.begin() as conn:
                n = _run_scheduled_syncs(conn)
                if n > 0:
                    logger.info("cron scheduler tick synced=%d", n)
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        logger.info("cron scheduler shutting down")
