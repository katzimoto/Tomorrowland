"""add document_key_points table

Stores ordered key bullet points extracted by the intelligence worker, one row
per point.  Replacement semantics are delete-then-insert (see
``IntelligenceRepository.upsert_key_points``).

Revision ID: i3j4k5l6m7n8
Revises: h2i3j4k5l6m7
Create Date: 2026-05-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "i3j4k5l6m7n8"
down_revision: str = "h2i3j4k5l6m7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_key_points",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key_point", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("document_id", "position", name="uq_document_key_points_doc_position"),
    )
    op.create_index(
        "ix_document_key_points_document_id",
        "document_key_points",
        ["document_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_key_points_document_id", table_name="document_key_points")
    op.drop_table("document_key_points")
