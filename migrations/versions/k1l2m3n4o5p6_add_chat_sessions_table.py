"""add chat_sessions table

Revision ID: k1l2m3n4o5p6
Revises: j4k5l6m7n8o9
Create Date: 2026-05-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "k1l2m3n4o5p6"
down_revision: str | None = "j4k5l6m7n8o9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False, server_default="New Chat"),
        sa.Column("scope_type", sa.Text(), nullable=False),
        sa.Column("scope_ids", sa.Text(), nullable=False, server_default="[]"),
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
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", sa.Text(), nullable=False, server_default="{}"),
    )
    op.create_index(
        "ix_chat_sessions_user_id",
        "chat_sessions",
        ["user_id"],
    )
    op.create_index(
        "ix_chat_sessions_updated_at",
        "chat_sessions",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_sessions_updated_at", table_name="chat_sessions")
    op.drop_index("ix_chat_sessions_user_id", table_name="chat_sessions")
    op.drop_table("chat_sessions")
