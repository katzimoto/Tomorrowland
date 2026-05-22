"""add chat_messages table

Revision ID: q7r8s9t0u1v2
Revises: k1l2m3n4o5p6
Create Date: 2026-05-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "q7r8s9t0u1v2"
down_revision: str | None = "k1l2m3n4o5p6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("rewritten_query", sa.Text(), nullable=True),
        sa.Column("citations", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("retrieval_trace", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("metadata", sa.Text(), nullable=False, server_default="{}"),
    )
    op.create_index(
        "ix_chat_messages_session_created",
        "chat_messages",
        ["session_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_messages_session_created", table_name="chat_messages")
    op.drop_table("chat_messages")
