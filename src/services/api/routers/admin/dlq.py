from __future__ import annotations

from typing import Annotated
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request

from services.api._helpers import _audit_log, _fmt_dt
from services.api.main import current_user
from services.api.schemas import DlqItem
from services.auth.models import TokenPayload
from services.permissions.enforcer import require_admin
from services.pipeline.jobs import PipelineJobRepository
from shared.db import to_uuid

router = APIRouter(tags=["admin"])


@router.get("/admin/dlq")
def admin_list_dlq(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> list[DlqItem]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        rows = connection.execute(
            sa.text("""
                SELECT id, document_id, error_message, retry_count, status, created_at, updated_at
                FROM dlq ORDER BY created_at DESC
                """)
        ).mappings()
        return [
            DlqItem(
                id=str(to_uuid(row["id"])),
                document_id=(str(to_uuid(row["document_id"])) if row["document_id"] else None),
                error_message=row["error_message"],
                retry_count=row["retry_count"],
                status=row["status"],
                created_at=_fmt_dt(row["created_at"]),
                updated_at=_fmt_dt(row["updated_at"]),
            )
            for row in rows
        ]


@router.post("/admin/pipeline/requeue-dead-letter")
def admin_requeue_dead_letter(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
    job_type: str | None = None,
    error_prefix: str | None = None,
) -> dict[str, object]:
    """Reset dead-lettered pipeline_jobs back to pending.

    Optional query params:
    - job_type: restrict to a specific job type (e.g. ``vector_index_document``)
    - error_prefix: restrict to jobs whose last_error starts with this string
      (e.g. ``UnexpectedResponse``)
    """
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        job_repo = PipelineJobRepository(connection)
        count = job_repo.requeue_dead_letter(job_type=job_type, error_prefix=error_prefix)
        _audit_log(
            connection,
            user.sub,
            "requeue_dead_letter",
            "pipeline_jobs",
            details={"job_type": job_type, "error_prefix": error_prefix, "count": count},
        )
        return {"requeued": count}


@router.post("/admin/documents/{document_id}/requeue")
def admin_requeue_document_dead_letters(
    document_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, object]:
    """Requeue all dead-letter pipeline jobs for a document back to pending."""
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        count = connection.execute(
            sa.text("""
                UPDATE pipeline_jobs
                SET status = 'pending', locked_by = NULL, locked_at = NULL,
                    last_error = NULL, run_after = NOW()
                WHERE document_id = :document_id AND status = 'dead_letter'
                """),
            {"document_id": document_id.hex},
        ).rowcount
        _audit_log(
            connection,
            user.sub,
            "requeue_document",
            "pipeline_jobs",
            str(document_id),
            {"count": count},
        )
        return {"requeued": count}


@router.post("/admin/dlq/{dlq_id}/retry")
def admin_retry_dlq(
    dlq_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, str]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        result = connection.execute(
            sa.text("""
                UPDATE dlq
                SET status = 'retried', retry_count = retry_count + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id AND status = 'pending'
                """),
            {"id": dlq_id.hex},
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="DLQ item not found or not pending")
        _audit_log(connection, user.sub, "retry", "dlq", str(dlq_id))
        return {"id": str(dlq_id), "status": "retried"}
