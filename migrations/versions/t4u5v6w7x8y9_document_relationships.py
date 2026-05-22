"""add document_relationships table

Revision ID: t4u5v6w7x8y9
Revises: s3t4u5v6w7x8
Create Date: 2026-05-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "t4u5v6w7x8y9"
down_revision: str | None = "s3t4u5v6w7x8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_relationships",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "parent_document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "child_document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relationship_type", sa.String(30), nullable=False),
        sa.Column("path_in_parent", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "parent_document_id",
            "child_document_id",
            name="uq_document_relationships_parent_child",
        ),
    )
    op.create_index(
        "ix_document_relationships_parent",
        "document_relationships",
        ["parent_document_id"],
    )
    op.create_index(
        "ix_document_relationships_child",
        "document_relationships",
        ["child_document_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_relationships_child", table_name="document_relationships")
    op.drop_index("ix_document_relationships_parent", table_name="document_relationships")
    op.drop_table("document_relationships")
