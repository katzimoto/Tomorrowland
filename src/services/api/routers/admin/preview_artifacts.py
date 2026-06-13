"""Admin endpoints for preview artifact orphan cleanup (#749).

GET  /admin/preview/artifacts/orphans  — dry-run scan (no deletions)
POST /admin/preview/artifacts/sweep    — execute orphan cleanup

Both endpoints require admin privileges and never expose internal filesystem
paths in responses or logs.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from services.api.main import current_user
from services.auth.models import TokenPayload
from services.permissions.enforcer import require_admin
from services.preview.artifact_repository import PreviewArtifactRepository
from services.preview.artifact_store import PreviewArtifactStore
from shared.request_context import get_request_id

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])


class PreviewArtifactSweepResponse(BaseModel):
    dry_run: bool
    scanned: int
    valid: int
    orphaned: int
    deleted: int
    bytes_reclaimable: int | None = None
    bytes_reclaimed: int | None = None
    error_count: int


def _build_valid_keys(engine: Any) -> set[tuple[str, str]]:
    with engine.begin() as connection:
        return PreviewArtifactRepository(connection).list_all_keys()


@router.get(
    "/admin/preview/artifacts/orphans",
    response_model=PreviewArtifactSweepResponse,
)
def admin_preview_artifacts_orphans(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> PreviewArtifactSweepResponse:
    """Dry-run scan: report orphaned preview artifact directories without deleting."""
    require_admin(user)
    request_id = get_request_id()
    valid_keys = _build_valid_keys(request.app.state.engine)
    store = PreviewArtifactStore(request.app.state.settings.files_root)
    report = store.scan_orphans(valid_keys)
    logger.info(
        "preview artifact orphan scan (dry-run): "
        "request_id=%s admin=%s scanned=%d valid=%d orphaned=%d bytes_orphaned=%d",
        request_id,
        user.sub,
        report["scanned"],
        report["valid"],
        report["orphaned"],
        report["bytes_orphaned"],
    )
    return PreviewArtifactSweepResponse(
        dry_run=True,
        scanned=report["scanned"],
        valid=report["valid"],
        orphaned=report["orphaned"],
        deleted=0,
        bytes_reclaimable=report["bytes_orphaned"],
        error_count=0,
    )


@router.post(
    "/admin/preview/artifacts/sweep",
    response_model=PreviewArtifactSweepResponse,
)
def admin_preview_artifacts_sweep(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> PreviewArtifactSweepResponse:
    """Execute preview artifact orphan cleanup.

    Deletes only directories under the preview artifact root whose
    ``(document_id, content_sha256)`` key has no live row in
    ``document_preview_artifacts``.  Never touches original uploaded files or
    extracted document payloads.
    """
    require_admin(user)
    request_id = get_request_id()
    valid_keys = _build_valid_keys(request.app.state.engine)
    store = PreviewArtifactStore(request.app.state.settings.files_root)

    # Scan first so we can report bytes_reclaimed.
    scan = store.scan_orphans(valid_keys)
    error_count = 0
    deleted = 0
    try:
        deleted = store.sweep_orphans(valid_keys)
    except Exception as exc:
        error_count = 1
        logger.error(
            "preview artifact sweep encountered an error: request_id=%s admin=%s error_type=%s",
            request_id,
            user.sub,
            type(exc).__name__,
        )

    logger.info(
        "preview artifact orphan sweep: "
        "request_id=%s admin=%s scanned=%d valid=%d orphaned=%d deleted=%d bytes=%d errors=%d",
        request_id,
        user.sub,
        scan["scanned"],
        scan["valid"],
        scan["orphaned"],
        deleted,
        scan["bytes_orphaned"],
        error_count,
    )
    return PreviewArtifactSweepResponse(
        dry_run=False,
        scanned=scan["scanned"],
        valid=scan["valid"],
        orphaned=scan["orphaned"],
        deleted=deleted,
        bytes_reclaimed=scan["bytes_orphaned"],
        error_count=error_count,
    )
