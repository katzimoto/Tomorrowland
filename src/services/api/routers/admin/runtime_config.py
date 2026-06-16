"""Admin runtime-configuration API (#812).

Exposes the curated config registry (``services.api.config_registry``) and
database-backed overrides for runtime-editable settings.  All endpoints are
admin-only.  Secrets are never returned in raw form, and override values are
validated against the registry before being stored.

This namespace (``/admin/runtime-config``) is intentionally distinct from the
pre-existing ``/admin/config`` router, which manages the free-form
``system_config`` key/value store.
"""

from __future__ import annotations

from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from services.api._helpers import _audit_log, _fmt_dt
from services.api.config_registry import (
    CONFIG_REGISTRY,
    PRECEDENCE,
    ValidationError,
    coerce_and_validate,
    describe_setting,
    get_setting,
)
from services.api.main import current_user
from services.auth.models import TokenPayload
from services.intelligence.runtime_config_repository import RuntimeConfigRepository
from services.permissions.enforcer import require_admin

router = APIRouter(tags=["admin"])


class _ConfigUpdate(BaseModel):
    value: Any


class _ConfigValidate(BaseModel):
    key: str
    value: Any


def _settings(request: Request) -> Any:
    return request.app.state.settings


@router.get("/admin/runtime-config")
def admin_list_runtime_config(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    settings = _settings(request)
    with request.app.state.engine.begin() as connection:
        overrides = RuntimeConfigRepository(connection).list_overrides()
    items = [
        describe_setting(setting, settings, overrides.get(setting.key))
        for setting in CONFIG_REGISTRY
    ]
    categories = list(dict.fromkeys(setting.category for setting in CONFIG_REGISTRY))
    return {"settings": items, "categories": categories, "precedence": PRECEDENCE}


@router.get("/admin/runtime-config/audit")
def admin_runtime_config_audit(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
    limit: int = 50,
) -> list[dict[str, Any]]:
    require_admin(user)
    limit = max(1, min(limit, 200))
    with request.app.state.engine.begin() as connection:
        rows = (
            connection.execute(
                sa.text("""
                    SELECT id, user_id, action, resource_id, details, created_at
                    FROM audit_log
                    WHERE resource_type = 'runtime_config'
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """),
                {"limit": limit},
            )
            .mappings()
            .all()
        )
    return [
        {
            "id": str(row["id"]),
            "user_id": str(row["user_id"]) if row["user_id"] else None,
            "action": row["action"],
            "key": row["resource_id"],
            "created_at": _fmt_dt(row["created_at"]),
        }
        for row in rows
    ]


def _describe_one(request: Request, key: str) -> dict[str, Any]:
    setting = get_setting(key)
    if setting is None:
        raise HTTPException(status_code=404, detail="Unknown configuration key")
    with request.app.state.engine.begin() as connection:
        override = RuntimeConfigRepository(connection).get_override(key)
    return describe_setting(setting, _settings(request), override)


@router.get("/admin/runtime-config/{key}")
def admin_get_runtime_config(
    key: str,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    return _describe_one(request, key)


@router.post("/admin/runtime-config/validate")
def admin_validate_runtime_config(
    body: _ConfigValidate,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    setting = get_setting(body.key)
    if setting is None:
        raise HTTPException(status_code=404, detail="Unknown configuration key")
    try:
        coerced = coerce_and_validate(setting, body.value)
    except ValidationError as exc:
        return {"valid": False, "error": str(exc)}
    return {"valid": True, "value": coerced}


@router.patch("/admin/runtime-config/{key}")
def admin_update_runtime_config(
    key: str,
    body: _ConfigUpdate,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    setting = get_setting(key)
    if setting is None:
        raise HTTPException(status_code=404, detail="Unknown configuration key")
    try:
        coerced = coerce_and_validate(setting, body.value)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    settings = _settings(request)
    with request.app.state.engine.begin() as connection:
        repo = RuntimeConfigRepository(connection)
        override = repo.set_override(key, coerced, setting.type, user.sub)
        _audit_log(
            connection,
            user.sub,
            "update",
            "runtime_config",
            key,
            {"value": coerced},
        )
    return describe_setting(setting, settings, override)


@router.delete("/admin/runtime-config/{key}")
def admin_delete_runtime_config(
    key: str,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    setting = get_setting(key)
    if setting is None:
        raise HTTPException(status_code=404, detail="Unknown configuration key")
    settings = _settings(request)
    with request.app.state.engine.begin() as connection:
        repo = RuntimeConfigRepository(connection)
        removed = repo.delete_override(key)
        if removed:
            _audit_log(connection, user.sub, "reset", "runtime_config", key)
    return describe_setting(setting, settings, None)


@router.post("/admin/runtime-config/reload")
def admin_reload_runtime_config(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    from shared.config_cache import invalidate_config_cache

    invalidate_config_cache()
    with request.app.state.engine.begin() as connection:
        _audit_log(connection, user.sub, "reload", "runtime_config")
    return {
        "reloaded": True,
        "note": (
            "Database-backed overrides re-read. Settings marked requires_restart / "
            "requires_worker_restart still need a process restart to take effect."
        ),
    }
