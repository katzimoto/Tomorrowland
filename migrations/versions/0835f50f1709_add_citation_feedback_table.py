"""add citation_feedback table

Revision ID: 0835f50f1709
Revises: m3n4o5p6q7r8
Create Date: 2026-06-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0835f50f1709"
down_revision: str | Sequence[str] | None = "m3n4o5p6q7r8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "citation_feedback",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("citation_id", sa.Text(), nullable=True),
        sa.Column(
            "message_id",
            sa.Uuid(),
            sa.ForeignKey("chat_messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Text(), nullable=True),
        sa.Column(
            "feedback_type",
            sa.Text(),
            nullable=False,
        ),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_citation_feedback_document_id",
        "citation_feedback",
        ["document_id"],
    )
    op.create_index(
        "ix_citation_feedback_message_id",
        "citation_feedback",
        ["message_id"],
    )
    op.create_index(
        "ix_citation_feedback_user_id",
        "citation_feedback",
        ["user_id"],
    )
    op.create_index(
        "ix_citation_feedback_feedback_type",
        "citation_feedback",
        ["feedback_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_citation_feedback_feedback_type", table_name="citation_feedback")
    op.drop_index("ix_citation_feedback_user_id", table_name="citation_feedback")
    op.drop_index("ix_citation_feedback_message_id", table_name="citation_feedback")
    op.drop_index("ix_citation_feedback_document_id", table_name="citation_feedback")
    op.drop_table("citation_feedback")
