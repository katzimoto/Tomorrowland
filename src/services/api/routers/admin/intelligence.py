from __future__ import annotations

import logging
from typing import Annotated, Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request

from services.api._helpers import _fmt_dt
from services.api.main import current_user
from services.auth.models import TokenPayload
from services.documents.repository import DocumentRepository
from services.intelligence.repository import IntelligenceRepository
from services.intelligence.worker import IntelligenceWorker
from services.permissions.enforcer import require_admin
from services.pipeline.jobs import PipelineJobRepository
from shared.correlation import get_correlation_id
from shared.db import to_uuid

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])


@router.post("/admin/intelligence/{document_id}/trigger")
def trigger_intelligence(
    document_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        doc_repo = DocumentRepository(connection)
        doc = doc_repo.get_by_id(document_id)
        if doc is None or doc.path is None:
            raise HTTPException(status_code=404, detail="Document not found")

        payload = PipelineJobRepository(connection).get_payload(document_id)
        text = (payload.get("content_text", "") if payload else None) or ""

        try:
            intelligence_repo = IntelligenceRepository(connection)
            ollama_client = request.app.state.llm_provider
            worker = IntelligenceWorker(
                repository=intelligence_repo,
                ollama_client=ollama_client,
                utility_model=request.app.state.settings.effective_utility_model,
            )
            worker.process_document(document_id, text)
        except Exception as exc:
            logger.warning(
                "Intelligence trigger degraded route=/admin/intelligence/%s/trigger "
                "error_type=%s correlation_id=%s",
                document_id,
                exc.__class__.__name__,
                get_correlation_id(),
            )

        return {"document_id": str(document_id), "triggered": True}


@router.post("/admin/intelligence/{document_id}/summary/regenerate")
def regenerate_summary(
    document_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    """Regenerate the summary for a document. Admin-only, idempotent."""
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        doc_repo = DocumentRepository(connection)
        doc = doc_repo.get_by_id(document_id)
        if doc is None or doc.path is None:
            raise HTTPException(status_code=404, detail="Document not found")

        payload = PipelineJobRepository(connection).get_payload(document_id)
        text = (payload.get("content_text", "") if payload else None) or ""

        try:
            intelligence_repo = IntelligenceRepository(connection)
            ollama_client = request.app.state.llm_provider
            worker = IntelligenceWorker(
                repository=intelligence_repo,
                ollama_client=ollama_client,
                utility_model=request.app.state.settings.effective_utility_model,
            )
            worker._summarize(document_id, text)
            logger.info(
                "Summary regenerated document_id=%s user_id=%s correlation=%s",
                document_id,
                user.sub,
                get_correlation_id(),
            )
        except Exception as exc:
            logger.warning(
                "Summary regeneration degraded route=/admin/intelligence/%s/summary/regenerate "
                "error_type=%s correlation_id=%s",
                document_id,
                exc.__class__.__name__,
                get_correlation_id(),
            )

        return {"document_id": str(document_id), "regenerated": True}


@router.get("/admin/enrichment-queue")
def enrichment_queue(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> list[dict[str, Any]]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        doc_repo = DocumentRepository(connection)
        pending = doc_repo.list_pending_enrichment()
        return [
            {
                "document_id": str(doc.id),
                "title": doc.title,
                "mime_type": doc.mime_type,
                "status": doc.status,
            }
            for doc in pending
        ]


@router.get("/admin/enrich-jobs")
def admin_list_enrich_jobs(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> list[dict[str, Any]]:
    """List all enrich_document jobs with their current state and priority."""
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        rows = connection.execute(
            sa.text("""
                SELECT pj.id, pj.document_id, pj.status, pj.priority,
                       pj.attempts, pj.max_attempts, pj.stage, pj.last_error,
                       pj.run_after, pj.locked_by, pj.created_at, pj.updated_at,
                       d.title AS document_title
                FROM pipeline_jobs pj
                LEFT JOIN documents d ON d.id = pj.document_id
                WHERE pj.job_type = 'enrich_document'
                ORDER BY pj.priority DESC, pj.created_at ASC
            """),
        ).mappings()
        return [
            {
                "id": str(to_uuid(row["id"])),
                "document_id": str(to_uuid(row["document_id"])),
                "document_title": row["document_title"],
                "status": row["status"],
                "priority": row["priority"],
                "attempts": row["attempts"],
                "max_attempts": row["max_attempts"],
                "stage": row["stage"],
                "last_error": row["last_error"],
                "run_after": _fmt_dt(row["run_after"]) if row["run_after"] else None,
                "locked_by": row["locked_by"],
                "created_at": _fmt_dt(row["created_at"]),
                "updated_at": _fmt_dt(row["updated_at"]),
            }
            for row in rows
        ]


@router.get("/admin/activity")
def admin_list_activity(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> list[dict[str, Any]]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        rows = connection.execute(
            sa.text("""
                SELECT id, user_id, action, resource_type, resource_id, details, created_at
                FROM audit_log ORDER BY created_at DESC LIMIT 100
                """)
        ).mappings()
        return [
            {
                "id": str(to_uuid(row["id"])),
                "user_id": str(to_uuid(row["user_id"])) if row["user_id"] else None,
                "action": row["action"],
                "resource_type": row["resource_type"],
                "resource_id": row["resource_id"],
                "details": row["details"],
                "created_at": _fmt_dt(row["created_at"]),
            }
            for row in rows
        ]
