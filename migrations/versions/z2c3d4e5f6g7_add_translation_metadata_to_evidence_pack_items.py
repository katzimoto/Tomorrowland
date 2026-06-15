"""add translation version identity columns to evidence_pack_items (#734)

Revision ID: z2c3d4e5f6g7
Revises: z1b2c3d4e5f6
Create Date: 2026-06-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "z2c3d4e5f6g7"
down_revision: str | Sequence[str] | None = "z1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evidence_pack_items",
        sa.Column("text_lane", sa.Text(), nullable=True),
    )
    op.add_column(
        "evidence_pack_items",
        sa.Column("translated_from", sa.Text(), nullable=True),
    )
    op.add_column(
        "evidence_pack_items",
        sa.Column("translation_version_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "evidence_pack_items",
        sa.Column("translation_quality", sa.Text(), nullable=True),
    )
    op.add_column(
        "evidence_pack_items",
        sa.Column("translation_validation_status", sa.Text(), nullable=True),
    )
    op.add_column(
        "evidence_pack_items",
        sa.Column("matched_text_kind", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("evidence_pack_items", "matched_text_kind")
    op.drop_column("evidence_pack_items", "translation_validation_status")
    op.drop_column("evidence_pack_items", "translation_quality")
    op.drop_column("evidence_pack_items", "translation_version_id")
    op.drop_column("evidence_pack_items", "translated_from")
    op.drop_column("evidence_pack_items", "text_lane")
