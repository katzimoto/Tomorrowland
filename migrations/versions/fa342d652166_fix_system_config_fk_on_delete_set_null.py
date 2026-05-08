"""fix system_config fk on delete set null

Revision ID: fa342d652166
Revises: 1914954ae9d7
Create Date: 2026-05-08 01:10:53.476700
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "fa342d652166"
down_revision: str | None = "1914954ae9d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("system_config") as batch_op:
        batch_op.drop_constraint("fk_system_config_updated_by_users", type_="foreignkey")
        batch_op.create_foreign_key(
            "fk_system_config_updated_by_users",
            "users",
            ["updated_by"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("system_config") as batch_op:
        batch_op.drop_constraint("fk_system_config_updated_by_users", type_="foreignkey")
        batch_op.create_foreign_key(
            "fk_system_config_updated_by_users",
            "users",
            ["updated_by"],
            ["id"],
        )
