"""Citation feedback API — lets users report citation quality problems."""

from __future__ import annotations

import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from services.api.main import current_user
from services.auth.models import TokenPayload
from services.auth.repository import AuthRepository
from services.chat.citation_feedback import (
    CitationFeedbackCreate,
    CitationFeedbackRepository,
    FeedbackType,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/citation-feedback", tags=["citation-feedback"])

_VALID_FEEDBACK_TYPES: set[str] = {
    "correct",
    "wrong_passage",
    "right_document_wrong_location",
    "missing_better_source",
    "unsupported_claim",
    "permission_concern",
    "other",
}


class CitationFeedbackRequest(BaseModel):
    citation_id: str | None = None
    message_id: UUID | None = None
    document_id: UUID
    chunk_id: str | None = None
    feedback_type: FeedbackType
    comment: str | None = None


@router.post("", status_code=201)
def submit_feedback(
    body: CitationFeedbackRequest,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    """Submit feedback for a citation.

    Permission check: user must have access to the document to submit feedback.
    Prevents anonymous or unauthorized users from polluting the feedback table.
    """
    with request.app.state.engine.begin() as connection:
        if not user.is_admin:
            auth_repo = AuthRepository(connection)
            source_id = auth_repo.document_source_id(body.document_id)
            if source_id is None or not auth_repo.user_can_access_source(
                user,  # type: ignore[arg-type]
                source_id,
            ):
                raise HTTPException(
                    status_code=403,
                    detail="You do not have access to this document.",
                )

        repo = CitationFeedbackRepository(connection)
        feedback = repo.create(
            CitationFeedbackCreate(
                citation_id=body.citation_id,
                message_id=body.message_id,
                document_id=body.document_id,
                chunk_id=body.chunk_id,
                feedback_type=body.feedback_type,
                comment=body.comment,
                user_id=user.sub,
            )
        )
        return {"id": str(feedback.id), "ok": True}


@router.get("/by-document/{document_id}")
def list_feedback_by_document(
    document_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List feedback for a document (admin only)."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    with request.app.state.engine.begin() as connection:
        repo = CitationFeedbackRepository(connection)
        items = repo.list_by_document(document_id, limit=limit, offset=offset)
        return {
            "items": [
                {
                    "id": str(f.id),
                    "citation_id": f.citation_id,
                    "message_id": str(f.message_id) if f.message_id else None,
                    "document_id": str(f.document_id),
                    "chunk_id": f.chunk_id,
                    "feedback_type": f.feedback_type,
                    "comment": f.comment,
                    "user_id": str(f.user_id),
                    "created_at": f.created_at.isoformat(),
                }
                for f in items
            ]
        }
