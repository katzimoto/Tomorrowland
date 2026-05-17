from __future__ import annotations

import logging
import time
from contextlib import suppress
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Request

from services.api._helpers import _fmt_dt, _translation_score
from services.api.main import current_user
from services.api.schemas import SearchRequest, SearchResponse, SearchResultItem
from services.auth.models import TokenPayload
from services.auth.repository import AuthRepository
from services.documents.models import DocumentRow
from services.documents.repository import DocumentRepository
from services.search.elastic import ElasticsearchSearchClient
from services.search.factory import build_encoder
from services.search.hybrid import SearchResult, merge_results
from services.search.meili_types import DocumentSearchQuery
from services.search.qdrant import QdrantSearchClient
from shared.correlation import get_correlation_id

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
    if not group_ids:
        http_request.app.state.metrics.search_requests_total.labels("hybrid", "success").inc()
        http_request.app.state.metrics.search_results_count.labels("hybrid").observe(0)
        http_request.app.state.metrics.search_duration_seconds.labels("hybrid").observe(
            time.perf_counter() - metrics_start
        )
        return SearchResponse(results=[], total=0)

    if http_request.app.state.admins_group_id in group_ids or user.is_admin:
        search_group_ids: list[str] = []
    else:
        with http_request.app.state.engine.begin() as _conn:
            _auth_repo = AuthRepository(_conn)
            _effective = set(user.groups) | set(_auth_repo.get_effective_group_ids(user.groups))
        search_group_ids = [str(g) for g in _effective]

    bm25_results: list[SearchResult] = []
    if http_request.app.state.meili_provider is not None:
        try:
            backend_start = time.perf_counter()
            meili_results = http_request.app.state.meili_provider.search(
                query=DocumentSearchQuery(
                    q=request.query,
                    limit=request.top_k,
                ),
                user=user,
            )
            logger.info(f"""Using Meilisearch provider results for search, \
                    query is {request.query} results are {meili_results}""")
            http_request.app.state.metrics.search_backend_duration_seconds.labels(
                "meilisearch", "search"
            ).observe(time.perf_counter() - backend_start)
            logger.debug(f"The Meilisearch provider returned {meili_results}")
            bm25_results = meili_results
        except Exception:
            logger.warning(
                "Meilisearch search degraded route=/search stage=bm25_search correlation_id=%s",
                get_correlation_id(),
            )

            raise
    else:
        try:
            es_client = http_request.app.state.es_client or ElasticsearchSearchClient(
                hosts=[http_request.app.state.settings.elastic_url]
            )
            encoder = build_encoder(http_request.app.state.settings)
            qdrant_client = http_request.app.state.qdrant_client or QdrantSearchClient(
                url=http_request.app.state.settings.qdrant_url,
                dimension=encoder.dimension,
            )

            backend_start = time.perf_counter()
            bm25_results = es_client.search(request.query, group_ids=search_group_ids, size=50)
            http_request.app.state.metrics.search_backend_duration_seconds.labels(
                "elasticsearch", "search"
            ).observe(time.perf_counter() - backend_start)
            logger.debug(f"The elastic search client returned {bm25_results}")
        except Exception as exc:
            logger.warning(
                "Elasticsearch search degraded route=/search stage=bm25_search "
                "error_type=%s correlation_id=%s",
                exc.__class__.__name__,
                get_correlation_id(),
            )

    vector_results: list[SearchResult] = []
    try:
        qdrant_client = http_request.app.state.qdrant_client or QdrantSearchClient(
            url=http_request.app.state.settings.qdrant_url
        )
        encoder = build_encoder(http_request.app.state.settings)
        query_vector = encoder.encode(request.query)
        backend_start = time.perf_counter()
        vector_results = qdrant_client.search(
            vector=query_vector, group_ids=search_group_ids, limit=50
        )
        logger.debug(f"The word vector returned {vector_results}")
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
        vector_row = connection.execute(
            sa.text("SELECT value FROM system_config WHERE key = 'search.vector_weight'"),
        ).scalar()
        bm25_row = connection.execute(
            sa.text("SELECT value FROM system_config WHERE key = 'search.bm25_weight'"),
        ).scalar()
        try:
            vector_weight = float(vector_row) if vector_row is not None else 0.7
        except (TypeError, ValueError):
            vector_weight = 0.7
        try:
            bm25_weight = float(bm25_row) if bm25_row is not None else 0.3
        except (TypeError, ValueError):
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

    # Filter out older versions unless explicitly requested
    if not request.include_older_versions:
        all_merged_ids: list[UUID] = []
        for r in merged:
            with suppress(ValueError):
                all_merged_ids.append(UUID(r.document_id))
        if all_merged_ids:
            with http_request.app.state.engine.begin() as connection:
                _doc_repo = DocumentRepository(connection)
                non_latest: set[str] = {
                    str(doc.id)
                    for doc in _doc_repo.list_by_ids(all_merged_ids)
                    if not doc.is_latest
                }
            merged = [r for r in merged if r.document_id not in non_latest]

    start = (request.page - 1) * request.page_size
    end = start + request.page_size
    page = merged[start:end]
    logger.info(f"The search result are {page}")
    # Enrich page with document metadata from the database
    doc_ids: list[UUID] = []
    for r in page:
        with suppress(ValueError):
            doc_ids.append(UUID(r.document_id))

    docs: dict[str, DocumentRow] = {}
    family_current: dict[UUID, UUID] = {}
    if doc_ids:
        with http_request.app.state.engine.begin() as connection:
            doc_repo = DocumentRepository(connection)
            for doc in doc_repo.list_by_ids(doc_ids):
                docs[str(doc.id)] = doc
            non_latest_family_ids = [
                d.version_family_id
                for d in docs.values()
                if d.version_family_id and not d.is_latest
            ]
            if non_latest_family_ids:
                family_current = doc_repo.get_family_current_doc_ids(non_latest_family_ids)

    now = datetime.now(UTC).isoformat()
    results: list[SearchResultItem] = []
    for r in page:
        doc_row = docs.get(r.document_id)
        if doc_row is None:
            results.append(
                SearchResultItem(
                    document_id=r.document_id,
                    source_id="",
                    external_id=None,
                    title=r.title,
                    snippet=r.chunk_text or "",
                    source="unknown",
                    source_label="Unknown",
                    mime_type="application/octet-stream",
                    tags=[],
                    translation_quality=None,
                    translation_score=0.0,
                    score=r.score,
                    updated_at=now,
                    indexed_at=now,
                )
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
    )
