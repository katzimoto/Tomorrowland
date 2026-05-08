"""add document_translation_versions table

Revision ID: 8e3f2a9c1d56
Revises: dc150d49033a
Create Date: 2026-05-08 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8e3f2a9c1d56"
down_revision: str | None = "dc150d49033a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_translation_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "doc_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("source_language", sa.Text(), nullable=True),
        sa.Column("target_language", sa.Text(), nullable=False, server_default="en"),
        sa.Column(
            "quality",
            sa.Text(),
            sa.CheckConstraint(
                "quality IN ('fast', 'high')", name="ck_translation_versions_quality"
            ),
            nullable=False,
        ),
        sa.Column(
            "request_type",
            sa.Text(),
            sa.CheckConstraint(
                "request_type IN ('ingestion', 'manual', 'auto_enrich')",
                name="ck_translation_versions_request_type",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Text(),
            sa.CheckConstraint(
                "status IN ('available', 'pending', 'running', 'failed', 'canceled')",
                name="ck_translation_versions_status",
            ),
            nullable=False,
        ),
        sa.Column("provider", sa.Text(), nullable=True),
        sa.Column(
            "requested_by_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("request_note", sa.Text(), nullable=True),
        sa.Column("source_content_hash", sa.Text(), nullable=True),
        sa.Column("translated_text", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.UniqueConstraint("doc_id", "version_number", name="uq_translation_versions_doc_number"),
    )
    op.create_index(
        "ix_translation_versions_doc_id",
        "document_translation_versions",
        ["doc_id"],
    )
    op.create_index(
        "ix_translation_versions_status",
        "document_translation_versions",
        ["status"],
    )
    op.create_index(
        "ix_translation_versions_requested_by",
        "document_translation_versions",
        ["requested_by_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_translation_versions_requested_by", table_name="document_translation_versions"
    )
    op.drop_index("ix_translation_versions_status", table_name="document_translation_versions")
    op.drop_index("ix_translation_versions_doc_id", table_name="document_translation_versions")
    op.drop_table("document_translation_versions")
