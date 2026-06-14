"""add evidence_packs and evidence_pack_items tables

Revision ID: c7e2a9b4d1f3
Revises: f2a4c6e8b0d2
Create Date: 2026-06-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7e2a9b4d1f3"
down_revision: str | Sequence[str] | None = "f2a4c6e8b0d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evidence_packs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_scope", sa.JSON(), nullable=True),
        sa.Column("created_from", sa.Text(), nullable=False, server_default="manual"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
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
        sa.CheckConstraint(
            "created_from IN ('chat', 'search', 'agent', 'manual')",
            name="ck_evidence_packs_created_from",
        ),
    )
    op.create_index(
        "ix_evidence_packs_owner_user_id",
        "evidence_packs",
        ["owner_user_id"],
    )

    op.create_table(
        "evidence_pack_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "evidence_pack_id",
            sa.Uuid(),
            sa.ForeignKey("evidence_packs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_id", sa.Text(), nullable=True),
        sa.Column("citation_id", sa.Text(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("section_heading", sa.Text(), nullable=True),
        sa.Column("text_excerpt", sa.Text(), nullable=False),
        sa.Column("translated_text", sa.Text(), nullable=True),
        sa.Column("claim", sa.Text(), nullable=True),
        sa.Column("item_type", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "item_type IN ('citation', 'passage', 'claim', 'note')",
            name="ck_evidence_pack_items_item_type",
        ),
    )
    op.create_index(
        "ix_evidence_pack_items_evidence_pack_id",
        "evidence_pack_items",
        ["evidence_pack_id"],
    )
    op.create_index(
        "ix_evidence_pack_items_document_id",
        "evidence_pack_items",
        ["document_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_evidence_pack_items_document_id",
        table_name="evidence_pack_items",
    )
    op.drop_index(
        "ix_evidence_pack_items_evidence_pack_id",
        table_name="evidence_pack_items",
    )
    op.drop_table("evidence_pack_items")
    op.drop_index(
        "ix_evidence_packs_owner_user_id",
        table_name="evidence_packs",
    )
    op.drop_table("evidence_packs")
