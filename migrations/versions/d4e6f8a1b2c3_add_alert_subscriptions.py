"""add alert subscriptions and notifications

Revision ID: d4e6f8a1b2c3
Revises: c3d5e7f2a4b6
Create Date: 2026-05-08 10:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e6f8a1b2c3"
down_revision: str | None = "c3d5e7f2a4b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alert_subscriptions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("similarity_threshold", sa.Float(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_notified", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_alert_subscriptions_user_id",
        "alert_subscriptions",
        ["user_id"],
    )

    op.create_table(
        "alert_notifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "subscription_id",
            sa.Uuid(),
            sa.ForeignKey("alert_subscriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("similarity", sa.Float(), nullable=False),
        sa.Column("read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_alert_notifications_user_read_created",
        "alert_notifications",
        ["user_id", "read", "created_at"],
    )
    op.create_index(
        "uq_alert_notifications_subscription_doc",
        "alert_notifications",
        ["subscription_id", "document_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_alert_notifications_subscription_doc", table_name="alert_notifications")
    op.drop_index("ix_alert_notifications_user_read_created", table_name="alert_notifications")
    op.drop_table("alert_notifications")
    op.drop_index("ix_alert_subscriptions_user_id", table_name="alert_subscriptions")
    op.drop_table("alert_subscriptions")
