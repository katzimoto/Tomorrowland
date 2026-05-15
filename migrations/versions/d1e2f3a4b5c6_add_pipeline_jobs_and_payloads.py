"""add pipeline jobs and document payloads tables

Revision ID: d1e2f3a4b5c6
Revises: b1c2d3e4f5a6
Create Date: 2026-05-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d1e2f3a4b5c6"
down_revision: str | None = "c9d7e5f3a1b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pipeline_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "doc_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            sa.Uuid(),
            sa.ForeignKey("ingestion_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("job_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("stage", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "run_after",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("locked_by", sa.Text(), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_pipeline_jobs_doc_id", "pipeline_jobs", ["doc_id"])
    op.create_index("ix_pipeline_jobs_source_id", "pipeline_jobs", ["source_id"])
    op.create_index(
        "ix_pipeline_jobs_ready",
        "pipeline_jobs",
        ["status", "run_after", "priority", "created_at"],
    )
    op.execute(
        """
        CREATE UNIQUE INDEX ix_pipeline_jobs_active_unique
        ON pipeline_jobs (doc_id, job_type)
        WHERE status IN ('pending', 'running', 'retry')
        """
    )

    op.create_table(
        "document_payloads",
        sa.Column(
            "doc_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("content_path", sa.Text(), nullable=True),
        sa.Column("content_sha256", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )


def downgrade() -> None:
    op.drop_table("document_payloads")
    op.execute("DROP INDEX IF EXISTS ix_pipeline_jobs_active_unique")
    op.drop_index("ix_pipeline_jobs_ready", table_name="pipeline_jobs")
    op.drop_index("ix_pipeline_jobs_source_id", table_name="pipeline_jobs")
    op.drop_index("ix_pipeline_jobs_doc_id", table_name="pipeline_jobs")
    op.drop_table("pipeline_jobs")
