"""add document_comments table

Revision ID: b2c4d6e8f1a3
Revises: a1b9c3d5e7f2
Create Date: 2026-05-08 14:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c4d6e8f1a3"
down_revision: str | None = "a1b9c3d5e7f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_comments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "doc_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("body", sa.Text(), nullable=False),
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
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "edited_by_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "deleted_by_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_document_comments_doc_id_created_at",
        "document_comments",
        ["doc_id", "created_at DESC"],
    )
    op.create_index(
        "ix_document_comments_author_id",
        "document_comments",
        ["author_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_comments_author_id", table_name="document_comments")
    op.drop_index(
        "ix_document_comments_doc_id_created_at",
        table_name="document_comments",
    )
    op.drop_table("document_comments")
