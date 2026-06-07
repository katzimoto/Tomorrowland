"""add performance indexes for documents and source_permissions

Revision ID: m3n4o5p6q7r8
Revises: e5f7g9h1i2j3
Create Date: 2026-06-07 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "m3n4o5p6q7r8"
down_revision: str | None = "e5f7g9h1i2j3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Speeds up version-family lookups during search and ingestion dedup.
    op.create_index(
        "ix_documents_version_family_id",
        "documents",
        ["version_family_id"],
    )
    # Speeds up dedup lookups by (source_id, external_id) during ingestion.
    op.create_index(
        "ix_documents_external_id_source",
        "documents",
        ["source_id", "external_id"],
    )
    # Speeds up permission checks during search ACL filtering.
    op.create_index(
        "ix_source_permissions_group_id",
        "source_permissions",
        ["group_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_source_permissions_group_id", table_name="source_permissions")
    op.drop_index("ix_documents_external_id_source", table_name="documents")
    op.drop_index("ix_documents_version_family_id", table_name="documents")
