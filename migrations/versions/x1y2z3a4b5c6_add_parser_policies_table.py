"""add parser_policies table

Revision ID: x1y2z3a4b5c6
Revises: 0835f50f1709
Create Date: 2026-06-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "x1y2z3a4b5c6"
down_revision: str | Sequence[str] | None = "0835f50f1709"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "parser_policies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "source_id",
            sa.Uuid(),
            sa.ForeignKey("ingestion_sources.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("mime_pattern", sa.Text(), nullable=False),
        sa.Column("parser_chain", sa.JSON(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_by", sa.Text(), nullable=True),
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
    )
    op.create_index(
        "uq_parser_policies_source_mime",
        "parser_policies",
        ["source_id", "mime_pattern"],
        unique=True,
    )
    op.create_index("ix_parser_policies_source_id", "parser_policies", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_parser_policies_source_id", table_name="parser_policies")
    op.drop_index("uq_parser_policies_source_mime", table_name="parser_policies")
    op.drop_table("parser_policies")
