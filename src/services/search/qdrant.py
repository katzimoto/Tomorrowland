from __future__ import annotations

from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PointStruct,
    VectorParams,
)

from services.search.hybrid import SearchResult

COLLECTION_NAME_PREFIX = "tomorrowland_chunks"


class QdrantSearchClient:
    """Thin wrapper around the Qdrant client for vector (semantic) search."""

    def __init__(
        self,
        url: str = "http://localhost:6333",
        dimension: int = 384,
    ) -> None:
        self._client = QdrantClient(url=url)
        self._dimension = dimension
        self._collection_name = f"{COLLECTION_NAME_PREFIX}_{dimension}"

    @property
    def collection_name(self) -> str:
        return self._collection_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def create_collection_if_not_exists(self) -> None:
        """Create the chunk collection if it does not exist."""
        if self._client.collection_exists(collection_name=self._collection_name):
            return

        self._client.create_collection(
            collection_name=self._collection_name,
            vectors_config=VectorParams(size=self._dimension, distance=Distance.COSINE),
        )

    def _ensure_vector_dimension(self, vector: list[float]) -> None:
        """Raise if *vector* dimension does not match the collection dimension."""
        if len(vector) != self._dimension:
            raise ValueError(
                f"Vector dimension mismatch: expected {self._dimension}, "
                f"got {len(vector)}. "
                f"Ensure the encoder and Qdrant collection use the same dimension."
            )

    def upsert_chunks(self, chunks: list[dict[str, Any]]) -> None:
        """Upsert chunk vectors into Qdrant.

        Each chunk dict must contain:
        - chunk_id: str
        - doc_id: str
        - group_id: str | list[str]
        - chunk_index: int
        - text: str
        - vector: list[float]
        """
        if not chunks:
            return

        points: list[PointStruct] = []
        for chunk in chunks:
            vector: list[float] = chunk["vector"]
            self._ensure_vector_dimension(vector)
            points.append(
                PointStruct(
                    id=chunk["chunk_id"],
                    vector=vector,
                    payload={
                        "doc_id": chunk["doc_id"],
                        "group_id": chunk["group_id"],
                        "chunk_index": chunk["chunk_index"],
                        "text": chunk["text"],
                    },
                )
            )

        self._client.upsert(collection_name=self._collection_name, points=points)

    def search(
        self,
        vector: list[float],
        group_ids: list[str],
        limit: int = 50,
    ) -> list[SearchResult]:
        """Vector search restricted to *group_ids*.

        When *group_ids* is empty (admins-group user), no permission
        filter is applied, giving the caller global document access.
        """
        self._ensure_vector_dimension(vector)

        query_filter = None
        if group_ids:
            query_filter = Filter(
                must=[FieldCondition(key="group_id", match=MatchAny(any=group_ids))]
            )

        response = self._client.query_points(
            collection_name=self._collection_name,
            query=vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )

        search_results: list[SearchResult] = []
        for point in response.points:
            payload = point.payload or {}
            search_results.append(
                SearchResult(
                    doc_id=payload.get("doc_id", ""),
                    score=float(point.score),
                    chunk_text=payload.get("text"),
                )
            )

        return search_results

    def delete_by_doc_id(self, doc_id: str) -> None:
        """Remove all chunks belonging to *doc_id*."""
        self._client.delete(
            collection_name=self._collection_name,
            points_selector=Filter(
                must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
            ),
        )

    def close(self) -> None:
        """Close the underlying Qdrant client."""
        self._client.close()
