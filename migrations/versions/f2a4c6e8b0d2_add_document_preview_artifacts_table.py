"""add document_preview_artifacts table

Revision ID: f2a4c6e8b0d2
Revises: d9e7f5a3b1c4
Create Date: 2026-06-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2a4c6e8b0d2"
down_revision: str | Sequence[str] | None = "d9e7f5a3b1c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_preview_artifacts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content_sha256", sa.Text(), nullable=False),
        sa.Column("renderer", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("manifest", sa.JSON(), nullable=True),
        sa.Column("files", sa.JSON(), nullable=True),
        sa.Column("error_category", sa.Text(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
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
        sa.UniqueConstraint(
            "document_id",
            "content_sha256",
            name="uq_preview_artifacts_doc_sha",
        ),
    )
    op.create_index(
        "ix_document_preview_artifacts_document_id",
        "document_preview_artifacts",
        ["document_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_document_preview_artifacts_document_id",
        table_name="document_preview_artifacts",
    )
    op.drop_table("document_preview_artifacts")
