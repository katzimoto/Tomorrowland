"""Preview manifest API (#539) — render status, artifacts, admin rerender.

Sibling of the existing ``GET /preview/{document_id}`` snippet endpoint; that
contract is untouched. Artifacts are addressed by opaque IDs resolved through
the DB row's files map — no client-supplied filenames, no paths in responses.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from services.api.main import current_user
from services.auth.models import TokenPayload
from services.auth.repository import AuthRepository
from services.documents.repository import DocumentRepository
from services.permissions.enforcer import assert_doc_access, require_admin
from services.pipeline.jobs import PipelineJobRepository
from services.preview.artifact_repository import (
    PreviewArtifactRepository,
    PreviewArtifactRow,
)
from services.preview.artifact_store import PreviewArtifactStore
from services.preview.manifest import (
    PENDING_RETRY_AFTER_MS,
    build_base_manifest,
    classify_kind,
    immediate_renderer,
    renders_via_worker,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["preview"])

_PREVIEW_JOB_TYPE = "preview_render"

_HTML_ARTIFACT_CSP = "default-src 'none'; img-src data:; style-src 'unsafe-inline'"


class ManifestError(BaseModel):
    category: str
    detail: str | None = None


class PreviewManifestResponse(BaseModel):
    document_id: str
    cache_key: str | None = None
    kind: str
    renderer: str
    status: str
    error: ManifestError | None = None
    generated_at: str | None = None
    retry_after_ms: int | None = None
    navigation: dict[str, Any]
    artifacts: list[dict[str, Any]]
    email: dict[str, Any] | None = None
    office: dict[str, Any] | None = None
    evidence: dict[str, Any]


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_response(row: PreviewArtifactRow, *, is_admin: bool) -> PreviewManifestResponse:
    manifest = dict(row.manifest or {})
    manifest.setdefault("document_id", str(row.document_id))
    manifest.setdefault("cache_key", f"sha256:{row.content_sha256}" if row.content_sha256 else None)
    manifest.setdefault("kind", "email" if row.renderer == "email" else "text")
    manifest.setdefault("renderer", row.renderer)
    manifest.setdefault("navigation", {"unit": "none", "count": 0, "items": []})
    manifest.setdefault("artifacts", [])
    manifest.setdefault(
        "evidence",
        {"supports_text_search": True, "anchor_unit": "body", "regions_available": False},
    )
    manifest["status"] = row.status
    if row.status == "failed" and row.error_category:
        manifest["error"] = {
            "category": row.error_category,
            "detail": row.error_detail if is_admin else None,
        }
    else:
        manifest["error"] = None
    if row.status in ("pending", "running"):
        manifest["retry_after_ms"] = PENDING_RETRY_AFTER_MS
    return PreviewManifestResponse(**manifest)


def _dispatch_render_job(request: Request, document_id: UUID, source_id: UUID) -> None:
    """Enqueue the preview_render job row and best-effort publish to RabbitMQ.

    Publish failures are tolerated: the job row remains and an operator (or a
    broker recovery) can still drive the render; the manifest stays pending
    rather than erroring the preview pane.
    """
    settings = request.app.state.settings
    with request.app.state.engine.begin() as connection:
        job_repo = PipelineJobRepository(connection)
        job_id = job_repo.enqueue_document(document_id, source_id, job_type=_PREVIEW_JOB_TYPE)

    if not settings.rabbitmq_enabled:
        return
    from shared.rabbit import RabbitClient, RabbitConnectionError

    rabbit = getattr(request.app.state, "rabbit", None) or RabbitClient(
        settings.rabbitmq_url, enabled=True
    )
    try:
        rabbit.connect()
        rabbit.declare_topology()
        rabbit.publish(
            "document.preview.requested",
            {
                "job_id": str(job_id),
                "document_id": str(document_id),
                "source_id": str(source_id),
                "attempt": 1,
                "pipeline_version": "v1",
            },
        )
    except RabbitConnectionError as exc:
        logger.warning(
            "preview render publish skipped (broker unreachable): document_id=%s error=%s",
            document_id,
            exc,
        )
    finally:
        rabbit.close()


@router.get("/preview/{document_id}/manifest", response_model=PreviewManifestResponse)
def preview_manifest(
    document_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> PreviewManifestResponse:
    settings = request.app.state.settings
    with request.app.state.engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        assert_doc_access(document_id, user, auth_repo)
        doc = DocumentRepository(connection).get_by_id(document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")
        sha = doc.content_sha256 or ""
        repo = PreviewArtifactRepository(connection)
        row = repo.get(document_id, sha)
        if row is not None:
            return _row_to_response(row, is_admin=user.is_admin)

        kind = classify_kind(doc.mime_type)
        if renders_via_worker(doc.mime_type) and settings.enable_preview_render:
            row = repo.create_pending(document_id, sha, renderer="email")
        else:
            manifest = build_base_manifest(
                document_id=str(document_id),
                content_sha256=sha,
                kind=kind,
                renderer=immediate_renderer(kind),
                status="ready",
                generated_at=_utc_now_iso(),
            )
            repo.create_pending(document_id, sha, renderer=manifest["renderer"])
            repo.mark_rendered(document_id, sha, status="ready", manifest=manifest, files={})
            row = repo.get(document_id, sha)
            assert row is not None

    if row.status == "pending" and row.renderer == "email":
        _dispatch_render_job(request, document_id, doc.source_id)
    return _row_to_response(row, is_admin=user.is_admin)


@router.get("/preview/{document_id}/artifact/{artifact_id}")
def preview_artifact(
    document_id: UUID,
    artifact_id: str,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> FileResponse:
    with request.app.state.engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        assert_doc_access(document_id, user, auth_repo)
        doc = DocumentRepository(connection).get_by_id(document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")
        sha = doc.content_sha256 or ""
        row = PreviewArtifactRepository(connection).get(document_id, sha)

    if row is None or row.status not in ("ready", "partial") or not row.files:
        raise HTTPException(status_code=404, detail="Preview artifact not found")
    filename = row.files.get(artifact_id)
    if filename is None:
        raise HTTPException(status_code=404, detail="Preview artifact not found")

    store = PreviewArtifactStore(request.app.state.settings.files_root)
    path = store.resolve(document_id, sha, filename)
    if path is None:
        raise HTTPException(status_code=404, detail="Preview artifact not found")

    content_type = "application/octet-stream"
    for entry in (row.manifest or {}).get("artifacts", []):
        if entry.get("id") == artifact_id:
            content_type = str(entry.get("content_type") or content_type)
            break

    headers = {
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, max-age=86400",
        "ETag": f'"{sha}"' if sha else f'"{artifact_id}"',
        "Content-Disposition": "inline",
    }
    if content_type == "text/html":
        headers["Content-Security-Policy"] = _HTML_ARTIFACT_CSP
    return FileResponse(path, media_type=content_type, headers=headers)


@router.post("/admin/preview/{document_id}/rerender")
def admin_rerender_preview(
    document_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, str]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        doc = DocumentRepository(connection).get_by_id(document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")
        sha = doc.content_sha256 or ""
        PreviewArtifactRepository(connection).delete(document_id, sha)

    store = PreviewArtifactStore(request.app.state.settings.files_root)
    store.delete(document_id, sha)
    logger.info("preview rerender requested: document_id=%s admin=%s", document_id, user.sub)
    return {"status": "pending"}
