"""add user_document_tags table

Revision ID: r1s2t3u4v5w6
Revises: q7r8s9t0u1v2
Create Date: 2026-05-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "r1s2t3u4v5w6"
down_revision: str | None = "q7r8s9t0u1v2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_document_tags",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tag", sa.String(100), nullable=False),
        sa.Column("is_private", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_user_document_tags_doc_user",
        "user_document_tags",
        ["document_id", "user_id"],
    )
    op.create_index(
        "ix_user_document_tags_doc_private",
        "user_document_tags",
        ["document_id", "is_private"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_document_tags_doc_private", table_name="user_document_tags")
    op.drop_index("ix_user_document_tags_doc_user", table_name="user_document_tags")
    op.drop_table("user_document_tags")
