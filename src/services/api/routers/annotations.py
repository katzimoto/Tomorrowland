from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from services.annotations.models import (
    AnnotationCreateRequest,
    AnnotationReplyCreateRequest,
    AnnotationUpdateRequest,
)
from services.annotations.repository import AnnotationRepository
from services.api._helpers import _fmt_dt, _parse_json
from services.api.main import current_user
from services.auth.models import TokenPayload
from services.auth.repository import AuthRepository
from services.permissions.enforcer import assert_doc_access
from shared.db import to_uuid

router = APIRouter(tags=["annotations"])


def _get_annotation_or_404_with_access(
    annotation_id: UUID,
    user: TokenPayload,
    repo: AnnotationRepository,
    connection: Any,
) -> dict[str, Any]:
    """Fetch annotation, assert document-level access, return the annotation row.

    Raises 404 if the annotation does not exist.
    Delegates to assert_doc_access for document-level permission enforcement
    (raises 403 when the user cannot access the document).

    Centralising this check here prevents individual endpoints from accidentally
    skipping the assert_doc_access call — the root cause of the delete_reply bug.
    """
    annotation = repo.get_by_id(annotation_id)
    if annotation is None:
        raise HTTPException(status_code=404, detail="Annotation not found")
    auth_repo = AuthRepository(connection)
    assert_doc_access(to_uuid(annotation["document_id"]), user, auth_repo)
    return annotation


@router.get("/documents/{document_id}/annotations")
def list_annotations(
    document_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    with request.app.state.engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        assert_doc_access(document_id, user, auth_repo)

        repo = AnnotationRepository(connection)
        annotations = repo.list_annotations(document_id, user.sub, is_admin=user.is_admin)
        return {
            "document_id": str(document_id),
            "annotations": [
                {
                    "id": str(to_uuid(a["id"])),
                    "user_id": str(to_uuid(a["user_id"])),
                    "user_display_name": a["user_display_name"],
                    "text": a["text"],
                    "note": a["note"],
                    "position": _parse_json(a["position"]),
                    "is_private": bool(a["is_private"]),
                    "created_at": _fmt_dt(a["created_at"]),
                    "reply_count": int(a.get("reply_count", 0)),
                    "can_modify": repo.can_modify(to_uuid(a["id"]), user.sub, user.is_admin),
                }
                for a in annotations
            ],
        }


@router.post("/documents/{document_id}/annotations", status_code=201)
def create_annotation(
    document_id: UUID,
    body: AnnotationCreateRequest,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    with request.app.state.engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        assert_doc_access(document_id, user, auth_repo)

        repo = AnnotationRepository(connection)
        annotation = repo.create(
            document_id=document_id,
            user_id=user.sub,
            text=body.text,
            note=body.note,
            position=body.position,
            is_private=body.is_private,
        )
        visibility = "private" if body.is_private else "shared"
        request.app.state.metrics.annotations_total.labels("create", visibility, "success").inc()
        return {
            "id": str(to_uuid(annotation["id"])),
            "document_id": str(to_uuid(annotation["document_id"])),
            "user_id": str(to_uuid(annotation["user_id"])),
            "text": annotation["text"],
            "note": annotation["note"],
            "position": _parse_json(annotation["position"]),
            "is_private": bool(annotation["is_private"]),
            "created_at": _fmt_dt(annotation["created_at"]),
            "can_modify": True,
        }


@router.put("/annotations/{annotation_id}")
def update_annotation(
    annotation_id: UUID,
    body: AnnotationUpdateRequest,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    with request.app.state.engine.begin() as connection:
        repo = AnnotationRepository(connection)
        _get_annotation_or_404_with_access(annotation_id, user, repo, connection)

        if not repo.can_modify(annotation_id, user.sub, user.is_admin):
            raise HTTPException(status_code=403, detail="Cannot modify this annotation")

        repo.update(
            annotation_id,
            text=body.text,
            note=body.note,
            position=body.position,
            is_private=body.is_private,
        )
        visibility = "private" if body.is_private else "shared"
        request.app.state.metrics.annotations_total.labels("update", visibility, "success").inc()
        updated = repo.get_by_id(annotation_id)
        if updated is None:
            raise HTTPException(status_code=404, detail="Annotation not found")
        return {
            "id": str(to_uuid(updated["id"])),
            "user_id": str(to_uuid(updated["user_id"])),
            "user_display_name": updated["user_display_name"],
            "text": updated["text"],
            "note": updated["note"],
            "position": _parse_json(updated["position"]),
            "is_private": bool(updated["is_private"]),
            "created_at": _fmt_dt(updated["created_at"]),
            "updated_at": _fmt_dt(updated["updated_at"]),
            "can_modify": True,
        }


@router.delete("/annotations/{annotation_id}", status_code=204)
def delete_annotation(
    annotation_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> None:
    with request.app.state.engine.begin() as connection:
        repo = AnnotationRepository(connection)
        annotation = _get_annotation_or_404_with_access(annotation_id, user, repo, connection)

        if not repo.can_modify(annotation_id, user.sub, user.is_admin):
            raise HTTPException(status_code=403, detail="Cannot delete this annotation")

        visibility = "private" if annotation["is_private"] else "shared"
        repo.delete(annotation_id)
        request.app.state.metrics.annotations_total.labels("delete", visibility, "success").inc()


# ---------------------------------------------------------------------------
# Annotation replies
# ---------------------------------------------------------------------------


@router.get("/annotations/{annotation_id}/replies")
def list_replies(
    annotation_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    with request.app.state.engine.begin() as connection:
        repo = AnnotationRepository(connection)
        annotation = _get_annotation_or_404_with_access(annotation_id, user, repo, connection)

        # Private annotations are only visible to their owner and admins — the same
        # rule enforced by list_annotations.  A non-owner with doc access must not
        # be able to enumerate replies on a private annotation by knowing its ID.
        if (
            annotation["is_private"]
            and not user.is_admin
            and to_uuid(annotation["user_id"]) != user.sub
        ):
            raise HTTPException(status_code=404, detail="Annotation not found")

        replies = repo.list_replies(annotation_id)
        return {
            "annotation_id": str(annotation_id),
            "replies": [
                {
                    "id": str(to_uuid(r["id"])),
                    "user_id": str(to_uuid(r["user_id"])),
                    "user_display_name": r.get("user_display_name"),
                    "body": r["body"],
                    "created_at": _fmt_dt(r["created_at"]),
                    "edited_at": _fmt_dt(r["edited_at"]) if r.get("edited_at") else None,
                    "can_modify": repo.can_modify_reply(to_uuid(r["id"]), user.sub, user.is_admin),
                }
                for r in replies
            ],
        }


@router.post("/annotations/{annotation_id}/replies", status_code=201)
def create_reply(
    annotation_id: UUID,
    body: AnnotationReplyCreateRequest,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    with request.app.state.engine.begin() as connection:
        repo = AnnotationRepository(connection)
        _get_annotation_or_404_with_access(annotation_id, user, repo, connection)

        reply = repo.create_reply(annotation_id, user.sub, body.body)
        return {
            "id": str(to_uuid(reply["id"])),
            "annotation_id": str(to_uuid(reply["annotation_id"])),
            "user_id": str(to_uuid(reply["user_id"])),
            "body": reply["body"],
            "created_at": _fmt_dt(reply["created_at"]),
            "can_modify": True,
        }


@router.delete("/annotation-replies/{reply_id}", status_code=204)
def delete_reply(
    reply_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> None:
    with request.app.state.engine.begin() as connection:
        repo = AnnotationRepository(connection)

        # Bug fix: assert document-level access before checking reply ownership.
        # Previously this endpoint skipped assert_doc_access entirely, allowing a
        # user whose document permission had been revoked to still delete their
        # own replies by knowing the reply UUID.
        reply = repo.get_reply_by_id(reply_id)
        if reply is None:
            raise HTTPException(status_code=404, detail="Reply not found")
        _get_annotation_or_404_with_access(to_uuid(reply["annotation_id"]), user, repo, connection)

        if not repo.can_modify_reply(reply_id, user.sub, user.is_admin):
            raise HTTPException(status_code=404, detail="Reply not found")
        repo.delete_reply(reply_id)
