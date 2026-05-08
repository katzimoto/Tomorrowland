"""add document views table

Revision ID: f24670c1811f
Revises: fa342d652166
Create Date: 2026-05-08 01:38:08.047342
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f24670c1811f"
down_revision: str | None = "fa342d652166"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_views",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "doc_id",
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
        sa.Column(
            "viewed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("doc_id", "user_id", name="uq_document_views_doc_user"),
    )
    op.create_index("ix_document_views_doc_id", "document_views", ["doc_id"])
    op.create_index("ix_document_views_user_id", "document_views", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_document_views_user_id", table_name="document_views")
    op.drop_index("ix_document_views_doc_id", table_name="document_views")
    op.drop_table("document_views")
