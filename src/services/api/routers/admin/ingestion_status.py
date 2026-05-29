from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from services.api._helpers import _fmt_dt
from services.api.main import current_user
from services.api.schemas import (
    DocumentTraceResponse,
    IngestionStatusResponse,
)
from services.auth.models import TokenPayload
from services.permissions.enforcer import require_admin
from services.pipeline.jobs import PipelineJobRepository

router = APIRouter(tags=["admin"])


def _job_to_dict(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(job["id"]),
        "document_id": str(job["document_id"]),
        "source_id": str(job["source_id"]),
        "document_title": job["document_title"],
        "source_name": job["source_name"],
        "job_type": job["job_type"],
        "status": job["status"],
        "stage": job["stage"],
        "attempts": job["attempts"],
        "max_attempts": job["max_attempts"],
        "last_error": job["last_error"],
        "created_at": _fmt_dt(job["created_at"]),
        "updated_at": _fmt_dt(job["updated_at"]),
    }


def _trace_job_to_dict(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(job["id"]),
        "job_type": job["job_type"],
        "status": job["status"],
        "stage": job["stage"],
        "attempts": job["attempts"],
        "max_attempts": job["max_attempts"],
        "last_error": job["last_error"],
        "created_at": _fmt_dt(job["created_at"]),
        "updated_at": _fmt_dt(job["updated_at"]),
    }


@router.get("/admin/ingestion/status", response_model=IngestionStatusResponse)
def admin_list_ingestion_status(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
    status: str | None = None,
    source_id: UUID | None = None,
    since: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    require_admin(user)
    with request.app.state.engine.begin() as conn:
        repo = PipelineJobRepository(conn)
        rows, total, summary = repo.list_ingestion_status(
            status=status,
            source_id=source_id,
            since=since,
            limit=limit,
            offset=offset,
        )
    return {
        "jobs": [_job_to_dict(r) for r in rows],
        "total": total,
        "summary": summary,
    }


@router.get("/admin/ingestion/status/{document_id}", response_model=DocumentTraceResponse)
def admin_document_trace(
    document_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    with request.app.state.engine.begin() as conn:
        repo = PipelineJobRepository(conn)
        document_title, source_name, jobs = repo.list_document_trace(document_id)
    if not jobs:
        raise HTTPException(status_code=404, detail="No pipeline jobs found for this document")
    return {
        "document_id": str(document_id),
        "document_title": document_title,
        "source_name": source_name,
        "jobs": [_trace_job_to_dict(j) for j in jobs],
    }
