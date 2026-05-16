"""add document version families

Revision ID: e1f2a3b4c5d6
Revises: f1a2b3c4d5e6
Create Date: 2026-05-16 00:00:00.000000
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_version_families",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("current_document_id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["ingestion_sources.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_version_families"),
        sa.UniqueConstraint(
            "source_id",
            "external_id",
            name="uq_document_version_families_source_external",
        ),
    )

    with op.batch_alter_table("documents") as batch_op:
        batch_op.add_column(sa.Column("version_family_id", sa.Uuid(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "version_number",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )
        batch_op.add_column(
            sa.Column(
                "is_latest",
                sa.Boolean(),
                nullable=False,
                server_default="1",
            )
        )

    conn = op.get_bind()
    groups = conn.execute(
        sa.text("SELECT DISTINCT source_id, external_id FROM documents")
    ).fetchall()

    for group_row in groups:
        source_id_val = str(group_row[0])
        external_id_val = str(group_row[1])
        family_id = str(uuid.uuid4())

        docs = conn.execute(
            sa.text(
                """
                SELECT id FROM documents
                WHERE source_id = :source_id AND external_id = :external_id
                ORDER BY created_at ASC, id ASC
                """
            ),
            {"source_id": source_id_val, "external_id": external_id_val},
        ).fetchall()

        if not docs:
            continue

        latest_doc_id = str(docs[-1][0])

        conn.execute(
            sa.text(
                """
                INSERT INTO document_version_families
                    (id, source_id, external_id, current_document_id)
                VALUES
                    (:id, :source_id, :external_id, :current_document_id)
                """
            ),
            {
                "id": family_id,
                "source_id": source_id_val,
                "external_id": external_id_val,
                "current_document_id": latest_doc_id,
            },
        )

        for i, (doc_id_val,) in enumerate(docs, start=1):
            conn.execute(
                sa.text(
                    """
                    UPDATE documents
                    SET version_family_id = :family_id,
                        version_number = :version_number,
                        is_latest = :is_latest
                    WHERE id = :doc_id
                    """
                ),
                {
                    "family_id": family_id,
                    "version_number": i,
                    "is_latest": 1 if str(doc_id_val) == latest_doc_id else 0,
                    "doc_id": str(doc_id_val),
                },
            )


def downgrade() -> None:
    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_column("is_latest")
        batch_op.drop_column("version_number")
        batch_op.drop_column("version_family_id")

    op.drop_table("document_version_families")
