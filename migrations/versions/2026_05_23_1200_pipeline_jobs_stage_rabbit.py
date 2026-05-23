"""Add rabbit_message_id to pipeline_jobs.

Revision ID: a1b2c3d4e5f6
Revises: u5v6w7x8y9z0
Create Date: 2026-05-23 12:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "u5v6w7x8y9z0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pipeline_jobs",
        sa.Column("rabbit_message_id", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pipeline_jobs", "rabbit_message_id")
