from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request

from services.api._helpers import _fmt_dt
from services.api.main import current_user
from services.auth.models import TokenPayload
from services.documents.repository import DocumentRepository
from services.extraction.registry import ExtractorRegistry
from services.intelligence.ollama_client import OllamaClient
from services.intelligence.repository import IntelligenceRepository
from services.intelligence.worker import IntelligenceWorker
from services.permissions.enforcer import require_admin
from services.search.elastic import ElasticsearchSearchClient
from shared.correlation import get_correlation_id
from shared.db import to_uuid

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])


@router.post("/admin/intelligence/{doc_id}/trigger")
def trigger_intelligence(
    doc_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        doc_repo = DocumentRepository(connection)
        doc = doc_repo.get_by_id(doc_id)
        if doc is None or doc.path is None:
            raise HTTPException(status_code=404, detail="Document not found")

        extractor = ExtractorRegistry()
        text = extractor.extract(Path(doc.path), doc.mime_type)

        try:
            intelligence_repo = IntelligenceRepository(connection)
            ollama_client = request.app.state.ollama_client or OllamaClient(
                base_url=request.app.state.settings.ollama_url,
                model=request.app.state.settings.ollama_model,
            )
            es_client = request.app.state.es_client or ElasticsearchSearchClient(
                hosts=[request.app.state.settings.elastic_url]
            )
            worker = IntelligenceWorker(
                repository=intelligence_repo,
                ollama_client=ollama_client,
                es_client=es_client,
            )
            worker.process_document(doc_id, text)
        except Exception as exc:
            logger.warning(
                "Intelligence trigger degraded route=/admin/intelligence/%s/trigger "
                "error_type=%s correlation_id=%s",
                doc_id,
                exc.__class__.__name__,
                get_correlation_id(),
            )

        return {"doc_id": str(doc_id), "triggered": True}


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
                "doc_id": str(doc.id),
                "title": doc.title,
                "mime_type": doc.mime_type,
                "status": doc.status,
            }
            for doc in pending
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
