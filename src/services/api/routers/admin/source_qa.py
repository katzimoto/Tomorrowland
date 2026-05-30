"""Admin endpoints for source-level QA diagnostics."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request

from services.api.main import current_user
from services.auth.models import TokenPayload
from services.intelligence.source_qa_service import run_source_qa
from services.permissions.enforcer import require_admin

router = APIRouter(tags=["admin"])


@router.get("/admin/sources/{source_id}/qa")
def admin_source_qa(
    source_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    """Run deterministic QA diagnostics for a source and return results."""
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        source_row = connection.execute(
            sa.text("SELECT id FROM ingestion_sources WHERE id = :id"),
            {"id": source_id.hex},
        ).scalar()
        if source_row is None:
            raise HTTPException(status_code=404, detail="Source not found")

        check = run_source_qa(connection, source_id)
        return check.to_dict()
