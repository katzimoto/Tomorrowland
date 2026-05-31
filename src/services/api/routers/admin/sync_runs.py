"""Admin API routes for sync runs and source health."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from services.api._helpers import _fmt_dt
from services.api.main import current_user
from services.auth.models import TokenPayload
from services.connectors.sync_repository import SyncRunRepository, get_source_health
from services.permissions.enforcer import require_admin

router = APIRouter(tags=["admin"])


def _sync_run_to_dict(run: Any) -> dict[str, Any]:
    return {
        "id": str(run.id),
        "source_id": str(run.source_id),
        "connector_type": run.connector_type,
        "sync_mode": run.sync_mode,
        "status": run.status,
        "started_at": _fmt_dt(run.started_at),
        "completed_at": _fmt_dt(run.completed_at),
        "checkpoint": run.checkpoint,
        "documents_discovered": run.documents_discovered,
        "documents_created": run.documents_created,
        "documents_updated": run.documents_updated,
        "documents_unchanged": run.documents_unchanged,
        "documents_deleted": run.documents_deleted,
        "documents_skipped": run.documents_skipped,
        "documents_failed": run.documents_failed,
        "error_summary": run.error_summary,
        "created_at": _fmt_dt(run.created_at),
        "updated_at": _fmt_dt(run.updated_at),
    }


@router.get("/admin/sources/{source_id}/sync-runs")
def admin_list_sync_runs(
    source_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List sync runs for a source, most recent first."""
    require_admin(user)
    # Bound the page size and offset so a client cannot request an unbounded set.
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    with request.app.state.engine.connect() as connection:
        repo = SyncRunRepository(connection)
        runs = repo.list_for_source(source_id, limit=limit, offset=offset)
    return [_sync_run_to_dict(r) for r in runs]


@router.get("/admin/sources/{source_id}/health")
def admin_source_health(
    source_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    """Return the health summary for a source."""
    require_admin(user)
    with request.app.state.engine.connect() as connection:
        health = get_source_health(connection, source_id)
    return {
        "last_sync_status": health.last_sync_status,
        "last_successful_sync_at": _fmt_dt(health.last_successful_sync_at),
        "last_failed_sync_at": _fmt_dt(health.last_failed_sync_at),
        "last_sync_error": health.last_sync_error,
        "failure_count": health.failure_count,
        "warning_count": health.warning_count,
        "last_sync_id": str(health.last_sync_id) if health.last_sync_id else None,
        "last_sync_indexed": health.last_sync_indexed,
        "last_sync_skipped": health.last_sync_skipped,
        "last_sync_failed": health.last_sync_failed,
        "last_sync_at": _fmt_dt(health.last_sync_at),
        "last_validation_status": health.last_validation_status,
        "last_validation_error": health.last_validation_error,
        "last_validated_at": _fmt_dt(health.last_validated_at),
    }
