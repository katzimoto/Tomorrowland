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

    def upsert_chunks(self, chunks: list[dict[str, Any]], delete_existing: bool = False) -> None:
        """Upsert chunk vectors into Qdrant.

        Each chunk dict must contain:
        - chunk_id: str
        - document_id: str
        - group_id: str | list[str]
        - chunk_index: int
        - text: str
        - vector: list[float]

        Optional per-chunk fields stored in the payload for citations/filtering:
        - source_id: str
        - title: str
        - source_language: str

        When *delete_existing* is True, all existing points for the document
        are deleted before the upsert so stale chunks from prior indexing runs
        cannot remain searchable.
        """
        if not chunks:
            return

        self.create_collection_if_not_exists()

        if delete_existing:
            doc_id = chunks[0]["document_id"]
            self.delete_by_doc_id(doc_id)

        points: list[PointStruct] = []
        for chunk in chunks:
            vector: list[float] = chunk["vector"]
            self._ensure_vector_dimension(vector)
            payload: dict[str, Any] = {
                "document_id": chunk["document_id"],
                "chunk_id": chunk["chunk_id"],
                "group_id": chunk["group_id"],
                "chunk_index": chunk["chunk_index"],
                "text": chunk["text"],
            }
            if "source_id" in chunk:
                payload["source_id"] = chunk["source_id"]
            if "title" in chunk:
                payload["title"] = chunk["title"]
            if "source_language" in chunk:
                payload["source_language"] = chunk["source_language"]
            points.append(
                PointStruct(
                    id=chunk["chunk_id"],
                    vector=vector,
                    payload=payload,
                )
            )

        self._client.upsert(collection_name=self._collection_name, points=points)

    def search(
        self,
        vector: list[float],
        group_ids: list[str],
        limit: int = 10,
        document_id: str | None = None,
        allow_all: bool = False,
    ) -> list[SearchResult]:
        """Vector search restricted to *group_ids*.

        When *group_ids* is non-empty the group filter is always applied.
        When *group_ids* is empty, a filter is only omitted if *allow_all*
        is explicitly True (admin bypass). Without *allow_all*, an empty
        *group_ids* returns no results to prevent accidental data exposure.
        When *document_id* is provided, results are further restricted to
        chunks belonging to that specific document.

        Returned ``SearchResult.metadata`` contains ``chunk_id``,
        ``source_id``, ``title``, and ``source_language`` when present in
        the Qdrant payload.
        """
        self._ensure_vector_dimension(vector)

        must_conditions = []
        if group_ids:
            must_conditions.append(FieldCondition(key="group_id", match=MatchAny(any=group_ids)))
        elif not allow_all:
            # No group IDs and no admin bypass → return nothing safely.
            return []
        if document_id:
            must_conditions.append(
                FieldCondition(key="document_id", match=MatchValue(value=document_id))
            )
        query_filter = Filter(must=list(must_conditions)) if must_conditions else None

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
            meta: dict[str, Any] = {"chunk_id": payload.get("chunk_id", str(point.id))}
            for extra_key in ("source_id", "title", "source_language", "chunk_index"):
                if extra_key in payload:
                    meta[extra_key] = payload[extra_key]
            search_results.append(
                SearchResult(
                    document_id=payload.get("document_id", ""),
                    score=float(point.score),
                    chunk_text=payload.get("text"),
                    metadata=meta,
                )
            )

        return search_results

    def delete_by_doc_id(self, document_id: str) -> None:
        """Remove all chunks belonging to *document_id*."""
        if not self._client.collection_exists(collection_name=self._collection_name):
            return
        self._client.delete(
            collection_name=self._collection_name,
            points_selector=Filter(
                must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
            ),
        )

    def close(self) -> None:
        """Close the underlying Qdrant client."""
        self._client.close()
