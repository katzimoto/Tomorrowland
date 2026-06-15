"""Repository for parser_policies CRUD and resolution.

Follows the same SQLAlchemy Core + Connection pattern as ProfileRepository.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from shared.db import db_now, db_resolve_json, db_uuid, to_uuid


def _ensure_json(value: Any) -> str:
    """Return a JSON string for JSON columns."""
    if isinstance(value, str):
        return value
    return json.dumps(value if value is not None else {})


def _row_to_dict(row: sa.RowMapping) -> dict[str, Any]:
    """Convert a parser_policies row to a dict with proper UUID/JSON handling."""
    return {
        "id": str(to_uuid(row["id"])),
        "source_id": str(to_uuid(row["source_id"])) if row.get("source_id") else None,
        "mime_pattern": row["mime_pattern"],
        "parser_chain": db_resolve_json(row["parser_chain"]) or [],
        "options": db_resolve_json(row["options"]) or {},
        "enabled": bool(row["enabled"]),
        "priority": int(row["priority"]),
        "created_by": row.get("created_by"),
        "created_at": (
            row["created_at"].isoformat()
            if isinstance(row.get("created_at"), datetime)
            else str(row["created_at"])
            if row.get("created_at")
            else None
        ),
        "updated_at": (
            row["updated_at"].isoformat()
            if isinstance(row.get("updated_at"), datetime)
            else str(row["updated_at"])
            if row.get("updated_at")
            else None
        ),
    }


_ALLOWED_COLUMNS = frozenset(
    {
        "id",
        "source_id",
        "mime_pattern",
        "parser_chain",
        "options",
        "enabled",
        "priority",
        "created_by",
        "updated_at",
    }
)


def _assert_no_sql_wildcards(mime_pattern: str) -> None:
    """Raise ValueError if *mime_pattern* contains SQL LIKE wildcards.

    MIME patterns stored in the DB are used in LIKE clauses where ``%`` and
    ``_`` are interpreted as wildcards.  Accidentally storing a pattern that
    contains these characters would produce incorrect matching behaviour.
    """
    if "%" in mime_pattern or "_" in mime_pattern:
        raise ValueError(f"mime_pattern must not contain SQL wildcards: {mime_pattern!r}")


class ParserPolicyRepository:
    """CRUD for parser_policies with source+mime matching."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def create(
        self,
        *,
        created_by: str | None = None,
        source_id: UUID | None = None,
        mime_pattern: str,
        parser_chain: list[str],
        options: dict[str, Any] | None = None,
        enabled: bool = True,
        priority: int = 0,
    ) -> UUID:
        """Create a parser policy. Returns the new policy's UUID."""
        _assert_no_sql_wildcards(mime_pattern)
        policy_id = uuid4()
        now = db_now()
        self._connection.execute(
            sa.text(
                """\
                INSERT INTO parser_policies (
                    id, source_id, mime_pattern, parser_chain, options,
                    enabled, priority, created_by, created_at, updated_at
                ) VALUES (
                    :id, :source_id, :mime, :chain, :options,
                    :enabled, :priority, :created_by, :now, :now
                )
                """
            ),
            {
                "id": db_uuid(policy_id),
                "source_id": db_uuid(source_id) if source_id else None,
                "mime": mime_pattern,
                "chain": json.dumps(parser_chain),
                "options": _ensure_json(options or {}),
                "enabled": enabled,
                "priority": priority,
                "created_by": created_by,
                "now": now,
            },
        )
        return policy_id

    def get(self, policy_id: UUID) -> dict[str, Any] | None:
        """Return a policy by id, or None."""
        row = (
            self._connection.execute(
                sa.text("SELECT * FROM parser_policies WHERE id = :id"),
                {"id": db_uuid(policy_id)},
            )
            .mappings()
            .first()
        )
        return _row_to_dict(row) if row else None

    def list(
        self,
        source_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        """List policies, optionally filtered by source_id."""
        query = "SELECT * FROM parser_policies"
        params: dict[str, Any] = {}
        if source_id is not None:
            query += " WHERE source_id = :source_id"
            params["source_id"] = db_uuid(source_id)
        query += " ORDER BY priority DESC, created_at DESC"
        rows = self._connection.execute(sa.text(query), params).mappings().all()
        return [_row_to_dict(r) for r in rows]

    def update(self, policy_id: UUID, **fields: Any) -> None:
        """Update a policy's fields.

        Typical fields: mime_pattern, parser_chain, options, enabled, priority.
        """
        if "parser_chain" in fields:
            fields["parser_chain"] = json.dumps(fields["parser_chain"])
        if "options" in fields:
            fields["options"] = _ensure_json(fields["options"])
        if "source_id" in fields:
            fields["source_id"] = db_uuid(fields["source_id"]) if fields["source_id"] else None

        fields["updated_at"] = db_now()
        fields["id"] = db_uuid(policy_id)

        unknown = set(fields) - _ALLOWED_COLUMNS
        if unknown:
            raise ValueError(f"Unknown columns in update: {', '.join(sorted(unknown))}")

        sets = ", ".join(f"{k} = :{k}" for k in fields)
        self._connection.execute(
            sa.text(f"UPDATE parser_policies SET {sets} WHERE id = :id"),
            fields,
        )

    def delete(self, policy_id: UUID) -> None:
        """Delete a policy by id."""
        self._connection.execute(
            sa.text("DELETE FROM parser_policies WHERE id = :id"),
            {"id": db_uuid(policy_id)},
        )

    def match(self, *, source_id: UUID, mime_type: str) -> dict[str, Any] | None:
        """Return the best policy for (source, mime) or None.

        Specificity order (most specific first):
          1. Exact (source_id, mime_type) match
          2. Source-specific glob match for mime_type
          3. Global (source_id IS NULL) exact match
          4. Global glob match

        Ties at the same specificity level are broken by priority DESC,
        then created_at DESC.
        """
        params: dict[str, Any] = {
            "src": db_uuid(source_id),
            "mime": mime_type,
        }
        base = (
            "SELECT * FROM parser_policies WHERE enabled = true "
            "AND (source_id = :src OR source_id IS NULL) "
            "AND ("
        )

        # Build the mime filter: exact match, then glob patterns by specificity.
        # We try three levels: exact match, prefix glob (e.g. image/*), wildcard (*).
        glob_patterns = _glob_patterns(mime_type)

        # Combine into one query ordered by match specificity + priority.
        # Specificity: 0 = exact mime, 1 = single-segment glob, 2 = multi-segment glob, 3 = "*"
        mime_conditions: list[str] = []
        for level, pattern in enumerate(glob_patterns):
            if pattern == "*":
                # Exact wildcard match — don't use LIKE which would match
                # every mime_pattern (including non-wildcard policies).
                mime_conditions.append("(mime_pattern = '*')")
            elif level == 0:
                # Exact mime match
                mime_conditions.append("(mime_pattern = :mime)")
            elif "*" in pattern:
                # Glob LIKE pattern (e.g. "application/%")
                param_name = f"glob_{level}"
                params[param_name] = pattern.replace("*", "%")
                mime_conditions.append(f"(mime_pattern LIKE :{param_name})")

        if not mime_conditions:
            return None

        query = base + " OR ".join(mime_conditions) + ")"
        # Order by source-specific over global, then mime specificity
        # (longer patterns = more specific), then priority.
        query += (
            " ORDER BY "
            "(source_id IS NOT NULL) DESC, "
            "LENGTH(mime_pattern) DESC, "
            "priority DESC, "
            "created_at DESC "
            "LIMIT 1"
        )

        row = self._connection.execute(sa.text(query), params).mappings().first()
        return _row_to_dict(row) if row else None


def _glob_patterns(mime_type: str) -> list[str]:
    """Return candidate mime_pattern tiers for a MIME type, most-specific first.

    For ``application/pdf`` this returns::

        [\"application/pdf\", \"application/*\", \"*\"]

    For ``text/html``::
        [\"text/html\", \"text/*\", \"*\"]

    So a policy with ``mime_pattern = \"application/*\"`` matches
    ``application/pdf``, ``application/json``, etc.
    """
    patterns: list[str] = [mime_type]
    parts = mime_type.split("/")
    if len(parts) == 2:
        patterns.append(f"{parts[0]}/*")
    patterns.append("*")
    return patterns
