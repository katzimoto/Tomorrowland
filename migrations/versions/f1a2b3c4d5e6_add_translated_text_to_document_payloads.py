"""add translated_text to document_payloads

Revision ID: f1a2b3c4d5e6
Revises: a2b3c4d5e6f7
Create Date: 2026-05-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "a2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "document_payloads",
        sa.Column("translated_text", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document_payloads", "translated_text")
