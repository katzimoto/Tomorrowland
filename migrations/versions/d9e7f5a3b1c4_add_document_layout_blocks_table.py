"""add document_layout_blocks table

Revision ID: d9e7f5a3b1c4
Revises: 8cca35f87327
Create Date: 2026-06-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d9e7f5a3b1c4"
down_revision: str | Sequence[str] | None = "8cca35f87327"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_layout_blocks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column(
            "block_type",
            sa.Text(),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("bbox", sa.JSON(), nullable=True),
        sa.Column("parser", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("reading_order", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_document_layout_blocks_document_id",
        "document_layout_blocks",
        ["document_id"],
    )
    op.create_index(
        "ix_document_layout_blocks_block_type",
        "document_layout_blocks",
        ["block_type"],
    )
    op.create_index(
        "ix_document_layout_blocks_doc_page",
        "document_layout_blocks",
        ["document_id", "page_number"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_layout_blocks_doc_page", table_name="document_layout_blocks")
    op.drop_index("ix_document_layout_blocks_block_type", table_name="document_layout_blocks")
    op.drop_index("ix_document_layout_blocks_document_id", table_name="document_layout_blocks")
    op.drop_table("document_layout_blocks")
