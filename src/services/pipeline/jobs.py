from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from shared.db import db_uuid, to_uuid

logger = logging.getLogger(__name__)

_MAX_ERROR_LENGTH = 200


def _is_sqlite(conn: sa.Connection) -> bool:
    """Return True when the connection uses SQLite dialect."""
    return conn.dialect.name == "sqlite"


def _sanitize_error(exc_or_msg: BaseException | str, stage: str = "") -> str:
    """Store only exception type/class-name and optional stage — never raw message text."""
    if isinstance(exc_or_msg, BaseException):
        tag = type(exc_or_msg).__name__
    elif isinstance(exc_or_msg, str):
        tag = exc_or_msg.strip()
    else:
        tag = "unknown"
    result = f"{tag}:{stage}" if stage else tag
    return result[:_MAX_ERROR_LENGTH]


class PipelineJobRepository:
    """Connector-agnostic DB-backed pipeline job queue."""

    def __init__(self, connection: sa.Connection) -> None:
        self._connection = connection

    def enqueue_document(
        self,
        doc_id: UUID,
        source_id: UUID,
        job_type: str = "process_document",
        priority: int = 0,
        max_attempts: int = 5,
        content_text: str | None = None,
        content_path: str | None = None,
        content_sha256: str | None = None,
        run_after: datetime | None = None,
    ) -> UUID:
        """Create a pending pipeline job for a document.

        If an active job (pending/running/retry) already exists for
        the same (doc_id, job_type), returns the existing job ID
        instead of creating a duplicate.
        """
        existing = self._connection.execute(
            sa.text(
                """
                SELECT id FROM pipeline_jobs
                WHERE doc_id = :doc_id
                  AND job_type = :job_type
                  AND status IN ('pending', 'running', 'retry')
                LIMIT 1
            """
            ),
            {"doc_id": db_uuid(doc_id), "job_type": job_type},
        ).scalar()
        if existing:
            return to_uuid(existing)

        job_id = uuid4()
        now = datetime.now(UTC)
        if run_after is None:
            run_after = now
        try:
            self._connection.execute(
                sa.text(
                    """
                    INSERT INTO pipeline_jobs
                        (id, doc_id, source_id, job_type, status, priority,
                         max_attempts, run_after, created_at, updated_at)
                    VALUES
                        (:id, :doc_id, :source_id, :job_type, 'pending', :priority,
                         :max_attempts, :run_after, :created_at, :updated_at)
                """
                ),
                {
                    "id": db_uuid(job_id),
                    "doc_id": db_uuid(doc_id),
                    "source_id": db_uuid(source_id),
                    "job_type": job_type,
                    "priority": priority,
                    "max_attempts": max_attempts,
                    "run_after": run_after,
                    "created_at": now,
                    "updated_at": now,
                },
            )
        except IntegrityError:
            existing = self._connection.execute(
                sa.text(
                    """
                    SELECT id FROM pipeline_jobs
                    WHERE doc_id = :doc_id
                      AND job_type = :job_type
                      AND status IN ('pending', 'running', 'retry')
                    LIMIT 1
                """
                ),
                {"doc_id": db_uuid(doc_id), "job_type": job_type},
            ).scalar()
            return to_uuid(existing)

        if content_text is not None or content_path is not None:
            self._connection.execute(
                sa.text(
                    """
                    INSERT INTO document_payloads
                        (doc_id, content_text, content_path, content_sha256,
                         created_at, updated_at)
                    VALUES
                        (:doc_id, :content_text, :content_path, :content_sha256,
                         :created_at, :updated_at)
                    ON CONFLICT (doc_id) DO UPDATE SET
                        content_text = EXCLUDED.content_text,
                        content_path = EXCLUDED.content_path,
                        content_sha256 = EXCLUDED.content_sha256,
                        updated_at = :updated_at
                """
                ),
                {
                    "doc_id": db_uuid(doc_id),
                    "content_text": content_text,
                    "content_path": content_path,
                    "content_sha256": content_sha256,
                    "created_at": now,
                    "updated_at": now,
                },
            )

        return job_id

    def claim_next(
        self, locker_id: str, job_types: list[str] | None = None
    ) -> dict[str, Any] | None:
        """Claim the next eligible job.

        Returns the job row or None.
        Prioritizes by priority (higher first), then created_at (oldest first).
        Uses ``FOR UPDATE SKIP LOCKED`` on PostgreSQL to avoid double-claiming.
        On SQLite, the SELECT and UPDATE are executed sequentially without
        row-level locking (SQLite serializes writes at the connection level).
        """
        params: dict[str, Any] = {"now": datetime.now(UTC)}
        type_filter = ""
        if job_types:
            type_filter = "AND job_type IN :job_types"
            params["job_types"] = tuple(job_types)

        lock_clause = "FOR UPDATE SKIP LOCKED" if not _is_sqlite(self._connection) else ""

        stmt = sa.text(
            f"""
            SELECT id, doc_id, source_id, job_type, priority, attempts,
                   max_attempts, stage, last_error, run_after
            FROM pipeline_jobs
            WHERE status IN ('pending', 'retry')
              AND run_after <= :now
              {type_filter}
            ORDER BY priority DESC, created_at ASC
            LIMIT 1
            {lock_clause}
        """
        )
        if job_types:
            stmt = stmt.bindparams(sa.bindparam("job_types", expanding=True))
        row = self._connection.execute(stmt, params).mappings().first()

        if row is None:
            return None

        now = datetime.now(UTC)
        self._connection.execute(
            sa.text(
                """
                UPDATE pipeline_jobs
                SET status = 'running',
                    locked_by = :locked_by,
                    locked_at = :locked_at,
                    attempts = attempts + 1,
                    updated_at = :updated_at
                WHERE id = :id
            """
            ),
            {
                "id": row["id"],
                "locked_by": locker_id,
                "locked_at": now,
                "updated_at": now,
            },
        )

        return {
            "id": to_uuid(row["id"]),
            "doc_id": to_uuid(row["doc_id"]),
            "source_id": to_uuid(row["source_id"]),
            "job_type": row["job_type"],
            "priority": row["priority"],
            "attempts": row["attempts"] + 1,
            "max_attempts": row["max_attempts"],
            "stage": row["stage"],
            "last_error": row["last_error"],
            "run_after": row["run_after"],
            "locked_by": locker_id,
            "locked_at": now,
        }

    def mark_running_stage(self, job_id: UUID, stage: str) -> None:
        """Update the current processing stage of a running job."""
        self._connection.execute(
            sa.text(
                """
                UPDATE pipeline_jobs
                SET stage = :stage, updated_at = :updated_at
                WHERE id = :id AND status = 'running'
            """
            ),
            {
                "id": db_uuid(job_id),
                "stage": stage,
                "updated_at": datetime.now(UTC),
            },
        )

    def mark_succeeded(self, job_id: UUID) -> None:
        """Mark a running job as succeeded."""
        self._connection.execute(
            sa.text(
                """
                UPDATE pipeline_jobs
                SET status = 'succeeded',
                    locked_by = NULL,
                    locked_at = NULL,
                    updated_at = :updated_at
                WHERE id = :id AND status = 'running'
            """
            ),
            {"id": db_uuid(job_id), "updated_at": datetime.now(UTC)},
        )

    def mark_retry(
        self,
        job_id: UUID,
        error: str | BaseException,
        retry_delay_seconds: int = 60,
        stage: str = "process",
    ) -> None:
        """Mark a running job for retry with a sanitized error and backoff."""
        now = datetime.now(UTC)
        self._connection.execute(
            sa.text(
                """
                UPDATE pipeline_jobs
                SET status = 'retry',
                    last_error = :last_error,
                    run_after = :run_after,
                    locked_by = NULL,
                    locked_at = NULL,
                    updated_at = :updated_at
                WHERE id = :id AND status = 'running'
            """
            ),
            {
                "id": db_uuid(job_id),
                "last_error": _sanitize_error(error, stage=stage),
                "run_after": now + timedelta(seconds=retry_delay_seconds),
                "updated_at": now,
            },
        )

    def mark_dead_letter(self, job_id: UUID, error: str | BaseException) -> None:
        """Move a running job to dead-letter state (final failure)."""
        self._connection.execute(
            sa.text(
                """
                UPDATE pipeline_jobs
                SET status = 'dead_letter',
                    last_error = :last_error,
                    locked_by = NULL,
                    locked_at = NULL,
                    updated_at = :updated_at
                WHERE id = :id AND status = 'running'
            """
            ),
            {
                "id": db_uuid(job_id),
                "last_error": _sanitize_error(error, stage="process"),
                "updated_at": datetime.now(UTC),
            },
        )

    def get_payload(self, doc_id: UUID) -> dict[str, Any] | None:
        """Return the stored document payload for a doc_id."""
        row = (
            self._connection.execute(
                sa.text(
                    """
                SELECT doc_id, content_text, content_path, content_sha256
                FROM document_payloads
                WHERE doc_id = :doc_id
            """
                ),
                {"doc_id": db_uuid(doc_id)},
            )
            .mappings()
            .first()
        )
        return (
            {
                "doc_id": to_uuid(row["doc_id"]),
                "content_text": row["content_text"],
                "content_path": row["content_path"],
                "content_sha256": row["content_sha256"],
            }
            if row
            else None
        )
