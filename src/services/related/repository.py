"""Database access for related documents and expertise signals."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from shared.db import db_uuid, to_uuid


class RelatedRepository:
    """Queries for related-document metadata and expertise evidence."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def get_document_tags_and_entities(self, doc_ids: list[str]) -> dict[str, dict[str, set[str]]]:
        """Return tags and entity tokens for each document id (string UUID).

        The entity token format is ``"<type>:<name>"`` so two docs sharing the
        same person and the same organization both count as overlapping
        entities. Missing documents map to empty sets.
        """
        if not doc_ids:
            return {}
        params, placeholders = _uuid_params(doc_ids)
        # Safe: `_uuid_params` generates only parameter placeholder names
        # (e.g. ":id_0, :id_1"), never user-controlled SQL.
        result: dict[str, dict[str, set[str]]] = {
            doc_id: {"tags": set(), "entities": set()} for doc_id in doc_ids
        }

        tag_rows = self._connection.execute(
            sa.text(
                f"SELECT document_id, tag FROM document_tags WHERE document_id IN ({placeholders})"
            ),
            params,
        ).mappings()
        for row in tag_rows:
            key = str(to_uuid(row["document_id"]))
            result.setdefault(key, {"tags": set(), "entities": set()})
            result[key]["tags"].add(str(row["tag"]))

        entity_rows = self._connection.execute(
            sa.text(
                f"""
                SELECT de.document_id, e.name, e.type
                FROM document_entities de
                JOIN entities e ON e.id = de.entity_id
                WHERE de.document_id IN ({placeholders})
                """
            ),
            params,
        ).mappings()
        for row in entity_rows:
            key = str(to_uuid(row["document_id"]))
            result.setdefault(key, {"tags": set(), "entities": set()})
            result[key]["entities"].add(f"{row['type']}:{row['name']}")
        return result

    def document_metadata(
        self, doc_ids: list[str], group_ids: list[str], *, allow_all: bool = False
    ) -> dict[str, dict[str, Any]]:
        """Return accessible metadata for document IDs keyed by string UUID.

        When *allow_all* is True the group filter is omitted (admin bypass).
        """
        if not doc_ids:
            return {}
        if not allow_all and not group_ids:
            return {}
        params, placeholders = _uuid_params(doc_ids)
        if allow_all:
            rows = self._connection.execute(
                sa.text(f"""
                    SELECT d.id, d.title, d.source, d.metadata
                    FROM documents d
                    WHERE d.id IN ({placeholders})
                    """),
                params,
            ).mappings()
        else:
            group_params, group_placeholders = _uuid_params(group_ids, prefix="group")
            params.update(group_params)
            rows = self._connection.execute(
                # EXISTS rather than JOIN+DISTINCT: a source granted to several
                # of the caller's groups would otherwise duplicate rows, and
                # SELECT DISTINCT over the json `metadata` column fails on
                # Postgres (json has no equality operator). EXISTS dedupes
                # without comparing json and is portable to SQLite.
                sa.text(f"""
                    SELECT d.id, d.title, d.source, d.metadata
                    FROM documents d
                    WHERE d.id IN ({placeholders})
                      AND EXISTS (
                          SELECT 1 FROM source_permissions sp
                          WHERE sp.source_id = d.source_id
                            AND sp.group_id IN ({group_placeholders})
                      )
                    """),
                params,
            ).mappings()
        return {str(to_uuid(row["id"])): dict(row) for row in rows}

    def expertise_signals(self, doc_ids: list[str], group_ids: list[str]) -> list[dict[str, Any]]:
        """Return per-user expertise signals for accessible matching documents."""
        if not doc_ids or not group_ids:
            return []
        params, placeholders = _uuid_params(doc_ids)
        group_params, group_placeholders = _uuid_params(group_ids, prefix="group")
        params.update(group_params)
        rows = self._connection.execute(
            sa.text(f"""
                WITH accessible_docs AS (
                    SELECT DISTINCT d.id, d.title
                    FROM documents d
                    JOIN source_permissions sp ON sp.source_id = d.source_id
                    WHERE d.id IN ({placeholders})
                      AND sp.group_id IN ({group_placeholders})
                ),
                signal_rows AS (
                    SELECT v.user_id, v.document_id, 'view' AS signal_type
                    FROM document_views v
                    JOIN accessible_docs ad ON ad.id = v.document_id

                    UNION ALL

                    SELECT c.author_id AS user_id, c.document_id, 'comment' AS signal_type
                    FROM document_comments c
                    JOIN accessible_docs ad ON ad.id = c.document_id
                    WHERE c.deleted_at IS NULL

                    UNION ALL

                    SELECT a.user_id, a.document_id, 'annotation' AS signal_type
                    FROM annotations a
                    JOIN accessible_docs ad ON ad.id = a.document_id
                    WHERE a.is_private = false
                )
                SELECT
                    s.user_id,
                    u.display_name,
                    s.document_id,
                    s.signal_type,
                    ad.title AS doc_title
                FROM signal_rows s
                JOIN users u ON u.id = s.user_id
                JOIN accessible_docs ad ON ad.id = s.document_id
                ORDER BY u.display_name, ad.title
                """),
            params,
        ).mappings()
        return [
            {
                **dict(row),
                "user_id": str(to_uuid(row["user_id"])),
                "document_id": str(to_uuid(row["document_id"])),
            }
            for row in rows
        ]

    def active_subscriptions(self) -> list[dict[str, Any]]:
        """Return enabled alert subscriptions with owner display names."""
        rows = self._connection.execute(
            sa.text("""
                SELECT
                    s.id,
                    s.user_id,
                    u.display_name,
                    s.name,
                    s.query
                FROM alert_subscriptions s
                JOIN users u ON u.id = s.user_id
                WHERE s.enabled = true
                """)
        ).mappings()
        return [
            {
                **dict(row),
                "user_id": str(to_uuid(row["user_id"])),
                "id": str(to_uuid(row["id"])),
            }
            for row in rows
        ]

    def user_shares_group(self, user_id: UUID, group_ids: list[str]) -> bool:
        """Return whether *user_id* is a member of at least one group in *group_ids*."""
        if not group_ids:
            return False
        params, placeholders = _uuid_params(group_ids, prefix="group")
        params["user_id"] = db_uuid(user_id)
        value = self._connection.execute(
            sa.text(f"""
                SELECT 1
                FROM user_groups ug
                WHERE ug.user_id = :user_id
                  AND ug.group_id IN ({placeholders})
                LIMIT 1
                """),
            params,
        ).scalar_one_or_none()
        return value is not None


def _uuid_params(values: list[str], prefix: str = "id") -> tuple[dict[str, str], str]:
    params = {f"{prefix}_{index}": UUID(value).hex for index, value in enumerate(values)}
    placeholders = ", ".join(f":{prefix}_{index}" for index in range(len(values)))
    return params, placeholders
