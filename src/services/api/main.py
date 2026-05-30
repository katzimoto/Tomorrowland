from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

import sqlalchemy as sa
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy import Engine

from services.api.readiness import ReadinessChecker
from services.auth.jwt import JwtService
from services.auth.ldap import LdapAuthenticator
from services.auth.models import TokenPayload
from services.intelligence.factory import build_llm_provider
from services.intelligence.llm_provider import LLMProvider
from services.intelligence.provider_registry import ProviderRegistry
from services.intelligence.task_defaults import TaskDefaultResolver
from services.search.meili_provider import MeilisearchSearchProvider
from services.search.qdrant import QdrantSearchClient
from services.translation.client import LibreTranslateClient
from shared.config import Settings
from shared.metrics import (
    MetricsRegistry,
    reset_current_metrics,
    route_template_for_request,
    set_current_metrics,
    status_class,
)
from shared.rate_limit import AgentRateLimiter
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


def create_app(
    engine: Engine,
    settings: Settings | None = None,
    ldap_authenticator: LdapAuthenticator | None = None,
    translator: LibreTranslateClient | None = None,
    qdrant_client: QdrantSearchClient | None = None,
    llm_provider: LLMProvider | None = None,
    meili_provider: MeilisearchSearchProvider | None = None,
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
    # Also expose as ldap_client for admin group-search routes (#582).
    if ldap_authenticator is not None and hasattr(ldap_authenticator, "search_groups"):
        app.state.ldap_client = ldap_authenticator
    else:
        app.state.ldap_client = None
    app.state.translator = translator
    app.state.qdrant_client = qdrant_client
    app.state.llm_provider = llm_provider or build_llm_provider(app.state.settings)

    # Provider registry — holds runtime adapter instances keyed by provider name.
    # Not yet used by chat / RAG / embedding consumers (that change is #578).
    # Gracefully degrades to empty when the DB tables don't exist yet
    # (e.g. before migrations run, or in unit tests).
    provider_registry = ProviderRegistry(
        engine=app.state.engine,
        credential_store_key=app.state.settings.credential_store_key,
    )
    try:
        provider_registry.load()
    except Exception:
        logger.warning("ProviderRegistry.load() failed — tables may not exist yet")
    app.state.provider_registry = provider_registry

    # Task default resolver — resolves model providers for named task types
    # from DB-backed model_task_defaults.  Falls back to env/config when no
    # DB row exists (zero-row backward compatibility).
    task_default_resolver = TaskDefaultResolver(
        engine=app.state.engine,
        settings=app.state.settings,
        credential_store_key=app.state.settings.credential_store_key,
    )
    try:
        task_default_resolver.load()
    except Exception:
        logger.warning("TaskDefaultResolver.load() failed — tables may not exist yet")
    app.state.task_default_resolver = task_default_resolver

    if meili_provider is not None:
        app.state.meili_provider = meili_provider
    elif app.state.settings.feature_meilisearch_search:
        import meilisearch

        is_meiliseach_shadow = app.state.settings.feature_meilisearch_shadow_index
        meili_client = meilisearch.Client(
            app.state.settings.meilisearch_url,
            api_key=app.state.settings.meilisearch_master_key,
        )
        app.state.meili_provider = MeilisearchSearchProvider(
            meili_client, metrics=app.state.metrics, is_shadow=is_meiliseach_shadow
        )
    else:
        app.state.meili_provider = None

    with app.state.engine.begin() as connection:
        try:
            admins_id = connection.execute(
                sa.text("SELECT id FROM groups WHERE name = 'admins'"),
            ).scalar()
            app.state.admins_group_id = str(admins_id) if admins_id else None
        except Exception:
            app.state.admins_group_id = None

    app.state.agent_rate_limiter = AgentRateLimiter(
        enabled=app.state.settings.agent_rate_limit_enabled,
        window_seconds=app.state.settings.agent_rate_limit_window_seconds,
        calls_per_window=app.state.settings.agent_rate_limit_calls_per_window,
        ask_corpus_calls_per_window=app.state.settings.agent_rate_limit_ask_corpus_calls_per_window,
    )

    app.state.readiness_checker = ReadinessChecker(
        engine=app.state.engine,
        settings=app.state.settings,
        metrics=app.state.metrics,
    )

    @app.middleware("http")
    async def request_observability_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Attach request IDs and record low-cardinality HTTP metrics."""
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
            return response
        except Exception as exc:
            route = route_template_for_request(request)
            elapsed = time.perf_counter() - start
            metrics = request.app.state.metrics
            error_type = exc.__class__.__name__
            metrics.http_request_duration_seconds.labels(request.method, route).observe(elapsed)
            metrics.http_requests_total.labels(request.method, route, "5xx").inc()
            metrics.http_exceptions_total.labels(route, error_type).inc()
            return Response(
                content="Internal Server Error",
                status_code=500,
                media_type="text/plain",
                headers={"X-Request-ID": request_id},
            )
        finally:
            reset_current_metrics(metrics_token)
            reset_request_id(token)

    # Register domain routers
    from services.api.routers.admin.config import router as admin_config_router
    from services.api.routers.admin.dlq import router as admin_dlq_router
    from services.api.routers.admin.ingestion import router as admin_ingestion_router
    from services.api.routers.admin.ingestion_status import router as admin_ingestion_status_router
    from services.api.routers.admin.intelligence import router as admin_intelligence_router
    from services.api.routers.admin.jobs import router as admin_jobs_router
    from services.api.routers.admin.ldap import router as admin_ldap_router
    from services.api.routers.admin.model_providers import router as admin_model_providers_router
    from services.api.routers.admin.rabbit import router as admin_rabbit_router
    from services.api.routers.admin.source_profiles import router as admin_source_profiles_router
    from services.api.routers.admin.source_qa import router as admin_source_qa_router
    from services.api.routers.admin.sources import router as admin_sources_router
    from services.api.routers.admin.users import router as admin_users_router
    from services.api.routers.agent import router as agent_router
    from services.api.routers.alerts import router as alerts_router
    from services.api.routers.annotations import router as annotations_router
    from services.api.routers.auth import router as auth_router
    from services.api.routers.chat import router as chat_router
    from services.api.routers.documents import router as documents_router
    from services.api.routers.search import router as search_router
    from services.api.routers.system import router as system_router
    from services.api.routers.vault import router as vault_router

    app.include_router(auth_router)
    app.include_router(chat_router)
    app.include_router(system_router)
    app.include_router(search_router)
    app.include_router(documents_router)
    app.include_router(annotations_router)
    app.include_router(alerts_router)
    app.include_router(admin_ingestion_router)
    app.include_router(admin_ingestion_status_router)
    app.include_router(admin_users_router)
    app.include_router(admin_sources_router)
    app.include_router(admin_config_router)
    app.include_router(admin_dlq_router)
    app.include_router(admin_intelligence_router)
    app.include_router(admin_jobs_router)
    app.include_router(admin_ldap_router)
    app.include_router(admin_model_providers_router)
    app.include_router(admin_rabbit_router)
    app.include_router(admin_source_profiles_router)
    app.include_router(admin_source_qa_router)
    app.include_router(vault_router)
    app.include_router(agent_router)

    return app
