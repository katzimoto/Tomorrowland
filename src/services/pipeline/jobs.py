from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from shared.db import db_uuid, to_uuid

logger = logging.getLogger(__name__)

_MAX_ERROR_LENGTH = 200

# Safe category strings for the string branch of _sanitize_error.
# Any string input that does not match one of these is replaced with "unknown".
_ALLOWED_ERROR_CATEGORIES = frozenset(
    {
        "process",
        "extract",
        "translate",
        "chunk",
        "index",
        "enqueue",
        "vector_encode",
        "vector_upsert",
        "intelligence",
        "alert",
        "timeout",
        "connection_refused",
        "not_found",
        "invalid_input",
    }
)


def _is_sqlite(conn: sa.Connection) -> bool:
    """Return True when the connection uses SQLite dialect."""
    return conn.dialect.name == "sqlite"


def _sanitize_error(exc_or_msg: BaseException | str, stage: str = "") -> str:
    """Store exception type and first line of message, never raw stack traces."""
    if isinstance(exc_or_msg, BaseException):
        tag = type(exc_or_msg).__name__
        msg = str(exc_or_msg).split("\n")[0].strip()
        if msg:
            tag = f"{tag}: {msg}"
    elif isinstance(exc_or_msg, str):
        tag = exc_or_msg.strip() if exc_or_msg.strip() in _ALLOWED_ERROR_CATEGORIES else "unknown"
    else:
        tag = "unknown"
    result = f"{tag}:{stage}" if stage else tag
    return result[:_MAX_ERROR_LENGTH]


class PipelineJobRepository:
    """Connector-agnostic DB-backed pipeline job queue."""

    def __init__(self, connection: sa.Connection) -> None:
        self._connection = connection

    def commit(self) -> None:
        """Commit the underlying connection's open transaction."""
        self._connection.commit()

    def enqueue_document(
        self,
        document_id: UUID,
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
        the same (document_id, job_type), returns the existing job ID
        instead of creating a duplicate.
        """
        existing = self._connection.execute(
            sa.text("""
                SELECT id FROM pipeline_jobs
                WHERE document_id = :document_id
                  AND job_type = :job_type
                  AND status IN ('pending', 'running', 'retry')
                LIMIT 1
            """),
            {"document_id": db_uuid(document_id), "job_type": job_type},
        ).scalar()
        if existing:
            return to_uuid(existing)

        job_id = uuid4()
        now = datetime.now(UTC)
        if run_after is None:
            run_after = now
        try:
            self._connection.execute(
                sa.text("""
                    INSERT INTO pipeline_jobs
                        (id, document_id, source_id, job_type, status, priority,
                         max_attempts, run_after, created_at, updated_at)
                    VALUES
                        (:id, :document_id, :source_id, :job_type, 'pending', :priority,
                         :max_attempts, :run_after, :created_at, :updated_at)
                """),
                {
                    "id": db_uuid(job_id),
                    "document_id": db_uuid(document_id),
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
                sa.text("""
                    SELECT id FROM pipeline_jobs
                    WHERE document_id = :document_id
                      AND job_type = :job_type
                      AND status IN ('pending', 'running', 'retry')
                    LIMIT 1
                """),
                {"document_id": db_uuid(document_id), "job_type": job_type},
            ).scalar()
            return to_uuid(existing)

        if content_text is not None or content_path is not None:
            self._connection.execute(
                sa.text("""
                    INSERT INTO document_payloads
                        (document_id, content_text, content_path, content_sha256,
                         created_at, updated_at)
                    VALUES
                        (:document_id, :content_text, :content_path, :content_sha256,
                         :created_at, :updated_at)
                    ON CONFLICT (document_id) DO UPDATE SET
                        content_text = EXCLUDED.content_text,
                        content_path = EXCLUDED.content_path,
                        content_sha256 = EXCLUDED.content_sha256,
                        updated_at = :updated_at
                """),
                {
                    "document_id": db_uuid(document_id),
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

        stmt = sa.text(f"""
            SELECT id, document_id, source_id, job_type, priority, attempts,
                   max_attempts, stage, last_error, run_after
            FROM pipeline_jobs
            WHERE status IN ('pending', 'retry')
              AND run_after <= :now
              {type_filter}
            ORDER BY priority DESC, created_at ASC
            LIMIT 1
            {lock_clause}
        """)
        if job_types:
            stmt = stmt.bindparams(sa.bindparam("job_types", expanding=True))
        row = self._connection.execute(stmt, params).mappings().first()

        if row is None:
            return None

        now = datetime.now(UTC)
        self._connection.execute(
            sa.text("""
                UPDATE pipeline_jobs
                SET status = 'running',
                    locked_by = :locked_by,
                    locked_at = :locked_at,
                    attempts = attempts + 1,
                    updated_at = :updated_at
                WHERE id = :id AND status IN ('pending', 'retry')
            """),
            {
                "id": row["id"],
                "locked_by": locker_id,
                "locked_at": now,
                "updated_at": now,
            },
        )

        return {
            "id": to_uuid(row["id"]),
            "document_id": to_uuid(row["document_id"]),
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
        """Update the current processing stage, transitioning to running if pending."""
        self._connection.execute(
            sa.text("""
                UPDATE pipeline_jobs
                SET status = 'running', stage = :stage, updated_at = :updated_at
                WHERE id = :id AND status IN ('pending', 'running', 'retry')
            """),
            {
                "id": db_uuid(job_id),
                "stage": stage,
                "updated_at": datetime.now(UTC),
            },
        )

    def set_rabbit_message_id(self, job_id: UUID, message_id: str) -> None:
        """Persist the RabbitMQ message ID for observability."""
        self._connection.execute(
            sa.text("""
                UPDATE pipeline_jobs
                SET rabbit_message_id = :message_id, updated_at = :updated_at
                WHERE id = :id
            """),
            {
                "id": db_uuid(job_id),
                "message_id": message_id,
                "updated_at": datetime.now(UTC),
            },
        )

    def get_max_attempts(self, job_id: UUID) -> int:
        """Return the max_attempts value for a job (default 5 if not found)."""
        result = self._connection.execute(
            sa.text("SELECT max_attempts FROM pipeline_jobs WHERE id = :id"),
            {"id": db_uuid(job_id)},
        ).scalar()
        return int(result) if result is not None else 5

    def mark_succeeded(self, job_id: UUID) -> None:
        """Mark a running job as succeeded."""
        self._connection.execute(
            sa.text("""
                UPDATE pipeline_jobs
                SET status = 'succeeded',
                    locked_by = NULL,
                    locked_at = NULL,
                    updated_at = :updated_at
                WHERE id = :id AND status = 'running'
            """),
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
            sa.text("""
                UPDATE pipeline_jobs
                SET status = 'retry',
                    last_error = :last_error,
                    run_after = :run_after,
                    locked_by = NULL,
                    locked_at = NULL,
                    updated_at = :updated_at
                WHERE id = :id AND status = 'running'
            """),
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
            sa.text("""
                UPDATE pipeline_jobs
                SET status = 'dead_letter',
                    last_error = :last_error,
                    locked_by = NULL,
                    locked_at = NULL,
                    updated_at = :updated_at
                WHERE id = :id AND status = 'running'
            """),
            {
                "id": db_uuid(job_id),
                "last_error": _sanitize_error(error, stage="process"),
                "updated_at": datetime.now(UTC),
            },
        )

    def get_payload(self, document_id: UUID) -> dict[str, Any] | None:
        """Return the stored document payload for a document_id."""
        row = (
            self._connection.execute(
                sa.text("""
                SELECT document_id, content_text, content_path, content_sha256,
                       translated_text, extraction_metadata
                FROM document_payloads
                WHERE document_id = :document_id
            """),
                {"document_id": db_uuid(document_id)},
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        metadata_raw = row["extraction_metadata"]
        return {
            "document_id": to_uuid(row["document_id"]),
            "content_text": row["content_text"],
            "content_path": row["content_path"],
            "content_sha256": row["content_sha256"],
            "translated_text": row["translated_text"],
            "extraction_metadata": json.loads(metadata_raw) if metadata_raw else None,
        }

    def update_extraction_metadata(self, document_id: UUID, metadata: list[dict[str, Any]]) -> None:
        """Persist extraction location metadata (page_number, section_heading) as JSON."""
        now = datetime.now(UTC)
        self._connection.execute(
            sa.text("""
                INSERT INTO document_payloads
                    (document_id, extraction_metadata, created_at, updated_at)
                VALUES (:document_id, :metadata, :now, :now)
                ON CONFLICT (document_id) DO UPDATE SET
                    extraction_metadata = EXCLUDED.extraction_metadata,
                    updated_at = :now
            """),
            {
                "document_id": db_uuid(document_id),
                "metadata": json.dumps(metadata),
                "now": now,
            },
        )

    def update_content_text(self, document_id: UUID, content_text: str) -> None:
        """Persist the extracted document text so downstream workers (e.g. translation-worker)
        can read raw content from the DB without re-running file extraction."""
        now = datetime.now(UTC)
        self._connection.execute(
            sa.text("""
                INSERT INTO document_payloads (document_id, content_text, created_at, updated_at)
                VALUES (:document_id, :content_text, :now, :now)
                ON CONFLICT (document_id) DO UPDATE SET
                    content_text = EXCLUDED.content_text,
                    updated_at = :now
            """),
            {
                "document_id": db_uuid(document_id),
                "content_text": content_text,
                "now": now,
            },
        )

    def update_translated_text(self, document_id: UUID, translated_text: str) -> None:
        """Persist the pipeline-translated text for later use by the index-worker."""
        now = datetime.now(UTC)
        self._connection.execute(
            sa.text("""
                INSERT INTO document_payloads (document_id, translated_text, created_at, updated_at)
                VALUES (:document_id, :translated_text, :now, :now)
                ON CONFLICT (document_id) DO UPDATE SET
                    translated_text = EXCLUDED.translated_text,
                    updated_at = :now
            """),
            {
                "document_id": db_uuid(document_id),
                "translated_text": translated_text,
                "now": now,
            },
        )

    def requeue_dead_letter(
        self,
        job_type: str | None = None,
        error_prefix: str | None = None,
    ) -> int:
        """Reset dead-lettered jobs back to pending so workers retry them.

        Clears attempts so the job gets a full retry budget again.
        Filters can be combined: *job_type* restricts by job type,
        *error_prefix* restricts to rows whose last_error starts with the prefix.

        Returns the number of jobs requeued.
        """
        now = datetime.now(UTC)
        params: dict[str, Any] = {"now": now}
        filters = ["status = 'dead_letter'"]

        if job_type is not None:
            filters.append("job_type = :job_type")
            params["job_type"] = job_type
        if error_prefix is not None:
            filters.append("last_error LIKE :error_prefix")
            params["error_prefix"] = error_prefix + "%"

        where = " AND ".join(filters)
        result = self._connection.execute(
            sa.text(f"""
                UPDATE pipeline_jobs
                SET status = 'pending',
                    attempts = 0,
                    last_error = NULL,
                    locked_by = NULL,
                    locked_at = NULL,
                    run_after = :now,
                    updated_at = :now
                WHERE {where}
            """),
            params,
        )
        return result.rowcount if result.rowcount is not None else 0

    def count_by_status(self) -> dict[tuple[str, str], int]:
        """Return job counts grouped by (status, job_type).

        Used to populate queue-depth gauges for operator visibility.
        """
        rows = self._connection.execute(
            sa.text("""
                SELECT status, job_type, COUNT(*) AS cnt
                FROM pipeline_jobs
                GROUP BY status, job_type
                """)
        ).fetchall()
        return {(row[0], row[1]): row[2] for row in rows}

    def reap_stale_locks(self, max_age_seconds: int = 300) -> int:
        """Reset jobs stuck in ``running`` state past *max_age_seconds* to ``pending``.

        Returns the number of jobs reset.
        This allows crashed workers' jobs to be picked up by other workers.
        """
        cutoff = datetime.now(UTC) - timedelta(seconds=max_age_seconds)
        result = self._connection.execute(
            sa.text("""
                UPDATE pipeline_jobs
                SET status = 'pending',
                    locked_by = NULL,
                    locked_at = NULL,
                    updated_at = :updated_at
                WHERE status = 'running'
                  AND locked_at IS NOT NULL
                  AND locked_at <= :cutoff
            """),
            {"cutoff": cutoff, "updated_at": datetime.now(UTC)},
        )
        return result.rowcount if result.rowcount is not None else 0
