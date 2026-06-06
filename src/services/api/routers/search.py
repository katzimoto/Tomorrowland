from __future__ import annotations

import logging
import time
from contextlib import suppress
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Request

from services.api._helpers import _fmt_dt, _translation_score, _verify_admin_membership
from services.api.main import current_user
from services.api.schemas import SearchRequest, SearchResponse, SearchResultItem
from services.auth.models import TokenPayload
from services.auth.repository import AuthRepository
from services.documents.models import DocumentRow
from services.documents.repository import DocumentRepository
from services.search.factory import build_encoder
from services.search.hybrid import SearchResult, merge_results
from services.search.meili_types import DocumentSearchFilters, DocumentSearchQuery
from services.search.qdrant import QdrantSearchClient
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
    if is_admin:
        # Re-verify admin status against the DB to prevent stale-JWT bypass.
        if not _verify_admin_membership(http_request.app.state.engine, group_ids):
            is_admin = False
    if not group_ids and not is_admin:
        http_request.app.state.metrics.search_requests_total.labels("hybrid", "success").inc()
        http_request.app.state.metrics.search_results_count.labels("hybrid").observe(0)
        http_request.app.state.metrics.search_duration_seconds.labels("hybrid").observe(
            time.perf_counter() - metrics_start
        )
        return SearchResponse(results=[], total=0)

    if is_admin:
        search_group_ids: list[str] = []
    else:
        with http_request.app.state.engine.begin() as _conn:
            _auth_repo = AuthRepository(_conn)
            _effective = set(user.groups) | set(_auth_repo.get_effective_group_ids(user.groups))
        search_group_ids = [str(g) for g in _effective]

    bm25_results: list[SearchResult] = []
    meili_facets: dict[str, dict[str, int]] = {}
    if http_request.app.state.meili_provider is not None:
        try:
            backend_start = time.perf_counter()
            meili_filters = _map_filters(request.filters)
            meili_sort = _map_sort(request.sort_by, request.sort_dir)
            meili_results = http_request.app.state.meili_provider.search(
                query=DocumentSearchQuery(
                    q=request.query,
                    limit=request.top_k,
                    filters=meili_filters,
                    sort=meili_sort,
                ),
                user=user,
            )
            logger.info(
                "Using Meilisearch provider results for search, query=%s results=%s",
                request.query,
                meili_results.results,
            )
            http_request.app.state.metrics.search_backend_duration_seconds.labels(
                "meilisearch", "search"
            ).observe(time.perf_counter() - backend_start)
            logger.debug("The Meilisearch provider returned results=%s", meili_results.results)
            bm25_results = meili_results.results
            meili_facets = meili_results.facets
        except Exception:
            logger.warning(
                "Meilisearch search degraded route=/search stage=bm25_search correlation_id=%s",
                get_correlation_id(),
            )
            # Degrade gracefully: continue with empty BM25 results so vector search
            # can still return results instead of surfacing a 500 to the user.

    vector_results: list[SearchResult] = []
    try:
        qdrant_client = http_request.app.state.qdrant_client or QdrantSearchClient(
            url=http_request.app.state.settings.qdrant_url
        )
        _settings = http_request.app.state.settings
        encoder = build_encoder(
            _settings,
            timeout=_settings.search_embedding_timeout,
        )
        query_vector = encoder.encode(request.query)
        backend_start = time.perf_counter()
        vector_results = qdrant_client.search(
            vector=query_vector, group_ids=search_group_ids, limit=50, allow_all=is_admin
        )
        logger.debug("The word vector returned results=%s", vector_results)
        http_request.app.state.metrics.search_backend_duration_seconds.labels(
            "qdrant", "search"
        ).observe(time.perf_counter() - backend_start)
    except Exception as exc:
        logger.warning(
            "Vector search degraded route=/search stage=vector_search "
            "error_type=%s correlation_id=%s",
            exc.__class__.__name__,
            get_correlation_id(),
        )
        http_request.app.state.metrics.search_requests_total.labels("hybrid", "degraded").inc()

    with http_request.app.state.engine.begin() as connection:
        _weight_rows = connection.execute(
            sa.text(
                "SELECT key, value FROM system_config"
                " WHERE key IN ('search.vector_weight', 'search.bm25_weight')"
            ),
        ).fetchall()
    _weight_map = {row[0]: row[1] for row in _weight_rows}
    try:
        vector_weight = float(_weight_map["search.vector_weight"])
    except (KeyError, TypeError, ValueError):
        vector_weight = 0.7
    try:
        bm25_weight = float(_weight_map["search.bm25_weight"])
    except (KeyError, TypeError, ValueError):
        bm25_weight = 0.3

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

    # Load all merged doc rows in one query — used for both is_latest filtering and enrichment.
    all_merged_ids: list[UUID] = []
    for r in merged:
        with suppress(ValueError):
            all_merged_ids.append(UUID(r.document_id))

    all_docs: dict[str, DocumentRow] = {}
    if all_merged_ids:
        with http_request.app.state.engine.begin() as connection:
            _doc_repo = DocumentRepository(connection)
            for doc in _doc_repo.list_by_ids(all_merged_ids):
                all_docs[str(doc.id)] = doc

    # Filter out older versions unless explicitly requested.
    # Orphaned vectors (no doc row) are also dropped here.
    if not request.include_older_versions:
        merged = [
            r for r in merged if r.document_id in all_docs and all_docs[r.document_id].is_latest
        ]

    start = (request.page - 1) * request.page_size
    end = start + request.page_size
    page = merged[start:end]
    logger.info("The search results are page=%s", page)

    # Resolve family current doc IDs for non-latest docs in this page (small set, conditional).
    family_current: dict[UUID, UUID] = {}
    non_latest_family_ids: list[UUID] = [
        fid
        for r in page
        if r.document_id in all_docs
        and not all_docs[r.document_id].is_latest
        and (fid := all_docs[r.document_id].version_family_id) is not None
    ]
    if non_latest_family_ids:
        with http_request.app.state.engine.begin() as connection:
            doc_repo = DocumentRepository(connection)
            family_current = doc_repo.get_family_current_doc_ids(non_latest_family_ids)

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
