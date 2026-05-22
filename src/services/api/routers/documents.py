from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

import sqlalchemy as sa
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
from services.api.schemas import DocumentRelationshipInfo, PreviewResponse
from services.auth.models import TokenPayload
from services.auth.repository import AuthRepository
from services.documents.models import UserDocumentTagCreate
from services.documents.repository import (
    DocumentRelationshipRepository,
    DocumentRepository,
    TranslationVersionRepository,
    UserDocumentTagRepository,
)
from services.intelligence.repository import IntelligenceRepository
from services.permissions.enforcer import assert_doc_access
from services.pipeline.jobs import PipelineJobRepository
from services.preview.service import PreviewService
from services.related.repository import RelatedRepository
from services.related.service import RelatedService
from services.search.factory import build_encoder
from services.search.qdrant import QdrantSearchClient
from shared.correlation import get_correlation_id
from shared.db import db_uuid
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

        rel_repo = DocumentRelationshipRepository(connection)
        raw_rels = rel_repo.get_relationships(document_id)
        relationships = [
            DocumentRelationshipInfo(
                direction=r["direction"],
                relationship_type=r["relationship_type"],
                other_document_id=r["other_document_id"],
                title=r["title"],
                path_in_parent=r["path_in_parent"],
            )
            for r in raw_rels
        ] or None

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
            source_language=doc_row.source_language if doc_row else None,
            target_language=doc_row.target_language if doc_row else None,
            status=doc_row.status if doc_row else None,
            content_sha256=doc_row.content_sha256 if doc_row else None,
            created_at=doc_row.created_at.isoformat() if doc_row else None,
            updated_at=doc_row.updated_at.isoformat() if doc_row else None,
            relationships=relationships,
        )


@router.get("/documents/{document_id}/text")
def get_document_text(
    document_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
    translation_version_id: UUID | None = None,
    show_original: bool = False,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=10000, ge=1, le=100000),
) -> dict[str, Any]:
    with request.app.state.engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        assert_doc_access(document_id, user, auth_repo)

        doc_repo = DocumentRepository(connection)
        if doc_repo.get_by_id(document_id) is None:
            raise HTTPException(status_code=404, detail="Document not found")

        preview_service = PreviewService(connection)
        full_text = preview_service.get_full_text(
            document_id,
            translation_version_id=translation_version_id,
            show_original=show_original,
        )

        total_length = len(full_text)
        sliced = full_text[offset : offset + limit] if offset < total_length else ""
        truncated = (offset + limit) < total_length

        return {
            "text": sliced,
            "total_length": total_length,
            "offset": offset,
            "limit": limit,
            "truncated": truncated,
        }


@router.get("/me/activity")
def me_activity(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
    skip: int = Query(default=0, ge=0, le=10000),
    limit: int = Query(default=50, ge=1, le=200),
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

        job_repo = PipelineJobRepository(connection)
        job_repo.enqueue_document(
            document_id=document_id,
            source_id=doc.source_id,
            job_type="enrich_document",
        )

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
        if versions:
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

        # Fallback: synthesize a version from document_payloads for documents
        # processed before the version-creation code was deployed.
        payload_row = (
            connection.execute(
                sa.text("""
                SELECT dp.translated_text, dp.updated_at,
                       d.translation_quality, d.target_language
                FROM document_payloads dp
                JOIN documents d ON d.id = dp.document_id
                WHERE dp.document_id = :document_id
                  AND dp.translated_text IS NOT NULL
                  AND dp.translated_text != ''
                """),
                {"document_id": db_uuid(document_id)},
            )
            .mappings()
            .first()
        )
        if payload_row:
            return [
                {
                    "version_id": str(document_id),
                    "version_number": 1,
                    "label": "Ingestion",
                    "quality": payload_row["translation_quality"] or "fast",
                    "status": "available",
                    "target_language": payload_row["target_language"] or "en",
                    "requested_at": _fmt_dt(payload_row["updated_at"]),
                }
            ]

        return []


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
            "summary_bullets": summary.get("summary_bullets"),
            "summary_status": summary.get("status", "available"),
            "summary_language": summary.get("language"),
            "summary_document_type": summary.get("document_type"),
            "summary_source_text": summary.get("source_text"),
            "summary_is_stale": False,
            "summary_error_summary": (
                summary.get("error_summary") if summary.get("status") == "failed" else None
            ),
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


@router.get("/documents/{document_id}/key_points")
def get_key_points(
    document_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    with request.app.state.engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        assert_doc_access(document_id, user, auth_repo)

        intelligence_repo = IntelligenceRepository(connection)
        key_points = intelligence_repo.get_key_points(document_id)
        return {"document_id": str(document_id), "key_points": key_points}


@router.get("/documents/{document_id}/intelligence")
def get_intelligence(
    document_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    with request.app.state.engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        assert_doc_access(document_id, user, auth_repo)

        intelligence_repo = IntelligenceRepository(connection)
        summary = intelligence_repo.get_summary(document_id)
        key_points = intelligence_repo.get_key_points(document_id)
        entities = intelligence_repo.get_entities(document_id)
        tags = intelligence_repo.get_tags(document_id)

        result: dict[str, Any] = {"document_id": str(document_id)}
        if summary is not None:
            result["summary"] = summary["summary"]
            result["summary_model"] = summary["model"]
            result["summary_updated_at"] = _fmt_dt(summary["updated_at"])
            result["summary_bullets"] = summary.get("summary_bullets")
            result["summary_status"] = summary.get("status", "available")
            result["summary_language"] = summary.get("language")
            result["summary_document_type"] = summary.get("document_type")
            result["summary_source_text"] = summary.get("source_text")
            result["summary_is_stale"] = False
            result["summary_error_summary"] = (
                summary.get("error_summary") if summary.get("status") == "failed" else None
            )
        result["key_points"] = key_points
        result["entities"] = [
            {
                "id": str(e["id"]),
                "name": e["name"],
                "type": e["type"],
                "frequency": e["frequency"],
            }
            for e in entities
        ]
        result["tags"] = tags
        return result


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

        raw_group_ids = [str(g) for g in user.groups]
        is_admin = user.is_admin or request.app.state.admins_group_id in raw_group_ids
        if is_admin:
            group_ids: list[str] = []
        elif raw_group_ids:
            _effective = set(user.groups) | set(auth_repo.get_effective_group_ids(user.groups))
            group_ids = [str(g) for g in _effective]
        else:
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
                allow_all=is_admin,
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
    topic: Annotated[str, Query(min_length=1, max_length=500)],
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
            return service.expertise(topic=topic, group_ids=group_ids, allow_all=user.is_admin)
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

    file_size = target.stat().st_size
    range_header = request.headers.get("Range")

    if range_header:
        try:
            unit, ranges = range_header.split("=", 1)
            if unit.strip() != "bytes":
                raise ValueError("unsupported unit")
            start_str, end_str = ranges.split("-", 1)
            start = int(start_str) if start_str else 0
            end = int(end_str) if end_str else file_size - 1
        except (ValueError, AttributeError):
            raise HTTPException(status_code=416, detail="Invalid Range header") from None

        if start >= file_size or end >= file_size or start > end:
            raise HTTPException(
                status_code=416,
                detail="Range Not Satisfiable",
                headers={"Content-Range": f"bytes */{file_size}"},
            )

        length = end - start + 1

        def range_iterator() -> Iterator[bytes]:
            with target.open("rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(8192, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return StreamingResponse(
            range_iterator(),
            status_code=206,
            media_type=doc.mime_type,
            headers={
                "Content-Disposition": f'inline; filename="{target.name}"',
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Content-Length": str(length),
                "Accept-Ranges": "bytes",
                "X-Content-Type-Options": "nosniff",
            },
        )

    def file_iterator() -> Iterator[bytes]:
        with target.open("rb") as f:
            while chunk := f.read(8192):
                yield chunk

    return StreamingResponse(
        file_iterator(),
        media_type=doc.mime_type,
        headers={
            "Content-Disposition": f'inline; filename="{target.name}"',
            "Content-Length": str(file_size),
            "Accept-Ranges": "bytes",
            "X-Content-Type-Options": "nosniff",
        },
    )


# ---------------------------------------------------------------------------
# User document tags
# ---------------------------------------------------------------------------


@router.get("/documents/{document_id}/user-tags")
def list_user_tags(
    document_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    with request.app.state.engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        assert_doc_access(document_id, user, auth_repo)

        tag_repo = UserDocumentTagRepository(connection)
        tags = tag_repo.list_tags(document_id, user.sub)
        return {
            "document_id": str(document_id),
            "tags": [
                {
                    "id": str(t.id),
                    "tag": t.tag,
                    "visibility": t.visibility,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "owned_by_me": t.user_id == user.sub,
                }
                for t in tags
            ],
        }


@router.post("/documents/{document_id}/user-tags", status_code=201)
def create_user_tag(
    document_id: UUID,
    body: UserDocumentTagCreate,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    with request.app.state.engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        assert_doc_access(document_id, user, auth_repo)

        tag_repo = UserDocumentTagRepository(connection)
        try:
            tag = tag_repo.create_tag(
                document_id=document_id,
                user_id=user.sub,
                tag=body.tag,
                is_private=body.visibility == "private",
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "id": str(tag.id),
            "tag": tag.tag,
            "visibility": tag.visibility,
            "created_at": tag.created_at.isoformat() if tag.created_at else None,
            "owned_by_me": True,
        }


@router.delete("/documents/{document_id}/user-tags/{tag_id}", status_code=204)
def delete_user_tag(
    document_id: UUID,
    tag_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> None:
    with request.app.state.engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        assert_doc_access(document_id, user, auth_repo)

        tag_repo = UserDocumentTagRepository(connection)
        try:
            found = tag_repo.delete_tag(tag_id, user.sub, user.is_admin)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        if not found:
            raise HTTPException(status_code=404, detail="Tag not found")
