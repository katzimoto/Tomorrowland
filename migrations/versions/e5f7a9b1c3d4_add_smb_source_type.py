"""add smb source type

Revision ID: e5f7a9b1c3d4
Revises: d4e6f8a1b2c3
Create Date: 2026-05-10 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5f7a9b1c3d4"
down_revision: str | None = "d4e6f8a1b2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SOURCE_TYPES_WITH_SMB = "('folder', 'nifi', 'confluence', 'jira', 'smb')"
_SOURCE_TYPES_WITHOUT_SMB = "('folder', 'nifi', 'confluence', 'jira')"


def upgrade() -> None:
    with op.batch_alter_table("ingestion_sources") as batch_op:
        batch_op.drop_constraint("ck_ingestion_sources_type", type_="check")
        batch_op.create_check_constraint(
            "ck_ingestion_sources_type",
            sa.text(f"type IN {_SOURCE_TYPES_WITH_SMB}"),
        )

    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_constraint("ck_documents_source", type_="check")
        batch_op.create_check_constraint(
            "ck_documents_source",
            sa.text(f"source IN {_SOURCE_TYPES_WITH_SMB}"),
        )


def downgrade() -> None:
    # WARNING: This downgrade will fail for existing SMB rows. On SQLite the
    # batch table rebuild raises a constraint violation; on PostgreSQL the
    # constraint is created but existing rows silently violate it. Delete all
    # rows where ingestion_sources.type='smb' or documents.source='smb' before
    # running this downgrade.
    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_constraint("ck_documents_source", type_="check")
        batch_op.create_check_constraint(
            "ck_documents_source",
            sa.text(f"source IN {_SOURCE_TYPES_WITHOUT_SMB}"),
        )

    with op.batch_alter_table("ingestion_sources") as batch_op:
        batch_op.drop_constraint("ck_ingestion_sources_type", type_="check")
        batch_op.create_check_constraint(
            "ck_ingestion_sources_type",
            sa.text(f"type IN {_SOURCE_TYPES_WITHOUT_SMB}"),
        )
