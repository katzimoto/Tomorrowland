"""Add admin_runtime_config_overrides table for #812 runtime configuration UI.

Stores database-backed overrides for runtime-editable settings declared in the
config registry (``services.api.config_registry``).  ``key`` is the natural
primary key so upserts can use ``ON CONFLICT (key)`` on both SQLite and
PostgreSQL.

Revision ID: cfg9a1b2d3e4
Revises: z2c3d4e5f6g7
Create Date: 2026-06-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "cfg9a1b2d3e4"
down_revision: str | Sequence[str] | None = "z2c3d4e5f6g7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_runtime_config_overrides",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column(
            "value_type",
            sa.Text(),
            nullable=False,
            comment="Registry type: string | int | float | bool | enum | json",
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "updated_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_admin_runtime_config_overrides_updated_at",
        "admin_runtime_config_overrides",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_admin_runtime_config_overrides_updated_at",
        table_name="admin_runtime_config_overrides",
    )
    op.drop_table("admin_runtime_config_overrides")
