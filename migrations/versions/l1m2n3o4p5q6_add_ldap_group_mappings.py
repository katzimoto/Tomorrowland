"""add ldap_group_mappings table

Revision ID: l1m2n3o4p5q6
Revises: c4d5e6f7a8b9
Create Date: 2026-05-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "l1m2n3o4p5q6"
down_revision: str | Sequence[str] | None = "c4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ldap_group_mappings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ldap_dn", sa.Text(), nullable=False),
        sa.Column("ldap_external_id_attr", sa.Text(), nullable=False),
        sa.Column("ldap_external_id", sa.Text(), nullable=True),
        sa.Column("ldap_display_name", sa.Text(), nullable=False),
        sa.Column(
            "target_group_id",
            sa.Uuid(),
            sa.ForeignKey("groups.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
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
        sa.UniqueConstraint("ldap_dn", name="uq_ldap_group_mappings_dn"),
        sa.UniqueConstraint(
            "ldap_external_id_attr",
            "ldap_external_id",
            name="uq_ldap_group_mappings_external",
        ),
    )
    op.create_index(
        "ix_ldap_group_mappings_target",
        "ldap_group_mappings",
        ["target_group_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_ldap_group_mappings_target", table_name="ldap_group_mappings")
    op.drop_table("ldap_group_mappings")
