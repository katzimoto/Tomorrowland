"""allow event dlq entries without documents

Revision ID: 9a65b7c3d4e5
Revises: e5f7a9b1c3d4
Create Date: 2026-05-10 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9a65b7c3d4e5"
down_revision: str | None = "e5f7a9b1c3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("dlq") as batch_op:
        batch_op.alter_column(
            "doc_id",
            existing_type=sa.Uuid(),
            nullable=True,
            existing_nullable=False,
        )


def downgrade() -> None:
    # Remove event-level DLQ records before restoring the original not-null
    # document requirement.
    op.execute("DELETE FROM dlq WHERE doc_id IS NULL")
    with op.batch_alter_table("dlq") as batch_op:
        batch_op.alter_column(
            "doc_id",
            existing_type=sa.Uuid(),
            nullable=False,
            existing_nullable=True,
        )
