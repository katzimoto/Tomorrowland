from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from services.annotations.models import AnnotationCreateRequest, AnnotationUpdateRequest
from services.annotations.repository import AnnotationRepository
from services.api._helpers import _fmt_dt, _parse_json
from services.api.main import current_user
from services.auth.models import TokenPayload
from services.auth.repository import AuthRepository
from services.permissions.enforcer import assert_doc_access
from shared.db import to_uuid

router = APIRouter(tags=["annotations"])


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
        annotation = repo.get_by_id(annotation_id)
        if annotation is None:
            raise HTTPException(status_code=404, detail="Annotation not found")

        # Verify doc access
        auth_repo = AuthRepository(connection)
        assert_doc_access(to_uuid(annotation["document_id"]), user, auth_repo)

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
        annotation = repo.get_by_id(annotation_id)
        if annotation is None:
            raise HTTPException(status_code=404, detail="Annotation not found")

        # Verify doc access
        auth_repo = AuthRepository(connection)
        assert_doc_access(to_uuid(annotation["document_id"]), user, auth_repo)

        if not repo.can_modify(annotation_id, user.sub, user.is_admin):
            raise HTTPException(status_code=403, detail="Cannot delete this annotation")

        visibility = "private" if annotation["is_private"] else "shared"
        repo.delete(annotation_id)
        request.app.state.metrics.annotations_total.labels("delete", visibility, "success").inc()
