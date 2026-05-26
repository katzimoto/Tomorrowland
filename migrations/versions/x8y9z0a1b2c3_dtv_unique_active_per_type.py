"""add partial unique index on document_translation_versions (document_id, request_type)
for active rows

Prevents duplicate pending/running translation jobs for the same
document + request_type pair under concurrent preview requests
(TOCTOU race in _maybe_auto_enrich).

The index only covers rows where status IN ('pending', 'running'), so
completed, failed, and available versions can coexist freely.

Revision ID: x8y9z0a1b2c3
Revises: w7x8y9z0a1b2
Create Date: 2026-05-26 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "x8y9z0a1b2c3"
down_revision: str | Sequence[str] | None = "w7x8y9z0a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE UNIQUE INDEX idx_dtv_one_active_per_type
        ON document_translation_versions (document_id, request_type)
        WHERE status IN ('pending', 'running')
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_dtv_one_active_per_type")
