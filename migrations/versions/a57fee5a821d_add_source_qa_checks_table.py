"""add source_qa_checks table

Revision ID: a57fee5a821d
Revises: a0b1c2d3e4f5
Create Date: 2026-05-30 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a57fee5a821d"
down_revision: str | Sequence[str] | None = "a0b1c2d3e4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_qa_checks",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "source_id",
            sa.Uuid(),
            sa.ForeignKey("ingestion_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("checked_at", sa.String(32), nullable=False),
        sa.Column("total_documents", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("indexed_documents", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("pending_documents", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("failed_documents", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("empty_chunks", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("missing_content", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("missing_metadata", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("missing_title", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("ocr_eligible", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("ocr_maybe_needed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("index_lag_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("issues", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("source_id", name="uq_source_qa_checks_source_id"),
    )
    op.create_index("ix_source_qa_checks_source_id", "source_qa_checks", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_source_qa_checks_source_id", table_name="source_qa_checks")
    op.drop_table("source_qa_checks")
