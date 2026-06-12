"""Timeline and safe retry endpoints for per-document processing stages (#673)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request

from services.api._helpers import _audit_log, _fmt_dt
from services.api.main import current_user
from services.api.schemas import DocumentTimelineResponse, RetryResponse
from services.auth.models import TokenPayload
from services.permissions.enforcer import require_admin
from services.pipeline.jobs import PipelineJobRepository
from shared.db import db_uuid, to_uuid

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])


def _build_timeline_stages(
    jobs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build a stage-centric timeline from raw pipeline_jobs rows.

    Each job represents one processing stage.  Stages are ordered by
    the job ``created_at`` timestamp.  Duration is computed from the
    ``created_at`` → ``updated_at`` delta when the job is completed.
    """
    # Sort all jobs by created_at (ascending)
    sorted_jobs = sorted(
        jobs, key=lambda j: j.get("created_at") or datetime.min.replace(tzinfo=UTC)
    )

    stages: list[dict[str, Any]] = []

    for job in sorted_jobs:
        stage_name = job.get("stage") or job.get("job_type") or "unknown"
        status = job.get("status", "pending")

        # Map pipeline job status → timeline stage status
        if status in ("succeeded",):
            stage_status = "completed"
        elif status in ("dead_letter",):
            stage_status = "failed"
        elif status in ("running",):
            stage_status = "running"
        elif status in ("retry",):
            stage_status = "pending"
        else:
            stage_status = "pending"

        # Compute duration for completed stages
        duration_ms: int | None = None
        created = job.get("created_at")
        updated = job.get("updated_at")
        if (
            stage_status == "completed"
            and created
            and updated
            and isinstance(created, datetime)
            and isinstance(updated, datetime)
        ):
            delta = updated - created
            duration_ms = int(delta.total_seconds() * 1000)

        stages.append(
            {
                "stage": stage_name,
                "status": stage_status,
                "at": _fmt_dt(updated or created),
                "duration_ms": duration_ms,
                "error": job.get("last_error"),
            }
        )

    return stages


def _requeue_jobs(
    connection: sa.Connection,
    document_id: UUID,
    user_id: UUID,
    action: str,
    stage: str | None = None,
) -> int:
    """Reset dead-letter pipeline jobs for a document back to pending.

    Returns the number of jobs requeued.  Audits the action.
    """
    params: dict[str, Any] = {
        "document_id": db_uuid(document_id),
    }
    stage_filter = ""
    if stage:
        stage_filter = "AND stage = :stage"
        params["stage"] = stage

    now = datetime.now(UTC)
    result = connection.execute(
        sa.text(f"""
            UPDATE pipeline_jobs
            SET status = 'pending',
                locked_by = NULL,
                locked_at = NULL,
                last_error = NULL,
                run_after = :now,
                updated_at = :now
            WHERE document_id = :document_id
              AND status = 'dead_letter'
              {stage_filter}
        """),
        {**params, "now": now},
    )

    count = result.rowcount if result.rowcount is not None else 0

    _audit_log(
        connection,
        user_id,
        action,
        "pipeline_jobs",
        str(document_id),
        {"stage": stage, "count": count},
    )

    return count


def _re_enqueue_job(
    connection: sa.Connection,
    document_id: UUID,
    source_id: UUID,
    job_type: str,
    user_id: UUID,
    action: str,
    content_text: str | None = None,
) -> int:
    """Re-enqueue a pipeline job for a document by creating a new pending entry.

    First resets any existing dead-letter jobs of the same (document, job_type)
    so the new job is the only one active.
    """
    repo = PipelineJobRepository(connection)
    now = datetime.now(UTC)

    # Reset any dead-letter jobs of this type first
    connection.execute(
        sa.text("""
            UPDATE pipeline_jobs
            SET status = 'pending',
                locked_by = NULL,
                locked_at = NULL,
                last_error = NULL,
                run_after = :now,
                updated_at = :now
            WHERE document_id = :document_id
              AND job_type = :job_type
              AND status = 'dead_letter'
        """),
        {
            "document_id": db_uuid(document_id),
            "job_type": job_type,
            "now": now,
        },
    )

    # Check if an active job already exists
    existing = connection.execute(
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
        _audit_log(
            connection,
            user_id,
            action,
            "pipeline_jobs",
            str(document_id),
            {"job_type": job_type, "existing": str(to_uuid(existing)), "count": 1},
        )
        return 1

    try:
        new_job_id = repo.enqueue_document(
            document_id=document_id,
            source_id=source_id,
            job_type=job_type,
            content_text=content_text,
        )
    except Exception:
        logger.exception("Failed to re-enqueue job for document %s", document_id)
        return 0

    _audit_log(
        connection,
        user_id,
        action,
        "pipeline_jobs",
        str(document_id),
        {"job_type": job_type, "new_job_id": str(new_job_id), "count": 1},
    )
    return 1


def _get_document_info(
    connection: sa.Connection,
    document_id: UUID,
) -> tuple[str | None, str | None, UUID | None]:
    """Return (title, source_name, source_id) for a document."""
    row = (
        connection.execute(
            sa.text("""
            SELECT d.title, s.name AS source_name, d.source_id
            FROM documents d
            LEFT JOIN ingestion_sources s ON s.id = d.source_id
            WHERE d.id = :document_id
        """),
            {"document_id": db_uuid(document_id)},
        )
        .mappings()
        .first()
    )

    if row is None:
        return None, None, None
    return (
        row["title"],
        row["source_name"],
        to_uuid(row["source_id"]) if row["source_id"] else None,
    )


# ──────────────────────── Endpoints ────────────────────────


@router.get(
    "/admin/documents/{document_id}/timeline",
    response_model=DocumentTimelineResponse,
)
def admin_document_timeline(
    document_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    """Return per-document processing timeline from pipeline_jobs history."""
    require_admin(user)
    with request.app.state.engine.begin() as conn:
        repo = PipelineJobRepository(conn)
        document_title, source_name, jobs = repo.list_document_trace(document_id)

    if not jobs:
        raise HTTPException(status_code=404, detail="No pipeline jobs found for this document")

    stages = _build_timeline_stages(jobs)

    return {
        "document_id": str(document_id),
        "document_title": document_title,
        "source_name": source_name,
        "stages": stages,
    }


@router.post(
    "/admin/documents/{document_id}/retry",
    response_model=RetryResponse,
)
def admin_retry_document(
    document_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, object]:
    """Retry all dead-letter pipeline jobs for a document."""
    require_admin(user)

    with request.app.state.engine.begin() as conn:
        # Verify document exists
        title, _, _ = _get_document_info(conn, document_id)
        if title is None:
            raise HTTPException(status_code=404, detail="Document not found")

        count = _requeue_jobs(conn, document_id, user.sub, "retry_document")

    return {"requeued": count, "action": "retry"}


@router.post(
    "/admin/documents/{document_id}/reprocess",
    response_model=RetryResponse,
)
def admin_reprocess_document(
    document_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, object]:
    """Re-run document extraction by re-enqueuing a process_document job."""
    require_admin(user)

    with request.app.state.engine.begin() as conn:
        title, _, source_id = _get_document_info(conn, document_id)
        if title is None or source_id is None:
            raise HTTPException(status_code=404, detail="Document not found or missing source")

        count = _re_enqueue_job(
            conn,
            document_id,
            source_id,
            "process_document",
            user.sub,
            "reprocess",
        )

    return {"requeued": count, "action": "reprocess"}


@router.post(
    "/admin/documents/{document_id}/reocr",
    response_model=RetryResponse,
)
def admin_reocr_document(
    document_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, object]:
    """Re-run OCR for a document if eligible."""
    require_admin(user)

    with request.app.state.engine.begin() as conn:
        title, _, source_id = _get_document_info(conn, document_id)
        if title is None or source_id is None:
            raise HTTPException(status_code=404, detail="Document not found or missing source")

        # Reset any dead-letter jobs at the OCR-related stage, then re-enqueue
        _requeue_jobs(conn, document_id, user.sub, "reocr", stage="ocr")
        count = _re_enqueue_job(
            conn,
            document_id,
            source_id,
            "process_document",
            user.sub,
            "reocr",
        )

    return {"requeued": count, "action": "reocr"}


@router.post(
    "/admin/documents/{document_id}/retranslate",
    response_model=RetryResponse,
)
def admin_retranslate_document(
    document_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, object]:
    """Re-run translation for a document."""
    require_admin(user)

    with request.app.state.engine.begin() as conn:
        title, _, source_id = _get_document_info(conn, document_id)
        if title is None or source_id is None:
            raise HTTPException(status_code=404, detail="Document not found or missing source")

        # Reset any dead-letter translation jobs
        _requeue_jobs(conn, document_id, user.sub, "retranslate", stage="translate")
        _requeue_jobs(conn, document_id, user.sub, "retranslate", stage="translated")
        count = _re_enqueue_job(
            conn,
            document_id,
            source_id,
            "translate_document",
            user.sub,
            "retranslate",
        )

    return {"requeued": count, "action": "retranslate"}


@router.post(
    "/admin/documents/{document_id}/reembed",
    response_model=RetryResponse,
)
def admin_reembed_document(
    document_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, object]:
    """Re-embed and re-index a document (triggers vector_index_document job)."""
    require_admin(user)

    with request.app.state.engine.begin() as conn:
        title, _, source_id = _get_document_info(conn, document_id)
        if title is None or source_id is None:
            raise HTTPException(status_code=404, detail="Document not found or missing source")

        # Reset any dead-letter index/embed jobs
        _requeue_jobs(conn, document_id, user.sub, "reembed", stage="embedded")
        _requeue_jobs(conn, document_id, user.sub, "reembed", stage="indexed")
        count = _re_enqueue_job(
            conn,
            document_id,
            source_id,
            "vector_index_document",
            user.sub,
            "reembed",
        )

    return {"requeued": count, "action": "reembed"}
