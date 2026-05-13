"""add source validation state

Revision ID: b8c1d2e3f7a9
Revises: a7d9c2e4f6b8
Create Date: 2026-05-13 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8c1d2e3f7a9"
down_revision: str | None = "a7d9c2e4f6b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("ingestion_sources") as batch_op:
        batch_op.add_column(sa.Column("last_validation_status", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("last_validation_error", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("ingestion_sources") as batch_op:
        batch_op.drop_column("last_validated_at")
        batch_op.drop_column("last_validation_error")
        batch_op.drop_column("last_validation_status")
