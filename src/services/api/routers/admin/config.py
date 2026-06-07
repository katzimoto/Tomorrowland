from __future__ import annotations

from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request

from services.api._helpers import _SENSITIVE_CONFIG_KEYS, _audit_log, _fmt_dt
from services.api.main import current_user
from services.api.schemas import UpdateConfigRequest
from services.auth.models import TokenPayload
from services.permissions.enforcer import require_admin

router = APIRouter(tags=["admin"])

_MASK = "••••••••"


def _mask_config_value(key: str, value: Any) -> Any:
    """Return a masked placeholder when *key* matches a sensitive pattern."""
    if any(sensitive in key.lower() for sensitive in _SENSITIVE_CONFIG_KEYS):
        return _MASK
    return value


@router.get("/admin/config")
def admin_list_config(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> list[dict[str, Any]]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        rows = connection.execute(
            sa.text("SELECT key, value, updated_at FROM system_config ORDER BY key")
        ).mappings()
        return [
            {
                "key": row["key"],
                "value": _mask_config_value(row["key"], row["value"]),
                "updated_at": _fmt_dt(row["updated_at"]),
            }
            for row in rows
        ]


@router.put("/admin/config/{key}")
def admin_update_config(
    key: str,
    body: UpdateConfigRequest,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        connection.execute(
            sa.text("""
                UPDATE system_config
                SET value = :value, updated_at = CURRENT_TIMESTAMP, updated_by = :user_id
                WHERE key = :key
                """).bindparams(sa.bindparam("value", type_=sa.JSON())),
            {
                "key": key,
                "value": body.value,
                "user_id": user.sub.hex,
            },
        )
        # Invalidate cached value so the next request picks up the change immediately.
        from shared.config_cache import invalidate_config_cache

        invalidate_config_cache(key)
        row = (
            connection.execute(
                sa.text("SELECT key, value, updated_at FROM system_config WHERE key = :key"),
                {"key": key},
            )
            .mappings()
            .first()
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Config key not found")
        _audit_log(
            connection,
            user.sub,
            "update",
            "system_config",
            key,
            {"value": body.value},
        )
        return {
            "key": row["key"],
            "value": _mask_config_value(row["key"], row["value"]),
            "updated_at": _fmt_dt(row["updated_at"]),
        }


@router.post("/admin/config/reset")
def admin_reset_config(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    from shared.feature_flags import SYSTEM_CONFIG_DEFAULTS

    with request.app.state.engine.begin() as connection:
        # Verify at least one config key exists before blindly resetting all.
        existing_count = connection.execute(sa.text("SELECT COUNT(*) FROM system_config")).scalar()
        if not existing_count:
            raise HTTPException(status_code=409, detail="No config rows to reset")

        for key, value in SYSTEM_CONFIG_DEFAULTS.items():
            connection.execute(
                sa.text("""
                    UPDATE system_config
                    SET value = :value, updated_at = CURRENT_TIMESTAMP, updated_by = :user_id
                    WHERE key = :key
                    """).bindparams(sa.bindparam("value", type_=sa.JSON())),
                {"key": key, "value": value, "user_id": user.sub.hex},
            )
        # Invalidate all cached config values after full reset.
        from shared.config_cache import invalidate_config_cache

        invalidate_config_cache()
        _audit_log(connection, user.sub, "reset", "system_config")
        return {"reset": True, "keys": list(SYSTEM_CONFIG_DEFAULTS.keys())}
