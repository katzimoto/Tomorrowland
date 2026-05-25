"""merge rabbit job bus and language detected flag heads

Revision ID: w7x8y9z0a1b2
Revises: a1b2c3d4e5f6, v6w7x8y9z0a1
Create Date: 2026-05-25 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "w7x8y9z0a1b2"
down_revision: tuple[str, ...] = ("a1b2c3d4e5f6", "v6w7x8y9z0a1")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
