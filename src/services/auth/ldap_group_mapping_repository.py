"""Repository for explicit LDAP group → Tomorrowland group mappings (#582).

All persistence goes through this module.  The admin search route
returns ephemeral results; only explicit mappings are stored.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from shared.db import db_uuid, to_uuid


class LdapGroupMappingRepository:
    """Persistence for explicit LDAP-group-to-Tomorrowland-group mappings."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def list_mappings(self) -> list[dict[str, Any]]:
        """Return all LDAP group mappings with resolved target group names."""
        rows = (
            self._connection.execute(
                sa.text("""
                    SELECT lgm.id, lgm.ldap_dn, lgm.ldap_external_id_attr,
                           lgm.ldap_external_id, lgm.ldap_display_name,
                           lgm.target_group_id, lgm.created_by,
                           lgm.created_at, lgm.updated_at,
                           g.name AS target_group_name
                    FROM ldap_group_mappings lgm
                    JOIN groups g ON g.id = lgm.target_group_id
                    ORDER BY lgm.ldap_display_name
                """)
            )
            .mappings()
            .all()
        )
        return [_format_mapping(row) for row in rows]

    def create_mapping(
        self,
        ldap_dn: str,
        ldap_external_id_attr: str,
        ldap_external_id: str | None,
        ldap_display_name: str,
        target_group_id: UUID,
        created_by: UUID | None = None,
    ) -> dict[str, Any]:
        """Create an explicit LDAP group mapping.

        Raises ``ValueError`` when the target Tomorrowland group does not exist.
        Raises ``sa.exc.IntegrityError`` when the DN or ``(attr, external_id)``
        combination is already mapped.
        """
        # Validate target group exists (defence in depth — the FK may not be
        # enforced on all DB engines, e.g. SQLite without PRAGMA foreign_keys).
        group_exists = self._connection.execute(
            sa.text("SELECT 1 FROM groups WHERE id = :id"),
            {"id": db_uuid(target_group_id)},
        ).scalar()
        if not group_exists:
            raise ValueError(f"Target group {target_group_id} does not exist")

        mapping_id = uuid4()
        self._connection.execute(
            sa.text("""
                INSERT INTO ldap_group_mappings
                    (id, ldap_dn, ldap_external_id_attr, ldap_external_id,
                     ldap_display_name, target_group_id, created_by)
                VALUES
                    (:id, :ldap_dn, :ldap_external_id_attr, :ldap_external_id,
                     :ldap_display_name, :target_group_id, :created_by)
            """),
            {
                "id": db_uuid(mapping_id),
                "ldap_dn": ldap_dn,
                "ldap_external_id_attr": ldap_external_id_attr,
                "ldap_external_id": ldap_external_id,
                "ldap_display_name": ldap_display_name,
                "target_group_id": db_uuid(target_group_id),
                "created_by": db_uuid(created_by) if created_by else None,
            },
        )
        # Re-read with join for full response.
        row = (
            self._connection.execute(
                sa.text("""
                    SELECT lgm.id, lgm.ldap_dn, lgm.ldap_external_id_attr,
                           lgm.ldap_external_id, lgm.ldap_display_name,
                           lgm.target_group_id, lgm.created_by,
                           lgm.created_at, lgm.updated_at,
                           g.name AS target_group_name
                    FROM ldap_group_mappings lgm
                    JOIN groups g ON g.id = lgm.target_group_id
                    WHERE lgm.id = :id
                """),
                {"id": db_uuid(mapping_id)},
            )
            .mappings()
            .first()
        )
        if row is None:
            raise RuntimeError("ldap group mapping insert did not persist")
        return _format_mapping(row)

    def delete_mapping(self, mapping_id: UUID) -> bool:
        """Delete an LDAP group mapping by id.  Returns ``True`` when a row was deleted."""
        result = self._connection.execute(
            sa.text("DELETE FROM ldap_group_mappings WHERE id = :id"),
            {"id": db_uuid(mapping_id)},
        )
        return result.rowcount is not None and result.rowcount > 0

    def get_mapped_tomorrowland_group_ids(self, ldap_group_dns: list[str]) -> list[UUID]:
        """Return Tomorrowland group IDs mapped from the given LDAP group DNs.

        Unmapped LDAP groups are silently ignored (no implicit group creation).
        """
        if not ldap_group_dns:
            return []

        placeholders = ", ".join(f":dn{i}" for i in range(len(ldap_group_dns)))
        params: dict[str, object] = {f"dn{i}": dn for i, dn in enumerate(ldap_group_dns)}

        # Safe: `placeholders` are generated parameter names (:dn0, :dn1, ...)
        # from a fixed-length list — no user-controlled SQL fragments.

        rows = self._connection.execute(
            sa.text(f"""
                SELECT target_group_id
                FROM ldap_group_mappings
                WHERE ldap_dn IN ({placeholders})
            """),
            params,
        ).scalars()
        return [to_uuid(r) for r in rows]

    def get_mapping_by_dn(self, ldap_dn: str) -> dict[str, Any] | None:
        """Return a single mapping by LDAP DN, or ``None``."""
        row = (
            self._connection.execute(
                sa.text("""
                    SELECT lgm.id, lgm.ldap_dn, lgm.ldap_external_id_attr,
                           lgm.ldap_external_id, lgm.ldap_display_name,
                           lgm.target_group_id, lgm.created_by,
                           lgm.created_at, lgm.updated_at,
                           g.name AS target_group_name
                    FROM ldap_group_mappings lgm
                    JOIN groups g ON g.id = lgm.target_group_id
                    WHERE lgm.ldap_dn = :ldap_dn
                """),
                {"ldap_dn": ldap_dn},
            )
            .mappings()
            .first()
        )
        return _format_mapping(row) if row else None


def _format_mapping(row: sa.RowMapping) -> dict[str, Any]:
    return {
        "id": str(to_uuid(row["id"])),
        "ldap_dn": row["ldap_dn"],
        "ldap_external_id_attr": row["ldap_external_id_attr"],
        "ldap_external_id": row["ldap_external_id"],
        "ldap_display_name": row["ldap_display_name"],
        "target_group_id": str(to_uuid(row["target_group_id"])),
        "target_group_name": row["target_group_name"],
        "created_by": str(to_uuid(row["created_by"])) if row["created_by"] else None,
        "created_at": _fmt_dt(row["created_at"]),
        "updated_at": _fmt_dt(row["updated_at"]),
    }


def _fmt_dt(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
