from __future__ import annotations

import contextlib
import json
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


def _decode_config_value(value: Any) -> Any:
    """Normalise a stored ``system_config`` value to its native JSON type.

    Raw ``sa.text`` reads of the JSON ``value`` column bypass SQLAlchemy's type
    processors, so SQLite hands back JSON-serialised strings (``'true'`` for a
    boolean, ``'"qwen3:4b"'`` for a string) while numbers come through typed.
    Decoding here gives the API a consistent, properly-typed contract.
    """
    if isinstance(value, str):
        with contextlib.suppress(json.JSONDecodeError, ValueError):
            return json.loads(value)
    return value


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
    from shared.feature_flags import SYSTEM_CONFIG_DEFAULTS

    with request.app.state.engine.begin() as connection:
        rows = {
            row["key"]: row
            for row in connection.execute(
                sa.text("SELECT key, value, updated_at FROM system_config")
            ).mappings()
        }

    # Surface every known configuration key, even those that have never been
    # written to the database yet, so the admin UI can display and edit the
    # default value. Stored rows override the registered defaults.
    entries: list[dict[str, Any]] = []
    for key in sorted(set(SYSTEM_CONFIG_DEFAULTS) | set(rows)):
        if key in rows:
            decoded = _decode_config_value(rows[key]["value"])
            # Treat a stored value that equals its registered default as "default"
            # so sentinel keys (e.g. empty model overrides) are not shown as
            # overridden.
            is_default = key in SYSTEM_CONFIG_DEFAULTS and decoded == SYSTEM_CONFIG_DEFAULTS[key]
            entries.append(
                {
                    "key": key,
                    "value": _mask_config_value(key, decoded),
                    "updated_at": _fmt_dt(rows[key]["updated_at"]),
                    "is_default": is_default,
                }
            )
        else:
            entries.append(
                {
                    "key": key,
                    "value": _mask_config_value(key, SYSTEM_CONFIG_DEFAULTS[key]),
                    "updated_at": None,
                    "is_default": True,
                }
            )
    return entries


@router.put("/admin/config/{key}")
def admin_update_config(
    key: str,
    body: UpdateConfigRequest,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    from shared.feature_flags import SYSTEM_CONFIG_DEFAULTS

    with request.app.state.engine.begin() as connection:
        exists = (
            connection.execute(
                sa.text("SELECT 1 FROM system_config WHERE key = :key"),
                {"key": key},
            ).first()
            is not None
        )
        # Reject keys that are neither stored nor part of the known registry.
        if not exists and key not in SYSTEM_CONFIG_DEFAULTS:
            raise HTTPException(status_code=404, detail="Config key not found")

        if exists:
            stmt = sa.text("""
                UPDATE system_config
                SET value = :value, updated_at = CURRENT_TIMESTAMP, updated_by = :user_id
                WHERE key = :key
                """)
        else:
            # Seed the default-only key on first write so the override persists.
            stmt = sa.text("""
                INSERT INTO system_config (key, value, updated_at, updated_by)
                VALUES (:key, :value, CURRENT_TIMESTAMP, :user_id)
                """)
        connection.execute(
            stmt.bindparams(sa.bindparam("value", type_=sa.JSON())),
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
            "value": _mask_config_value(row["key"], _decode_config_value(row["value"])),
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
            updated = connection.execute(
                sa.text("""
                    UPDATE system_config
                    SET value = :value, updated_at = CURRENT_TIMESTAMP, updated_by = :user_id
                    WHERE key = :key
                    """).bindparams(sa.bindparam("value", type_=sa.JSON())),
                {"key": key, "value": value, "user_id": user.sub.hex},
            )
            if updated.rowcount == 0:
                # Default-only key that was never written — seed it now.
                connection.execute(
                    sa.text("""
                        INSERT INTO system_config (key, value, updated_at, updated_by)
                        VALUES (:key, :value, CURRENT_TIMESTAMP, :user_id)
                        """).bindparams(sa.bindparam("value", type_=sa.JSON())),
                    {"key": key, "value": value, "user_id": user.sub.hex},
                )
        # Invalidate all cached config values after full reset.
        from shared.config_cache import invalidate_config_cache

        invalidate_config_cache()
        _audit_log(connection, user.sub, "reset", "system_config")
        return {"reset": True, "keys": list(SYSTEM_CONFIG_DEFAULTS.keys())}
