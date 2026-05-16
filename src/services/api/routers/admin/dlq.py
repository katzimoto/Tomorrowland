from __future__ import annotations

from typing import Annotated
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request

from services.api._helpers import _audit_log, _fmt_dt
from services.api.main import current_user
from services.api.schemas import DlqItem
from services.auth.models import TokenPayload
from services.permissions.enforcer import require_admin
from shared.db import to_uuid

router = APIRouter(tags=["admin"])


@router.get("/admin/dlq")
def admin_list_dlq(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> list[DlqItem]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        rows = connection.execute(
            sa.text("""
                SELECT id, doc_id, error_message, retry_count, status, created_at, updated_at
                FROM dlq ORDER BY created_at DESC
                """)
        ).mappings()
        return [
            DlqItem(
                id=str(to_uuid(row["id"])),
                doc_id=str(to_uuid(row["doc_id"])) if row["doc_id"] else None,
                error_message=row["error_message"],
                retry_count=row["retry_count"],
                status=row["status"],
                created_at=_fmt_dt(row["created_at"]),
                updated_at=_fmt_dt(row["updated_at"]),
            )
            for row in rows
        ]


@router.post("/admin/dlq/{dlq_id}/retry")
def admin_retry_dlq(
    dlq_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, str]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        result = connection.execute(
            sa.text("""
                UPDATE dlq
                SET status = 'retried', retry_count = retry_count + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id AND status = 'pending'
                """),
            {"id": dlq_id.hex},
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="DLQ item not found or not pending")
        _audit_log(connection, user.sub, "retry", "dlq", str(dlq_id))
        return {"id": str(dlq_id), "status": "retried"}
