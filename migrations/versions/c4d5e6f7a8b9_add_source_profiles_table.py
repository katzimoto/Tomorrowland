"""add source_profiles table

Revision ID: c4d5e6f7a8b9
Revises: z0a1b2c3d4e5
Create Date: 2026-05-30 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4d5e6f7a8b9"
down_revision: str | Sequence[str] | None = "a57fee5a821d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_profiles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "source_id",
            sa.Uuid(),
            sa.ForeignKey("ingestion_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "domain_type",
            sa.Text(),
            sa.CheckConstraint(
                sa.text(
                    "domain_type IN ('legal','engineering','logs','email','spreadsheet','generic')"
                ),
                name="ck_source_profiles_domain_type",
            ),
            nullable=False,
        ),
        sa.Column(
            "chunking_strategy",
            sa.Text(),
            sa.CheckConstraint(
                sa.text(
                    "chunking_strategy IN ('paragraph','clause','heading','row','thread','page','code_block','default')"
                ),  # noqa: E501
                name="ck_source_profiles_chunking_strategy",
            ),
            nullable=False,
        ),
        sa.Column(
            "retrieval_strategy",
            sa.Text(),
            sa.CheckConstraint(
                sa.text(
                    "retrieval_strategy IN ('hybrid','vector_only','keyword_only','metadata_first','default')"
                ),  # noqa: E501
                name="ck_source_profiles_retrieval_strategy",
            ),
            nullable=False,
        ),
        sa.Column(
            "extraction_strategy",
            sa.Text(),
            sa.CheckConstraint(
                sa.text(
                    "extraction_strategy IN ('full_text','ocr_required','table_aware','header_metadata','default')"
                ),  # noqa: E501
                name="ck_source_profiles_extraction_strategy",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Text(),
            sa.CheckConstraint(
                sa.text("status IN ('draft', 'active', 'needs_review', 'deprecated')"),
                name="ck_source_profiles_status",
            ),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column(
            "model_policy_provider_id",
            sa.Uuid(),
            sa.ForeignKey("model_providers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("config", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("approved_by", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
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
        "ix_source_profiles_source_id",
        "source_profiles",
        ["source_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_source_profiles_source_id", table_name="source_profiles")
    op.drop_table("source_profiles")
