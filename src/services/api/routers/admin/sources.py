from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request

from services.api._helpers import (
    _SENSITIVE_CONFIG_KEYS,
    _audit_log,
    _classify_connection_error,
    _fmt_dt,
    _source_config,
)
from services.api.main import current_user
from services.api.schemas import (
    ConnectionTestResult,
    CreateSourceRequest,
    GrantPermissionRequest,
    UpdateSourceRequest,
)
from services.auth.models import TokenPayload
from services.auth.repository import AuthRepository
from services.connectors.factory import build_connector, connector_types
from services.permissions.enforcer import require_admin
from shared.db import to_uuid

router = APIRouter(tags=["admin"])


@router.get("/admin/connector-types")
def admin_connector_types(
    user: Annotated[TokenPayload, Depends(current_user)],
) -> list[dict[str, Any]]:
    require_admin(user)
    return connector_types()


@router.get("/admin/source-languages")
def admin_source_languages(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> list[str]:
    require_admin(user)
    return request.app.state.settings.supported_translation_source_languages_list  # type: ignore[no-any-return]


@router.post(
    "/admin/sources/{source_id}/test-connection",
    response_model=ConnectionTestResult,
)
def admin_test_source_connection(
    source_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> ConnectionTestResult:
    """Validate a source configuration and reachability."""
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        source_row = (
            connection.execute(
                sa.text("SELECT * FROM ingestion_sources WHERE id = :id"),
                {"id": source_id.hex},
            )
            .mappings()
            .first()
        )
        if source_row is None:
            raise HTTPException(status_code=404, detail="Source not found")

        connector_type = str(source_row["type"])
        checked_at = datetime.now(UTC).isoformat()

        try:
            connector = build_connector(source_row)
            connector.validate()
        except Exception as exc:
            status, error = _classify_connection_error(exc, connector_type, source_row)
            connection.execute(
                sa.text("""
                    UPDATE ingestion_sources
                    SET last_validation_status = :status,
                        last_validation_error = :error,
                        last_validated_at = :checked_at
                    WHERE id = :id
                    """),
                {
                    "id": source_id.hex,
                    "status": status,
                    "error": error,
                    "checked_at": checked_at,
                },
            )
            return ConnectionTestResult(
                source_id=str(source_id),
                status=status,
                checked_at=checked_at,
                error=error,
            )

        details: dict[str, Any] = {"config_valid": True}
        connection.execute(
            sa.text("""
                UPDATE ingestion_sources
                SET last_validation_status = 'ok',
                    last_validation_error = NULL,
                    last_validated_at = :checked_at
                WHERE id = :id
                """),
            {
                "id": source_id.hex,
                "checked_at": checked_at,
            },
        )
        return ConnectionTestResult(
            source_id=str(source_id),
            status="ok",
            checked_at=checked_at,
            details=details,
        )


@router.get("/admin/sources")
def admin_list_sources(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> list[dict[str, Any]]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        rows = connection.execute(
            sa.text("""
                SELECT id, name, type, path, source_language, enabled, created_at,
                       last_sync_status, last_sync_indexed, last_sync_skipped,
                       last_sync_failed, last_sync_error, last_sync_at,
                       last_validation_status, last_validation_error, last_validated_at
                FROM ingestion_sources ORDER BY created_at DESC
                """)
        ).mappings()
        return [
            {
                "id": str(to_uuid(row["id"])),
                "name": row["name"],
                "type": row["type"],
                "path": row["path"],
                "source_language": row["source_language"],
                "enabled": row["enabled"],
                "created_at": _fmt_dt(row["created_at"]),
                "last_sync_status": row.get("last_sync_status"),
                "last_sync_indexed": row.get("last_sync_indexed"),
                "last_sync_skipped": row.get("last_sync_skipped"),
                "last_sync_failed": row.get("last_sync_failed"),
                "last_sync_error": row.get("last_sync_error"),
                "last_sync_at": _fmt_dt(row.get("last_sync_at")),
                "last_validation_status": row.get("last_validation_status"),
                "last_validation_error": row.get("last_validation_error"),
                "last_validated_at": _fmt_dt(row.get("last_validated_at")),
            }
            for row in rows
        ]


@router.get("/admin/sources/{source_id}")
def admin_get_source(
    source_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        row = (
            connection.execute(
                sa.text("""
                SELECT id, name, type, path, source_language, enabled, created_at,
                       config,
                       last_sync_status, last_sync_indexed, last_sync_skipped,
                       last_sync_failed, last_sync_error, last_sync_at,
                       last_validation_status, last_validation_error, last_validated_at
                FROM ingestion_sources WHERE id = :id
                """),
                {"id": source_id.hex},
            )
            .mappings()
            .first()
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Source not found")

        config = _source_config(row.get("config"))
        masked_config: dict[str, Any] = {}
        for key, value in config.items():
            if key.lower() in _SENSITIVE_CONFIG_KEYS:
                masked_config[key] = "••••••••"
            else:
                masked_config[key] = value

        permissions = (
            connection.execute(
                sa.text("""
                SELECT g.id, g.name
                FROM source_permissions sp
                JOIN groups g ON g.id = sp.group_id
                WHERE sp.source_id = :source_id
                ORDER BY g.name
                """),
                {"source_id": source_id.hex},
            )
            .mappings()
            .all()
        )

        return {
            "id": str(to_uuid(row["id"])),
            "name": row["name"],
            "type": row["type"],
            "path": row["path"],
            "source_language": row["source_language"],
            "enabled": row["enabled"],
            "created_at": _fmt_dt(row["created_at"]),
            "config": masked_config,
            "last_sync_status": row.get("last_sync_status"),
            "last_sync_indexed": row.get("last_sync_indexed"),
            "last_sync_skipped": row.get("last_sync_skipped"),
            "last_sync_failed": row.get("last_sync_failed"),
            "last_sync_error": row.get("last_sync_error"),
            "last_sync_at": _fmt_dt(row.get("last_sync_at")),
            "last_validation_status": row.get("last_validation_status"),
            "last_validation_error": row.get("last_validation_error"),
            "last_validated_at": _fmt_dt(row.get("last_validated_at")),
            "groups": [{"id": str(to_uuid(p["id"])), "name": p["name"]} for p in permissions],
        }


@router.put("/admin/sources/{source_id}")
def admin_update_source(
    source_id: UUID,
    body: UpdateSourceRequest,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        existing = connection.execute(
            sa.text("SELECT id FROM ingestion_sources WHERE id = :id"),
            {"id": source_id.hex},
        ).scalar()
        if existing is None:
            raise HTTPException(status_code=404, detail="Source not found")

        updates: list[str] = []
        params: dict[str, Any] = {"id": source_id.hex}
        if body.name is not None:
            updates.append("name = :name")
            params["name"] = body.name
        if body.source_language is not None:
            updates.append("source_language = :source_language")
            params["source_language"] = body.source_language
        if body.enabled is not None:
            updates.append("enabled = :enabled")
            params["enabled"] = body.enabled
        if body.config is not None:
            updates.append("config = :config")
            params["config"] = json.dumps(body.config)
        if updates:
            connection.execute(
                sa.text(f"UPDATE ingestion_sources SET {', '.join(updates)} WHERE id = :id"),
                params,
            )
        _audit_log(connection, user.sub, "update", "source", str(source_id))
        return {"id": str(source_id)}


@router.post("/admin/sources", status_code=201)
def admin_create_source(
    body: CreateSourceRequest,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        source_id = uuid4()
        connection.execute(
            sa.text("""
                INSERT INTO ingestion_sources
                    (id, name, type, path, source_language, enabled, config)
                VALUES
                    (:id, :name, :type, :path, :source_language, :enabled, :config)
                """),
            {
                "id": source_id.hex,
                "name": body.name,
                "type": body.type,
                "path": body.path,
                "source_language": body.source_language,
                "enabled": body.enabled,
                "config": json.dumps(body.config),
            },
        )
        auth_repo = AuthRepository(connection)
        admins_group_id = auth_repo.ensure_group("admins")
        auth_repo.grant_source_to_group(source_id, admins_group_id)
        _audit_log(
            connection,
            user.sub,
            "create",
            "source",
            str(source_id),
            {"name": body.name},
        )
        return {
            "id": str(source_id),
            "name": body.name,
            "type": body.type,
            "path": body.path,
            "source_language": body.source_language,
            "enabled": body.enabled,
            "created_at": None,
            "last_sync_status": None,
            "last_sync_indexed": None,
            "last_sync_skipped": None,
            "last_sync_failed": None,
            "last_sync_error": None,
            "last_sync_at": None,
            "last_validation_status": None,
            "last_validation_error": None,
            "last_validated_at": None,
        }


@router.post("/admin/sources/{source_id}/permissions", status_code=201)
def admin_grant_permission(
    source_id: UUID,
    body: GrantPermissionRequest,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    group_id = UUID(body.group_id)
    with request.app.state.engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        auth_repo.grant_source_to_group(source_id, group_id)
        _audit_log(
            connection,
            user.sub,
            "grant",
            "permission",
            str(source_id),
            {"group_id": str(group_id)},
        )
        return {"source_id": str(source_id), "group_id": str(group_id)}


@router.delete("/admin/sources/{source_id}/permissions/{group_id}", status_code=204)
def admin_revoke_permission(
    source_id: UUID,
    group_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> None:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        connection.execute(
            sa.text("""
                DELETE FROM source_permissions
                WHERE source_id = :source_id AND group_id = :group_id
                """),
            {"source_id": source_id.hex, "group_id": group_id.hex},
        )
        _audit_log(
            connection,
            user.sub,
            "revoke",
            "permission",
            str(source_id),
            {"group_id": str(group_id)},
        )
