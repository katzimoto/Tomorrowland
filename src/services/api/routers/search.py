from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request

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

router = APIRouter(tags=["search"])


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

    # Single DB transaction for admin verification + auth groups + search weights.
    with http_request.app.state.engine.begin() as connection:
        # Re-verify admin status against the DB to prevent stale-JWT bypass —
        # reuses the transaction connection instead of opening a new one.
        if is_admin and not _verify_admin_membership(connection, group_ids):
            is_admin = False

        if is_admin:
            search_group_ids: list[str] = []
        else:
            _auth_repo = AuthRepository(connection)
            _effective = set(user.groups) | set(_auth_repo.get_effective_group_ids(user.groups))
            search_group_ids = [str(g) for g in _effective]

        # Cache search weights via config_cache to avoid repeated system_config reads.
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

    # ── Run Meilisearch and Qdrant in parallel ──────────────────────────
    bm25_results: list[SearchResult] = []
    meili_facets: dict[str, dict[str, int]] = {}
    vector_results: list[SearchResult] = []

    # Pre-compute encoder outside the thread pool to avoid extra work.
    # Wrapped in try/except so an embedding-model outage degrades to
    # BM25-only results instead of crashing the route with a 500.
    _settings = http_request.app.state.settings
    encoder = build_encoder(_settings, timeout=_settings.search_embedding_timeout)
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

    def _run_meilisearch() -> tuple[list[SearchResult], dict[str, dict[str, int]], bool]:
        backend_start = time.perf_counter()
        try:
            meili_results = meili_provider.search(
                query=DocumentSearchQuery(
                    q=request.query,
                    limit=request.top_k,
                    filters=meili_filters,
                    sort=meili_sort,
                ),
                user=user,
            )
            http_request.app.state.metrics.search_backend_duration_seconds.labels(
                "meilisearch", "search"
            ).observe(time.perf_counter() - backend_start)
            return meili_results.results, meili_results.facets, False
        except Exception:
            logger.warning(
                "Meilisearch search degraded route=/search stage=bm25_search correlation_id=%s",
                get_correlation_id(),
            )
            return [], {}, True

    def _run_qdrant(
        query_vector: list[float],
    ) -> tuple[list[SearchResult], bool]:
        backend_start = time.perf_counter()
        try:
            results = qdrant_client.search(
                vector=query_vector,
                group_ids=search_group_ids,
                limit=50,
                allow_all=is_admin,
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

    retrieval_degraded = False

    # Fire both backends concurrently.
    # Note: the closures capture ``http_request`` (a Starlette Request).  We only
    # read scalar attributes (request.query, app.state.*, settings.*) which are
    # safe to access from the thread-pool threads.  Do not mutate request.state
    # or read headers/body from inside these closures.
    if meili_provider is not None and query_vector is not None:
        # Both backends available — run in parallel.
        with ThreadPoolExecutor(max_workers=2) as pool:
            meili_future = pool.submit(_run_meilisearch)
            qdrant_future = pool.submit(_run_qdrant, query_vector)
            try:
                bm25_results, meili_facets, _meili_degraded = meili_future.result(timeout=30)
            except Exception:
                bm25_results, meili_facets, _meili_degraded = [], {}, True
                logger.warning("Meilisearch future failed/timed out — degraded to BM25-only")
            try:
                vector_results, _qdrant_degraded = qdrant_future.result(timeout=30)
            except Exception:
                vector_results, _qdrant_degraded = [], True
                logger.warning("Qdrant future failed/timed out — no vector results")
            retrieval_degraded = _meili_degraded or _qdrant_degraded
    elif meili_provider is not None:
        # Encoder failed — vector unavailable; BM25-only is a degraded state.
        bm25_results, meili_facets, _meili_degraded = _run_meilisearch()
        retrieval_degraded = True
    elif query_vector is not None:
        # Meilisearch not configured — run Qdrant only.
        vector_results, _qdrant_degraded = _run_qdrant(query_vector)
        retrieval_degraded = _qdrant_degraded
    else:
        # Neither backend available.
        vector_results = []
        retrieval_degraded = True

    if vector_results:
        merged = merge_results(
            bm25_results=bm25_results,
            vector_results=vector_results,
            vector_weight=vector_weight,
            bm25_weight=bm25_weight,
        )
    else:
        merged = merge_results(
            bm25_results=bm25_results,
            vector_results=[],
            vector_weight=0.0,
            bm25_weight=1.0,
        )

    # --- Reranker pass (post-retrieval relevance scoring) ---
    _settings = http_request.app.state.settings
    reranker_applied = False
    if _settings.search_reranker_enabled and merged:
        try:
            reranker = build_reranker(
                _settings,
                llm_provider=getattr(http_request.app.state, "llm_provider", None),
            )
            rerank_start = time.perf_counter()
            merged = reranker.rerank(request.query, merged)
            http_request.app.state.metrics.search_backend_duration_seconds.labels(
                "reranker", "rerank"
            ).observe(time.perf_counter() - rerank_start)
            reranker_applied = True
        except Exception:
            logger.warning(
                "Search reranker degraded route=/search stage=rerank correlation_id=%s",
                get_correlation_id(),
            )
            # Continue with un-reranked results — reranker is best-effort.

    # Load all merged doc rows in one query — used for both is_latest filtering and enrichment.
    # Deduplicate before the batch query to avoid redundant IN-clause entries.
    all_merged_ids_set: set[UUID] = set()
    for r in merged:
        with suppress(ValueError):
            all_merged_ids_set.add(UUID(r.document_id))
    all_merged_ids = list(all_merged_ids_set)

    # Single DB transaction: load document rows + resolve family current IDs.
    all_docs: dict[str, DocumentRow] = {}
    family_current: dict[UUID, UUID] = {}
    if all_merged_ids:
        with http_request.app.state.engine.begin() as connection:
            _doc_repo = DocumentRepository(connection)
            for doc in _doc_repo.list_by_ids(all_merged_ids):
                all_docs[str(doc.id)] = doc
            # Resolve family current doc IDs while we still hold the connection.
            _non_latest_fids: list[UUID] = [
                fid
                for doc in all_docs.values()
                if not doc.is_latest and (fid := doc.version_family_id) is not None
            ]
            if _non_latest_fids:
                family_current = _doc_repo.get_family_current_doc_ids(_non_latest_fids)

    # Filter out older versions unless explicitly requested.
    # Orphaned vectors (no doc row) are also dropped here.
    if not request.include_older_versions:
        merged = [
            r for r in merged if r.document_id in all_docs and all_docs[r.document_id].is_latest
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
            # Orphaned Qdrant vector — document row was deleted but vector not yet purged.
            # Drop silently to avoid leaking chunk_text after deletion.
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
    return SearchResponse(
        results=results,
        total=len(merged),
        query=request.query,
        facets=meili_facets,
        reranker_applied=reranker_applied,
        retrieval_degraded=retrieval_degraded,
    )


# ---------------------------------------------------------------------------
# Filter mapping helpers
# ---------------------------------------------------------------------------


def _map_filters(raw: dict[str, Any]) -> DocumentSearchFilters:
    """Convert the generic frontend filters dict to DocumentSearchFilters.

    Note: Meilisearch's filter model supports ``created_after`` and
    ``updated_after`` but has no ``created_before`` field. Date-range
    upper bounds (``date_to``) are applied client-side; we only map
    ``date_from`` as the lower-bound filter here.
    """
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
    # date_to is handled client-side — no created_before field in Meilisearch

    return f


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
