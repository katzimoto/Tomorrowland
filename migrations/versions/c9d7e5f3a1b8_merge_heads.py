"""merge heads

Revision ID: c9d7e5f3a1b8
Revises: b8c1d2e3f7a9, b1c2d3e4f5a6
Create Date: 2026-05-13 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "c9d7e5f3a1b8"
down_revision: tuple[str, ...] = ("b8c1d2e3f7a9", "b1c2d3e4f5a6")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
