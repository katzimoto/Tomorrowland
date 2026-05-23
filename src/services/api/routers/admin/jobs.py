"""Admin routes for pipeline job inspection and retry."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request

from services.api.main import current_user
from services.auth.models import TokenPayload
from services.permissions.enforcer import require_admin
from shared.db import to_uuid

router = APIRouter(tags=["admin"])


def _row_to_job(row: Any) -> dict[str, Any]:
    return {
        "id": str(to_uuid(row["id"])),
        "document_id": str(to_uuid(row["document_id"])) if row["document_id"] else None,
        "source_id": str(to_uuid(row["source_id"])) if row["source_id"] else None,
        "job_type": row["job_type"],
        "status": row["status"],
        "stage": row["stage"],
        "attempts": row["attempts"],
        "max_attempts": row["max_attempts"],
        "last_error": row["last_error"],
        "rabbit_message_id": row["rabbit_message_id"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


@router.get("/admin/jobs")
def admin_list_jobs(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
    status: str | None = None,
    job_type: str | None = None,
    stage: str | None = None,
    source_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    require_admin(user)
    filters = []
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if status:
        filters.append("status = :status")
        params["status"] = status
    if job_type:
        filters.append("job_type = :job_type")
        params["job_type"] = job_type
    if stage:
        filters.append("stage = :stage")
        params["stage"] = stage
    if source_id:
        filters.append("source_id = :source_id")
        params["source_id"] = source_id.hex
    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    with request.app.state.engine.begin() as conn:
        rows = (
            conn.execute(
                sa.text(f"""
                    SELECT id, document_id, source_id, job_type, status, stage,
                           attempts, max_attempts, last_error, rabbit_message_id,
                           created_at, updated_at
                    FROM pipeline_jobs {where}
                    ORDER BY created_at DESC
                    LIMIT :limit OFFSET :offset
                """),
                params,
            )
            .mappings()
            .all()
        )
        total = conn.execute(
            sa.text(f"SELECT COUNT(*) FROM pipeline_jobs {where}"),
            {k: v for k, v in params.items() if k not in ("limit", "offset")},
        ).scalar_one()
    return {"jobs": [_row_to_job(r) for r in rows], "total": total}


@router.get("/admin/jobs/{job_id}")
def admin_get_job(
    job_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    with request.app.state.engine.begin() as conn:
        row = (
            conn.execute(
                sa.text("""
                SELECT id, document_id, source_id, job_type, status, stage,
                       attempts, max_attempts, last_error, rabbit_message_id,
                       created_at, updated_at
                FROM pipeline_jobs WHERE id = :id
            """),
                {"id": job_id.hex},
            )
            .mappings()
            .first()
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _row_to_job(row)


@router.post("/admin/jobs/{job_id}/retry")
def admin_retry_job(
    job_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    with request.app.state.engine.begin() as conn:
        row = (
            conn.execute(
                sa.text("SELECT status FROM pipeline_jobs WHERE id = :id"),
                {"id": job_id.hex},
            )
            .mappings()
            .first()
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if row["status"] != "dead_letter":
            raise HTTPException(
                status_code=409,
                detail=f"Job is not dead-lettered (status={row['status']})",
            )
        conn.execute(
            sa.text("""
                UPDATE pipeline_jobs
                SET status = 'pending', attempts = 0, last_error = NULL,
                    locked_by = NULL, locked_at = NULL,
                    run_after = :now, updated_at = :now
                WHERE id = :id AND status = 'dead_letter'
            """),
            {"id": job_id.hex, "now": datetime.now(UTC)},
        )
    return {"retried": str(job_id)}
