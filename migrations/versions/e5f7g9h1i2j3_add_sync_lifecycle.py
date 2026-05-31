"""add sync lifecycle tables (sync_runs, document_tombstones) and source health columns

Revision ID: e5f7g9h1i2j3
Revises: l1m2n3o4p5q6
Create Date: 2026-05-31 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5f7g9h1i2j3"
down_revision: str | None = "l1m2n3o4p5q6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -- sync_runs: tracks each sync lifecycle from queued to completion --
    op.create_table(
        "sync_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "source_id",
            sa.Uuid(),
            sa.ForeignKey("ingestion_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("connector_type", sa.Text(), nullable=False),
        sa.Column("sync_mode", sa.Text(), nullable=False, server_default="incremental"),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checkpoint", sa.Text(), nullable=True),
        sa.Column("documents_discovered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("documents_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("documents_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("documents_unchanged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("documents_deleted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("documents_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("documents_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "sync_mode IN ('incremental', 'full_resync')",
            name="ck_sync_runs_sync_mode",
        ),
        sa.CheckConstraint(
            sa.text(
                "status IN ('queued','running','completed',"
                "'completed_with_warnings','failed','cancelled')"
            ),
            name="ck_sync_runs_status",
        ),
    )
    op.create_index("ix_sync_runs_source_id", "sync_runs", ["source_id"])
    op.create_index("ix_sync_runs_status", "sync_runs", ["status"])
    op.create_index(
        "ix_sync_runs_source_id_started_at",
        "sync_runs",
        ["source_id", "started_at"],
    )

    # -- document_tombstones: tracks upstream deletions so documents can be
    #    excluded from search without immediately destroying data. --
    op.create_table(
        "document_tombstones",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "source_id",
            sa.Uuid(),
            sa.ForeignKey("ingestion_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_family_id", sa.Uuid(), nullable=True),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "tombstoned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_document_tombstones_source_id",
        "document_tombstones",
        ["source_id"],
    )
    op.create_index(
        "ix_document_tombstones_external_id",
        "document_tombstones",
        ["source_id", "external_id"],
    )
    op.create_index(
        "ix_document_tombstones_version_family_id",
        "document_tombstones",
        ["version_family_id"],
    )

    # -- Add source health columns to ingestion_sources --
    with op.batch_alter_table("ingestion_sources") as batch_op:
        batch_op.add_column(
            sa.Column("last_successful_sync_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("last_failed_sync_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("warning_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(sa.Column("last_sync_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ingestion_sources") as batch_op:
        batch_op.drop_column("last_sync_id")
        batch_op.drop_column("warning_count")
        batch_op.drop_column("failure_count")
        batch_op.drop_column("last_failed_sync_at")
        batch_op.drop_column("last_successful_sync_at")

    op.drop_index("ix_document_tombstones_version_family_id", table_name="document_tombstones")
    op.drop_index("ix_document_tombstones_external_id", table_name="document_tombstones")
    op.drop_index("ix_document_tombstones_source_id", table_name="document_tombstones")
    op.drop_table("document_tombstones")

    op.drop_index("ix_sync_runs_source_id_started_at", table_name="sync_runs")
    op.drop_index("ix_sync_runs_status", table_name="sync_runs")
    op.drop_index("ix_sync_runs_source_id", table_name="sync_runs")
    op.drop_table("sync_runs")
