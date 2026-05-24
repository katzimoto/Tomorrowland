from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SearchResult:
    document_id: str
    score: float
    title: str | None = None
    chunk_text: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class SearchResults:
    results: list[SearchResult]
    facets: dict[str, dict[str, int]]
