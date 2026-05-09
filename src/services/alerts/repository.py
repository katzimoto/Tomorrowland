"""Database access for alert subscriptions and notifications."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from shared.db import db_uuid
from shared.metrics import current_metrics


class AlertRepository:
    """CRUD and matching queries for alerts."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def list_subscriptions(self, user_id: UUID) -> list[dict[str, Any]]:
        """List subscriptions owned by a user."""
        rows = self._connection.execute(
            sa.text(
                """
                SELECT
                    s.id,
                    s.user_id,
                    s.name,
                    s.query,
                    s.similarity_threshold,
                    s.enabled,
                    s.created_at,
                    s.updated_at,
                    s.last_notified,
                    COUNT(n.id) FILTER (WHERE n.read = false) AS unread_count
                FROM alert_subscriptions s
                LEFT JOIN alert_notifications n ON n.subscription_id = s.id
                WHERE s.user_id = :user_id
                GROUP BY s.id, s.user_id, s.name, s.query, s.similarity_threshold,
                         s.enabled, s.created_at, s.updated_at, s.last_notified
                ORDER BY s.created_at DESC
                """
            ),
            {"user_id": db_uuid(user_id)},
        ).mappings()
        return [dict(row) for row in rows]

    def create_subscription(
        self,
        user_id: UUID,
        name: str,
        query: str,
        similarity_threshold: float | None,
        enabled: bool,
    ) -> dict[str, Any]:
        """Create an alert subscription."""
        subscription_id = uuid4()
        row = (
            self._connection.execute(
                sa.text(
                    """
                    INSERT INTO alert_subscriptions (
                        id, user_id, name, query, similarity_threshold, enabled,
                        created_at, updated_at
                    )
                    VALUES (
                        :id, :user_id, :name, :query, :similarity_threshold, :enabled,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    RETURNING id, user_id, name, query, similarity_threshold, enabled,
                              created_at, updated_at, last_notified
                    """
                ),
                {
                    "id": db_uuid(subscription_id),
                    "user_id": db_uuid(user_id),
                    "name": name,
                    "query": query,
                    "similarity_threshold": similarity_threshold,
                    "enabled": enabled,
                },
            )
            .mappings()
            .first()
        )
        if row is None:
            raise RuntimeError("subscription insert did not persist")
        return dict(row)

    def get_subscription(self, subscription_id: UUID) -> dict[str, Any] | None:
        """Return a subscription by id."""
        row = (
            self._connection.execute(
                sa.text("SELECT * FROM alert_subscriptions WHERE id = :id"),
                {"id": db_uuid(subscription_id)},
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None

    def update_subscription(
        self,
        subscription_id: UUID,
        name: str | None = None,
        query: str | None = None,
        similarity_threshold: float | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any] | None:
        """Update a subscription and return the refreshed row."""
        fields: list[str] = []
        params: dict[str, Any] = {"id": db_uuid(subscription_id)}
        if name is not None:
            fields.append("name = :name")
            params["name"] = name
        if query is not None:
            fields.append("query = :query")
            params["query"] = query
        if similarity_threshold is not None:
            fields.append("similarity_threshold = :similarity_threshold")
            params["similarity_threshold"] = similarity_threshold
        if enabled is not None:
            fields.append("enabled = :enabled")
            params["enabled"] = enabled
        if fields:
            fields.append("updated_at = CURRENT_TIMESTAMP")
            self._connection.execute(
                sa.text(
                    f"""
                    UPDATE alert_subscriptions
                    SET {", ".join(fields)}
                    WHERE id = :id
                    """
                ),
                params,
            )
        return self.get_subscription(subscription_id)

    def delete_subscription(self, subscription_id: UUID) -> None:
        """Delete a subscription and its notifications."""
        self._connection.execute(
            sa.text("DELETE FROM alert_subscriptions WHERE id = :id"),
            {"id": db_uuid(subscription_id)},
        )

    def active_subscriptions_for_doc(self, doc_id: UUID) -> list[dict[str, Any]]:
        """Return active subscriptions whose owners can access a document."""
        rows = self._connection.execute(
            sa.text(
                """
                SELECT DISTINCT
                    s.id,
                    s.user_id,
                    s.name,
                    s.query,
                    s.similarity_threshold
                FROM alert_subscriptions s
                JOIN user_groups ug ON ug.user_id = s.user_id
                JOIN documents d ON d.id = :doc_id
                JOIN source_permissions sp
                  ON sp.source_id = d.source_id
                 AND sp.group_id = ug.group_id
                WHERE s.enabled = true
                """
            ),
            {"doc_id": db_uuid(doc_id)},
        ).mappings()
        return [dict(row) for row in rows]

    def create_notification(
        self,
        subscription_id: UUID,
        user_id: UUID,
        doc_id: UUID,
        similarity: float,
    ) -> bool:
        """Create a notification if one does not already exist."""
        notification_id = uuid4()
        result = self._connection.execute(
            sa.text(
                """
                INSERT INTO alert_notifications (
                    id, subscription_id, user_id, doc_id, similarity, read, created_at
                )
                VALUES (
                    :id, :subscription_id, :user_id, :doc_id, :similarity,
                    false, CURRENT_TIMESTAMP
                )
                ON CONFLICT (subscription_id, doc_id) DO NOTHING
                """
            ),
            {
                "id": db_uuid(notification_id),
                "subscription_id": db_uuid(subscription_id),
                "user_id": db_uuid(user_id),
                "doc_id": db_uuid(doc_id),
                "similarity": similarity,
            },
        )
        if result.rowcount:
            self._connection.execute(
                sa.text(
                    """
                    UPDATE alert_subscriptions
                    SET last_notified = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                    """
                ),
                {"id": db_uuid(subscription_id)},
            )
        created = bool(result.rowcount)
        metrics = current_metrics()
        if metrics is not None:
            metrics.notifications_total.labels("create", "success" if created else "skipped").inc()
        return created

    def list_notifications(self, user_id: UUID, unread_only: bool = True) -> list[dict[str, Any]]:
        """List notifications for a user."""
        read_filter = "AND n.read = false" if unread_only else ""
        rows = self._connection.execute(
            sa.text(
                f"""
                SELECT
                    n.id,
                    n.subscription_id,
                    n.user_id,
                    n.doc_id,
                    n.similarity,
                    n.read,
                    n.created_at,
                    s.name AS subscription_name,
                    s.query AS subscription_query,
                    d.title AS doc_title
                FROM alert_notifications n
                JOIN alert_subscriptions s ON s.id = n.subscription_id
                JOIN documents d ON d.id = n.doc_id
                WHERE n.user_id = :user_id
                  {read_filter}
                ORDER BY n.created_at DESC
                """
            ),
            {"user_id": db_uuid(user_id)},
        ).mappings()
        return [dict(row) for row in rows]

    def get_notification(self, notification_id: UUID) -> dict[str, Any] | None:
        """Return a notification by id."""
        row = (
            self._connection.execute(
                sa.text("SELECT * FROM alert_notifications WHERE id = :id"),
                {"id": db_uuid(notification_id)},
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None

    def mark_notification_read(self, notification_id: UUID) -> dict[str, Any] | None:
        """Mark a notification as read and return it."""
        self._connection.execute(
            sa.text("UPDATE alert_notifications SET read = true WHERE id = :id"),
            {"id": db_uuid(notification_id)},
        )
        return self.get_notification(notification_id)
