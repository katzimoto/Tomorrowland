"""Unit tests for _map_sort in the search router.

Proves that snake_case frontend sort_by values are correctly translated to
camelCase Meilisearch sort strings, covering all mapped fields and directions.
"""

from __future__ import annotations

import pytest

from services.api.routers.search import _map_sort


@pytest.mark.parametrize(
    "sort_by, sort_dir, expected",
    [
        # --- relevance (explicit and fallback) ---
        ("relevance", "desc", "relevance"),
        ("relevance", "asc", "relevance"),
        # --- updated_at ---
        ("updated_at", "desc", "updatedAt:desc"),
        ("updated_at", "asc", "updatedAt:asc"),
        # --- created_at ---
        ("created_at", "desc", "createdAt:desc"),
        ("created_at", "asc", "createdAt:asc"),
        # --- title falls back to relevance (not sortable in Meilisearch) ---
        ("title", "desc", "relevance"),
        ("title", "asc", "relevance"),
        # --- unknown field falls back to relevance ---
        ("unknown_field", "desc", "relevance"),
        ("unknown_field", "asc", "relevance"),
    ],
)
def test_map_sort(sort_by: str, sort_dir: str, expected: str) -> None:
    assert _map_sort(sort_by, sort_dir) == expected
