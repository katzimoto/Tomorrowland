from __future__ import annotations

import time
from typing import Any

from services.auth.models import TokenPayload, UserIdentity
from services.search.meili_acl import (
    build_permission_filter,
    compose_filters,
    needs_acl_short_circuit,
)
from services.search.meili_settings import (
    INDEX_NAME,
    SHADOW_INDEX_NAME,
    apply_index_settings,
)
from services.search.meili_types import (
    ChunkPosition,
    DocumentSearchFilters,
    DocumentSearchQuery,
    DocumentSearchResult,
    DocumentSearchResultMetadata,
    SearchChunkRecord,
)
from services.search.models import SearchResult
from shared.metrics import MetricsRegistry

# Requires: pip install meilisearch
# Client type is Any to avoid a hard import error before the package is installed.
_MeilisearchClient = Any

_SORT_MAP: dict[str, list[str]] = {
    "relevance": [],
    "updatedAt:desc": ["metadata.updated_at:desc"],
    "createdAt:desc": ["metadata.created_at:desc"],
    "importedAt:desc": ["metadata.imported_at:desc"],
}

# Maximum chunks fetched when scanning a document's existing index records.
_MAX_CHUNK_SCAN = 10_000


def _build_user_filter(filters: DocumentSearchFilters) -> str:
    """Translate DocumentSearchFilters into a Meilisearch filter expression."""
    parts: list[str] = []

    def _in(field: str, values: list[str]) -> None:
        if values:
            quoted = ", ".join(f'"{v}"' for v in values)
            parts.append(f"{field} IN [{quoted}]")

    def _gte(field: str, value: str | None) -> None:
        if value:
            parts.append(f'{field} >= "{value}"')

    _in("metadata.source", filters.source)
    _in("metadata.document_type", filters.document_type)
    _in("metadata.mime_type", filters.mime_type)
    _in("metadata.file_extension", filters.file_extension)
    _in("metadata.language", filters.language)
    _in("metadata.author", filters.author)
    _in("metadata.owner", filters.owner)
    _in("metadata.tags", filters.tags)
    _in("metadata.labels", filters.labels)
    _in("metadata.topics", filters.topics)
    _in("metadata.project", filters.project)
    _in("metadata.workspace", filters.workspace)
    _in("metadata.collection", filters.collection)
    _gte("metadata.created_at", filters.created_after)
    _gte("metadata.updated_at", filters.updated_after)
    _gte("metadata.imported_at", filters.imported_after)

    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return " AND ".join(f"({p})" for p in parts)


def _map_result(hit: dict[str, Any]) -> DocumentSearchResult:
    """Map a single Meilisearch hit to a DocumentSearchResult."""
    pos_raw = hit.get("position") or {}
    pos = ChunkPosition(
        chunk_index=pos_raw.get("chunk_index", hit.get("chunk_index", 0)),
        page_number=pos_raw.get("page_number"),
    )

    meta_raw = hit.get("metadata") or {}
    meta = DocumentSearchResultMetadata(
        document_type=meta_raw.get("document_type"),
        file_name=meta_raw.get("file_name"),
        source=meta_raw.get("source"),
        language=meta_raw.get("language"),
        tags=meta_raw.get("tags") or [],
        updated_at=meta_raw.get("updated_at"),
        project=meta_raw.get("project"),
        workspace=meta_raw.get("workspace"),
        collection=meta_raw.get("collection"),
    )

    # Prefer the language-matched snippet field; fall back to original content.
    snippet = hit.get("_formatted", {}).get("content") or hit.get("content") or ""

    return DocumentSearchResult(
        document_id=hit["document_id"],
        chunk_id=hit["id"],
        title=hit.get("title") or "",
        heading=hit.get("heading"),
        section_path=hit.get("section_path") or [],
        snippet=snippet,
        metadata=meta,
        position=pos,
        score=hit.get("_rankingScore"),
    )


class MeilisearchSearchProvider:
    """Meilisearch client wrapper implementing the document search interface.

    The caller owns retry scheduling, DLQ routing, and feature-flag gating.
    This class exposes clean primitives only.

    Args:
        client: A ``meilisearch.Client`` instance.
    """

    def __init__(
        self,
        client: _MeilisearchClient,
        metrics: MetricsRegistry | None = None,
        is_shadow: bool = False,
        hybrid: bool = False,
        embedding_url: str = "http://ollama-embed:11434/api/embed",
        embedding_model: str = "nomic-embed-text",
        embedding_dimension: int = 768,
        embedder_name: str = "default",
        semantic_ratio: float = 0.5,
    ) -> None:
        self._client = client
        self._metrics = metrics
        self._hybrid = hybrid
        self._embedder_name = embedder_name
        self._semantic_ratio = semantic_ratio
        self.apply_settings(
            shadow=is_shadow,
            hybrid=hybrid,
            embedding_url=embedding_url,
            embedding_model=embedding_model,
            embedding_dimension=embedding_dimension,
            embedder_name=embedder_name,
        )

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    def apply_settings(
        self,
        *,
        shadow: bool = False,
        hybrid: bool = False,
        embedding_url: str = "http://ollama-embed:11434/api/embed",
        embedding_model: str = "nomic-embed-text",
        embedding_dimension: int = 768,
        embedder_name: str = "default",
    ) -> None:
        """Apply index settings idempotently. Safe to call on every startup."""
        apply_index_settings(
            self._client,
            shadow=shadow,
            hybrid=hybrid,
            embedding_url=embedding_url,
            embedding_model=embedding_model,
            embedding_dimension=embedding_dimension,
            embedder_name=embedder_name,
        )

    def swap_indexes(self) -> str:
        """Atomically swap the live and shadow indexes.

        After the swap, live queries go to the former shadow. The old live
        index becomes the new shadow and can be dropped once stable.

        Returns the Meilisearch task UID as a string.
        """
        task = self._client.swap_indexes([{"indexes": [INDEX_NAME, SHADOW_INDEX_NAME]}])
        return str(task.task_uid)

    def drop_shadow_index(self) -> str:
        """Delete the shadow index. Call after a successful swap and validation."""
        task = self._client.index(SHADOW_INDEX_NAME).delete()
        return str(task.task_uid)

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def index(self, document: SearchChunkRecord, *, shadow: bool = False) -> str:
        """Add or replace a single chunk record. Returns the task UID."""
        name = SHADOW_INDEX_NAME if shadow else INDEX_NAME
        task = self._client.index(name).add_documents([document.model_dump()], primary_key="id")
        return str(task.task_uid)

    def index_batch(self, documents: list[SearchChunkRecord], *, shadow: bool = False) -> str:
        """Add or replace a batch of chunk records. Returns the task UID.

        Prefer this over repeated index() calls — Meilisearch processes a
        batch as a single task, reducing overhead and queue depth.
        """
        name = SHADOW_INDEX_NAME if shadow else INDEX_NAME
        task = self._client.index(name).add_documents(
            [d.model_dump() for d in documents], primary_key="id"
        )
        return str(task.task_uid)

    def patch_translations(
        self,
        chunk_id: str,
        translations: dict[str, str | None],
    ) -> str:
        """Partially update translation fields on an existing chunk record.

        Only the supplied keys are written. ``content``, ``contentChecksum``,
        ``allowed_group_ids``, and ``indexedAt`` are not touched.

        Args:
            chunk_id: The ``id`` primary key of the chunk record.
            translations: Mapping of flat translation field names to values,
                e.g. ``{"content_en": "...", "title_en": "..."}``.

        Returns the task UID.
        """
        payload = {
            "id": chunk_id,
            **{k: v for k, v in translations.items() if v is not None},
        }
        task = self._client.index(INDEX_NAME).update_documents([payload])
        return str(task.task_uid)

    def remove(self, chunk_id: str) -> str:
        """Delete a single chunk record by primary key. Returns the task UID."""
        task = self._client.index(INDEX_NAME).delete_document(chunk_id)
        return str(task.task_uid)

    def remove_by_document_id(self, document_id: str) -> str:
        """Delete all chunk records for a document. Returns the task UID.

        Uses a filter-based delete — safe regardless of chunk count.
        Mirrors QdrantSearchClient.delete_by_doc_id.
        """
        task = self._client.index(INDEX_NAME).delete_documents_by_filter(
            f'document_id = "{document_id}"'
        )
        return str(task.task_uid)

    # ------------------------------------------------------------------
    # Stale chunk detection
    # ------------------------------------------------------------------

    def existing_chunk_checksums(self, document_id: str, *, shadow: bool = False) -> dict[str, str]:
        """Return {chunk_id: contentChecksum} for all indexed chunks of a document.

        Used to skip unchanged chunks during reindex of a single document.
        Fetches up to _MAX_CHUNK_SCAN records — documents with more chunks
        than this are fully reindexed without checksum comparison.

        When *shadow* is True the shadow index is queried instead of the live
        index. This is used during backfill to compare against previously
        backfilled data.
        """
        name = SHADOW_INDEX_NAME if shadow else INDEX_NAME
        result = self._client.index(name).search(
            "",
            {
                "filter": f'document_id = "{document_id}"',
                "limit": _MAX_CHUNK_SCAN,
                "attributesToRetrieve": ["id", "content_checksum"],
            },
        )
        return {hit["id"]: hit.get("content_checksum", "") for hit in result.get("hits", [])}

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def _metric(self, result: str) -> None:
        """Increment permission-filter metric when metrics are configured."""
        if self._metrics is not None:
            self._metrics.search_permission_filter_applied_total.labels(
                result=result,
            ).inc()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: DocumentSearchQuery,
        user: TokenPayload | UserIdentity,
    ) -> list[SearchResult]:
        """Execute a search with the ACL filter applied server-side.

        The permission filter is constructed from the authenticated user's
        token and composed with any user-supplied filters. The caller cannot
        omit the ACL filter.

        Returns an empty response immediately if the user cannot access any
        document (non-admin with no group memberships).
        """
        if needs_acl_short_circuit(user):
            self._metric("bypassed_admin")
            return []

        acl_filter = build_permission_filter(user)
        user_filter: str = _build_user_filter(query.filters)
        combined_filter = compose_filters(acl_filter, user_filter)

        if not user.groups:
            self._metric("zero_groups")
        else:
            self._metric("applied")

        sort = _SORT_MAP.get(query.sort, [])

        params: dict[str, Any] = {
            "limit": query.limit,
            "offset": query.offset,
            "attributesToHighlight": ["content", "content_en", "content_he"],
            "highlightPreTag": "<mark>",
            "highlightPostTag": "</mark>",
            "showRankingScore": True,
            "facets": [
                "metadata.document_type",
                "metadata.source",
                "metadata.language",
                "metadata.tags",
                "metadata.project",
                "metadata.workspace",
                "metadata.collection",
            ],
        }
        if combined_filter:
            params["filter"] = combined_filter
        if sort:
            params["sort"] = sort
        if self._hybrid:
            params["hybrid"] = {
                "embedder": self._embedder_name,
                "semanticRatio": self._semantic_ratio,
            }

        raw = self._client.index(INDEX_NAME).search(query.q, params)

        items = [_map_result(h) for h in raw.get("hits", [])]

        results = [
            SearchResult(
                document_id=i.document_id,
                score=i.score or 0.0,
                title=i.title,
                chunk_text=i.snippet,
                metadata=i.metadata.model_dump(),
            )
            for i in items
        ]
        return results

    def search_rag(
        self,
        text: str,
        group_ids: list[str],
        allow_all: bool = False,
        limit: int = 20,
    ) -> list[SearchResult]:
        """Search Meilisearch for RAG — no user object required.

        Uses ``build_permission_filter_for_ids`` directly so callers can pass
        pre-resolved effective group IDs. Returns ``SearchResult`` objects
        compatible with ``merge_results()``.
        """
        from services.search.meili_acl import build_permission_filter_for_ids

        filter_expr = build_permission_filter_for_ids(list(group_ids), is_admin=allow_all)

        params: dict[str, Any] = {
            "limit": limit,
            "showRankingScore": True,
        }
        if filter_expr:
            params["filter"] = filter_expr
        if self._hybrid:
            params["hybrid"] = {
                "embedder": self._embedder_name,
                "semanticRatio": self._semantic_ratio,
            }

        raw = self._client.index(INDEX_NAME).search(text, params)

        return [
            SearchResult(
                document_id=hit["document_id"],
                score=hit.get("_rankingScore") or 0.0,
                title=hit.get("title") or "",
                chunk_text=hit.get("content") or "",
                metadata={
                    "chunk_id": hit.get("id"),
                    "chunk_index": hit.get("chunk_index"),
                    "page_number": (hit.get("position") or {}).get("page_number"),
                    "section_heading": hit.get("heading"),
                    "source_language": (hit.get("metadata") or {}).get("language"),
                },
            )
            for hit in raw.get("hits", [])
        ]

    def search_rag_metadata(
        self,
        text: str,
        group_ids: list[str],
        allow_all: bool = False,
        limit: int = 20,
    ) -> list[SearchResult]:
        """Search metadata fields (tags, entities, summary, document_type).

        Uses ``attributes_to_search_on`` to restrict the query to metadata
        fields. Requires Meilisearch 1.8+. Fused into the main result set
        with a lower weight than the full-text BM25 search.
        """
        from services.search.meili_acl import build_permission_filter_for_ids

        filter_expr = build_permission_filter_for_ids(list(group_ids), is_admin=allow_all)

        params: dict[str, Any] = {
            "limit": limit,
            "showRankingScore": True,
            "attributesToSearchOn": [
                "summary",
                "summary_en",
                "summary_he",
                "metadata_text",
                "metadata.tags",
                "metadata.labels",
                "metadata.topics",
                "metadata.project",
                "metadata.collection",
                "metadata.file_name",
                "metadata.author",
                "metadata.owner",
            ],
        }
        if filter_expr:
            params["filter"] = filter_expr

        raw = self._client.index(INDEX_NAME).search(text, params)

        return [
            SearchResult(
                document_id=hit["document_id"],
                score=hit.get("_rankingScore") or 0.0,
                title=hit.get("title") or "",
                chunk_text=hit.get("content") or "",
                metadata={
                    "chunk_id": hit.get("id"),
                    "chunk_index": hit.get("chunk_index"),
                    "page_number": (hit.get("position") or {}).get("page_number"),
                    "section_heading": hit.get("heading"),
                    "source_language": (hit.get("metadata") or {}).get("language"),
                },
            )
            for hit in raw.get("hits", [])
        ]

    def search_rag_translated(
        self,
        text: str,
        group_ids: list[str],
        allow_all: bool = False,
        limit: int = 20,
    ) -> list[SearchResult]:
        """Search translated text fields (content_en, content_he).

        Uses ``attributes_to_search_on`` to restrict the query to translated
        content fields. Fused into the main result set with a lower weight.
        """
        from services.search.meili_acl import build_permission_filter_for_ids

        filter_expr = build_permission_filter_for_ids(list(group_ids), is_admin=allow_all)

        params: dict[str, Any] = {
            "limit": limit,
            "showRankingScore": True,
            "attributesToSearchOn": [
                "content_en",
                "content_he",
                "summary_en",
                "summary_he",
            ],
        }
        if filter_expr:
            params["filter"] = filter_expr

        raw = self._client.index(INDEX_NAME).search(text, params)

        return [
            SearchResult(
                document_id=hit["document_id"],
                score=hit.get("_rankingScore") or 0.0,
                title=hit.get("title") or "",
                chunk_text=hit.get("content") or "",
                metadata={
                    "chunk_id": hit.get("id"),
                    "chunk_index": hit.get("chunk_index"),
                    "page_number": (hit.get("position") or {}).get("page_number"),
                    "section_heading": hit.get("heading"),
                    "source_language": (hit.get("metadata") or {}).get("language"),
                },
            )
            for hit in raw.get("hits", [])
        ]

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def task_status(self, task_uid: str) -> dict[str, Any]:
        """Return the status dict for a Meilisearch task.

        Keys always present: ``status`` (str), ``uid`` (int).
        Key present on failure: ``error`` (dict).
        """
        task = self._client.get_task(int(task_uid))
        return {
            "uid": task.uid,
            "status": task.status,
            "error": getattr(task, "error", None),
        }

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_settings(
        cls,
        client: _MeilisearchClient,
        settings: Any,
        *,
        metrics: Any = None,
        is_shadow: bool = False,
    ) -> "MeilisearchSearchProvider":
        """Construct a provider from a ``Settings`` instance.

        Reads ``feature_meilisearch_hybrid``, ``embedding_url``,
        ``embedding_model``, ``embedding_dimension``, ``meili_embedder_name``,
        and ``meili_semantic_ratio`` so every call site stays in sync.
        """
        embedding_url = (
            getattr(settings, "embedding_url", "") or "http://ollama-embed:11434"
        ).rstrip("/") + "/api/embed"
        return cls(
            client=client,
            metrics=metrics,
            is_shadow=is_shadow,
            hybrid=getattr(settings, "feature_meilisearch_hybrid", False),
            embedding_url=embedding_url,
            embedding_model=getattr(settings, "embedding_model", "nomic-embed-text"),
            embedding_dimension=getattr(settings, "embedding_dimension", 768),
            embedder_name=getattr(settings, "meili_embedder_name", "default"),
            semantic_ratio=getattr(settings, "meili_semantic_ratio", 0.5),
        )

    def wait_for_task(
        self,
        task_uid: str,
        *,
        timeout_seconds: float = 30.0,
        poll_interval_seconds: float = 0.5,
    ) -> dict[str, Any]:
        """Poll task_status until the task succeeds, fails, or times out.

        Raises ``TimeoutError`` on timeout; raises ``RuntimeError`` if the
        task fails or is cancelled.
        """
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            status = self.task_status(task_uid)
            if status["status"] == "succeeded":
                return status
            if status["status"] in ("failed", "canceled"):
                raise RuntimeError(
                    f"Meilisearch task {task_uid} ended with status "
                    f"'{status['status']}': {status.get('error')}"
                )
            time.sleep(poll_interval_seconds)
        raise TimeoutError(
            f"Meilisearch task {task_uid} did not complete within {timeout_seconds}s"
        )

    def health_check(self) -> dict[str, Any]:
        """Return health status suitable for the /admin/readiness probe.

        Returns a dict with ``ok: bool`` and ``latency_ms: float``.
        Never raises — errors are captured in the return value.
        """
        start = time.monotonic()
        try:
            self._client.health()
            ok = True
            error = None
        except Exception as exc:
            ok = False
            error = str(exc)
        latency_ms = (time.monotonic() - start) * 1000
        return {"ok": ok, "latency_ms": round(latency_ms, 1), "error": error}
