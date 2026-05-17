from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from services.api._helpers import (
    _fmt_dt,
    _translation_score,
    related_docs_limit,
    require_expertise_enabled,
    require_related_docs_enabled,
)
from services.api.main import current_user
from services.api.schemas import PreviewResponse
from services.auth.models import TokenPayload
from services.auth.repository import AuthRepository
from services.documents.repository import (
    DocumentRepository,
    TranslationVersionRepository,
)
from services.intelligence.repository import IntelligenceRepository
from services.permissions.enforcer import assert_doc_access
from services.preview.service import PreviewService
from services.related.repository import RelatedRepository
from services.related.service import RelatedService
from services.search.factory import build_encoder
from services.search.qdrant import QdrantSearchClient
from shared.correlation import get_correlation_id
from shared.metrics import mime_family

logger = logging.getLogger(__name__)

router = APIRouter(tags=["documents"])


@router.get("/preview/{document_id}", response_model=PreviewResponse)
def preview(
    document_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
    translation_version_id: UUID | None = None,
    show_original: bool = False,
) -> PreviewResponse:
    with request.app.state.engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        assert_doc_access(document_id, user, auth_repo)

        preview_service = PreviewService(connection)
        result = preview_service.get_preview(
            document_id,
            user.sub,
            translation_version_id=translation_version_id,
            show_original=show_original,
        )
        if not result:
            request.app.state.metrics.preview_requests_total.labels("unknown", "failure").inc()
            raise HTTPException(status_code=404, detail="Document not found")

        request.app.state.metrics.preview_requests_total.labels(
            mime_family(result["mime_type"]), "success"
        ).inc()

        doc_repo = DocumentRepository(connection)
        doc_row = doc_repo.get_by_id(document_id)

        version_number: int | None = None
        is_latest_val: bool | None = None
        latest_document_id: str | None = None
        has_newer_version: bool | None = None
        if doc_row is not None:
            version_number = doc_row.version_number
            is_latest_val = doc_row.is_latest
            has_newer_version = not doc_row.is_latest
            if doc_row.is_latest:
                latest_document_id = str(doc_row.id)
            elif doc_row.version_family_id:
                family_map = doc_repo.get_family_current_doc_ids([doc_row.version_family_id])
                raw = family_map.get(doc_row.version_family_id)
                latest_document_id = str(raw) if raw else None

        return PreviewResponse(
            document_id=result["document_id"],
            title=result["title"],
            mime_type=result["mime_type"],
            translation_quality=result["translation_quality"],
            translation_score=_translation_score(result["translation_quality"]),
            metadata=result["metadata"],
            snippet=result["snippet"],
            view_count=result["view_count"],
            version_number=version_number,
            is_latest=is_latest_val,
            latest_document_id=latest_document_id,
            has_newer_version=has_newer_version,
        )


@router.get("/me/activity")
def me_activity(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
    skip: int = 0,
    limit: int = 50,
) -> list[dict[str, Any]]:
    with request.app.state.engine.begin() as connection:
        preview_service = PreviewService(connection)
        return preview_service.get_user_activity(user.sub, limit=limit, offset=skip)


@router.post("/documents/{document_id}/translate")
def request_translation(
    document_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    with request.app.state.engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        assert_doc_access(document_id, user, auth_repo)

        doc_repo = DocumentRepository(connection)
        doc = doc_repo.get_by_id(document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")

        version_repo = TranslationVersionRepository(connection)
        existing = version_repo.find_pending_or_running(document_id, doc.target_language)
        if existing:
            return {
                "document_id": str(document_id),
                "translation_version_id": str(existing["id"]),
                "status": existing["status"],
            }

        version = version_repo.create_version(
            document_id=document_id,
            label=f"Manual {doc.target_language}",
            quality="high",
            request_type="manual",
            requested_by_id=user.sub,
            target_language=doc.target_language,
        )
        doc_repo.update_translation_quality(document_id, "pending_high")

        return {
            "document_id": str(document_id),
            "translation_version_id": str(version["id"]),
            "status": version["status"],
        }


@router.get("/documents/{document_id}/translation-versions")
def list_translation_versions(
    document_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> list[dict[str, Any]]:
    with request.app.state.engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        assert_doc_access(document_id, user, auth_repo)

        version_repo = TranslationVersionRepository(connection)
        versions = version_repo.list_versions(document_id)
        return [
            {
                "version_id": str(v["id"]),
                "version_number": v["version_number"],
                "label": v["label"],
                "quality": v["quality"],
                "status": v["status"],
                "target_language": v["target_language"],
                "requested_at": _fmt_dt(v["requested_at"]),
            }
            for v in versions
        ]


@router.get("/documents/{document_id}/versions")
def list_document_versions(
    document_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> list[dict[str, Any]]:
    with request.app.state.engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        assert_doc_access(document_id, user, auth_repo)

        doc_repo = DocumentRepository(connection)
        versions = doc_repo.list_versions_in_family(document_id)
        return [
            {
                "document_id": str(v.id),
                "version_number": v.version_number,
                "is_latest": v.is_latest,
                "title": v.title,
                "created_at": _fmt_dt(v.created_at),
            }
            for v in versions
        ]


@router.get("/documents/{document_id}/summary")
def get_summary(
    document_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    with request.app.state.engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        assert_doc_access(document_id, user, auth_repo)

        intelligence_repo = IntelligenceRepository(connection)
        summary = intelligence_repo.get_summary(document_id)
        if summary is None:
            raise HTTPException(status_code=404, detail="Summary not found")
        return {
            "document_id": str(document_id),
            "summary": summary["summary"],
            "model": summary["model"],
            "updated_at": _fmt_dt(summary["updated_at"]),
        }


@router.get("/documents/{document_id}/entities")
def get_entities(
    document_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> list[dict[str, Any]]:
    with request.app.state.engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        assert_doc_access(document_id, user, auth_repo)

        intelligence_repo = IntelligenceRepository(connection)
        entities = intelligence_repo.get_entities(document_id)
        return [
            {
                "id": str(e["id"]),
                "name": e["name"],
                "type": e["type"],
                "frequency": e["frequency"],
            }
            for e in entities
        ]


@router.get("/documents/{document_id}/tags")
def get_tags(
    document_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    with request.app.state.engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        assert_doc_access(document_id, user, auth_repo)

        intelligence_repo = IntelligenceRepository(connection)
        tags = intelligence_repo.get_tags(document_id)
        return {"document_id": str(document_id), "tags": tags}


@router.get("/documents/{document_id}/related")
def related_documents(
    document_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    with request.app.state.engine.begin() as connection:
        require_related_docs_enabled(connection, request.app.state.settings)
        auth_repo = AuthRepository(connection)
        assert_doc_access(document_id, user, auth_repo)

        doc_repo = DocumentRepository(connection)
        doc = doc_repo.get_by_id(document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")

        group_ids = [str(group_id) for group_id in user.groups]
        if not group_ids:
            return {"document_id": str(document_id), "related": []}

        encoder = build_encoder(request.app.state.settings)
        qdrant_client = request.app.state.qdrant_client or QdrantSearchClient(
            url=request.app.state.settings.qdrant_url,
            dimension=encoder.dimension,
        )
        service = RelatedService(
            repository=RelatedRepository(connection),
            qdrant_client=qdrant_client,
            encoder=encoder,
        )
        try:
            related = service.related_documents(
                doc=doc,
                group_ids=group_ids,
                limit=related_docs_limit(connection),
            )
        except Exception as exc:
            logger.warning(
                "Related documents degraded route=/documents/{document_id}/related "
                "stage=vector_search error_type=%s correlation_id=%s",
                exc.__class__.__name__,
                get_correlation_id(),
            )
            related = []
        return {"document_id": str(document_id), "related": related}


@router.get("/expertise")
def expertise(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
    topic: Annotated[str, Query(min_length=1)],
) -> list[dict[str, Any]]:
    topic = topic.strip()
    if not topic:
        raise HTTPException(status_code=422, detail="Topic must not be empty")
    with request.app.state.engine.begin() as connection:
        require_expertise_enabled(connection, request.app.state.settings)
        if not user.groups:
            return []
        if user.is_admin:
            group_ids: list[str] = []
        else:
            _auth_repo = AuthRepository(connection)
            _effective = set(user.groups) | set(_auth_repo.get_effective_group_ids(user.groups))
            group_ids = [str(g) for g in _effective]
        encoder = build_encoder(request.app.state.settings)
        qdrant_client = request.app.state.qdrant_client or QdrantSearchClient(
            url=request.app.state.settings.qdrant_url,
            dimension=encoder.dimension,
        )
        service = RelatedService(
            repository=RelatedRepository(connection),
            qdrant_client=qdrant_client,
            encoder=encoder,
        )
        try:
            return service.expertise(topic=topic, group_ids=group_ids)
        except Exception as exc:
            logger.warning(
                "Expertise degraded route=/expertise stage=vector_search "
                "error_type=%s correlation_id=%s",
                exc.__class__.__name__,
                get_correlation_id(),
            )
            return []


@router.get("/download/{document_id}")
def download(
    document_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> StreamingResponse:
    with request.app.state.engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        assert_doc_access(document_id, user, auth_repo)

        doc_repo = DocumentRepository(connection)
        doc = doc_repo.get_by_id(document_id)
        if doc is None or doc.path is None:
            request.app.state.metrics.download_requests_total.labels("failure").inc()
            raise HTTPException(status_code=404, detail="Document not found")

    files_root = request.app.state.settings.files_root.resolve()
    target = Path(doc.path).resolve()
    if not target.is_relative_to(files_root):
        request.app.state.metrics.download_requests_total.labels("failure").inc()
        raise HTTPException(status_code=400, detail="Invalid file path")
    request.app.state.metrics.download_requests_total.labels("success").inc()

    def file_iterator() -> Iterator[bytes]:
        with target.open("rb") as f:
            while chunk := f.read(8192):
                yield chunk

    return StreamingResponse(
        file_iterator(),
        media_type=doc.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{target.name}"'},
    )
