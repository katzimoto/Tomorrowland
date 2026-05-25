"""Add language_detected flag to documents table.

Revision ID: v6w7x8y9z0a1
Revises: u5v6w7x8y9z0
Create Date: 2026-05-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "v6w7x8y9z0a1"
down_revision: str | None = "u5v6w7x8y9z0"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    """Add language_detected boolean column to documents."""
    op.add_column(
        "documents",
        sa.Column(
            "language_detected",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
    )


def downgrade() -> None:
    """Remove language_detected column from documents."""
    op.drop_column("documents", "language_detected")
