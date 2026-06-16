"""Repository for database-backed runtime configuration overrides (#812).

Backs the ``admin_runtime_config_overrides`` table.  ``key`` is the natural
primary key, so upserts use ``ON CONFLICT (key)`` which is supported on both
SQLite and PostgreSQL.  JSON values are bound with an explicit ``sa.JSON()``
bindparam so PostgreSQL accepts non-string payloads.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from shared.db import db_now, db_resolve_json


def _row_to_dict(row: sa.RowMapping) -> dict[str, Any]:
    updated_at = row["updated_at"]
    return {
        "key": row["key"],
        "value": db_resolve_json(row["value_json"]),
        "value_type": row["value_type"],
        "version": row["version"],
        "updated_at": (updated_at.isoformat() if hasattr(updated_at, "isoformat") else updated_at),
    }


class RuntimeConfigRepository:
    """CRUD for ``admin_runtime_config_overrides``."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def list_overrides(self) -> dict[str, dict[str, Any]]:
        """Return a ``{key: override_dict}`` mapping of all stored overrides."""
        rows = (
            self._connection.execute(
                sa.text("SELECT * FROM admin_runtime_config_overrides ORDER BY key")
            )
            .mappings()
            .all()
        )
        return {row["key"]: _row_to_dict(row) for row in rows}

    def get_override(self, key: str) -> dict[str, Any] | None:
        """Return a single override by key, or None."""
        row = (
            self._connection.execute(
                sa.text("SELECT * FROM admin_runtime_config_overrides WHERE key = :key"),
                {"key": key},
            )
            .mappings()
            .first()
        )
        return _row_to_dict(row) if row else None

    def set_override(
        self,
        key: str,
        value: Any,
        value_type: str,
        updated_by: UUID | None,
    ) -> dict[str, Any]:
        """Insert or update an override, bumping ``version`` on update."""
        self._connection.execute(
            sa.text("""
                INSERT INTO admin_runtime_config_overrides
                    (key, value_json, value_type, version, updated_by, updated_at)
                VALUES (:key, :value_json, :value_type, 1, :updated_by, :updated_at)
                ON CONFLICT (key) DO UPDATE SET
                    value_json = excluded.value_json,
                    value_type = excluded.value_type,
                    version = admin_runtime_config_overrides.version + 1,
                    updated_by = excluded.updated_by,
                    updated_at = excluded.updated_at
                """).bindparams(sa.bindparam("value_json", type_=sa.JSON())),
            {
                "key": key,
                "value_json": value,
                "value_type": value_type,
                "updated_by": updated_by.hex if updated_by else None,
                "updated_at": db_now(),
            },
        )
        stored = self.get_override(key)
        assert stored is not None  # noqa: S101 - just inserted
        return stored

    def delete_override(self, key: str) -> bool:
        """Delete an override. Returns True when a row was removed."""
        result = self._connection.execute(
            sa.text("DELETE FROM admin_runtime_config_overrides WHERE key = :key"),
            {"key": key},
        )
        return bool(result.rowcount)
