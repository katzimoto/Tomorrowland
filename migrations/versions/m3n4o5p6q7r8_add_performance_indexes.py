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
    # Build the indexes CONCURRENTLY so we do not take a write-blocking SHARE
    # lock on ``documents`` / ``source_permissions`` while ingestion is running
    # on large production tables. CONCURRENTLY cannot run inside a transaction,
    # hence the autocommit block (a no-op on SQLite, which ignores the
    # ``postgresql_concurrently`` flag). ``if_not_exists`` keeps the migration
    # re-runnable if a previous attempt left an index behind.
    with op.get_context().autocommit_block():
        # Speeds up version-family lookups during search and ingestion dedup.
        op.create_index(
            "ix_documents_version_family_id",
            "documents",
            ["version_family_id"],
            postgresql_concurrently=True,
            if_not_exists=True,
        )
        # Speeds up dedup lookups by (source_id, external_id) during ingestion.
        op.create_index(
            "ix_documents_external_id_source",
            "documents",
            ["source_id", "external_id"],
            postgresql_concurrently=True,
            if_not_exists=True,
        )
        # Speeds up permission checks during search ACL filtering.
        op.create_index(
            "ix_source_permissions_group_id",
            "source_permissions",
            ["group_id"],
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_source_permissions_group_id",
            table_name="source_permissions",
            postgresql_concurrently=True,
            if_exists=True,
        )
        op.drop_index(
            "ix_documents_external_id_source",
            table_name="documents",
            postgresql_concurrently=True,
            if_exists=True,
        )
        op.drop_index(
            "ix_documents_version_family_id",
            table_name="documents",
            postgresql_concurrently=True,
            if_exists=True,
        )
