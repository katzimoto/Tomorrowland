"""Comments router — deprecated.

Document comments have been migrated into annotations (document-level
annotations with position=NULL).  All endpoints return HTTP 410 Gone.
The file is preserved for one release cycle in case external clients
still POST to /documents/{id}/comments.

Migrated: 2026-05-22 — issue #487
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["comments"])


@router.get("/documents/{document_id}/comments")
def list_comments(document_id: UUID) -> None:
    raise HTTPException(status_code=410, detail="Comments migrated to annotations")


@router.post("/documents/{document_id}/comments", status_code=201)
def create_comment(document_id: UUID) -> None:
    raise HTTPException(status_code=410, detail="Comments migrated to annotations")


@router.patch("/documents/{document_id}/comments/{comment_id}")
def update_comment(document_id: UUID, comment_id: UUID) -> None:
    raise HTTPException(status_code=410, detail="Comments migrated to annotations")


@router.delete("/documents/{document_id}/comments/{comment_id}", status_code=204)
def delete_comment(document_id: UUID, comment_id: UUID) -> None:
    raise HTTPException(status_code=410, detail="Comments migrated to annotations")
