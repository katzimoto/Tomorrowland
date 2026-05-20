"""add summary v2 columns to document_summaries

Extends the table with status, structured metadata, content hash, and safe
failure tracking.  All new columns are nullable so existing rows remain valid.

Revision ID: j4k5l6m7n8o9
Revises: i3j4k5l6m7n8
Create Date: 2026-05-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "j4k5l6m7n8o9"
down_revision: str = "i3j4k5l6m7n8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "document_summaries",
        sa.Column("status", sa.Text(), nullable=True, server_default="available"),
    )
    op.add_column(
        "document_summaries",
        sa.Column("summary_bullets", sa.JSON(), nullable=True),
    )
    op.add_column(
        "document_summaries",
        sa.Column("language", sa.Text(), nullable=True),
    )
    op.add_column(
        "document_summaries",
        sa.Column("document_type", sa.Text(), nullable=True),
    )
    op.add_column(
        "document_summaries",
        sa.Column("source_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "document_summaries",
        sa.Column("input_chars", sa.Integer(), nullable=True),
    )
    op.add_column(
        "document_summaries",
        sa.Column("content_hash", sa.Text(), nullable=True),
    )
    op.add_column(
        "document_summaries",
        sa.Column("error_type", sa.Text(), nullable=True),
    )
    op.add_column(
        "document_summaries",
        sa.Column("error_summary", sa.Text(), nullable=True),
    )
    op.add_column(
        "document_summaries",
        sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=True),
    )
    with op.get_context().autocommit_block():
        op.execute("UPDATE document_summaries SET status = 'available' WHERE status IS NULL")


def downgrade() -> None:
    op.drop_column("document_summaries", "last_attempted_at")
    op.drop_column("document_summaries", "error_summary")
    op.drop_column("document_summaries", "error_type")
    op.drop_column("document_summaries", "content_hash")
    op.drop_column("document_summaries", "input_chars")
    op.drop_column("document_summaries", "source_text")
    op.drop_column("document_summaries", "document_type")
    op.drop_column("document_summaries", "language")
    op.drop_column("document_summaries", "summary_bullets")
    op.drop_column("document_summaries", "status")
