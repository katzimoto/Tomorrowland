from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from services.api._helpers import _fmt_dt
from services.api.main import current_user
from services.auth.models import TokenPayload
from services.auth.repository import AuthRepository
from services.comments.models import CommentCreateRequest, CommentUpdateRequest
from services.comments.repository import CommentRepository
from services.permissions.enforcer import assert_doc_access
from shared.db import to_uuid

router = APIRouter(tags=["comments"])


@router.get("/documents/{document_id}/comments")
def list_comments(
    document_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
    skip: int = Query(default=0, ge=0, le=10000),
    limit: int = Query(default=50, ge=1, le=200),
    sort: str = Query(default="newest", max_length=10),
) -> dict[str, Any]:
    with request.app.state.engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        assert_doc_access(document_id, user, auth_repo)

        repo = CommentRepository(connection)
        comments = repo.list_comments(document_id, skip=skip, limit=limit, sort=sort)
        total = repo.count_comments(document_id)
        return {
            "document_id": str(document_id),
            "comments": [
                {
                    "id": str(to_uuid(c["id"])),
                    "author_id": str(to_uuid(c["author_id"])),
                    "author_display_name": c["author_display_name"],
                    "body": c["body"],
                    "created_at": _fmt_dt(c["created_at"]),
                    "edited_at": _fmt_dt(c["edited_at"]),
                    "edited_by_id": (
                        str(to_uuid(c["edited_by_id"])) if c["edited_by_id"] else None
                    ),
                    "deleted_at": _fmt_dt(c["deleted_at"]),
                }
                for c in comments
            ],
            "total": total,
            "skip": skip,
            "limit": limit,
        }


@router.post("/documents/{document_id}/comments", status_code=201)
def create_comment(
    document_id: UUID,
    body: CommentCreateRequest,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    with request.app.state.engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        assert_doc_access(document_id, user, auth_repo)

        repo = CommentRepository(connection)
        comment = repo.create(document_id, user.sub, body.body)
        request.app.state.metrics.comments_total.labels("create", "success").inc()
        return {
            "id": str(to_uuid(comment["id"])),
            "document_id": str(to_uuid(comment["document_id"])),
            "author_id": str(to_uuid(comment["author_id"])),
            "body": comment["body"],
            "created_at": _fmt_dt(comment["created_at"]),
        }


@router.patch("/documents/{document_id}/comments/{comment_id}")
def update_comment(
    document_id: UUID,
    comment_id: UUID,
    body: CommentUpdateRequest,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    with request.app.state.engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        assert_doc_access(document_id, user, auth_repo)

        repo = CommentRepository(connection)
        comment = repo.get_by_id(comment_id)
        if comment is None or comment["deleted_at"] is not None:
            raise HTTPException(status_code=404, detail="Comment not found")
        if not repo.can_edit(comment_id, user.sub, user.is_admin):
            raise HTTPException(status_code=403, detail="Cannot edit this comment")

        repo.update(comment_id, body.body, edited_by_id=user.sub)
        request.app.state.metrics.comments_total.labels("update", "success").inc()
        updated = repo.get_by_id(comment_id)
        if updated is None:
            raise HTTPException(status_code=404, detail="Comment not found")
        return {
            "id": str(to_uuid(updated["id"])),
            "author_id": str(to_uuid(updated["author_id"])),
            "author_display_name": updated["author_display_name"],
            "body": updated["body"],
            "created_at": _fmt_dt(updated["created_at"]),
            "edited_at": _fmt_dt(updated["edited_at"]),
            "edited_by_id": (
                str(to_uuid(updated["edited_by_id"])) if updated["edited_by_id"] else None
            ),
        }


@router.delete("/documents/{document_id}/comments/{comment_id}", status_code=204)
def delete_comment(
    document_id: UUID,
    comment_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> None:
    with request.app.state.engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        assert_doc_access(document_id, user, auth_repo)

        repo = CommentRepository(connection)
        comment = repo.get_by_id(comment_id)
        if comment is None or comment["deleted_at"] is not None:
            raise HTTPException(status_code=404, detail="Comment not found")
        if not repo.can_delete(comment_id, user.sub, user.is_admin):
            raise HTTPException(status_code=403, detail="Cannot delete this comment")

        repo.soft_delete(comment_id, deleted_by_id=user.sub)
        request.app.state.metrics.comments_total.labels("delete", "success").inc()
