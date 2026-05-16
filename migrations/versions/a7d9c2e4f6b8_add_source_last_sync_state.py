"""add source last sync state

Revision ID: a7d9c2e4f6b8
Revises: e5f7a9b1c3d4
Create Date: 2026-05-10 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7d9c2e4f6b8"
down_revision: str | None = "e5f7a9b1c3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("ingestion_sources") as batch_op:
        batch_op.add_column(sa.Column("last_sync_status", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("last_sync_indexed", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("last_sync_skipped", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("last_sync_failed", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("last_sync_error", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ingestion_sources") as batch_op:
        batch_op.drop_column("last_sync_at")
        batch_op.drop_column("last_sync_error")
        batch_op.drop_column("last_sync_failed")
        batch_op.drop_column("last_sync_skipped")
        batch_op.drop_column("last_sync_indexed")
        batch_op.drop_column("last_sync_status")
