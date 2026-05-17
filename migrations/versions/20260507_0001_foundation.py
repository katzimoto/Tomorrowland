"""create foundation schema

Revision ID: 20260507_0001
Revises:
Create Date: 2026-05-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from shared.feature_flags import SYSTEM_CONFIG_DEFAULTS

revision: str = "20260507_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_pk() -> sa.Column[sa.Uuid]:
    return sa.Column("id", sa.Uuid(), primary_key=True)


def upgrade() -> None:
    op.create_table(
        "users",
        _uuid_pk(),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("auth_source", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("auth_source IN ('local', 'ldap')", name="ck_users_auth_source"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "groups",
        _uuid_pk(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.UniqueConstraint("name", name="uq_groups_name"),
    )

    op.create_table(
        "user_groups",
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "group_id",
            sa.Uuid(),
            sa.ForeignKey("groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id", "group_id", name="pk_user_groups"),
    )

    op.create_table(
        "ingestion_sources",
        _uuid_pk(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=True),
        sa.Column("source_language", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("config", sa.JSON(), nullable=True),
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
            "type IN ('folder', 'nifi', 'confluence', 'jira')",
            name="ck_ingestion_sources_type",
        ),
    )

    op.create_table(
        "source_permissions",
        sa.Column(
            "source_id",
            sa.Uuid(),
            sa.ForeignKey("ingestion_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "group_id",
            sa.Uuid(),
            sa.ForeignKey("groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("source_id", "group_id", name="pk_source_permissions"),
    )

    op.create_table(
        "documents",
        _uuid_pk(),
        sa.Column(
            "source_id",
            sa.Uuid(),
            sa.ForeignKey("ingestion_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=True),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("source_language", sa.Text(), nullable=True),
        sa.Column("target_language", sa.Text(), nullable=False, server_default="en"),
        sa.Column("translation_quality", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
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
            "source IN ('folder', 'nifi', 'confluence', 'jira')",
            name="ck_documents_source",
        ),
        sa.CheckConstraint(
            "translation_quality IN ('fast', 'high') OR translation_quality IS NULL",
            name="ck_documents_translation_quality",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'indexed', 'deleted', 'failed')",
            name="ck_documents_status",
        ),
        sa.UniqueConstraint("source_id", "external_id", name="uq_documents_source_external"),
    )
    op.create_index("ix_documents_source_id", "documents", ["source_id"])
    op.create_index("ix_documents_status", "documents", ["status"])

    op.create_table(
        "ingested_files",
        sa.Column("sha256", sa.Text(), primary_key=True),
        sa.Column(
            "document_id",
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
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "system_config",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
    )

    system_config = sa.table(
        "system_config",
        sa.column("key", sa.Text()),
        sa.column("value", sa.JSON()),
    )
    op.bulk_insert(
        system_config,
        [{"key": key, "value": value} for key, value in SYSTEM_CONFIG_DEFAULTS.items()],
    )


def downgrade() -> None:
    op.drop_table("system_config")
    op.drop_table("ingested_files")
    op.drop_index("ix_documents_status", table_name="documents")
    op.drop_index("ix_documents_source_id", table_name="documents")
    op.drop_table("documents")
    op.drop_table("source_permissions")
    op.drop_table("ingestion_sources")
    op.drop_table("user_groups")
    op.drop_table("groups")
    op.drop_table("users")
