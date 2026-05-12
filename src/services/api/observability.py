from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, cast
from uuid import uuid4

from fastapi import Request
from fastapi.responses import Response
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware

from shared.metrics import (
    MetricsRegistry,
    reset_current_metrics,
    route_template_for_request,
    set_current_metrics,
    status_class,
)
from shared.request_context import reset_request_id, set_request_id

logger = logging.getLogger(__name__)


def configure_api_logging(log_level: str) -> None:
    """Configure API log verbosity for container runtimes.

    The container writes logs to stdout/stderr, so Docker Compose can collect them
    through the json-file logging driver. Invalid values fall back to INFO rather
    than preventing startup.
    """
    normalized = log_level.upper()
    level = getattr(logging, normalized, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    logging.getLogger().setLevel(level)
    logging.getLogger("services").setLevel(level)
    logging.getLogger("shared").setLevel(level)
    logging.getLogger("uvicorn.error").setLevel(level)
    logging.getLogger("uvicorn.access").setLevel(level)


def _is_default_request_observability_middleware(middleware: Middleware) -> bool:
    """Return true for the basic request middleware registered in create_app."""
    if middleware.cls is not BaseHTTPMiddleware:  # type: ignore[comparison-overlap]
        return False
    dispatch = middleware.kwargs.get("dispatch")
    return getattr(dispatch, "__name__", None) == "request_observability_middleware"


def install_enhanced_request_observability(app: Any) -> None:
    """Replace the default request middleware with one that logs exceptions.

    ``services.api.main.create_app`` owns the route wiring and installs the basic
    metrics/request-ID middleware. Production ASGI startup calls this helper to
    preserve those metrics while adding actionable exception logs for 500s.
    """
    user_middleware = cast("list[Middleware]", app.user_middleware)
    app.user_middleware = [
        middleware
        for middleware in user_middleware
        if not _is_default_request_observability_middleware(middleware)
    ]
    app.middleware_stack = None
    app.add_middleware(BaseHTTPMiddleware, dispatch=enhanced_request_observability_middleware)


async def enhanced_request_observability_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Attach request IDs, record HTTP metrics, and log unhandled 500s."""
    request_id = request.headers.get("x-request-id") or str(uuid4())
    token = set_request_id(request_id)
    metrics_token = set_current_metrics(request.app.state.metrics)
    start = time.perf_counter()
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
        source_id = request.path_params.get("source_id") if request.path_params else None
        logger.exception(
            "Unhandled API request error request_id=%s method=%s path=%s route=%s "
            "status_code=500 error_type=%s source_id=%s",
            request_id,
            request.method,
            request.url.path,
            route,
            error_type,
            source_id,
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
