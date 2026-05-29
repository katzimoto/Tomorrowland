"""add extraction_metadata json column to document_payloads

Preserves best-effort location data (page_number, section_heading) from
PDF/PPTX/DOCX extractors so downstream vector workers can attach them to
Qdrant points and ultimately to RAG citations.

Revision ID: y9z0a1b2c3d4
Revises: x8y9z0a1b2c3
Create Date: 2026-05-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "y9z0a1b2c3d4"
down_revision: str | Sequence[str] | None = "x8y9z0a1b2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "document_payloads",
        sa.Column("extraction_metadata", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document_payloads", "extraction_metadata")
