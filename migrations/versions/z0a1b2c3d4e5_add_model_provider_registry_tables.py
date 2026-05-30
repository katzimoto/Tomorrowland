"""add model provider registry tables

Revision ID: z0a1b2c3d4e5
Revises: y9z0a1b2c3d4
Create Date: 2026-05-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "z0a1b2c3d4e5"
down_revision: str | Sequence[str] | None = "y9z0a1b2c3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_providers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("provider_type", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("api_key_ref", sa.Text(), nullable=True),
        sa.Column(
            "locality",
            sa.Text(),
            sa.CheckConstraint(
                "locality IN ('local', 'self_hosted', 'external')",
                name="ck_model_providers_locality",
            ),
            nullable=False,
            server_default="local",
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
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
        sa.UniqueConstraint("name", name="uq_model_providers_name"),
    )

    op.create_table(
        "model_descriptors",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "provider_id",
            sa.Uuid(),
            sa.ForeignKey("model_providers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("capabilities", sa.JSON(), nullable=True),
        sa.Column("context_window", sa.Integer(), nullable=True),
        sa.Column("max_output_tokens", sa.Integer(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
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
            "provider_id",
            "model_name",
            name="uq_model_descriptors_provider_model",
        ),
    )
    op.create_index(
        "ix_model_descriptors_provider_id",
        "model_descriptors",
        ["provider_id"],
    )

    op.create_table(
        "model_task_defaults",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("task_type", sa.Text(), nullable=False),
        sa.Column(
            "provider_id",
            sa.Uuid(),
            sa.ForeignKey("model_providers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "model_descriptor_id",
            sa.Uuid(),
            sa.ForeignKey("model_descriptors.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("parameters", sa.JSON(), nullable=True),
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
        sa.UniqueConstraint("task_type", name="uq_model_task_defaults_task_type"),
    )


def downgrade() -> None:
    op.drop_table("model_task_defaults")
    op.drop_index("ix_model_descriptors_provider_id", table_name="model_descriptors")
    op.drop_table("model_descriptors")
    op.drop_table("model_providers")
