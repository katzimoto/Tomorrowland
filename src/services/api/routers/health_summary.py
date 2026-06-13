"""Non-admin endpoint for source health summaries.

Returns a safe user-facing health summary for Evidence Inspector and
retrieval diagnostics.  Admin-only details are removed for non-admin
callers.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request

from services.api.main import current_user
from services.auth.models import TokenPayload
from services.intelligence.health_summary import compute_health_summary
from services.intelligence.source_qa_service import get_latest_qa

router = APIRouter(tags=["sources"])


@router.get("/sources/{source_id}/health-summary")
def source_health_summary(
    source_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    """Return a safe health summary for a source.

    Returns ``{"status": "unknown", ...}`` when no QA data exists.
    Admin callers receive detailed issue labels; non-admin callers
    only see safe generic messages.
    """
    with request.app.state.engine.begin() as connection:
        source_row = connection.execute(
            sa.text("SELECT id FROM ingestion_sources WHERE id = :id"),
            {"id": source_id.hex},
        ).scalar()
        if source_row is None:
            raise HTTPException(status_code=404, detail="Source not found")

        check = get_latest_qa(connection, source_id)
        is_admin = bool(user.is_admin)
        return compute_health_summary(check, admin=is_admin)
