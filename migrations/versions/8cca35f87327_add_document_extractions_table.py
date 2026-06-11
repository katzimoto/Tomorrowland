"""add document_extractions table

Revision ID: 8cca35f87327
Revises: e46868074714
Create Date: 2026-06-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8cca35f87327"
down_revision: str | Sequence[str] | None = "e46868074714"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_extractions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("parser_name", sa.Text(), nullable=False),
        sa.Column("parser_version", sa.Text(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("warnings", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("attempts", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_document_extractions_document_id",
        "document_extractions",
        ["document_id"],
    )
    op.create_index(
        "ix_document_extractions_parser_name",
        "document_extractions",
        ["parser_name"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_extractions_parser_name", table_name="document_extractions")
    op.drop_index("ix_document_extractions_document_id", table_name="document_extractions")
    op.drop_table("document_extractions")
