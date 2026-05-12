"""allow same source file versions by sha

Revision ID: b1c2d3e4f5a6
Revises: 9a65b7c3d4e5
Create Date: 2026-05-13 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "9a65b7c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch_op:
        batch_op.add_column(
            sa.Column("content_sha256", sa.Text(), nullable=False, server_default="")
        )

    op.execute(
        """
        UPDATE documents
        SET content_sha256 = COALESCE((
            SELECT ingested_files.sha256
            FROM ingested_files
            WHERE ingested_files.doc_id = documents.id
            LIMIT 1
        ), '')
        WHERE content_sha256 = ''
        """
    )

    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_constraint("uq_documents_source_external", type_="unique")
        batch_op.create_unique_constraint(
            "uq_documents_source_external_sha",
            ["source_id", "external_id", "content_sha256"],
        )

    op.create_table(
        "ingested_files_v2",
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False, server_default=""),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("doc_id", sa.Uuid(), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["doc_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["ingestion_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint(
            "source_id", "external_id", "sha256", name="pk_ingested_files_source_external_sha"
        ),
    )
    op.execute(
        """
        INSERT INTO ingested_files_v2 (source_id, external_id, sha256, doc_id, ingested_at)
        SELECT i.source_id, COALESCE(d.external_id, ''), i.sha256, i.doc_id, i.ingested_at
        FROM ingested_files AS i
        LEFT JOIN documents AS d ON d.id = i.doc_id
        """
    )
    op.drop_table("ingested_files")
    op.rename_table("ingested_files_v2", "ingested_files")


def downgrade() -> None:
    # Collapse version rows before restoring the old one-document-per-source-item
    # uniqueness constraint.
    op.execute(
        """
        DELETE FROM documents
        WHERE id IN (
            SELECT id
            FROM (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY source_id, external_id
                        ORDER BY created_at ASC, id ASC
                    ) AS version_rank
                FROM documents
            ) AS ranked_documents
            WHERE version_rank > 1
        )
        """
    )

    op.create_table(
        "ingested_files_v1",
        sa.Column("sha256", sa.Text(), primary_key=True),
        sa.Column("doc_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["doc_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["ingestion_sources.id"], ondelete="CASCADE"),
    )
    op.execute(
        """
        INSERT INTO ingested_files_v1 (sha256, doc_id, source_id, ingested_at)
        SELECT sha256, MIN(doc_id), MIN(source_id), MIN(ingested_at)
        FROM ingested_files
        GROUP BY sha256
        """
    )
    op.drop_table("ingested_files")
    op.rename_table("ingested_files_v1", "ingested_files")

    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_constraint("uq_documents_source_external_sha", type_="unique")
        batch_op.create_unique_constraint(
            "uq_documents_source_external",
            ["source_id", "external_id"],
        )
        batch_op.drop_column("content_sha256")
