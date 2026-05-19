"""Vault export routes."""

from __future__ import annotations

import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from services.api.main import current_user
from services.auth.models import TokenPayload
from services.vault.service import VaultExportService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["vault"])


@router.post("/vault/export")
def export_vault(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
    group_id: str,
) -> StreamingResponse:
    """Export all documents in *group_id* as a zip of Markdown files.

    The caller must be a member of the requested group (or an admin).
    """
    group_uuid = UUID(group_id)
    if not user.is_admin and group_uuid not in user.groups:
        raise HTTPException(
            status_code=403,
            detail="You are not a member of the requested group",
        )

    with request.app.state.engine.begin() as connection:
        service = VaultExportService(connection)
        buf = service.export(group_uuid)

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="vault-{group_id}.zip"'},
    )


@router.get("/vault/topics")
def vault_topics(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> list[dict[str, Any]]:
    """Return a tag cloud (topics index) for all groups the caller belongs to.

    Each entry: ``{"tag": str, "document_count": int, "documents": [...]}``.
    Admin callers see topics across all groups (no group filter).
    """
    if not user.is_admin and not user.groups:
        return []

    with request.app.state.engine.begin() as connection:
        service = VaultExportService(connection)
        if user.is_admin:
            return [dict(entry) for entry in service.get_tag_index(allow_all=True)]

        seen: dict[str, dict[str, Any]] = {}
        for gid in user.groups:
            for entry in service.get_tag_index(gid):
                tag = str(entry["tag"])
                existing = seen.get(tag)
                if existing:
                    existing_docs: list[dict[str, str]] = list(existing["documents"])
                    existing_docs.extend(entry["documents"])
                    existing["document_count"] = len(existing_docs)
                    existing["documents"] = existing_docs
                else:
                    seen[tag] = dict(entry)
        return list(seen.values())
