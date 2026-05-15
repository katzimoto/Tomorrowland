"""add group_memberships table for nested groups

Revision ID: a2b3c4d5e6f7
Revises: d1e2f3a4b5c6
Create Date: 2026-05-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a2b3c4d5e6f7"
down_revision: str | None = "d1e2f3a4b5c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "group_memberships",
        sa.Column(
            "parent_group_id",
            sa.Uuid(),
            sa.ForeignKey("groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "child_group_id",
            sa.Uuid(),
            sa.ForeignKey("groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("parent_group_id", "child_group_id", name="pk_group_memberships"),
        sa.CheckConstraint(
            "parent_group_id <> child_group_id",
            name="ck_group_memberships_no_self_membership",
        ),
    )
    op.create_index(
        "ix_group_memberships_child",
        "group_memberships",
        ["child_group_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_group_memberships_child", table_name="group_memberships")
    op.drop_table("group_memberships")
