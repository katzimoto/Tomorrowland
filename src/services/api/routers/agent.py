"""Read-only permissioned researcher API endpoints (#558).

Surfaces a stable read-only HTTP surface that future Hermes / MCP clients
(#560) can call through the same app-level authorization rules as normal
users.  Every endpoint enforces the standard source/document ACL — no
endpoint may bypass app-level authorization, no raw DB / Qdrant /
Meilisearch is exposed, and corpus answers cite only documents the caller
can access.
"""

from __future__ import annotations

import logging
from contextlib import suppress
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.api._helpers import (
    _fmt_dt,
    related_docs_limit,
    require_related_docs_enabled,
)
from services.api.main import current_user
from services.auth.models import TokenPayload
from services.auth.repository import AuthRepository
from services.documents.repository import DocumentRepository
from services.intelligence.repository import IntelligenceRepository
from services.permissions.enforcer import assert_doc_access
from services.pipeline.jobs import PipelineJobRepository
from services.rag.reranker import NoOpReranker
from services.rag.service import RagService
from services.related.repository import RelatedRepository
from services.related.service import RelatedService
from services.search.factory import build_encoder
from services.search.hybrid import SearchResult, merge_results
from services.search.meili_types import DocumentSearchFilters, DocumentSearchQuery
from services.search.qdrant import QdrantSearchClient
from shared.correlation import get_correlation_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent/v1", tags=["agent"])


# ---------------------------------------------------------------------------
# Request / response schemas (kept local to this router to avoid leaking the
# agent surface into the broader public schemas module).
# ---------------------------------------------------------------------------


class AgentSearchFilters(BaseModel):
    """Whitelisted filter fields for the agent search endpoint.

    Restricting filters here (rather than accepting an open ``dict``) keeps
    the agent-facing surface predictable and avoids accidentally proxying
    new filter fields without explicit review.
    """

    sources: list[str] = Field(default_factory=list)
    mime_types: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    date_from: str | None = None
    date_to: str | None = None


class AgentSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    top_k: int = Field(default=20, ge=1, le=50)
    page: int = Field(default=1, ge=1, le=20)
    filters: AgentSearchFilters = Field(default_factory=AgentSearchFilters)


class AgentSearchResultItem(BaseModel):
    document_id: str
    source_id: str
    title: str | None = None
    snippet: str | None = None
    source: str
    mime_type: str
    score: float
    language: str | None = None
    updated_at: str
    indexed_at: str


class AgentSearchResponse(BaseModel):
    results: list[AgentSearchResultItem]
    total: int
    query: str


class AgentDocumentResponse(BaseModel):
    document_id: str
    source_id: str
    title: str | None = None
    mime_type: str
    source: str
    source_language: str | None = None
    target_language: str | None = None
    translation_quality: str | None = None
    status: str | None = None
    version_number: int | None = None
    is_latest: bool | None = None
    created_at: str | None = None
    updated_at: str | None = None
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)


class AgentPassage(BaseModel):
    chunk_id: str | None = None
    chunk_index: int | None = None
    text: str
    page_number: int | None = None
    section_heading: str | None = None
    language: str | None = None


class AgentPassagesResponse(BaseModel):
    document_id: str
    passages: list[AgentPassage]
    total: int


class AgentAskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=20)
    document_id: str | None = None


class AgentAskCitation(BaseModel):
    document_id: str
    doc_title: str | None = None
    chunk_text: str
    score: float
    chunk_index: int | None = None
    source_id: str | None = None
    page_number: int | None = None
    section_heading: str | None = None
    language: str | None = None


class AgentAskResponse(BaseModel):
    question: str
    answer: str
    citations: list[AgentAskCitation]
    model: str


class AgentRelatedItem(BaseModel):
    document_id: str
    title: str | None = None
    score: float
    source: str | None = None
    relation_score: float | None = None
    reasons: list[dict[str, Any]] = Field(default_factory=list)


class AgentRelatedResponse(BaseModel):
    document_id: str
    related: list[AgentRelatedItem]


class AgentFacetsResponse(BaseModel):
    facets: dict[str, dict[str, int]]


# ---------------------------------------------------------------------------
# Permission helpers
# ---------------------------------------------------------------------------


def _resolve_effective_groups(
    request: Request,
    user: TokenPayload,
    connection: sa.Connection,
) -> tuple[list[str], bool]:
    """Compute (group_ids, is_admin) using transitive group expansion.

    Mirrors the pattern used by ``/search``, ``/expertise`` and
    ``/documents/{id}/related`` so the agent surface inherits the same
    permission semantics.
    """
    raw_group_ids = [str(g) for g in user.groups]
    is_admin = user.is_admin or request.app.state.admins_group_id in raw_group_ids
    if is_admin:
        return [], True
    if not raw_group_ids:
        return [], False
    auth_repo = AuthRepository(connection)
    effective = set(user.groups) | set(auth_repo.get_effective_group_ids(user.groups))
    return [str(g) for g in effective], False


def _map_agent_filters(filters: AgentSearchFilters) -> DocumentSearchFilters:
    """Translate the agent-facing filter shape to the internal Meili filters."""
    f = DocumentSearchFilters()
    if filters.sources:
        f.source = list(filters.sources)
    if filters.mime_types:
        f.mime_type = list(filters.mime_types)
    if filters.languages:
        f.language = list(filters.languages)
    if filters.tags:
        f.tags = list(filters.tags)
    if filters.date_from:
        f.created_after = filters.date_from
    if filters.date_to:
        f.updated_after = filters.date_to
    return f


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/search_documents", response_model=AgentSearchResponse)
def search_documents(
    body: AgentSearchRequest,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> AgentSearchResponse:
    """Hybrid search restricted to documents the caller can access."""
    settings = request.app.state.settings

    with request.app.state.engine.begin() as connection:
        group_ids, is_admin = _resolve_effective_groups(request, user, connection)
        if not group_ids and not is_admin:
            return AgentSearchResponse(results=[], total=0, query=body.query)

        bm25_results: list[SearchResult] = []
        if request.app.state.meili_provider is not None:
            try:
                meili_query = DocumentSearchQuery(
                    q=body.query,
                    limit=body.top_k,
                    filters=_map_agent_filters(body.filters),
                    sort="relevance",
                )
                meili_results = request.app.state.meili_provider.search(
                    query=meili_query, user=user
                )
                bm25_results = meili_results.results
            except Exception:
                logger.warning(
                    "Agent meilisearch degraded route=/api/agent/v1/search_documents "
                    "correlation_id=%s",
                    get_correlation_id(),
                )

        vector_results: list[SearchResult] = []
        try:
            encoder = build_encoder(settings, timeout=settings.search_embedding_timeout)
            qdrant_client = request.app.state.qdrant_client or QdrantSearchClient(
                url=settings.qdrant_url, dimension=encoder.dimension
            )
            query_vector = encoder.encode(body.query)
            vector_results = qdrant_client.search(
                vector=query_vector,
                group_ids=group_ids,
                limit=max(body.top_k, 50),
                allow_all=is_admin,
            )
        except Exception as exc:
            logger.warning(
                "Agent vector search degraded route=/api/agent/v1/search_documents "
                "error_type=%s correlation_id=%s",
                exc.__class__.__name__,
                get_correlation_id(),
            )

        if vector_results:
            merged = merge_results(
                bm25_results=bm25_results,
                vector_results=vector_results,
                vector_weight=0.7,
                bm25_weight=0.3,
            )
        else:
            merged = merge_results(
                bm25_results=bm25_results,
                vector_results=[],
                vector_weight=0.0,
                bm25_weight=1.0,
            )

        # Hydrate via DocumentRepository so we drop orphaned vectors and apply
        # the standard latest-version filter used by /search.
        merged_ids: list[UUID] = []
        for r in merged:
            with suppress(ValueError):
                merged_ids.append(UUID(r.document_id))

        docs: dict[str, Any] = {}
        if merged_ids:
            doc_repo = DocumentRepository(connection)
            for d in doc_repo.list_by_ids(merged_ids):
                docs[str(d.id)] = d

        merged = [r for r in merged if r.document_id in docs and docs[r.document_id].is_latest]

        # Defence in depth: re-check source ACL per row for non-admin callers
        # so tampered Qdrant payloads cannot leak documents the caller cannot
        # actually reach.
        if not is_admin:
            auth_repo = AuthRepository(connection)
            allowed = [
                r
                for r in merged
                if auth_repo.user_can_access_source(user, docs[r.document_id].source_id)  # type: ignore[arg-type]
            ]
            merged = allowed

        start = (body.page - 1) * body.top_k
        end = start + body.top_k
        page_results = merged[start:end]

        now = datetime.now(UTC).isoformat()
        items: list[AgentSearchResultItem] = []
        for r in page_results:
            doc = docs[r.document_id]
            items.append(
                AgentSearchResultItem(
                    document_id=r.document_id,
                    source_id=str(doc.source_id),
                    title=r.title or doc.title,
                    snippet=r.chunk_text or doc.title or "",
                    source=doc.source,
                    mime_type=doc.mime_type,
                    score=r.score,
                    language=doc.source_language,
                    updated_at=_fmt_dt(doc.updated_at) or now,
                    indexed_at=_fmt_dt(doc.created_at) or now,
                )
            )

        return AgentSearchResponse(
            results=items,
            total=len(merged),
            query=body.query,
        )


@router.get("/get_document", response_model=AgentDocumentResponse)
def get_document(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
    document_id: Annotated[UUID, Query(...)],
) -> AgentDocumentResponse:
    """Return permissioned metadata for a single document."""
    with request.app.state.engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        assert_doc_access(document_id, user, auth_repo)

        doc_repo = DocumentRepository(connection)
        doc = doc_repo.get_by_id(document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")

        intelligence_repo = IntelligenceRepository(connection)
        summary_row = intelligence_repo.get_summary(document_id)
        tags = intelligence_repo.get_tags(document_id)

        return AgentDocumentResponse(
            document_id=str(doc.id),
            source_id=str(doc.source_id),
            title=doc.title,
            mime_type=doc.mime_type,
            source=doc.source,
            source_language=doc.source_language,
            target_language=doc.target_language,
            translation_quality=doc.translation_quality,
            status=doc.status,
            version_number=doc.version_number,
            is_latest=doc.is_latest,
            created_at=_fmt_dt(doc.created_at),
            updated_at=_fmt_dt(doc.updated_at),
            summary=summary_row["summary"] if summary_row else None,
            tags=tags,
        )


@router.get("/get_passages", response_model=AgentPassagesResponse)
def get_passages(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
    document_id: Annotated[UUID, Query(...)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=10000)] = 0,
) -> AgentPassagesResponse:
    """Return ordered passages (chunks) for a document the caller can access."""
    settings = request.app.state.settings
    with request.app.state.engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        assert_doc_access(document_id, user, auth_repo)

        group_ids, is_admin = _resolve_effective_groups(request, user, connection)
        if not group_ids and not is_admin:
            return AgentPassagesResponse(document_id=str(document_id), passages=[], total=0)

    encoder = build_encoder(settings, timeout=settings.search_embedding_timeout)
    qdrant_client = request.app.state.qdrant_client or QdrantSearchClient(
        url=settings.qdrant_url, dimension=encoder.dimension
    )

    try:
        chunk_results = qdrant_client.list_chunks_by_document(
            document_id=str(document_id),
            group_ids=group_ids,
            allow_all=is_admin,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        logger.warning(
            "Agent passages degraded route=/api/agent/v1/get_passages "
            "error_type=%s correlation_id=%s",
            exc.__class__.__name__,
            get_correlation_id(),
        )
        chunk_results = []

    passages = [
        AgentPassage(
            chunk_id=(r.metadata or {}).get("chunk_id"),
            chunk_index=(r.metadata or {}).get("chunk_index"),
            text=r.chunk_text or "",
            page_number=(r.metadata or {}).get("page_number"),
            section_heading=(r.metadata or {}).get("section_heading"),
            language=(r.metadata or {}).get("source_language"),
        )
        for r in chunk_results
    ]
    return AgentPassagesResponse(
        document_id=str(document_id),
        passages=passages,
        total=len(passages),
    )


@router.post("/ask_corpus", response_model=AgentAskResponse)
def ask_corpus(
    body: AgentAskRequest,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> AgentAskResponse:
    """Answer a question over the user's accessible corpus.

    Citations are restricted to documents the caller can access by virtue
    of the standard group filter applied to Qdrant, plus an explicit
    per-citation source-ACL re-check for defence in depth.
    """
    settings = request.app.state.settings

    with request.app.state.engine.begin() as connection:
        group_ids, is_admin = _resolve_effective_groups(request, user, connection)
        if not group_ids and not is_admin:
            raise HTTPException(
                status_code=403,
                detail="You do not belong to any groups with document access.",
            )

        # When document_id is supplied, enforce single-doc access up front.
        document_uuid: UUID | None = None
        if body.document_id is not None:
            try:
                document_uuid = UUID(body.document_id)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail="Invalid document_id") from exc
            auth_repo = AuthRepository(connection)
            assert_doc_access(document_uuid, user, auth_repo)

        encoder = build_encoder(settings)
        qdrant_client = request.app.state.qdrant_client or QdrantSearchClient(
            url=settings.qdrant_url, dimension=encoder.dimension
        )

        prompt_row = (
            connection.execute(
                sa.text("SELECT value FROM system_config WHERE key = :key"),
                {"key": "llm.qa_system_prompt"},
            )
            .mappings()
            .first()
        )
        system_prompt = str(prompt_row["value"]) if prompt_row else None

        rag = RagService(
            qdrant_client=qdrant_client,
            encoder=encoder,
            ollama_client=request.app.state.llm_provider,
            connection=connection,
            system_prompt=system_prompt,
            max_chunks=settings.rag_max_chunks,
            max_tokens_context=settings.rag_max_tokens_context,
            score_threshold=settings.rag_score_threshold,
            meili_provider=request.app.state.meili_provider,
            reranker=NoOpReranker(),
        )

        try:
            answer = rag.answer(
                question=body.question,
                group_ids=group_ids,
                top_k=body.top_k,
                document_id=str(document_uuid) if document_uuid else None,
                allow_all=is_admin,
            )
        except Exception as exc:
            logger.warning(
                "Agent ask_corpus degraded route=/api/agent/v1/ask_corpus "
                "error_type=%s correlation_id=%s",
                exc.__class__.__name__,
                get_correlation_id(),
            )
            raise HTTPException(
                status_code=503,
                detail="Could not search the document collection right now.",
            ) from exc

        # Defence in depth: drop any citation whose source the caller cannot
        # actually access.  RagService already filters via Qdrant group_ids,
        # but a misconfigured payload should never produce a leak.
        auth_repo = AuthRepository(connection)
        doc_repo = DocumentRepository(connection)
        safe_citations: list[AgentAskCitation] = []
        for c in answer.citations:
            try:
                cited_uuid = UUID(c.document_id)
            except ValueError:
                continue
            doc = doc_repo.get_by_id(cited_uuid)
            if doc is None:
                continue
            if not is_admin and not auth_repo.user_can_access_source(user, doc.source_id):  # type: ignore[arg-type]
                continue
            safe_citations.append(
                AgentAskCitation(
                    document_id=c.document_id,
                    doc_title=c.doc_title,
                    chunk_text=c.chunk_text,
                    score=c.score,
                    chunk_index=c.chunk_index,
                    source_id=c.source_id,
                    page_number=c.page_number,
                    section_heading=c.section_heading,
                    language=c.language,
                )
            )

        return AgentAskResponse(
            question=answer.question,
            answer=answer.answer,
            citations=safe_citations,
            model=answer.model,
        )


@router.get("/get_related_documents", response_model=AgentRelatedResponse)
def get_related_documents(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
    document_id: Annotated[UUID, Query(...)],
) -> AgentRelatedResponse:
    """Return related documents the caller can access."""
    settings = request.app.state.settings
    with request.app.state.engine.begin() as connection:
        require_related_docs_enabled(connection, settings)
        auth_repo = AuthRepository(connection)
        assert_doc_access(document_id, user, auth_repo)

        doc_repo = DocumentRepository(connection)
        doc = doc_repo.get_by_id(document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")

        group_ids, is_admin = _resolve_effective_groups(request, user, connection)
        if not group_ids and not is_admin:
            return AgentRelatedResponse(document_id=str(document_id), related=[])

        encoder = build_encoder(settings)
        qdrant_client = request.app.state.qdrant_client or QdrantSearchClient(
            url=settings.qdrant_url, dimension=encoder.dimension
        )
        service = RelatedService(
            repository=RelatedRepository(connection),
            qdrant_client=qdrant_client,
            encoder=encoder,
            job_repo=PipelineJobRepository(connection),
        )
        try:
            raw_related = service.related_documents(
                doc=doc,
                group_ids=group_ids,
                limit=related_docs_limit(connection),
                allow_all=is_admin,
            )
        except Exception as exc:
            logger.warning(
                "Agent related documents degraded route=/api/agent/v1/get_related_documents "
                "error_type=%s correlation_id=%s",
                exc.__class__.__name__,
                get_correlation_id(),
            )
            raw_related = []

        related = [
            AgentRelatedItem(
                document_id=str(r["document_id"]),
                title=r.get("title"),
                score=float(r.get("score") or 0.0),
                source=r.get("source"),
                relation_score=r.get("relation_score"),
                reasons=list(r.get("reasons") or []),
            )
            for r in raw_related
        ]
        return AgentRelatedResponse(document_id=str(document_id), related=related)


@router.get("/list_facets", response_model=AgentFacetsResponse)
def list_facets(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
    query: Annotated[str, Query(min_length=0, max_length=500)] = "",
) -> AgentFacetsResponse:
    """Return facet distributions over documents the caller can access."""
    with request.app.state.engine.begin() as connection:
        group_ids, is_admin = _resolve_effective_groups(request, user, connection)
        if not group_ids and not is_admin:
            return AgentFacetsResponse(facets={})

    if request.app.state.meili_provider is None:
        return AgentFacetsResponse(facets={})

    try:
        meili_query = DocumentSearchQuery(
            q=query,
            limit=1,
            filters=DocumentSearchFilters(),
            sort="relevance",
        )
        meili_results = request.app.state.meili_provider.search(query=meili_query, user=user)
    except Exception as exc:
        logger.warning(
            "Agent list_facets degraded route=/api/agent/v1/list_facets "
            "error_type=%s correlation_id=%s",
            exc.__class__.__name__,
            get_correlation_id(),
        )
        return AgentFacetsResponse(facets={})

    return AgentFacetsResponse(facets=meili_results.facets or {})

# Translation quality is not exposed directly on AgentSearchResultItem to keep
# the surface narrow; clients that need it can call ``get_document``.
