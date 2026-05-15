from __future__ import annotations

import time
from typing import Any

from services.auth.models import TokenPayload, UserIdentity
from services.search.meili_acl import (  # type: ignore[import-not-found]
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
    DocumentSearchResponse,
    DocumentSearchResult,
    DocumentSearchResultMetadata,
    SearchChunkRecord,
)

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

    def __init__(self, client: _MeilisearchClient) -> None:
        self._client = client

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    def apply_settings(self, *, shadow: bool = False) -> None:
        """Apply index settings idempotently. Safe to call on every startup."""
        apply_index_settings(self._client, shadow=shadow)

    def prepare_shadow_index(self) -> None:
        """Create the shadow index with the same settings as the live index.

        Idempotent — safe to call even if the shadow index already exists.
        Used as the first step of a safe reindex (swap-indexes) operation.
        """
        apply_index_settings(self._client, shadow=True)

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
        payload = {"id": chunk_id, **{k: v for k, v in translations.items() if v is not None}}
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

    def existing_chunk_checksums(self, document_id: str) -> dict[str, str]:
        """Return {chunk_id: contentChecksum} for all indexed chunks of a document.

        Used to skip unchanged chunks during reindex of a single document.
        Fetches up to _MAX_CHUNK_SCAN records — documents with more chunks
        than this are fully reindexed without checksum comparison.
        """
        result = self._client.index(INDEX_NAME).search(
            "",
            {
                "filter": f'document_id = "{document_id}"',
                "limit": _MAX_CHUNK_SCAN,
                "attributesToRetrieve": ["id", "content_checksum"],
            },
        )
        return {hit["id"]: hit.get("content_checksum", "") for hit in result.get("hits", [])}

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: DocumentSearchQuery,
        user: TokenPayload | UserIdentity,
    ) -> DocumentSearchResponse:
        """Execute a search with the ACL filter applied server-side.

        The permission filter is constructed from the authenticated user's
        token and composed with any user-supplied filters. The caller cannot
        omit the ACL filter.

        Returns an empty response immediately if the user cannot access any
        document (non-admin with no group memberships).
        """
        if needs_acl_short_circuit(user):
            return DocumentSearchResponse(
                total=0,
                estimated_total=0,
                items=[],
                processing_time_ms=0,
            )

        acl_filter = build_permission_filter(user)
        user_filter = _build_user_filter(query.filters)
        combined_filter = compose_filters(acl_filter, user_filter)

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

        raw = self._client.index(INDEX_NAME).search(query.q, params)

        items = [_map_result(h) for h in raw.get("hits", [])]

        return DocumentSearchResponse(
            total=raw.get("nbHits", len(items)),
            estimated_total=raw.get("estimatedTotalHits", len(items)),
            items=items,
            processing_time_ms=raw.get("processingTimeMs", 0),
            facets=raw.get("facetDistribution") or {},
        )

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
