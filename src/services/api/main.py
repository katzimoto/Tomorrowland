from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal, cast
from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from services.alerts.models import SubscriptionCreateRequest, SubscriptionUpdateRequest
from services.alerts.repository import AlertRepository
from services.alerts.service import AlertMatcher
from services.annotations.models import AnnotationCreateRequest, AnnotationUpdateRequest
from services.annotations.repository import AnnotationRepository
from services.api.readiness import ReadinessChecker, ReadinessResponse
from services.auth.jwt import JwtService
from services.auth.ldap import LdapAuthenticator
from services.auth.models import LoginRequest, LoginResponse, TokenPayload, UserResponse
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from services.auth.service import AuthService
from services.comments.models import CommentCreateRequest, CommentUpdateRequest
from services.comments.repository import CommentRepository
from services.connectors.factory import build_connector, connector_types
from services.documents.models import DocumentRow, DocumentSource
from services.documents.repository import DocumentRepository, TranslationVersionRepository
from services.extraction.registry import ExtractorRegistry
from services.health import HealthResponse, health
from services.intelligence.ollama_client import OllamaClient
from services.intelligence.repository import IntelligenceRepository
from services.intelligence.worker import IntelligenceWorker
from services.permissions.enforcer import assert_doc_access, require_admin
from services.pipeline.worker import PipelineWorker
from services.preview.service import PreviewService
from services.rag.models import QuestionRequest
from services.rag.service import RagService
from services.related.repository import RelatedRepository
from services.related.service import RelatedService
from services.search.elastic import ElasticsearchSearchClient
from services.search.factory import build_encoder
from services.search.hybrid import SearchResult, merge_results
from services.search.qdrant import QdrantSearchClient
from services.translation.client import LibreTranslateClient
from shared.config import Settings
from shared.correlation import get_correlation_id
from shared.db import db_uuid, to_uuid
from shared.logging import log_extra
from shared.metrics import (
    MetricsRegistry,
    current_metrics,
    mime_family,
    reset_current_metrics,
    route_template_for_request,
    safe_label_value,
    set_current_metrics,
    status_class,
)
from shared.request_context import reset_request_id, set_request_id

AUTH_SCHEME = "Bearer "
logger = logging.getLogger(__name__)


def current_user(request: Request) -> TokenPayload:
    """Decode the bearer token for the current request."""
    authorization = request.headers.get("authorization")
    if authorization is None or not authorization.startswith(AUTH_SCHEME):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.removeprefix(AUTH_SCHEME)
    jwt_service = JwtService(secret=request.app.state.settings.jwt_secret)
    return jwt_service.decode(token)


def _fmt_dt(value: Any) -> str | None:
    """Format a datetime value (object or string) to ISO format."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    # value is a datetime object
    return str(value.isoformat())


def _parse_json(value: Any) -> Any:
    """Parse a JSON value from the database (string or dict)."""
    if value is None:
        return None
    if isinstance(value, str):
        return json.loads(value)
    return value


def _config_bool(value: Any, default: bool) -> bool:
    """Parse a runtime config value as a boolean."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _audit_log(
    connection: sa.Connection,
    user_id: UUID | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Write an audit log entry."""
    metrics = current_metrics()
    if metrics is not None:
        metrics.admin_actions_total.labels(
            safe_label_value(action), safe_label_value(resource_type)
        ).inc()
    connection.execute(
        sa.text(
            """
            INSERT INTO audit_log (id, user_id, action, resource_type, resource_id, details)
            VALUES (:id, :user_id, :action, :resource_type, :resource_id, :details)
            """
        ),
        {
            "id": uuid4().hex,
            "user_id": user_id.hex if user_id else None,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "details": json.dumps(details or {}),
        },
    )


def _subscription_response(row: dict[str, Any]) -> dict[str, Any]:
    """Serialize an alert subscription row."""
    return {
        "id": str(to_uuid(row["id"])),
        "user_id": str(to_uuid(row["user_id"])),
        "name": row["name"],
        "query": row["query"],
        "similarity_threshold": row["similarity_threshold"],
        "enabled": bool(row["enabled"]),
        "unread_count": int(row.get("unread_count") or 0),
        "last_notified": _fmt_dt(row["last_notified"]),
        "created_at": _fmt_dt(row["created_at"]),
        "updated_at": _fmt_dt(row["updated_at"]),
    }


def _notification_response(row: dict[str, Any]) -> dict[str, Any]:
    """Serialize an alert notification row."""
    return {
        "id": str(to_uuid(row["id"])),
        "subscription_id": str(to_uuid(row["subscription_id"])),
        "subscription_name": row["subscription_name"],
        "subscription_query": row["subscription_query"],
        "doc_id": str(to_uuid(row["doc_id"])),
        "doc_title": row["doc_title"],
        "similarity": row["similarity"],
        "read": bool(row["read"]),
        "created_at": _fmt_dt(row["created_at"]),
    }


class SearchRequest(BaseModel):
    """Search request body."""

    query: str
    mode: str = "hybrid"
    filters: dict[str, Any] = Field(default_factory=dict)
    top_k: int = Field(default=20, ge=1, le=100)
    page: int = 1
    page_size: int = Field(default=20, ge=1, le=100)


class SearchResultItem(BaseModel):
    """Single search result."""

    doc_id: str
    source_id: str
    external_id: str | None = None
    title: str | None = None
    snippet: str | None = None
    source: str
    source_label: str
    mime_type: str
    tags: list[str] = Field(default_factory=list)
    translation_quality: str | None = None
    score: float
    updated_at: str
    indexed_at: str


class SearchResponse(BaseModel):
    """Search response."""

    results: list[SearchResultItem]
    total: int
    query: str = ""


class PreviewResponse(BaseModel):
    """Document preview response."""

    doc_id: str
    title: str | None = None
    mime_type: str
    translation_quality: str | None = None
    metadata: dict[str, Any]
    snippet: str
    view_count: int


class CreateUserRequest(BaseModel):
    """Admin create user request."""

    email: str
    password: str
    display_name: str | None = None
    is_admin: bool = False
    group_names: list[str] = Field(default_factory=list)


class CreateGroupRequest(BaseModel):
    """Admin create group request."""

    name: str


class CreateSourceRequest(BaseModel):
    """Admin create source request."""

    name: str
    type: Literal["folder", "nifi", "confluence", "jira", "smb"] = "folder"
    path: str | None = None
    source_language: str | None = "en"
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class GrantPermissionRequest(BaseModel):
    """Admin grant permission request."""

    group_id: str


class UpdateConfigRequest(BaseModel):
    """Admin update config request."""

    value: Any


class DlqItem(BaseModel):
    """DLQ item response."""

    id: str
    doc_id: str | None
    error_message: str
    retry_count: int
    status: str
    created_at: str | None = None
    updated_at: str | None = None


def create_app(
    engine: Engine,
    settings: Settings | None = None,
    ldap_authenticator: LdapAuthenticator | None = None,
    translator: LibreTranslateClient | None = None,
    es_client: ElasticsearchSearchClient | None = None,
    qdrant_client: QdrantSearchClient | None = None,
    ollama_client: OllamaClient | None = None,
) -> FastAPI:
    """Create the API app with Phase 02 auth routes."""
    app = FastAPI(title="Tomorrowland API")
    app.state.engine = engine
    app.state.settings = settings or Settings()
    app.state.metrics = MetricsRegistry(
        version=app.state.settings.app_version,
        commit=app.state.settings.build_commit,
        environment=app.state.settings.app_env,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app.state.settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.ldap_authenticator = ldap_authenticator
    app.state.translator = translator
    app.state.es_client = es_client
    app.state.qdrant_client = qdrant_client
    app.state.ollama_client = ollama_client
    app.state.readiness_checker = ReadinessChecker(
        engine=app.state.engine,
        settings=app.state.settings,
        metrics=app.state.metrics,
    )

    @contextmanager
    def repository_context() -> Iterator[AuthRepository]:
        with app.state.engine.begin() as connection:
            yield AuthRepository(connection)

    def jwt_service() -> JwtService:
        return JwtService(secret=app.state.settings.jwt_secret)

    @app.middleware("http")
    async def request_observability_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Attach request IDs, record metrics, and emit structured JSON logs."""
        request_id = request.headers.get("x-request-id") or str(uuid4())
        token = set_request_id(request_id)
        metrics_token = set_current_metrics(request.app.state.metrics)
        start = time.perf_counter()
        route = "__unknown__"
        try:
            response = await call_next(request)
            route = route_template_for_request(request)
            elapsed = time.perf_counter() - start
            metrics: MetricsRegistry = request.app.state.metrics
            metrics.http_request_duration_seconds.labels(request.method, route).observe(elapsed)
            metrics.http_requests_total.labels(
                request.method, route, status_class(response.status_code)
            ).inc()
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "http_request_completed",
                extra=log_extra(
                    {
                        "component": "api",
                        "outcome": "success",
                        "method": request.method,
                        "route": route,
                        "status_code": response.status_code,
                        "duration_ms": round(elapsed * 1000),
                    }
                ),
            )
            return response
        except Exception as exc:
            route = route_template_for_request(request)
            elapsed = time.perf_counter() - start
            metrics = request.app.state.metrics
            error_type = exc.__class__.__name__
            metrics.http_request_duration_seconds.labels(request.method, route).observe(elapsed)
            metrics.http_requests_total.labels(request.method, route, "5xx").inc()
            metrics.http_exceptions_total.labels(route, error_type).inc()
            logger.error(
                "http_request_failed",
                exc_info=True,
                extra=log_extra(
                    {
                        "component": "api",
                        "outcome": "failure",
                        "method": request.method,
                        "route": route,
                        "status_code": 500,
                        "duration_ms": round(elapsed * 1000),
                        "error_type": error_type,
                    }
                ),
            )
            return Response(
                content="Internal Server Error",
                status_code=500,
                media_type="text/plain",
                headers={"X-Request-ID": request_id},
            )
        finally:
            reset_current_metrics(metrics_token)
            reset_request_id(token)

    def require_subscriptions_enabled(connection: sa.Connection) -> None:
        """Raise 404 when subscriptions are disabled."""
        if not app.state.settings.feature_subscriptions:
            raise HTTPException(status_code=404, detail="Subscriptions are disabled")
        row = (
            connection.execute(
                sa.text("SELECT value FROM system_config WHERE key = :key"),
                {"key": "feature.subscriptions"},
            )
            .mappings()
            .first()
        )
        if row and not _config_bool(row["value"], default=True):
            raise HTTPException(status_code=404, detail="Subscriptions are disabled")

    def require_related_docs_enabled(connection: sa.Connection) -> None:
        """Raise 404 when related documents are disabled."""
        if not app.state.settings.feature_related_docs:
            raise HTTPException(status_code=404, detail="Related documents are disabled")
        row = (
            connection.execute(
                sa.text("SELECT value FROM system_config WHERE key = :key"),
                {"key": "feature.related_docs"},
            )
            .mappings()
            .first()
        )
        if row and not _config_bool(row["value"], default=True):
            raise HTTPException(status_code=404, detail="Related documents are disabled")

    def require_expertise_enabled(connection: sa.Connection) -> None:
        """Raise 404 when expertise map is disabled."""
        if not app.state.settings.feature_expertise_map:
            raise HTTPException(status_code=404, detail="Expertise map is disabled")
        row = (
            connection.execute(
                sa.text("SELECT value FROM system_config WHERE key = :key"),
                {"key": "feature.expertise_map"},
            )
            .mappings()
            .first()
        )
        if row and not _config_bool(row["value"], default=True):
            raise HTTPException(status_code=404, detail="Expertise map is disabled")

    def related_docs_limit(connection: sa.Connection) -> int:
        """Read related document limit from runtime config."""
        row = (
            connection.execute(
                sa.text("SELECT value FROM system_config WHERE key = :key"),
                {"key": "search.related_docs_limit"},
            )
            .mappings()
            .first()
        )
        if row is None:
            return 5
        return int(row["value"])

    def default_alert_threshold(connection: sa.Connection) -> float:
        """Read the default alert similarity threshold from runtime config."""
        row = (
            connection.execute(
                sa.text("SELECT value FROM system_config WHERE key = :key"),
                {"key": "alerts.similarity_threshold"},
            )
            .mappings()
            .first()
        )
        if row is None:
            return 0.75
        return float(row["value"])

    def alerts_check_on_ingest(connection: sa.Connection) -> bool:
        """Return whether ingest-time alert matching is enabled."""
        row = (
            connection.execute(
                sa.text("SELECT value FROM system_config WHERE key = :key"),
                {"key": "alerts.check_on_ingest"},
            )
            .mappings()
            .first()
        )
        return _config_bool(row["value"], default=True) if row else True

    @app.post("/auth/login", response_model=LoginResponse)
    def login(request: LoginRequest) -> LoginResponse:
        with repository_context() as repository:
            service = AuthService(
                repository=repository,
                jwt_service=jwt_service(),
                auth_provider=app.state.settings.auth_provider,
                ldap_authenticator=app.state.ldap_authenticator,
                metrics=app.state.metrics,
            )
            return service.authenticate(request.email, request.password)

    @app.get("/health")
    def app_health() -> HealthResponse:
        return health("api")

    @app.get("/admin/readiness", response_model=None)
    def admin_readiness(user: Annotated[TokenPayload, Depends(current_user)]) -> ReadinessResponse:
        require_admin(user)
        readiness: ReadinessResponse = app.state.readiness_checker.check()
        return readiness

    @app.get("/metrics")
    def metrics() -> Response:
        try:
            with app.state.engine.begin() as connection:
                pending = connection.execute(
                    sa.text("SELECT COUNT(*) FROM dlq WHERE status = 'pending'")
                ).scalar_one_or_none()
        except sa.exc.SQLAlchemyError:
            pending = 0
        app.state.metrics.dlq_pending.set(float(pending or 0))
        return Response(
            content=generate_latest(app.state.metrics.registry),
            media_type=CONTENT_TYPE_LATEST,
        )

    @app.post("/auth/logout")
    def logout(_: Annotated[TokenPayload, Depends(current_user)]) -> dict[str, bool]:
        return {"ok": True}

    @app.get("/auth/me", response_model=UserResponse)
    def me(user: Annotated[TokenPayload, Depends(current_user)]) -> UserResponse:
        return UserResponse.from_token(user)

    @app.get("/admin/health")
    def admin_health(user: Annotated[TokenPayload, Depends(current_user)]) -> dict[str, str]:
        require_admin(user)
        return {"status": "ok"}

    @app.post("/admin/ingestion/{source_id}/sync-now")
    def sync_now(
        source_id: UUID,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> dict[str, Any]:
        require_admin(user)

        with app.state.engine.begin() as connection:
            source_row = (
                connection.execute(
                    sa.text("SELECT * FROM ingestion_sources WHERE id = :id"),
                    {"id": source_id.hex},
                )
                .mappings()
                .first()
            )
            if source_row is None:
                raise HTTPException(status_code=404, detail="Source not found")

            try:
                connector = build_connector(source_row)
                connector.validate()
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

            doc_repo = DocumentRepository(connection)
            translator = app.state.translator or LibreTranslateClient(
                base_url=app.state.settings.libretranslate_url
            )
            es_client = app.state.es_client or ElasticsearchSearchClient(
                hosts=[app.state.settings.elastic_url]
            )
            qdrant_client = app.state.qdrant_client or QdrantSearchClient(
                url=app.state.settings.qdrant_url
            )

            worker = PipelineWorker(
                document_repository=doc_repo,
                extractor_registry=ExtractorRegistry(),
                translator=translator,
                encoder=build_encoder(app.state.settings),
                es_client=es_client,
                qdrant_client=qdrant_client,
                alert_matcher=(
                    AlertMatcher(
                        repository=AlertRepository(connection),
                        encoder=build_encoder(app.state.settings),
                        default_threshold=default_alert_threshold(connection),
                    )
                    if alerts_check_on_ingest(connection)
                    else None
                ),
                metrics=app.state.metrics,
            )

            source_language = source_row.get("source_language")
            results: dict[str, int] = {"indexed": 0, "skipped": 0, "failed": 0}

            def _record_sync_dlq(
                doc_id: UUID | None,
                message: str,
            ) -> None:
                connection.execute(
                    sa.text(
                        """
                        INSERT INTO dlq (id, doc_id, error_message, status)
                        VALUES (:id, :doc_id, :error_message, 'pending')
                        """
                    ),
                    {
                        "id": db_uuid(uuid4()),
                        "doc_id": db_uuid(doc_id) if doc_id is not None else None,
                        "error_message": message,
                    },
                )

            connector_type = str(source_row["type"])
            try:
                for item in connector.fetch_documents():
                    doc_id_for_dlq: UUID | None = None
                    try:
                        app.state.metrics.ingestion_documents_total.labels(
                            safe_label_value(connector_type), "discovered"
                        ).inc()

                        doc = doc_repo.create(
                            source_id=source_id,
                            external_id=item.external_id,
                            source=cast("DocumentSource", source_row["type"]),
                            mime_type=item.mime_type,
                            path=item.path,
                            title=item.title,
                            source_language=item.source_language or source_language,
                            sha256=item.sha256,
                            metadata=item.metadata,
                        )
                        if doc is None:
                            results["skipped"] += 1
                            app.state.metrics.ingestion_documents_total.labels(
                                safe_label_value(connector_type), "skipped"
                            ).inc()
                            continue

                        doc_id_for_dlq = doc.id
                        try:
                            worker.process_document(doc.id, pre_extracted_text=item.text_content)
                            results["indexed"] += 1
                            app.state.metrics.ingestion_documents_total.labels(
                                safe_label_value(connector_type), "success"
                            ).inc()
                        except Exception:
                            results["failed"] += 1
                            app.state.metrics.ingestion_documents_total.labels(
                                safe_label_value(connector_type), "failure"
                            ).inc()
                            _record_sync_dlq(doc.id, "Document processing failed")
                    except Exception:
                        results["failed"] += 1
                        app.state.metrics.ingestion_documents_total.labels(
                            safe_label_value(connector_type), "failure"
                        ).inc()
                        _record_sync_dlq(doc_id_for_dlq, "Document creation or discovery failed")
                    finally:
                        if connector_type == "smb" and item.path:
                            with suppress(OSError):
                                os.unlink(item.path)
            except Exception:
                raise HTTPException(status_code=502, detail="Source enumeration failed") from None

            sync_outcome = "failure" if results["failed"] else "success"
            app.state.metrics.ingestion_syncs_total.labels(
                safe_label_value(connector_type), sync_outcome
            ).inc()
            return results

    @app.post("/search", response_model=SearchResponse)
    def search(
        request: SearchRequest,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> SearchResponse:
        metrics_start = time.perf_counter()
        group_ids = [str(g) for g in user.groups]
        if not group_ids:
            app.state.metrics.search_requests_total.labels("hybrid", "success").inc()
            app.state.metrics.search_results_count.labels("hybrid").observe(0)
            app.state.metrics.search_duration_seconds.labels("hybrid").observe(
                time.perf_counter() - metrics_start
            )
            return SearchResponse(results=[], total=0)

        es_client = app.state.es_client or ElasticsearchSearchClient(
            hosts=[app.state.settings.elastic_url]
        )
        qdrant_client = app.state.qdrant_client or QdrantSearchClient(
            url=app.state.settings.qdrant_url
        )
        encoder = build_encoder(app.state.settings)

        backend_start = time.perf_counter()
        bm25_results = es_client.search(request.query, group_ids=group_ids, size=50)
        app.state.metrics.search_backend_duration_seconds.labels("elasticsearch", "search").observe(
            time.perf_counter() - backend_start
        )

        vector_results: list[SearchResult] = []
        try:
            query_vector = encoder.encode(request.query)
            backend_start = time.perf_counter()
            vector_results = qdrant_client.search(
                vector=query_vector, group_ids=group_ids, limit=50
            )
            app.state.metrics.search_backend_duration_seconds.labels("qdrant", "search").observe(
                time.perf_counter() - backend_start
            )
        except Exception as exc:
            logger.warning(
                "Vector search degraded route=/search stage=vector_search "
                "error_type=%s correlation_id=%s",
                exc.__class__.__name__,
                get_correlation_id(),
            )
            app.state.metrics.search_requests_total.labels("hybrid", "degraded").inc()

        # TODO: read weights from system_config in Phase 04
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

        start = (request.page - 1) * request.page_size
        end = start + request.page_size
        page = merged[start:end]

        # Enrich page with document metadata from the database
        doc_ids: list[UUID] = []
        for r in page:
            with suppress(ValueError):
                doc_ids.append(UUID(r.doc_id))

        docs: dict[str, DocumentRow] = {}
        if doc_ids:
            with app.state.engine.begin() as connection:
                doc_repo = DocumentRepository(connection)
                for doc in doc_repo.list_by_ids(doc_ids):
                    docs[str(doc.id)] = doc

        now = datetime.now(UTC).isoformat()
        results: list[SearchResultItem] = []
        for r in page:
            doc_row = docs.get(r.doc_id)
            if doc_row is None:
                results.append(
                    SearchResultItem(
                        doc_id=r.doc_id,
                        source_id="",
                        external_id=None,
                        title=r.title,
                        snippet=r.chunk_text or "",
                        source="unknown",
                        source_label="Unknown",
                        mime_type="application/octet-stream",
                        tags=[],
                        translation_quality=None,
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
            results.append(
                SearchResultItem(
                    doc_id=r.doc_id,
                    source_id=str(doc_row.source_id),
                    external_id=doc_row.external_id or None,
                    title=r.title or doc_row.title,
                    snippet=r.chunk_text or doc_row.title or "",
                    source=doc_row.source,
                    source_label=doc_row.source.capitalize(),
                    mime_type=doc_row.mime_type,
                    tags=list(tags),
                    translation_quality=doc_row.translation_quality,
                    score=r.score,
                    updated_at=_fmt_dt(doc_row.updated_at) or now,
                    indexed_at=_fmt_dt(doc_row.created_at) or now,
                )
            )

        if vector_results:
            app.state.metrics.search_requests_total.labels("hybrid", "success").inc()
        app.state.metrics.search_results_count.labels("hybrid").observe(len(merged))
        app.state.metrics.search_duration_seconds.labels("hybrid").observe(
            time.perf_counter() - metrics_start
        )
        return SearchResponse(
            results=results,
            total=len(merged),
            query=request.query,
        )

    @app.get("/preview/{doc_id}", response_model=PreviewResponse)
    def preview(
        doc_id: UUID,
        user: Annotated[TokenPayload, Depends(current_user)],
        translation_version_id: UUID | None = None,
    ) -> PreviewResponse:
        with app.state.engine.begin() as connection:
            auth_repo = AuthRepository(connection)
            assert_doc_access(doc_id, user, auth_repo)

            preview_service = PreviewService(connection)
            result = preview_service.get_preview(
                doc_id, user.sub, translation_version_id=translation_version_id
            )
            if not result:
                app.state.metrics.preview_requests_total.labels("unknown", "failure").inc()
                raise HTTPException(status_code=404, detail="Document not found")

            app.state.metrics.preview_requests_total.labels(
                mime_family(result["mime_type"]), "success"
            ).inc()
            return PreviewResponse(
                doc_id=result["doc_id"],
                title=result["title"],
                mime_type=result["mime_type"],
                translation_quality=result["translation_quality"],
                metadata=result["metadata"],
                snippet=result["snippet"],
                view_count=result["view_count"],
            )

    @app.get("/me/activity")
    def me_activity(
        user: Annotated[TokenPayload, Depends(current_user)],
        skip: int = 0,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        with app.state.engine.begin() as connection:
            preview_service = PreviewService(connection)
            return preview_service.get_user_activity(user.sub, limit=limit, offset=skip)

    @app.post("/documents/{doc_id}/translate")
    def request_translation(
        doc_id: UUID,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> dict[str, Any]:
        with app.state.engine.begin() as connection:
            auth_repo = AuthRepository(connection)
            assert_doc_access(doc_id, user, auth_repo)

            doc_repo = DocumentRepository(connection)
            doc = doc_repo.get_by_id(doc_id)
            if doc is None:
                raise HTTPException(status_code=404, detail="Document not found")

            version_repo = TranslationVersionRepository(connection)
            existing = version_repo.find_pending_or_running(doc_id, doc.target_language)
            if existing:
                return {
                    "doc_id": str(doc_id),
                    "translation_version_id": str(existing["id"]),
                    "status": existing["status"],
                }

            version = version_repo.create_version(
                doc_id=doc_id,
                label=f"Manual {doc.target_language}",
                quality="high",
                request_type="manual",
                requested_by_id=user.sub,
                target_language=doc.target_language,
            )
            doc_repo.update_translation_quality(doc_id, "pending_high")

            return {
                "doc_id": str(doc_id),
                "translation_version_id": str(version["id"]),
                "status": version["status"],
            }

    @app.get("/documents/{doc_id}/translation-versions")
    def list_translation_versions(
        doc_id: UUID,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> list[dict[str, Any]]:
        with app.state.engine.begin() as connection:
            auth_repo = AuthRepository(connection)
            assert_doc_access(doc_id, user, auth_repo)

            version_repo = TranslationVersionRepository(connection)
            versions = version_repo.list_versions(doc_id)
            return [
                {
                    "version_id": str(v["id"]),
                    "version_number": v["version_number"],
                    "label": v["label"],
                    "quality": v["quality"],
                    "status": v["status"],
                    "target_language": v["target_language"],
                    "requested_at": _fmt_dt(v["requested_at"]),
                }
                for v in versions
            ]

    @app.get("/documents/{doc_id}/summary")
    def get_summary(
        doc_id: UUID,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> dict[str, Any]:
        with app.state.engine.begin() as connection:
            auth_repo = AuthRepository(connection)
            assert_doc_access(doc_id, user, auth_repo)

            intelligence_repo = IntelligenceRepository(connection)
            summary = intelligence_repo.get_summary(doc_id)
            if summary is None:
                raise HTTPException(status_code=404, detail="Summary not found")
            return {
                "doc_id": str(doc_id),
                "summary": summary["summary"],
                "model": summary["model"],
                "updated_at": _fmt_dt(summary["updated_at"]),
            }

    @app.get("/documents/{doc_id}/entities")
    def get_entities(
        doc_id: UUID,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> list[dict[str, Any]]:
        with app.state.engine.begin() as connection:
            auth_repo = AuthRepository(connection)
            assert_doc_access(doc_id, user, auth_repo)

            intelligence_repo = IntelligenceRepository(connection)
            entities = intelligence_repo.get_entities(doc_id)
            return [
                {
                    "id": str(e["id"]),
                    "name": e["name"],
                    "type": e["type"],
                    "frequency": e["frequency"],
                }
                for e in entities
            ]

    @app.get("/documents/{doc_id}/tags")
    def get_tags(
        doc_id: UUID,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> dict[str, Any]:
        with app.state.engine.begin() as connection:
            auth_repo = AuthRepository(connection)
            assert_doc_access(doc_id, user, auth_repo)

            intelligence_repo = IntelligenceRepository(connection)
            tags = intelligence_repo.get_tags(doc_id)
            return {"doc_id": str(doc_id), "tags": tags}

    @app.get("/documents/{doc_id}/related")
    def related_documents(
        doc_id: UUID,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> dict[str, Any]:
        with app.state.engine.begin() as connection:
            require_related_docs_enabled(connection)
            auth_repo = AuthRepository(connection)
            assert_doc_access(doc_id, user, auth_repo)

            doc_repo = DocumentRepository(connection)
            doc = doc_repo.get_by_id(doc_id)
            if doc is None:
                raise HTTPException(status_code=404, detail="Document not found")

            group_ids = [str(group_id) for group_id in user.groups]
            if not group_ids:
                return {"doc_id": str(doc_id), "related": []}

            qdrant_client = app.state.qdrant_client or QdrantSearchClient(
                url=app.state.settings.qdrant_url
            )
            service = RelatedService(
                repository=RelatedRepository(connection),
                qdrant_client=qdrant_client,
                encoder=build_encoder(app.state.settings),
            )
            try:
                related = service.related_documents(
                    doc=doc,
                    group_ids=group_ids,
                    limit=related_docs_limit(connection),
                )
            except Exception as exc:
                logger.warning(
                    "Related documents degraded route=/documents/{doc_id}/related "
                    "stage=vector_search error_type=%s correlation_id=%s",
                    exc.__class__.__name__,
                    get_correlation_id(),
                )
                related = []
            return {"doc_id": str(doc_id), "related": related}

    @app.get("/expertise")
    def expertise(
        user: Annotated[TokenPayload, Depends(current_user)],
        topic: Annotated[str, Query(min_length=1)],
    ) -> list[dict[str, Any]]:
        topic = topic.strip()
        if not topic:
            raise HTTPException(status_code=422, detail="Topic must not be empty")
        with app.state.engine.begin() as connection:
            require_expertise_enabled(connection)
            group_ids = [str(group_id) for group_id in user.groups]
            if not group_ids:
                return []
            qdrant_client = app.state.qdrant_client or QdrantSearchClient(
                url=app.state.settings.qdrant_url
            )
            service = RelatedService(
                repository=RelatedRepository(connection),
                qdrant_client=qdrant_client,
                encoder=build_encoder(app.state.settings),
            )
            try:
                return service.expertise(topic=topic, group_ids=group_ids)
            except Exception as exc:
                logger.warning(
                    "Expertise degraded route=/expertise stage=vector_search "
                    "error_type=%s correlation_id=%s",
                    exc.__class__.__name__,
                    get_correlation_id(),
                )
                return []

    @app.get("/documents/{doc_id}/comments")
    def list_comments(
        doc_id: UUID,
        user: Annotated[TokenPayload, Depends(current_user)],
        skip: int = 0,
        limit: int = 50,
        sort: Literal["newest", "oldest"] = "newest",
    ) -> dict[str, Any]:
        with app.state.engine.begin() as connection:
            auth_repo = AuthRepository(connection)
            assert_doc_access(doc_id, user, auth_repo)

            repo = CommentRepository(connection)
            comments = repo.list_comments(doc_id, skip=skip, limit=limit, sort=sort)
            total = repo.count_comments(doc_id)
            return {
                "doc_id": str(doc_id),
                "comments": [
                    {
                        "id": str(to_uuid(c["id"])),
                        "author_id": str(to_uuid(c["author_id"])),
                        "author_display_name": c["author_display_name"],
                        "body": c["body"],
                        "created_at": _fmt_dt(c["created_at"]),
                        "edited_at": _fmt_dt(c["edited_at"]),
                        "edited_by_id": (
                            str(to_uuid(c["edited_by_id"])) if c["edited_by_id"] else None
                        ),
                        "deleted_at": _fmt_dt(c["deleted_at"]),
                    }
                    for c in comments
                ],
                "total": total,
                "skip": skip,
                "limit": limit,
            }

    @app.post("/documents/{doc_id}/comments", status_code=201)
    def create_comment(
        doc_id: UUID,
        request: CommentCreateRequest,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> dict[str, Any]:
        with app.state.engine.begin() as connection:
            auth_repo = AuthRepository(connection)
            assert_doc_access(doc_id, user, auth_repo)

            repo = CommentRepository(connection)
            comment = repo.create(doc_id, user.sub, request.body)
            app.state.metrics.comments_total.labels("create", "success").inc()
            return {
                "id": str(to_uuid(comment["id"])),
                "doc_id": str(to_uuid(comment["doc_id"])),
                "author_id": str(to_uuid(comment["author_id"])),
                "body": comment["body"],
                "created_at": _fmt_dt(comment["created_at"]),
            }

    @app.patch("/documents/{doc_id}/comments/{comment_id}")
    def update_comment(
        doc_id: UUID,
        comment_id: UUID,
        request: CommentUpdateRequest,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> dict[str, Any]:
        with app.state.engine.begin() as connection:
            auth_repo = AuthRepository(connection)
            assert_doc_access(doc_id, user, auth_repo)

            repo = CommentRepository(connection)
            comment = repo.get_by_id(comment_id)
            if comment is None or comment["deleted_at"] is not None:
                raise HTTPException(status_code=404, detail="Comment not found")
            if not repo.can_edit(comment_id, user.sub, user.is_admin):
                raise HTTPException(status_code=403, detail="Cannot edit this comment")

            repo.update(comment_id, request.body, edited_by_id=user.sub)
            app.state.metrics.comments_total.labels("update", "success").inc()
            updated = repo.get_by_id(comment_id)
            if updated is None:
                raise HTTPException(status_code=404, detail="Comment not found")
            return {
                "id": str(to_uuid(updated["id"])),
                "author_id": str(to_uuid(updated["author_id"])),
                "author_display_name": updated["author_display_name"],
                "body": updated["body"],
                "created_at": _fmt_dt(updated["created_at"]),
                "edited_at": _fmt_dt(updated["edited_at"]),
                "edited_by_id": (
                    str(to_uuid(updated["edited_by_id"])) if updated["edited_by_id"] else None
                ),
            }

    @app.delete("/documents/{doc_id}/comments/{comment_id}", status_code=204)
    def delete_comment(
        doc_id: UUID,
        comment_id: UUID,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> None:
        with app.state.engine.begin() as connection:
            auth_repo = AuthRepository(connection)
            assert_doc_access(doc_id, user, auth_repo)

            repo = CommentRepository(connection)
            comment = repo.get_by_id(comment_id)
            if comment is None or comment["deleted_at"] is not None:
                raise HTTPException(status_code=404, detail="Comment not found")
            if not repo.can_delete(comment_id, user.sub, user.is_admin):
                raise HTTPException(status_code=403, detail="Cannot delete this comment")

            repo.soft_delete(comment_id, deleted_by_id=user.sub)
            app.state.metrics.comments_total.labels("delete", "success").inc()

    @app.get("/documents/{doc_id}/annotations")
    def list_annotations(
        doc_id: UUID,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> dict[str, Any]:
        with app.state.engine.begin() as connection:
            auth_repo = AuthRepository(connection)
            assert_doc_access(doc_id, user, auth_repo)

            repo = AnnotationRepository(connection)
            annotations = repo.list_annotations(doc_id, user.sub, is_admin=user.is_admin)
            return {
                "doc_id": str(doc_id),
                "annotations": [
                    {
                        "id": str(to_uuid(a["id"])),
                        "user_id": str(to_uuid(a["user_id"])),
                        "user_display_name": a["user_display_name"],
                        "text": a["text"],
                        "note": a["note"],
                        "position": _parse_json(a["position"]),
                        "is_private": bool(a["is_private"]),
                        "created_at": _fmt_dt(a["created_at"]),
                    }
                    for a in annotations
                ],
            }

    @app.post("/documents/{doc_id}/annotations", status_code=201)
    def create_annotation(
        doc_id: UUID,
        request: AnnotationCreateRequest,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> dict[str, Any]:
        with app.state.engine.begin() as connection:
            auth_repo = AuthRepository(connection)
            assert_doc_access(doc_id, user, auth_repo)

            repo = AnnotationRepository(connection)
            annotation = repo.create(
                doc_id=doc_id,
                user_id=user.sub,
                text=request.text,
                note=request.note,
                position=request.position,
                is_private=request.is_private,
            )
            visibility = "private" if request.is_private else "shared"
            app.state.metrics.annotations_total.labels("create", visibility, "success").inc()
            return {
                "id": str(to_uuid(annotation["id"])),
                "doc_id": str(to_uuid(annotation["doc_id"])),
                "user_id": str(to_uuid(annotation["user_id"])),
                "text": annotation["text"],
                "note": annotation["note"],
                "position": _parse_json(annotation["position"]),
                "is_private": bool(annotation["is_private"]),
                "created_at": _fmt_dt(annotation["created_at"]),
            }

    @app.put("/annotations/{annotation_id}")
    def update_annotation(
        annotation_id: UUID,
        request: AnnotationUpdateRequest,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> dict[str, Any]:
        with app.state.engine.begin() as connection:
            repo = AnnotationRepository(connection)
            annotation = repo.get_by_id(annotation_id)
            if annotation is None:
                raise HTTPException(status_code=404, detail="Annotation not found")

            # Verify doc access
            auth_repo = AuthRepository(connection)
            assert_doc_access(to_uuid(annotation["doc_id"]), user, auth_repo)

            if not repo.can_modify(annotation_id, user.sub, user.is_admin):
                raise HTTPException(status_code=403, detail="Cannot modify this annotation")

            repo.update(
                annotation_id,
                text=request.text,
                note=request.note,
                position=request.position,
                is_private=request.is_private,
            )
            visibility = "private" if request.is_private else "shared"
            app.state.metrics.annotations_total.labels("update", visibility, "success").inc()
            updated = repo.get_by_id(annotation_id)
            if updated is None:
                raise HTTPException(status_code=404, detail="Annotation not found")
            return {
                "id": str(to_uuid(updated["id"])),
                "user_id": str(to_uuid(updated["user_id"])),
                "user_display_name": updated["user_display_name"],
                "text": updated["text"],
                "note": updated["note"],
                "position": _parse_json(updated["position"]),
                "is_private": bool(updated["is_private"]),
                "created_at": _fmt_dt(updated["created_at"]),
                "updated_at": _fmt_dt(updated["updated_at"]),
            }

    @app.delete("/annotations/{annotation_id}", status_code=204)
    def delete_annotation(
        annotation_id: UUID,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> None:
        with app.state.engine.begin() as connection:
            repo = AnnotationRepository(connection)
            annotation = repo.get_by_id(annotation_id)
            if annotation is None:
                raise HTTPException(status_code=404, detail="Annotation not found")

            # Verify doc access
            auth_repo = AuthRepository(connection)
            assert_doc_access(to_uuid(annotation["doc_id"]), user, auth_repo)

            if not repo.can_modify(annotation_id, user.sub, user.is_admin):
                raise HTTPException(status_code=403, detail="Cannot delete this annotation")

            visibility = "private" if annotation["is_private"] else "shared"
            repo.delete(annotation_id)
            app.state.metrics.annotations_total.labels("delete", visibility, "success").inc()

    @app.get("/subscriptions")
    def list_subscriptions(
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> list[dict[str, Any]]:
        with app.state.engine.begin() as connection:
            require_subscriptions_enabled(connection)
            repo = AlertRepository(connection)
            return [_subscription_response(row) for row in repo.list_subscriptions(user.sub)]

    @app.post("/subscriptions", status_code=201)
    def create_subscription(
        request: SubscriptionCreateRequest,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> dict[str, Any]:
        with app.state.engine.begin() as connection:
            require_subscriptions_enabled(connection)
            repo = AlertRepository(connection)
            row = repo.create_subscription(
                user_id=user.sub,
                name=request.name,
                query=request.query,
                similarity_threshold=request.similarity_threshold,
                enabled=request.enabled,
            )
            app.state.metrics.subscriptions_total.labels("create", "success").inc()
            return _subscription_response(row)

    @app.put("/subscriptions/{subscription_id}")
    def update_subscription(
        subscription_id: UUID,
        request: SubscriptionUpdateRequest,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> dict[str, Any]:
        with app.state.engine.begin() as connection:
            require_subscriptions_enabled(connection)
            repo = AlertRepository(connection)
            subscription = repo.get_subscription(subscription_id)
            if subscription is None or to_uuid(subscription["user_id"]) != user.sub:
                raise HTTPException(status_code=404, detail="Subscription not found")
            updated = repo.update_subscription(
                subscription_id,
                name=request.name,
                query=request.query,
                similarity_threshold=request.similarity_threshold,
                enabled=request.enabled,
            )
            if updated is None:
                raise HTTPException(status_code=404, detail="Subscription not found")
            app.state.metrics.subscriptions_total.labels("update", "success").inc()
            return _subscription_response(updated)

    @app.delete("/subscriptions/{subscription_id}", status_code=204)
    def delete_subscription(
        subscription_id: UUID,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> None:
        with app.state.engine.begin() as connection:
            require_subscriptions_enabled(connection)
            repo = AlertRepository(connection)
            subscription = repo.get_subscription(subscription_id)
            if subscription is None or to_uuid(subscription["user_id"]) != user.sub:
                raise HTTPException(status_code=404, detail="Subscription not found")
            repo.delete_subscription(subscription_id)
            app.state.metrics.subscriptions_total.labels("delete", "success").inc()

    @app.get("/notifications")
    def list_notifications(
        user: Annotated[TokenPayload, Depends(current_user)],
        unread_only: bool = True,
    ) -> list[dict[str, Any]]:
        with app.state.engine.begin() as connection:
            require_subscriptions_enabled(connection)
            repo = AlertRepository(connection)
            return [
                _notification_response(row)
                for row in repo.list_notifications(user.sub, unread_only=unread_only)
            ]

    @app.put("/notifications/{notification_id}/read")
    def mark_notification_read(
        notification_id: UUID,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> dict[str, Any]:
        with app.state.engine.begin() as connection:
            require_subscriptions_enabled(connection)
            repo = AlertRepository(connection)
            notification = repo.get_notification(notification_id)
            if notification is None or to_uuid(notification["user_id"]) != user.sub:
                raise HTTPException(status_code=404, detail="Notification not found")
            updated = repo.mark_notification_read(notification_id)
            if updated is None:
                raise HTTPException(status_code=404, detail="Notification not found")
            app.state.metrics.notifications_total.labels("read", "success").inc()
            return {
                "id": str(to_uuid(updated["id"])),
                "read": bool(updated["read"]),
            }

    @app.post("/admin/alerts/{doc_id}/trigger")
    def trigger_alert_matching(
        doc_id: UUID,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> dict[str, Any]:
        require_admin(user)
        with app.state.engine.begin() as connection:
            require_subscriptions_enabled(connection)
            doc_repo = DocumentRepository(connection)
            doc = doc_repo.get_by_id(doc_id)
            if doc is None or doc.path is None:
                raise HTTPException(status_code=404, detail="Document not found")

            content = ExtractorRegistry().extract(Path(doc.path), doc.mime_type)
            matcher = AlertMatcher(
                repository=AlertRepository(connection),
                encoder=build_encoder(app.state.settings),
                default_threshold=default_alert_threshold(connection),
            )
            created = matcher.match_document(doc, content)
            return {"doc_id": str(doc_id), "notifications_created": created}

    @app.post("/qa")
    def qa(
        request: QuestionRequest,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> dict[str, Any]:
        if not app.state.settings.feature_rag_qa:
            raise HTTPException(status_code=404, detail="RAG Q&A is disabled")

        group_ids = [str(g) for g in user.groups]
        if not group_ids:
            return {
                "question": request.question,
                "answer": "You do not belong to any groups with document access.",
                "citations": [],
                "model": "",
            }

        with app.state.engine.begin() as connection:
            flag_row = (
                connection.execute(
                    sa.text("SELECT value FROM system_config WHERE key = :key"),
                    {"key": "feature.rag_qa"},
                )
                .mappings()
                .first()
            )
            if flag_row and not _config_bool(flag_row["value"], default=True):
                raise HTTPException(status_code=404, detail="RAG Q&A is disabled")

            qdrant_client = app.state.qdrant_client or QdrantSearchClient(
                url=app.state.settings.qdrant_url
            )
            encoder = build_encoder(app.state.settings)
            ollama_client = app.state.ollama_client or OllamaClient(
                base_url=app.state.settings.ollama_url,
                model=app.state.settings.ollama_model,
            )

            # Read system prompt from config
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
                ollama_client=ollama_client,
                connection=connection,
                system_prompt=system_prompt,
            )
            try:
                result = rag.answer(
                    question=request.question,
                    group_ids=group_ids,
                    top_k=request.top_k,
                )
            except Exception as exc:
                logger.warning(
                    "RAG Q&A degraded route=/qa stage=retrieval error_type=%s correlation_id=%s",
                    exc.__class__.__name__,
                    get_correlation_id(),
                )
                return {
                    "question": request.question,
                    "answer": (
                        "I could not search the document collection right now. "
                        "Please try again later."
                    ),
                    "citations": [],
                    "model": "",
                }
            return {
                "question": result.question,
                "answer": result.answer,
                "citations": [
                    {
                        "doc_id": c.doc_id,
                        "doc_title": c.doc_title,
                        "chunk_text": c.chunk_text,
                        "score": c.score,
                    }
                    for c in result.citations
                ],
                "model": result.model,
            }

    @app.post("/admin/intelligence/{doc_id}/trigger")
    def trigger_intelligence(
        doc_id: UUID,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> dict[str, Any]:
        require_admin(user)
        with app.state.engine.begin() as connection:
            doc_repo = DocumentRepository(connection)
            doc = doc_repo.get_by_id(doc_id)
            if doc is None or doc.path is None:
                raise HTTPException(status_code=404, detail="Document not found")

            # Extract text for intelligence
            from services.extraction.registry import ExtractorRegistry

            extractor = ExtractorRegistry()
            text = extractor.extract(Path(doc.path), doc.mime_type)

            intelligence_repo = IntelligenceRepository(connection)
            ollama_client = OllamaClient(
                base_url=app.state.settings.ollama_url,
                model=app.state.settings.ollama_model,
            )
            es_client = app.state.es_client or ElasticsearchSearchClient(
                hosts=[app.state.settings.elastic_url]
            )
            worker = IntelligenceWorker(
                repository=intelligence_repo,
                ollama_client=ollama_client,
                es_client=es_client,
            )
            worker.process_document(doc_id, text)

            return {"doc_id": str(doc_id), "triggered": True}

    @app.get("/admin/enrichment-queue")
    def enrichment_queue(
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> list[dict[str, Any]]:
        require_admin(user)
        with app.state.engine.begin() as connection:
            doc_repo = DocumentRepository(connection)
            pending = doc_repo.list_pending_enrichment()
            return [
                {
                    "doc_id": str(doc.id),
                    "title": doc.title,
                    "mime_type": doc.mime_type,
                    "status": doc.status,
                }
                for doc in pending
            ]

    @app.get("/download/{doc_id}")
    def download(
        doc_id: UUID,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> StreamingResponse:
        with app.state.engine.begin() as connection:
            auth_repo = AuthRepository(connection)
            assert_doc_access(doc_id, user, auth_repo)

            doc_repo = DocumentRepository(connection)
            doc = doc_repo.get_by_id(doc_id)
            if doc is None or doc.path is None:
                app.state.metrics.download_requests_total.labels("failure").inc()
                raise HTTPException(status_code=404, detail="Document not found")

        files_root = app.state.settings.files_root.resolve()
        target = Path(doc.path).resolve()
        if not target.is_relative_to(files_root):
            app.state.metrics.download_requests_total.labels("failure").inc()
            raise HTTPException(status_code=400, detail="Invalid file path")
        app.state.metrics.download_requests_total.labels("success").inc()

        def file_iterator() -> Iterator[bytes]:
            with target.open("rb") as f:
                while chunk := f.read(8192):
                    yield chunk

        return StreamingResponse(
            file_iterator(),
            media_type=doc.mime_type,
            headers={"Content-Disposition": f'attachment; filename="{target.name}"'},
        )

    # Admin endpoints

    @app.get("/admin/users")
    def admin_list_users(
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> list[dict[str, Any]]:
        require_admin(user)
        with app.state.engine.begin() as connection:
            rows = connection.execute(
                sa.text(
                    """
                    SELECT id, email, display_name, auth_source, is_admin, created_at
                    FROM users ORDER BY created_at DESC
                    """
                )
            ).mappings()
            return [
                {
                    "id": str(to_uuid(row["id"])),
                    "email": row["email"],
                    "display_name": row["display_name"],
                    "auth_source": row["auth_source"],
                    "is_admin": row["is_admin"],
                    "created_at": _fmt_dt(row["created_at"]),
                }
                for row in rows
            ]

    @app.post("/admin/users", status_code=201)
    def admin_create_user(
        request: CreateUserRequest,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> dict[str, Any]:
        require_admin(user)
        with app.state.engine.begin() as connection:
            auth_repo = AuthRepository(connection)
            identity = auth_repo.create_local_user(
                email=request.email,
                password_hash=hash_password(request.password),
                display_name=request.display_name,
                is_admin=request.is_admin,
                group_names=request.group_names,
            )
            _audit_log(
                connection,
                user.sub,
                "create",
                "user",
                str(identity.id),
                {"email": identity.email},
            )
            return {
                "id": str(identity.id),
                "email": identity.email,
                "display_name": identity.display_name,
                "is_admin": identity.is_admin,
            }

    @app.delete("/admin/users/{user_id}", status_code=204)
    def admin_delete_user(
        user_id: UUID,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> None:
        require_admin(user)
        if user_id == user.sub:
            raise HTTPException(status_code=400, detail="Cannot delete yourself")
        with app.state.engine.begin() as connection:
            result = connection.execute(
                sa.text("DELETE FROM users WHERE id = :id"),
                {"id": user_id.hex},
            )
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="User not found")
            _audit_log(connection, user.sub, "delete", "user", str(user_id))

    @app.get("/admin/groups")
    def admin_list_groups(
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> list[dict[str, Any]]:
        require_admin(user)
        with app.state.engine.begin() as connection:
            rows = connection.execute(
                sa.text("SELECT id, name FROM groups ORDER BY name")
            ).mappings()
            return [{"id": str(to_uuid(row["id"])), "name": row["name"]} for row in rows]

    @app.post("/admin/groups", status_code=201)
    def admin_create_group(
        request: CreateGroupRequest,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> dict[str, Any]:
        require_admin(user)
        with app.state.engine.begin() as connection:
            auth_repo = AuthRepository(connection)
            group_id = auth_repo.ensure_group(request.name)
            _audit_log(connection, user.sub, "create", "group", str(group_id))
            return {"id": str(group_id), "name": request.name}

    @app.get("/admin/connector-types")
    def admin_connector_types(
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> list[dict[str, Any]]:
        require_admin(user)
        return connector_types()

    @app.get("/admin/sources")
    def admin_list_sources(
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> list[dict[str, Any]]:
        require_admin(user)
        with app.state.engine.begin() as connection:
            rows = connection.execute(
                sa.text(
                    """
                    SELECT id, name, type, path, source_language, enabled, created_at
                    FROM ingestion_sources ORDER BY created_at DESC
                    """
                )
            ).mappings()
            return [
                {
                    "id": str(to_uuid(row["id"])),
                    "name": row["name"],
                    "type": row["type"],
                    "path": row["path"],
                    "source_language": row["source_language"],
                    "enabled": row["enabled"],
                    "created_at": _fmt_dt(row["created_at"]),
                }
                for row in rows
            ]

    @app.post("/admin/sources", status_code=201)
    def admin_create_source(
        request: CreateSourceRequest,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> dict[str, Any]:
        require_admin(user)
        with app.state.engine.begin() as connection:
            source_id = uuid4()
            connection.execute(
                sa.text(
                    """
                    INSERT INTO ingestion_sources
                        (id, name, type, path, source_language, enabled, config)
                    VALUES
                        (:id, :name, :type, :path, :source_language, :enabled, :config)
                    """
                ),
                {
                    "id": source_id.hex,
                    "name": request.name,
                    "type": request.type,
                    "path": request.path,
                    "source_language": request.source_language,
                    "enabled": request.enabled,
                    "config": json.dumps(request.config),
                },
            )
            _audit_log(
                connection,
                user.sub,
                "create",
                "source",
                str(source_id),
                {"name": request.name},
            )
            return {
                "id": str(source_id),
                "name": request.name,
                "type": request.type,
                "path": request.path,
                "source_language": request.source_language,
                "enabled": request.enabled,
                "config": request.config,
            }

    @app.post("/admin/sources/{source_id}/permissions", status_code=201)
    def admin_grant_permission(
        source_id: UUID,
        request: GrantPermissionRequest,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> dict[str, Any]:
        require_admin(user)
        group_id = UUID(request.group_id)
        with app.state.engine.begin() as connection:
            auth_repo = AuthRepository(connection)
            auth_repo.grant_source_to_group(source_id, group_id)
            _audit_log(
                connection,
                user.sub,
                "grant",
                "permission",
                str(source_id),
                {"group_id": str(group_id)},
            )
            return {"source_id": str(source_id), "group_id": str(group_id)}

    @app.delete("/admin/sources/{source_id}/permissions/{group_id}", status_code=204)
    def admin_revoke_permission(
        source_id: UUID,
        group_id: UUID,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> None:
        require_admin(user)
        with app.state.engine.begin() as connection:
            connection.execute(
                sa.text(
                    """
                    DELETE FROM source_permissions
                    WHERE source_id = :source_id AND group_id = :group_id
                    """
                ),
                {"source_id": source_id.hex, "group_id": group_id.hex},
            )
            _audit_log(
                connection,
                user.sub,
                "revoke",
                "permission",
                str(source_id),
                {"group_id": str(group_id)},
            )

    @app.get("/admin/config")
    def admin_list_config(
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> list[dict[str, Any]]:
        require_admin(user)
        with app.state.engine.begin() as connection:
            rows = connection.execute(
                sa.text("SELECT key, value, updated_at FROM system_config ORDER BY key")
            ).mappings()
            return [
                {
                    "key": row["key"],
                    "value": row["value"],
                    "updated_at": _fmt_dt(row["updated_at"]),
                }
                for row in rows
            ]

    @app.put("/admin/config/{key}")
    def admin_update_config(
        key: str,
        request: UpdateConfigRequest,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> dict[str, Any]:
        require_admin(user)
        with app.state.engine.begin() as connection:
            connection.execute(
                sa.text(
                    """
                    UPDATE system_config
                    SET value = :value, updated_at = CURRENT_TIMESTAMP, updated_by = :user_id
                    WHERE key = :key
                    """
                ),
                {
                    "key": key,
                    "value": request.value,
                    "user_id": user.sub.hex,
                },
            )
            row = (
                connection.execute(
                    sa.text("SELECT key, value, updated_at FROM system_config WHERE key = :key"),
                    {"key": key},
                )
                .mappings()
                .first()
            )
            if row is None:
                raise HTTPException(status_code=404, detail="Config key not found")
            _audit_log(
                connection,
                user.sub,
                "update",
                "system_config",
                key,
                {"value": request.value},
            )
            return {
                "key": row["key"],
                "value": row["value"],
                "updated_at": _fmt_dt(row["updated_at"]),
            }

    @app.post("/admin/config/reset")
    def admin_reset_config(
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> dict[str, Any]:
        require_admin(user)
        from shared.feature_flags import SYSTEM_CONFIG_DEFAULTS

        with app.state.engine.begin() as connection:
            for key, value in SYSTEM_CONFIG_DEFAULTS.items():
                connection.execute(
                    sa.text(
                        """
                        UPDATE system_config
                        SET value = :value, updated_at = CURRENT_TIMESTAMP, updated_by = :user_id
                        WHERE key = :key
                        """
                    ),
                    {"key": key, "value": value, "user_id": user.sub.hex},
                )
            _audit_log(connection, user.sub, "reset", "system_config")
            return {"reset": True, "keys": list(SYSTEM_CONFIG_DEFAULTS.keys())}

    @app.get("/admin/dlq")
    def admin_list_dlq(
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> list[DlqItem]:
        require_admin(user)
        with app.state.engine.begin() as connection:
            rows = connection.execute(
                sa.text(
                    """
                    SELECT id, doc_id, error_message, retry_count, status, created_at, updated_at
                    FROM dlq ORDER BY created_at DESC
                    """
                )
            ).mappings()
            return [
                DlqItem(
                    id=str(to_uuid(row["id"])),
                    doc_id=str(to_uuid(row["doc_id"])) if row["doc_id"] else None,
                    error_message=row["error_message"],
                    retry_count=row["retry_count"],
                    status=row["status"],
                    created_at=_fmt_dt(row["created_at"]),
                    updated_at=_fmt_dt(row["updated_at"]),
                )
                for row in rows
            ]

    @app.post("/admin/dlq/{dlq_id}/retry")
    def admin_retry_dlq(
        dlq_id: UUID,
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> dict[str, Any]:
        require_admin(user)
        with app.state.engine.begin() as connection:
            result = connection.execute(
                sa.text(
                    """
                    UPDATE dlq
                    SET status = 'retried', retry_count = retry_count + 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id AND status = 'pending'
                    """
                ),
                {"id": dlq_id.hex},
            )
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="DLQ item not found or not pending")
            _audit_log(connection, user.sub, "retry", "dlq", str(dlq_id))
            return {"id": str(dlq_id), "status": "retried"}

    @app.get("/admin/activity")
    def admin_list_activity(
        user: Annotated[TokenPayload, Depends(current_user)],
    ) -> list[dict[str, Any]]:
        require_admin(user)
        with app.state.engine.begin() as connection:
            rows = connection.execute(
                sa.text(
                    """
                    SELECT id, user_id, action, resource_type, resource_id, details, created_at
                    FROM audit_log ORDER BY created_at DESC LIMIT 100
                    """
                )
            ).mappings()
            return [
                {
                    "id": str(to_uuid(row["id"])),
                    "user_id": str(to_uuid(row["user_id"])) if row["user_id"] else None,
                    "action": row["action"],
                    "resource_type": row["resource_type"],
                    "resource_id": row["resource_id"],
                    "details": row["details"],
                    "created_at": _fmt_dt(row["created_at"]),
                }
                for row in rows
            ]

    return app
