"""allow pending_high translation quality

Revision ID: dc150d49033a
Revises: f24670c1811f
Create Date: 2026-05-08 03:47:06.315632
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "dc150d49033a"
down_revision: str | None = "f24670c1811f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_constraint("ck_documents_translation_quality", type_="check")
        batch_op.create_check_constraint(
            "ck_documents_translation_quality",
            sa.text(
                "translation_quality IN ('fast', 'high', 'pending_high') "
                "OR translation_quality IS NULL"
            ),
        )


def downgrade() -> None:
    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_constraint("ck_documents_translation_quality", type_="check")
        batch_op.create_check_constraint(
            "ck_documents_translation_quality",
            sa.text("translation_quality IN ('fast', 'high') OR translation_quality IS NULL"),
        )
