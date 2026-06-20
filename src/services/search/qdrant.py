from __future__ import annotations

import uuid as _uuid
from typing import TYPE_CHECKING, Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    BinaryQuantization,
    BinaryQuantizationConfig,
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PointStruct,
    QuantizationConfig,
    QuantizationSearchParams,
    ScalarQuantization,
    ScalarQuantizationConfig,
    ScalarType,
    SearchParams,
    VectorParams,
)

from services.search.hybrid import SearchResult

if TYPE_CHECKING:
    from shared.config import Settings

COLLECTION_NAME_PREFIX = "tomorrowland_chunks"

_OPTIONAL_PAYLOAD_FIELDS = (
    "source_id",
    "title",
    "source_language",
    "language",
    "text_lane",
    "translated_from",
    "translation_version_id",
    "translation_quality",
    "translation_validation_status",
    "content_en",
    "content_he",
    "chunk_index",
    "page_number",
    "section_heading",
    "layout_block_id",
)


def _group_condition(group_ids: list[str]) -> FieldCondition:
    return FieldCondition(key="group_id", match=MatchAny(any=group_ids))


def _point_to_search_result(
    point: Any,
    score: float | None = None,
) -> SearchResult:
    """Convert a Qdrant point to a SearchResult, extracting metadata."""
    payload = point.payload or {}
    meta: dict[str, Any] = {"chunk_id": payload.get("chunk_id", str(point.id))}
    for key in _OPTIONAL_PAYLOAD_FIELDS:
        if key in payload:
            meta[key] = payload[key]
    return SearchResult(
        document_id=payload.get("document_id", ""),
        score=score if score is not None else float(point.score),
        chunk_text=payload.get("text"),
        metadata=meta,
    )


class QdrantSearchClient:
    """Thin wrapper around the Qdrant client for vector (semantic) search."""

    def __init__(
        self,
        url: str = "http://localhost:6333",
        dimension: int = 384,
        *,
        quantization: str = "",
        search_rescore: bool = True,
        search_oversampling: float = 2.0,
    ) -> None:
        self._client = QdrantClient(url=url)
        self._dimension = dimension
        self._collection_name = f"{COLLECTION_NAME_PREFIX}_{dimension}"
        self._quantization = quantization
        self._search_rescore = search_rescore
        self._search_oversampling = search_oversampling

    @classmethod
    def from_settings(cls, settings: Settings, *, dimension: int) -> QdrantSearchClient:
        """Build a client with vector-store tuning resolved from *settings*."""
        return cls(
            url=settings.qdrant_url,
            dimension=dimension,
            quantization=settings.qdrant_quantization,
            search_rescore=settings.qdrant_search_rescore,
            search_oversampling=settings.qdrant_search_oversampling,
        )

    def _quantization_config(self) -> QuantizationConfig | None:
        """Build the Qdrant quantization config, or None when disabled."""
        if self._quantization == "scalar":
            return ScalarQuantization(
                scalar=ScalarQuantizationConfig(type=ScalarType.INT8, always_ram=True)
            )
        if self._quantization == "binary":
            return BinaryQuantization(binary=BinaryQuantizationConfig(always_ram=True))
        return None

    def _search_params(self) -> SearchParams | None:
        """Per-query rescore/oversampling params, or None when quantization is off."""
        if not self._quantization:
            return None
        return SearchParams(
            quantization=QuantizationSearchParams(
                rescore=self._search_rescore,
                oversampling=self._search_oversampling,
            )
        )

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
            quantization_config=self._quantization_config(),
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
            payload.update({k: chunk[k] for k in _OPTIONAL_PAYLOAD_FIELDS if k in chunk})
            # Qdrant point IDs must be valid UUIDs or unsigned integers.
            # chunk_id is a human-readable string (e.g. "<uuid>-orig-0") that
            # is not itself a valid UUID, so derive a stable UUID5 from it.
            point_id = str(_uuid.uuid5(_uuid.NAMESPACE_DNS, chunk["chunk_id"]))
            points.append(
                PointStruct(
                    id=point_id,
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
        extra_conditions: list[FieldCondition] | None = None,
    ) -> list[SearchResult]:
        """Vector search restricted to *group_ids*.

        When *group_ids* is non-empty the group filter is always applied.
        When *group_ids* is empty, a filter is only omitted if *allow_all*
        is explicitly True (admin bypass). Without *allow_all*, an empty
        *group_ids* returns no results to prevent accidental data exposure.
        When *document_id* is provided, results are further restricted to
        chunks belonging to that specific document.

        *extra_conditions* allows callers to push additional payload filters
        (e.g. source_language) into the Qdrant query to reduce wasted
        vector candidates before the post-retrieval filter runs.

        Returned ``SearchResult.metadata`` contains ``chunk_id``,
        ``source_id``, ``title``, and ``source_language`` when present in
        the Qdrant payload.
        """
        self._ensure_vector_dimension(vector)

        self.create_collection_if_not_exists()

        must_conditions: list[FieldCondition] = []
        if group_ids:
            must_conditions.append(_group_condition(group_ids))
        elif not allow_all:
            # No group IDs and no admin bypass → return nothing safely.
            return []
        if document_id:
            must_conditions.append(
                FieldCondition(key="document_id", match=MatchValue(value=document_id))
            )
        if extra_conditions:
            must_conditions.extend(extra_conditions)
        query_filter = Filter(must=list(must_conditions)) if must_conditions else None

        response = self._client.query_points(
            collection_name=self._collection_name,
            query=vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
            search_params=self._search_params(),
        )

        search_results: list[SearchResult] = [
            _point_to_search_result(point) for point in response.points
        ]

        return search_results

    def search_filtered(
        self,
        vector: list[float],
        query_filter: Filter | None,
        limit: int = 10,
    ) -> list[SearchResult]:
        """Vector search using a pre-built Qdrant Filter.

        The caller is responsible for including all required conditions
        (permission filters, scope filters, etc.) in *query_filter*.
        When *query_filter* is None, all points are candidates.
        """
        self._ensure_vector_dimension(vector)

        self.create_collection_if_not_exists()

        response = self._client.query_points(
            collection_name=self._collection_name,
            query=vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
            search_params=self._search_params(),
        )

        return [_point_to_search_result(point) for point in response.points]

    def list_chunks_by_document(
        self,
        document_id: str,
        group_ids: list[str],
        allow_all: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SearchResult]:
        """List chunks belonging to *document_id* using Qdrant scroll.

        Always applies the same group-id permission filter used by ``search``
        as a defence-in-depth measure: even if the caller has already verified
        document access at the application level, this method refuses to
        return chunks whose payload ``group_id`` does not overlap *group_ids*
        unless *allow_all* is True (admin bypass).

        Results are ordered by ``chunk_index`` ascending. *offset* is applied
        client-side after pagination so callers can safely page through chunks
        without leaking points from other documents.
        """
        if not group_ids and not allow_all:
            return []

        if not self._client.collection_exists(collection_name=self._collection_name):
            return []

        must_conditions: list[Any] = [
            FieldCondition(key="document_id", match=MatchValue(value=document_id)),
        ]
        if group_ids:
            must_conditions.append(_group_condition(group_ids))
        scroll_filter = Filter(must=must_conditions)

        # Pull all matching points from Qdrant via scroll pagination;
        # we sort + paginate client-side so chunks come back in stable
        # chunk_index order regardless of point id.
        points: list[Any] = []
        next_page_id: Any = None
        while True:
            page, next_page_id = self._client.scroll(
                collection_name=self._collection_name,
                scroll_filter=scroll_filter,
                limit=1000,
                offset=next_page_id,
                with_payload=True,
                with_vectors=False,
            )
            points.extend(page)
            if next_page_id is None:
                break

        results: list[SearchResult] = [
            _point_to_search_result(point, score=0.0) for point in points
        ]

        results.sort(
            key=lambda r: (
                int((r.metadata or {}).get("chunk_index") or 0),
                (r.metadata or {}).get("chunk_id") or "",
            )
        )
        return results[offset : offset + limit]

    def count_chunks_by_document(
        self,
        document_id: str,
        group_ids: list[str],
        allow_all: bool = False,
    ) -> int:
        """Return total count of chunks for *document_id* matching group filter.

        Uses Qdrant's ``count`` API for efficient total without fetching points.
        """
        if not group_ids and not allow_all:
            return 0

        if not self._client.collection_exists(collection_name=self._collection_name):
            return 0

        must_conditions: list[Any] = [
            FieldCondition(key="document_id", match=MatchValue(value=document_id)),
        ]
        if group_ids:
            must_conditions.append(_group_condition(group_ids))
        count_filter = Filter(must=must_conditions)

        count_result = self._client.count(
            collection_name=self._collection_name,
            count_filter=count_filter,
        )
        return count_result.count

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
