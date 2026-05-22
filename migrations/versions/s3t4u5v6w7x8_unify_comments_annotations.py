"""unify comments as annotations + add annotation_replies table

Revision ID: s3t4u5v6w7x8
Revises: r1s2t3u4v5w6
Create Date: 2026-05-22

Moves surviving document_comments into the annotations table as
document-level annotations (position=NULL), creates annotation_replies
for threaded replies, and preserves soft-deleted comments as [deleted]
annotations.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "s3t4u5v6w7x8"
down_revision: str | None = "r1s2t3u4v5w6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "annotation_replies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "annotation_id",
            sa.Uuid(),
            sa.ForeignKey("annotations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_annotation_replies_annotation_created",
        "annotation_replies",
        ["annotation_id", "created_at"],
    )

    # Migrate non-deleted comments into annotations
    op.execute(
        sa.text("""
        INSERT INTO annotations
            (id, document_id, user_id, text, note, position,
             is_private, created_at, updated_at)
        SELECT
            c.id,
            c.document_id,
            c.author_id,
            CASE WHEN c.deleted_at IS NOT NULL THEN '[deleted]' ELSE c.body END,
            CASE WHEN c.deleted_at IS NOT NULL THEN '[migrated from deleted comment]'
                 ELSE '[migrated from comment]' END,
            NULL,
            FALSE,
            c.created_at,
            COALESCE(c.edited_at, c.updated_at)
        FROM document_comments c
        ORDER BY c.created_at ASC
    """)
    )

    # Migrate soft-deleted comments too (as [deleted] placeholder)
    # The INSERT above already handles them via the CASE.


def downgrade() -> None:
    # Remove migrated comments from annotations
    op.execute(
        sa.text("""
        DELETE FROM annotations
        WHERE note = '[migrated from comment]'
           OR note = '[migrated from deleted comment]'
    """)
    )
    op.drop_index("ix_annotation_replies_annotation_created", table_name="annotation_replies")
    op.drop_table("annotation_replies")
