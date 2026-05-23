"""add schedule column to ingestion_sources

Revision ID: u5v6w7x8y9z0
Revises: t4u5v6w7x8y9
Create Date: 2026-05-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "u5v6w7x8y9z0"
down_revision: str | None = "t4u5v6w7x8y9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("ingestion_sources") as batch_op:
        batch_op.add_column(sa.Column("schedule", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ingestion_sources") as batch_op:
        batch_op.drop_column("schedule")
