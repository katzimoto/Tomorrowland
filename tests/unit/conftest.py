"""Unit-test conftest.

Provides a ``worker_id`` fixture so that ``migrated_engine`` (which is
session-scoped and uses ``worker_id`` for xdist-safe Postgres template naming)
works when pytest-xdist is not installed.  When xdist *is* installed and
running, it supplies its own ``worker_id`` fixture and this one is ignored.
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session")
def worker_id() -> str:
    return "main"
