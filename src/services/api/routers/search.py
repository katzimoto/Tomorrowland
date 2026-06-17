from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from qdrant_client.models import FieldCondition, MatchAny

from services.api._helpers import _fmt_dt, _translation_score, _verify_admin_membership
from services.api.main import current_user
from services.api.schemas import SearchRequest, SearchResponse, SearchResultItem
from services.auth.models import TokenPayload
from services.auth.repository import AuthRepository
from services.documents.models import DocumentRow
from services.documents.repository import DocumentRepository
from services.search.factory import build_encoder, build_reranker
from services.search.hybrid import SearchResult, merge_results
from services.search.meili_types import DocumentSearchFilters, DocumentSearchQuery
from services.search.qdrant import QdrantSearchClient
from shared.config_cache import get_cached_config
from shared.correlation import get_correlation_id

_MeiliSort = Literal["relevance", "updatedAt:desc", "createdAt:desc", "importedAt:desc"]

logger = logging.getLogger(__name__)


@dataclass
class _SearchDispatch:
    merged: list[SearchResult] = field(default_factory=list)
    bm25_results: list[SearchResult] = field(default_factory=list)
    vector_results: list[SearchResult] = field(default_factory=list)
    meili_facets: dict[str, dict[str, int]] = field(default_factory=dict)
    meili_total: int = 0
    retrieval_degraded: bool = False
    meili_filters: DocumentSearchFilters = field(default_factory=DocumentSearchFilters)


router = APIRouter(tags=["search"])


def _run_meilisearch(
    meili_provider: Any,
    query: str,
    top_k: int,
    filters: DocumentSearchFilters,
    sort: _MeiliSort,
    user: TokenPayload,
    http_request: Request,
) -> tuple[list[SearchResult], dict[str, dict[str, int]], bool, int]:
    backend_start = time.perf_counter()
    try:
        meili_results = meili_provider.search(
            query=DocumentSearchQuery(
                q=query,
                limit=top_k,
                filters=filters,
                sort=sort,
            ),
            user=user,
        )
        http_request.app.state.metrics.search_backend_duration_seconds.labels(
            "meilisearch", "search"
        ).observe(time.perf_counter() - backend_start)
        return meili_results.results, meili_results.facets, False, meili_results.total
    except Exception:
        logger.warning(
            "Meilisearch search degraded route=/search stage=bm25_search correlation_id=%s",
            get_correlation_id(),
        )
        return [], {}, True, 0


def _run_qdrant(
    query_vector: list[float],
    qdrant_client: QdrantSearchClient,
    group_ids: list[str],
    is_admin: bool,
    qdrant_extra: list[Any] | None,
    http_request: Request,
) -> tuple[list[SearchResult], bool]:
    backend_start = time.perf_counter()
    try:
        results = qdrant_client.search(
            vector=query_vector,
            group_ids=group_ids,
            limit=50,
            allow_all=is_admin,
            extra_conditions=qdrant_extra or None,
        )
        http_request.app.state.metrics.search_backend_duration_seconds.labels(
            "qdrant", "search"
        ).observe(time.perf_counter() - backend_start)
        return results, False
    except Exception as exc:
        logger.warning(
            "Vector search degraded route=/search stage=vector_search "
            "error_type=%s correlation_id=%s",
            exc.__class__.__name__,
            get_correlation_id(),
        )
        http_request.app.state.metrics.search_requests_total.labels("hybrid", "degraded").inc()
        return [], True


def _dispatch_and_merge(
    request: SearchRequest,
    http_request: Request,
    user: TokenPayload,
    group_ids: list[str],
    is_admin: bool,
    vector_weight: float = 0.7,
    bm25_weight: float = 0.3,
) -> _SearchDispatch:
    """Run Meilisearch and Qdrant in parallel (or fallback). Returns merged results."""
    _settings = http_request.app.state.settings

    encoder = build_encoder(
        _settings,
        timeout=_settings.search_embedding_timeout,
        resolver=getattr(http_request.app.state, "task_default_resolver", None),
    )
    try:
        query_vector = encoder.encode(request.query)
    except Exception:
        logger.warning(
            "Embedding encode failed — falling back to BM25-only search correlation_id=%s",
            get_correlation_id(),
        )
        query_vector = None

    qdrant_client = http_request.app.state.qdrant_client or QdrantSearchClient(
        url=_settings.qdrant_url,
        dimension=encoder.dimension,
    )

    meili_filters = _map_filters(request.filters)
    meili_sort = _map_sort(request.sort_by, request.sort_dir)
    meili_provider = http_request.app.state.meili_provider
    qdrant_extra = _qdrant_extra_conditions(meili_filters)

    search_group_ids = group_ids if not is_admin else []

    bm25_results: list[SearchResult] = []
    meili_facets: dict[str, dict[str, int]] = {}
    meili_total: int = 0
    vector_results: list[SearchResult] = []
    retrieval_degraded = False

    if meili_provider is not None and query_vector is not None:
        pool = ThreadPoolExecutor(max_workers=2)
        try:
            meili_future = pool.submit(
                _run_meilisearch,
                meili_provider,
                request.query,
                request.top_k,
                meili_filters,
                meili_sort,
                user,
                http_request,
            )
            qdrant_future = pool.submit(
                _run_qdrant,
                query_vector,
                qdrant_client,
                search_group_ids,
                is_admin,
                qdrant_extra,
                http_request,
            )
            try:
                bm25_results, meili_facets, _meili_degraded, meili_total = meili_future.result(
                    timeout=30
                )
            except Exception:
                bm25_results = []
                meili_facets = {}
                _meili_degraded = True
                meili_total = 0
                logger.warning("Meilisearch future failed/timed out — degraded to BM25-only")
            try:
                vector_results, _qdrant_degraded = qdrant_future.result(timeout=30)
            except Exception:
                vector_results, _qdrant_degraded = [], True
                logger.warning("Qdrant future failed/timed out — no vector results")
            retrieval_degraded = _meili_degraded or _qdrant_degraded
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
    elif meili_provider is not None:
        bm25_results, meili_facets, _meili_degraded, meili_total = _run_meilisearch(
            meili_provider,
            request.query,
            request.top_k,
            meili_filters,
            meili_sort,
            user,
            http_request,
        )
        retrieval_degraded = True
    elif query_vector is not None:
        vector_results, _qdrant_degraded = _run_qdrant(
            query_vector,
            qdrant_client,
            search_group_ids,
            is_admin,
            qdrant_extra,
            http_request,
        )
        retrieval_degraded = _qdrant_degraded
    else:
        retrieval_degraded = True

    merged = merge_results(
        bm25_results=bm25_results,
        vector_results=vector_results or [],
        vector_weight=vector_weight if vector_results else 0.0,
        bm25_weight=bm25_weight if vector_results else 1.0,
    )

    return _SearchDispatch(
        merged=merged,
        bm25_results=bm25_results,
        vector_results=vector_results,
        meili_facets=meili_facets,
        meili_total=meili_total,
        retrieval_degraded=retrieval_degraded,
        meili_filters=meili_filters,
    )


def _apply_reranker(
    http_request: Request,
    query: str,
    merged: list[SearchResult],
) -> tuple[list[SearchResult], bool]:
    _settings = http_request.app.state.settings
    if not _settings.search_reranker_enabled or not merged:
        return merged, False
    try:
        reranker = build_reranker(
            _settings,
            llm_provider=getattr(http_request.app.state, "llm_provider", None),
            resolver=getattr(http_request.app.state, "task_default_resolver", None),
        )
        rerank_start = time.perf_counter()
        reranked = reranker.rerank(query, merged)
        http_request.app.state.metrics.search_backend_duration_seconds.labels(
            "reranker", "rerank"
        ).observe(time.perf_counter() - rerank_start)
        return reranked, True
    except Exception:
        logger.warning(
            "Search reranker degraded route=/search stage=rerank correlation_id=%s",
            get_correlation_id(),
        )
        return merged, False


def _build_search_response(
    http_request: Request,
    request: SearchRequest,
    merged: list[SearchResult],
    bm25_results: list[SearchResult],
    vector_results: list[SearchResult],
    meili_facets: dict[str, dict[str, int]],
    meili_total: int,
    reranker_applied: bool,
    retrieval_degraded: bool,
    metrics_start: float,
) -> SearchResponse:
    all_merged_ids_set: set[UUID] = set()
    for r in merged:
        with suppress(ValueError):
            all_merged_ids_set.add(UUID(r.document_id))
    all_merged_ids = list(all_merged_ids_set)

    all_docs: dict[str, DocumentRow] = {}
    family_current: dict[UUID, UUID] = {}
    if all_merged_ids:
        with http_request.app.state.engine.begin() as connection:
            _doc_repo = DocumentRepository(connection)
            for doc in _doc_repo.list_by_ids(all_merged_ids):
                all_docs[str(doc.id)] = doc
            _non_latest_fids: list[UUID] = [
                fid
                for doc in all_docs.values()
                if not doc.is_latest and (fid := doc.version_family_id) is not None
            ]
            if _non_latest_fids:
                family_current = _doc_repo.get_family_current_doc_ids(_non_latest_fids)

    candidate_count = len(merged)

    meili_filters = _map_filters(request.filters)
    merged = [
        r
        for r in merged
        if r.document_id in all_docs
        and (request.include_older_versions or all_docs[r.document_id].is_latest)
        and _matches_filters(all_docs[r.document_id], meili_filters)
    ]

    start = (request.page - 1) * request.page_size
    end = start + request.page_size
    page = merged[start:end]
    logger.debug("search page_size=%d correlation_id=%s", len(page), get_correlation_id())

    now = datetime.now(UTC).isoformat()
    results: list[SearchResultItem] = []
    for r in page:
        doc_row = all_docs.get(r.document_id)
        if doc_row is None:
            logger.warning(
                "Orphaned Qdrant vector skipped document_id=%s route=/search correlation=%s",
                r.document_id,
                get_correlation_id(),
            )
            continue

        metadata = doc_row.metadata or {}
        tags = metadata.get("tags", [])
        if isinstance(tags, str):
            tags = [tags]

        if doc_row.is_latest:
            latest_doc_id: str | None = str(doc_row.id)
        elif doc_row.version_family_id:
            latest_raw = family_current.get(doc_row.version_family_id)
            latest_doc_id = str(latest_raw) if latest_raw else None
        else:
            latest_doc_id = None

        results.append(
            SearchResultItem(
                document_id=r.document_id,
                source_id=str(doc_row.source_id),
                external_id=doc_row.external_id or None,
                title=r.title or doc_row.title,
                snippet=r.chunk_text or doc_row.title or "",
                source=doc_row.source,
                source_label=doc_row.source.capitalize(),
                mime_type=doc_row.mime_type,
                tags=list(tags),
                translation_quality=doc_row.translation_quality,
                translation_score=_translation_score(doc_row.translation_quality),
                score=r.score,
                updated_at=_fmt_dt(doc_row.updated_at) or now,
                indexed_at=_fmt_dt(doc_row.created_at) or now,
                version_number=doc_row.version_number,
                is_latest=doc_row.is_latest,
                latest_document_id=latest_doc_id,
                has_newer_version=not doc_row.is_latest,
            )
        )

    if vector_results:
        http_request.app.state.metrics.search_requests_total.labels("hybrid", "success").inc()
    http_request.app.state.metrics.search_results_count.labels("hybrid").observe(len(merged))
    http_request.app.state.metrics.search_duration_seconds.labels("hybrid").observe(
        time.perf_counter() - metrics_start
    )

    total = len(merged)
    bm25_window_truncated = meili_total > len(bm25_results)
    total_is_approximate = bool(vector_results) or bm25_window_truncated

    return SearchResponse(
        results=results,
        total=total,
        total_is_approximate=total_is_approximate,
        candidate_count=candidate_count,
        returned_count=len(results),
        offset=start,
        limit=request.page_size,
        query=request.query,
        facets=meili_facets,
        reranker_applied=reranker_applied,
        retrieval_degraded=retrieval_degraded,
    )


# ---------------------------------------------------------------------------
# Route handler
# ---------------------------------------------------------------------------


@router.post("/search", response_model=SearchResponse)
def search(
    request: SearchRequest,
    http_request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> SearchResponse:
    metrics_start = time.perf_counter()
    group_ids = [str(g) for g in user.groups]
    is_admin = user.is_admin or http_request.app.state.admins_group_id in group_ids
    if not group_ids and not is_admin:
        http_request.app.state.metrics.search_requests_total.labels("hybrid", "success").inc()
        http_request.app.state.metrics.search_results_count.labels("hybrid").observe(0)
        http_request.app.state.metrics.search_duration_seconds.labels("hybrid").observe(
            time.perf_counter() - metrics_start
        )
        return SearchResponse(results=[], total=0)

    with http_request.app.state.engine.begin() as connection:
        if is_admin and not _verify_admin_membership(connection, group_ids):
            is_admin = False
        search_group_ids: list[str] = []
        if not is_admin:
            _auth_repo = AuthRepository(connection)
            _effective = set(user.groups) | set(_auth_repo.get_effective_group_ids(user.groups))
            search_group_ids = [str(g) for g in _effective]

        _vw = get_cached_config(connection, "search.vector_weight")
        _bw = get_cached_config(connection, "search.bm25_weight")
        try:
            vector_weight = float(_vw) if _vw else 0.7
        except (TypeError, ValueError):
            vector_weight = 0.7
        try:
            bm25_weight = float(_bw) if _bw else 0.3
        except (TypeError, ValueError):
            bm25_weight = 0.3

    if not group_ids and not is_admin:
        return SearchResponse(results=[], total=0)

    dispatch = _dispatch_and_merge(
        request,
        http_request,
        user,
        search_group_ids,
        is_admin,
        vector_weight=vector_weight,
        bm25_weight=bm25_weight,
    )

    merged, reranker_applied = _apply_reranker(http_request, request.query, dispatch.merged)

    return _build_search_response(
        http_request,
        request,
        merged,
        dispatch.bm25_results,
        dispatch.vector_results,
        dispatch.meili_facets,
        dispatch.meili_total,
        reranker_applied,
        dispatch.retrieval_degraded,
        metrics_start,
    )


# ---------------------------------------------------------------------------
# Filter mapping helpers
# ---------------------------------------------------------------------------


def _map_filters(raw: dict[str, Any]) -> DocumentSearchFilters:
    """Convert the generic frontend filters dict to DocumentSearchFilters."""
    f = DocumentSearchFilters()

    if isinstance(raw.get("source"), list):
        f.source = [str(s) for s in raw["source"] if s]
    if isinstance(raw.get("file_type"), list):
        f.mime_type = [str(m) for m in raw["file_type"] if m]
    if isinstance(raw.get("file_extension"), list):
        f.file_extension = [str(e) for e in raw["file_extension"] if e]
    if isinstance(raw.get("tags"), list):
        f.tags = [str(t) for t in raw["tags"] if t]
    if isinstance(raw.get("language"), str) and raw["language"]:
        f.language = [raw["language"]]
    if isinstance(raw.get("date_from"), str):
        f.created_after = raw["date_from"]
    if isinstance(raw.get("date_to"), str):
        f.created_before = raw["date_to"]

    return f


def _qdrant_extra_conditions(filters: DocumentSearchFilters) -> list[FieldCondition]:
    """Build Qdrant payload conditions for filters available in the chunk payload.

    Only fields stored in the Qdrant payload at index time can be pushed
    here. All other filters are enforced by ``_matches_filters`` after
    ``DocumentRow`` enrichment.
    """
    conditions: list[FieldCondition] = []
    if filters.language:
        conditions.append(
            FieldCondition(key="source_language", match=MatchAny(any=filters.language))
        )
    return conditions


def _matches_filters(doc: DocumentRow, filters: DocumentSearchFilters) -> bool:
    """Return True if *doc* satisfies every active user filter.

    Applied to all merged results after DocumentRow enrichment so that
    Qdrant/vector candidates obey the same filters as Meilisearch/BM25
    candidates.  An empty filter list is a no-op (returns True).
    """
    if filters.source and doc.source not in filters.source:
        return False
    if filters.mime_type and doc.mime_type not in filters.mime_type:
        return False
    if filters.language:
        doc_lang = doc.source_language or ""
        if doc_lang not in filters.language:
            return False
    if filters.tags:
        raw_tags = doc.metadata.get("tags") or []
        doc_tags: list[str] = [raw_tags] if isinstance(raw_tags, str) else list(raw_tags)
        if not any(t in doc_tags for t in filters.tags):
            return False
    if filters.file_extension:
        doc_ext = str(doc.metadata.get("file_extension") or "").lower()
        if doc_ext not in [e.lower() for e in filters.file_extension]:
            return False
    if filters.created_after:
        try:
            cutoff = datetime.fromisoformat(filters.created_after)
            if cutoff.tzinfo is None:
                cutoff = cutoff.replace(tzinfo=UTC)
            doc_dt = doc.created_at if doc.created_at.tzinfo else doc.created_at.replace(tzinfo=UTC)
            if doc_dt < cutoff:
                return False
        except (ValueError, TypeError):
            logger.warning(
                "Invalid created_after date filter: %r",
                filters.created_after,
            )
            return True
    if filters.created_before:
        try:
            cutoff = datetime.fromisoformat(filters.created_before)
            if cutoff.tzinfo is None:
                cutoff = cutoff.replace(tzinfo=UTC)
            doc_dt = doc.created_at if doc.created_at.tzinfo else doc.created_at.replace(tzinfo=UTC)
            if doc_dt > cutoff:
                return False
        except (ValueError, TypeError):
            logger.warning(
                "Invalid created_before date filter: %r",
                filters.created_before,
            )
            return True
    return True


_MEILI_SORT_MAP = {
    "relevance": "relevance",
    "updated_at": "updatedAt:desc",
    "created_at": "createdAt:desc",
    "title": "relevance",  # Meilisearch doesn't sort by title natively
}


def _map_sort(sort_by: str, sort_dir: str) -> _MeiliSort:
    """Map frontend sort to Meilisearch sort string.

    ``sort_by`` arrives in snake_case (e.g. ``updated_at``). The valid
    Meilisearch sort strings use camelCase fields (e.g. ``updatedAt:desc``).
    ``_MEILI_SORT_MAP`` holds the snake→camel translation; we apply the
    requested direction after looking up the camel field name.
    """
    if sort_by == "relevance":
        return "relevance"
    # Resolve the camelCase base (e.g. "updated_at" → "updatedAt:desc").
    # The map values already include ":desc" as the canonical form; strip it
    # to get the bare field name, then re-apply the requested direction.
    mapped = _MEILI_SORT_MAP.get(sort_by)
    if mapped is None or mapped == "relevance":
        return "relevance"
    camel_field = mapped.split(":")[0]  # e.g. "updatedAt"
    suffix = "desc" if sort_dir == "desc" else "asc"
    return f"{camel_field}:{suffix}"  # type: ignore[return-value]
